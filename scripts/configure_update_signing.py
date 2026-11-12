"""Activate update signing without ever writing the private key to disk."""
from __future__ import annotations

import argparse
import base64
import re
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRUST_FILE = ROOT / "update_trust.py"
_PUBLIC_KEYS_LINE = re.compile(
    r"^UPDATE_SIGNING_PUBLIC_KEYS = \((?P<keys>[^)]*)\)$", re.MULTILINE)


def require_unconfigured(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    match = _PUBLIC_KEYS_LINE.search(source)
    if match is None:
        raise RuntimeError("update trust file has no public-key setting")
    if match.group("keys").strip():
        raise RuntimeError(
            "a public key is already configured; use the documented "
            "two-release rotation instead of replacing it in place")
    return source


def install_public_key(path: Path, public_text: str) -> None:
    source = require_unconfigured(path)
    updated = _PUBLIC_KEYS_LINE.sub(
        f'UPDATE_SIGNING_PUBLIC_KEYS = ("{public_text}",)', source, count=1)
    path.write_text(updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the update key, store its secret in GitHub, and pin its public half.")
    parser.add_argument("--repo", default="vlad-demchyk/xbrain-audit")
    parser.add_argument("--trust-file", type=Path, default=DEFAULT_TRUST_FILE)
    args = parser.parse_args()

    # Refuse before creating or changing a GitHub secret. A one-release key
    # replacement would lock every client that still trusts the previous key
    # out of the update path.
    require_unconfigured(args.trust_file)
    private_key = Ed25519PrivateKey.generate()
    private_text = base64.b64encode(
        private_key.private_bytes_raw()).decode("ascii")
    public_text = base64.b64encode(
        private_key.public_key().public_bytes_raw()).decode("ascii")

    # gh reads the secret from stdin. It is neither an argv value nor a file,
    # so it cannot appear in process listings or remain in the checkout.
    subprocess.run(
        ["gh", "secret", "set", "UPDATE_SIGNING_KEY",
         "--repo", args.repo],
        input=private_text + "\n",
        text=True,
        check=True,
    )
    install_public_key(args.trust_file, public_text)
    print(f"GitHub secret set for {args.repo}.")
    print(f"Public key pinned in {args.trust_file}.")
    print("Review, test, commit and push the public-key change before releasing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
