"""A release is data until its origin and exact bytes have been proved."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import updater
from scripts import configure_update_signing
from scripts import update_manifest


class _Response:
    def __init__(self, payload: bytes, *, url: str = "https://github.com/file",
                 content_length: int | None = None):
        self._body = io.BytesIO(payload)
        self._url = url
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def read(self, size=-1):
        return self._body.read(size)

    def geturl(self):
        return self._url

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _release(*assets) -> updater.ReleaseInfo:
    return updater.ReleaseInfo(
        tag="v9.9.9",
        version="9.9.9",
        body="",
        assets=list(assets),
        html_url="https://github.com/vlad-demchyk/xbrain-audit/releases/tag/v9.9.9",
    )


def _asset(name: str, size: int = 3, host: str = "github.com") -> dict:
    return {
        "name": name,
        "size": size,
        "browser_download_url": f"https://{host}/release/{name}",
    }


class OnlyGitHubMayDeliverAnUpdate(unittest.TestCase):
    def test_the_exact_release_origins_are_allowed(self):
        for host in sorted(updater._TRUSTED_UPDATE_HOSTS):
            with self.subTest(host=host):
                self.assertEqual(
                    updater._require_trusted_url(f"https://{host}/asset"),
                    f"https://{host}/asset",
                )

    def test_lookalikes_plain_http_userinfo_and_custom_ports_are_rejected(self):
        urls = (
            "http://github.com/asset",
            "https://github.com.example/asset",
            "https://github.com@evil.example/asset",
            "https://user:secret@github.com/asset",
            "https://github.com:444/asset",
        )
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(RuntimeError):
                    updater._require_trusted_url(url)

    def test_a_redirect_to_another_host_is_rejected_before_it_is_followed(self):
        handler = updater._TrustedRedirectHandler()
        with self.assertRaisesRegex(RuntimeError, "untrusted update URL"):
            handler.redirect_request(
                None, None, 302, "Found", {},
                "https://downloads.evil.example/XBrainAudit.app.zip",
            )


class TheApiTokenStaysOnTheApiHost(unittest.TestCase):
    """`urllib` copies every header but content-length and content-type onto
    a redirected request, so a personal access token followed the release
    asset from `api.github.com` to the download host that never asked for
    it. The signed asset URL needs no credential."""

    def redirected(self, from_url: str, to_url: str):
        from urllib.request import Request

        request = Request(from_url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer ghp_secret",
        })
        return updater._TrustedRedirectHandler().redirect_request(
            request, None, 302, "Found", {}, to_url)

    def test_the_credential_is_dropped_when_the_host_changes(self):
        followed = self.redirected(
            updater.API_URL,
            "https://objects.githubusercontent.com/XBrain Audit-cli.tar.gz")
        names = {name.lower() for name in followed.headers}
        self.assertNotIn("authorization", names)
        self.assertIn("accept", names)

    def test_the_credential_survives_a_redirect_on_the_same_host(self):
        followed = self.redirected(
            "https://api.github.com/repos/o/r/releases/latest",
            "https://api.github.com/repos/o/r/releases/9")
        values = {name.lower(): value
                  for name, value in followed.headers.items()}
        self.assertEqual(values.get("authorization"), "Bearer ghp_secret")

    def test_a_redirect_off_the_allowlist_is_still_refused(self):
        with self.assertRaisesRegex(RuntimeError, "untrusted update URL"):
            self.redirected(updater.API_URL,
                            "https://downloads.evil.example/x.zip")


class TheManifestIsTheReleaseContract(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.cli = root / "xaudit-cli-macos-arm64.tar.gz"
        self.gui = root / "XBrainAudit.app.zip"
        self.cli.write_bytes(b"cli")
        self.gui.write_bytes(b"gui-app")
        self.payload = update_manifest.manifest_bytes(
            "v9.9.9", [self.cli, self.gui])

    def test_the_generator_records_exact_size_and_sha256(self):
        data = json.loads(self.payload)
        record = data["assets"][self.gui.name]
        self.assertEqual(record["size"], len(b"gui-app"))
        self.assertEqual(record["sha256"], hashlib.sha256(b"gui-app").hexdigest())

    def test_the_generator_is_deterministic(self):
        reversed_payload = update_manifest.manifest_bytes(
            "v9.9.9", [self.gui, self.cli])
        self.assertEqual(self.payload, reversed_payload)

    def test_an_unsigned_build_writes_an_explicit_empty_signature(self):
        output = Path(self._tmp.name) / updater.MANIFEST_ASSET
        update_manifest.write_manifest(
            "v9.9.9", [self.cli, self.gui], output, "")
        self.assertEqual(output.read_bytes(), self.payload)
        self.assertEqual(Path(str(output) + ".sig").read_bytes(), b"")

    def test_a_manifest_for_another_release_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            updater._parse_update_manifest(
                self.payload.replace(b"v9.9.9", b"v9.9.8"),
                _release(),
                signature_verified=False,
            )

    def test_invalid_integrity_fields_are_rejected(self):
        data = json.loads(self.payload)
        data["assets"][self.cli.name]["sha256"] = "not-a-hash"
        with self.assertRaisesRegex(RuntimeError, "integrity data"):
            updater._parse_update_manifest(
                json.dumps(data).encode(), _release(),
                signature_verified=False,
            )


class SigningCanBeActivatedWithoutChangingTheProtocol(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_text = base64.b64encode(
            self.private_key.public_key().public_bytes_raw()).decode("ascii")
        self.payload = b'{"assets":{},"release":"v9.9.9","version":1}\n'
        self.signature = base64.b64encode(
            self.private_key.sign(self.payload)) + b"\n"

    def test_a_valid_ed25519_signature_is_accepted(self):
        with patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEYS", (self.public_text,)):
            self.assertTrue(updater._verify_manifest_signature(
                self.payload, self.signature))

    def test_a_bridge_release_may_trust_old_and_new_public_keys(self):
        another = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        public_keys = (
            base64.b64encode(another).decode("ascii"),
            self.public_text,
        )
        with patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEYS", public_keys):
            self.assertTrue(updater._verify_manifest_signature(
                self.payload, self.signature))

    def test_the_release_generator_and_updater_share_the_same_signature(self):
        private_text = base64.b64encode(
            self.private_key.private_bytes_raw()).decode("ascii")
        generated = update_manifest.signature_bytes(
            self.payload, private_text)
        with patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEYS", (self.public_text,)):
            self.assertTrue(updater._verify_manifest_signature(
                self.payload, generated))

    def test_a_changed_manifest_is_rejected(self):
        with patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEYS", (self.public_text,)):
            with self.assertRaisesRegex(RuntimeError, "signature is invalid"):
                updater._verify_manifest_signature(
                    self.payload + b" ", self.signature)

    def test_a_configured_key_makes_a_missing_signature_an_error(self):
        with patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEYS", (self.public_text,)):
            with self.assertRaisesRegex(RuntimeError, "signature is missing"):
                updater._verify_manifest_signature(self.payload, b"")

    def test_no_public_key_selects_the_checksum_fallback(self):
        with patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEYS", ()):
            self.assertFalse(updater._verify_manifest_signature(
                self.payload, b""))

    def test_the_activation_helper_pins_only_the_public_key(self):
        with tempfile.TemporaryDirectory() as directory:
            trust_file = Path(directory) / "update_trust.py"
            trust_file.write_text(
                "UPDATE_SIGNING_PUBLIC_KEYS = ()\n", encoding="utf-8")

            configure_update_signing.install_public_key(
                trust_file, self.public_text)

            self.assertEqual(
                trust_file.read_text(encoding="utf-8"),
                f'UPDATE_SIGNING_PUBLIC_KEYS = ("{self.public_text}",)\n',
            )
            private_text = base64.b64encode(
                self.private_key.private_bytes_raw()).decode("ascii")
            self.assertNotIn(private_text, trust_file.read_text())

    def test_the_activation_helper_refuses_an_in_place_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            trust_file = Path(directory) / "update_trust.py"
            trust_file.write_text(
                f'UPDATE_SIGNING_PUBLIC_KEYS = ("{self.public_text}",)\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "two-release rotation"):
                configure_update_signing.install_public_key(
                    trust_file, "another-public-key")


class DownloadedBytesMustMatch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name) / "asset.zip"
        self.payload = b"the exact release bytes"
        self.integrity = updater.AssetIntegrity(
            self.dest.name,
            len(self.payload),
            hashlib.sha256(self.payload).hexdigest(),
        )

    def test_the_exact_asset_is_accepted(self):
        response = _Response(self.payload, content_length=len(self.payload))
        with patch.object(updater, "_open_trusted", return_value=response):
            updater._download("https://github.com/asset", self.dest,
                              self.integrity)
        self.assertEqual(self.dest.read_bytes(), self.payload)

    def test_a_changed_payload_is_rejected(self):
        changed = self.payload[:-1] + b"!"
        response = _Response(changed, content_length=len(changed))
        with patch.object(updater, "_open_trusted", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                updater._download("https://github.com/asset", self.dest,
                                  self.integrity)

    def test_a_size_disagreement_is_rejected_before_extraction(self):
        response = _Response(self.payload, content_length=len(self.payload) + 1)
        with patch.object(updater, "_open_trusted", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "Content-Length"):
                updater._download("https://github.com/asset", self.dest,
                                  self.integrity)

    def test_api_metadata_must_agree_with_the_manifest(self):
        release = _release()
        manifest = updater._parse_update_manifest(
            json.dumps({
                "version": 1,
                "release": release.tag,
                "assets": {
                    "asset.zip": {
                        "size": 3,
                        "sha256": hashlib.sha256(b"abc").hexdigest(),
                    },
                },
            }).encode(),
            release,
            signature_verified=False,
        )
        with self.assertRaisesRegex(RuntimeError, "size disagrees"):
            updater._asset_integrity(_asset("asset.zip", size=4), manifest)

        asset = _asset("asset.zip", size=3)
        asset["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(RuntimeError, "digest disagrees"):
            updater._asset_integrity(asset, manifest)


if __name__ == "__main__":
    unittest.main()


class TheTlsTrust(unittest.TestCase):
    """0.72.1 from CI could not reach GitHub: the default context trusted the
    build runner's CA path, which no user's Mac has."""

    def test_the_updater_trusts_the_bundled_ca_file(self):
        import certifi

        with mock.patch("ssl.create_default_context") as make:
            updater._tls_context()
        make.assert_called_once_with(cafile=certifi.where())

    def test_the_context_is_handed_to_the_opener(self):
        seen = []

        class _Opener:
            def open(self, request, timeout):
                raise OSError("stop")

        def build(*handlers):
            seen.extend(handlers)
            return _Opener()

        with mock.patch.object(updater, "build_opener", build), \
                mock.patch.object(updater, "_tls_context", return_value="ctx"):
            with self.assertRaises(OSError):
                updater._open_trusted(updater.API_URL, timeout=1)
        https = [h for h in seen if h.__class__.__name__ == "HTTPSHandler"]
        self.assertEqual(len(https), 1)
        self.assertEqual(https[0]._context, "ctx")
