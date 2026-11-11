"""Exercise installation quoting and private storage on disposable files."""
import json
import os
import stat
import subprocess
import sys
from unittest.mock import patch

import pytest

import applog
import cli_install
from llm import credentials


#: Windows has no owner/group/other modes - `os.chmod` only toggles the
#: read-only flag and `st_mode` always reads 0o666 or 0o444 - so checking them
#: there checks nothing. The files live under the user's own profile folder,
#: which NTFS already restricts to that user. Everything else these tests
#: check (redaction, atomic replace, concurrent writers) runs everywhere.
_POSIX_MODES = os.name != "nt"


@pytest.mark.skipif(sys.platform != "darwin",
                    reason="the admin path is an osascript command with BSD `ln -h`")
def test_admin_paths_are_shell_data(tmp_path, monkeypatch):
    source = tmp_path / "app ' $(touch injected) `touch injected2`"
    source.write_text("binary")
    directory = tmp_path / "bin ; touch injected3"
    commands = []
    monkeypatch.setattr(cli_install, "_clear_quarantine", lambda _: None)
    monkeypatch.setattr(cli_install, "_run_admin", commands.append)
    target = cli_install.install(source, directory, use_admin=True)
    subprocess.run(["/bin/sh", "-c", commands.pop()], cwd=tmp_path, check=True)
    assert target.resolve() == source
    cli_install.uninstall(directory, use_admin=True)
    subprocess.run(["/bin/sh", "-c", commands.pop()], cwd=tmp_path, check=True)
    assert not target.is_symlink()
    assert not list(tmp_path.glob("injected*"))


def test_log_redacts_nested_urls_and_secrets_before_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("XANALYZE_LOG_DIR", str(tmp_path / "logs"))
    applog._reset_for_tests()
    url = "https://user:password@example.org/page?custom=QUERYSECRET#FRAGMENTSECRET"
    applog.info(url, nested={"values": [url], "refresh_token": "TOKENSECRET"}, error=ValueError(url))
    path = applog.file_for()
    raw = path.read_text()
    for secret in ("password", "QUERYSECRET", "FRAGMENTSECRET", "TOKENSECRET"):
        assert secret not in raw
    assert "example.org/page" in raw
    assert not _POSIX_MODES or stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not _POSIX_MODES or stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    path.chmod(0o644)
    applog.info("again")
    assert not _POSIX_MODES or stat.S_IMODE(path.stat().st_mode) == 0o600


def test_credential_replace_is_private_and_failure_preserves_old(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    credentials._file_save("old", "old-value")
    path = credentials._fallback_path()
    before = path.read_bytes()

    def fail_replace(source, target):
        assert not _POSIX_MODES or stat.S_IMODE(source.stat().st_mode) == 0o600
        assert json.loads(source.read_text())["new"] == "new-value"
        raise OSError("disk failure")

    with patch.object(credentials.os, "replace", side_effect=fail_replace):
        with pytest.raises(OSError):
            credentials._file_save("new", "new-value")
    assert path.read_bytes() == before
    assert not _POSIX_MODES or stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(path.parent.glob(".credentials-*"))


def test_concurrent_credential_writers_preserve_all_accounts(tmp_path):
    environment = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path)}
    script = (
        "from llm import credentials as c; import sys,time; original=c._read_file; "
        "c._read_file=lambda p: (original(p),time.sleep(0.03))[0]; "
        "c._file_save(sys.argv[1], 'test-value')"
    )
    processes = [subprocess.Popen([sys.executable, "-c", script, str(i)], env=environment)
                 for i in range(12)]
    for process in processes:
        assert process.wait(timeout=15) == 0
    path = tmp_path / "xanalyze/credentials.json"
    assert set(json.loads(path.read_text())) == {str(i) for i in range(12)}
    assert not _POSIX_MODES or stat.S_IMODE(path.stat().st_mode) == 0o600


def test_corrupt_credentials_are_not_silently_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = credentials._fallback_path()
    path.write_text("damaged")
    with pytest.raises(ValueError):
        credentials._file_save("account", "value")
    assert path.read_text() == "damaged"
