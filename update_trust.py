"""Pinned trust root for signed XBrain Audit update manifests.

Add the base64-encoded raw 32-byte Ed25519 public key before enabling signed
releases. An empty tuple deliberately keeps the transitional
HTTPS + size + SHA-256 fallback active.
"""

UPDATE_SIGNING_PUBLIC_KEYS = ("PWH/Hha0QIsqvGEgjHHfbwuKqlSkbAYJd1KLJLZciTI=",)
