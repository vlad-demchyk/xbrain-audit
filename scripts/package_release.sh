#!/bin/bash
# Pack the built app into this release's assets.
#
#   scripts/package_release.sh VERSION
#
# Used by `make package` and by `.github/workflows/release.yml`, so the two
# cannot drift apart. Writes, into $DIST_DIR (default `dist`):
#
#   XBrainAudit.app.zip                    the app, what `updater.py` looks for
#   xbrain-audit-update-manifest.json(.sig)
#   XAnalyze.app.zip                       the same app under its pre-rename
#                                          folder name, `XAnalyze.app`
#   xanalyze-update-manifest.json(.sig)    the same manifest, same signature
#
# The last two are for an XAnalyze (0.73 and older) that is already
# installed: it looks for exactly those names and for an `XAnalyze.app`
# inside the archive, and it is the only way such an install reaches this
# version. Drop them once no supported install predates the rename.
#
# `ditto`, not `zip -r`: it keeps the bundle's symlinks (Qt's frameworks are
# made of them) and its executable bits, which `updater._unzip_bundle`
# restores. The manifest is signed when UPDATE_SIGNING_KEY is set.
set -euo pipefail

version="${1:?usage: scripts/package_release.sh VERSION}"
root="$(cd "$(dirname "$0")/.." && pwd)"
dist="$(cd "${DIST_DIR:-$root/dist}" && pwd)"
python="${PYTHON:-$root/venv/bin/python}"
app="XBrain Audit.app"
legacy_app="XAnalyze.app"

if [ ! -d "$dist/$app" ]; then
    echo "no $dist/$app - build it first (make rebuild)" >&2
    exit 1
fi

rm -f "$dist/XBrainAudit.app.zip" "$dist/XAnalyze.app.zip" \
      "$dist"/xbrain-audit-update-manifest.json* \
      "$dist"/xanalyze-update-manifest.json*

(cd "$dist" && ditto -c -k --sequesterRsrc --keepParent "$app" XBrainAudit.app.zip)

# The pre-rename archive: a copy of the bundle under the old folder name,
# packed from a scratch folder that is removed whatever happens.
scratch="$(mktemp -d "$dist/.legacy-asset.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
ditto "$dist/$app" "$scratch/$legacy_app"
(cd "$scratch" && ditto -c -k --sequesterRsrc --keepParent "$legacy_app" "$dist/XAnalyze.app.zip")

"$python" "$root/scripts/update_manifest.py" \
    --release "v$version" \
    --output "$dist/xbrain-audit-update-manifest.json" \
    --also-output "$dist/xanalyze-update-manifest.json" \
    "$dist/XBrainAudit.app.zip" "$dist/XAnalyze.app.zip"
