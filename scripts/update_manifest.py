"""Build and optionally sign the release manifest consumed by updater.py."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path


def manifest_bytes(release: str, assets: list[Path]) -> bytes:
    records = {}
    for path in sorted(assets, key=lambda item: item.name):
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.name in records:
            raise ValueError(f"duplicate release asset name: {path.name}")
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        records[path.name] = {
            "sha256": digest.hexdigest(),
            "size": path.stat().st_size,
        }
    if not records:
        raise ValueError("at least one release asset is required")
    document = {"version": 1, "release": release, "assets": records}
    return (json.dumps(document, sort_keys=True, separators=(",", ":"))
            + "\n").encode("utf-8")


def signature_bytes(payload: bytes, private_key_text: str) -> bytes:
    """Return a base64 Ed25519 signature, or empty bytes for fallback mode."""
    if not private_key_text.strip():
        return b""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    try:
        private_bytes = base64.b64decode(private_key_text.strip(),
                                         validate=True)
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    except (TypeError, ValueError) as exc:
        raise ValueError("UPDATE_SIGNING_KEY is not a base64 raw Ed25519 key") from exc
    return base64.b64encode(private_key.sign(payload)) + b"\n"


def write_manifest(release: str, assets: list[Path], output: Path,
                   private_key_text: str,
                   also: tuple[Path, ...] = ()) -> None:
    """Write the manifest and its `.sig` to `output`, and to each of `also`.

    `also` is the pre-rename name (`xanalyze-update-manifest.json`), which
    an installed XAnalyze looks for. The same bytes and the same signature:
    one manifest under two names, so both readers verify the same document.
    """
    payload = manifest_bytes(release, assets)
    signature = signature_bytes(payload, private_key_text)
    for path in (output, *also):
        path.write_bytes(payload)
        path.with_name(path.name + ".sig").write_bytes(signature)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--also-output", type=Path, action="append", default=[],
                        help="write the same manifest and signature here too")
    parser.add_argument("assets", type=Path, nargs="+")
    args = parser.parse_args()
    write_manifest(
        args.release,
        args.assets,
        args.output,
        os.environ.get("UPDATE_SIGNING_KEY", ""),
        tuple(args.also_output),
    )
    mode = "signed" if os.environ.get("UPDATE_SIGNING_KEY", "").strip() else "unsigned fallback"
    for path in (args.output, *args.also_output):
        print(f"Wrote {path} and {path.name}.sig ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
