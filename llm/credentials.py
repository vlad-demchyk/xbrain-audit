"""Credential storage for account-based providers.

Order of preference:
1. `keyring` — the OS keychain (macOS Keychain, Windows Credential Manager,
   GNOME Keyring / KWallet). Encrypted at rest, managed by the OS.
2. A file under the app's config dir with 0600 permissions, used only if
   keyring isn't installed or has no usable backend (common on bare Linux
   servers). This is clearly less safe and the settings dialog says so.

What gets stored is the session/refresh token, never the password —
the password is used once to sign in and then dropped.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

SERVICE_NAME = "xanalyze"
# Pre-rename service/dir name. `load_secret` falls back to this so a token
# saved before the rename doesn't become invisible; see its docstring.
OLD_SERVICE_NAME = "ai-content-scanner"
_file_mutex = threading.Lock()


def _fallback_path() -> Path:
    import platform_dirs

    base = str(platform_dirs.config_home())
    d = Path(base) / SERVICE_NAME
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    d.chmod(0o700)
    return d / "credentials.json"


@contextmanager
def _locked_file():
    with _file_mutex:
        path = _fallback_path()
        fd = os.open(path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "r+b") as lock:
            if os.name != "nt":
                os.fchmod(lock.fileno(), 0o600)
            if os.name == "nt":
                import msvcrt
                if os.fstat(lock.fileno()).st_size == 0:
                    lock.write(b"\0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                if not path.exists():
                    legacy = path.parent.parent / OLD_SERVICE_NAME / path.name
                    if legacy.exists():
                        _write_file(path, _read_file(legacy))
                yield path
            finally:
                if os.name == "nt":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _read_file(path):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {}
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        if os.name != "nt":
            os.fchmod(stream.fileno(), 0o600)
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("invalid credential store")
    return data


def _write_file(path, data):
    fd, name = tempfile.mkstemp(prefix=".credentials-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _keyring():
    """Return the keyring module only if it has a backend that actually
    works.

    `keyring` installs cleanly on headless Linux but resolves to a
    `fail.Keyring` stub that raises NoKeyringError on first use, so the
    presence of the package proves nothing. The stub lives in
    `keyring.backends.fail` but its class is plain `Keyring`, so it has to
    be identified by module, not class name.
    """
    try:
        import keyring
    except ImportError:
        return None
    try:
        kr = keyring.get_keyring()
    except Exception:  # noqa: BLE001
        return None
    if kr is None:
        return None
    module = type(kr).__module__ or ""
    if module.endswith("backends.fail") or type(kr).__name__ == "FailKeyring":
        return None
    return keyring


def using_keyring() -> bool:
    return _keyring() is not None


def _file_save(account: str, value: str) -> None:
    with _locked_file() as path:
        data = _read_file(path)
        data[account] = value
        _write_file(path, data)


def _file_load(account: str) -> str | None:
    try:
        with _locked_file() as path:
            return _read_file(path).get(account)
    except (ValueError, OSError):
        return None


def save_secret(account: str, value: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE_NAME, account, value)
            return
        except Exception:  # noqa: BLE001 - locked/broken keychain at runtime
            pass  # fall through to the file so sign-in still works
    _file_save(account, value)


def load_secret(account: str) -> str | None:
    kr = _keyring()
    if kr is not None:
        try:
            value = kr.get_password(SERVICE_NAME, account)
            if value is not None:
                return value
        except Exception:  # noqa: BLE001 - a locked keychain shouldn't crash the app
            pass
        # Nothing under the new service name. Before concluding there's no
        # secret at all, check whether it's sitting under the pre-rename
        # service name — otherwise renaming SERVICE_NAME would silently
        # strand every previously-saved token (xFormat access/refresh,
        # an Anthropic key) in the keychain: still there, but unreachable
        # since nothing looks it up under the old name any more.
        #
        # Migrated eagerly rather than left in place: once copied under the
        # new name it's a duplicate the user never asked to keep, and an
        # orphaned "ai-content-scanner" keychain entry is just confusing
        # clutter with no code left pointing at it. Only removed after the
        # copy under the new name actually succeeds, so a failure here never
        # loses the only copy of the secret.
        try:
            old_value = kr.get_password(OLD_SERVICE_NAME, account)
        except Exception:  # noqa: BLE001
            old_value = None
        if old_value is not None:
            try:
                kr.set_password(SERVICE_NAME, account, old_value)
            except Exception:  # noqa: BLE001
                pass
            else:
                try:
                    kr.delete_password(OLD_SERVICE_NAME, account)
                except Exception:  # noqa: BLE001 - stale copy left behind is harmless
                    pass
            return old_value
    # Also checked when a keyring exists: a secret may have been written to
    # the file earlier, before a backend became available.
    return _file_load(account)


def delete_secret(account: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE_NAME, account)
        except Exception:  # noqa: BLE001 - already absent is fine
            pass
    # Always clear the file copy too, so signing out really removes it.
    try:
        with _locked_file() as path:
            data = _read_file(path)
            data.pop(account, None)
            _write_file(path, data)
    except (ValueError, OSError):
        pass
