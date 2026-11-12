#!/usr/bin/env bash
# The CI test job (.github/workflows/release.yml, job `test`), run locally in
# Ubuntu by `linux-ci`. Keep the two in step: what this skips, CI catches
# only after a push - which is how 0.72.0's release failed on two tests that
# could never pass on Linux.
set -euo pipefail

PYTHON_VERSION=3.14

# The system libraries Qt links against, tolerant of renamed packages - the
# workflow's list, installed once and then a no-op. The second block is what
# GitHub's runner image already carries and a clean Ubuntu does not: without
# it QtWebEngine fails to load (`libsnappy.so.1`) and 450 Qt tests skip.
if [ ! -f /var/lib/linux-ci/xaudit-qt-libs-v2 ]; then
  sudo apt-get update -qq
  for pkg in \
    libegl1 libgl1 libdbus-1-3 libnss3 libgbm1 libdrm2 \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
    libxcb-xinerama0 libxcb-xkb1 \
    libxcomposite1 libxdamage1 libxrandr2 libxtst6 \
    libpango-1.0-0 libcairo2 \
    libasound2t64 libasound2 \
    libatk1.0-0t64 libatk1.0-0 \
    libatk-bridge2.0-0t64 libatk-bridge2.0-0 \
    libcups2t64 libcups2 \
    liblcms2-2 libminizip1t64 libminizip1 libopus0 libpulse0 libsnappy1v5 \
    libwayland-cursor0 libwebpdemux2 libwebpmux3 libxfixes3 \
  ; do
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "$pkg" >/dev/null 2>&1 \
      || echo "not on this image, skipped: $pkg"
  done
  sudo touch /var/lib/linux-ci/xaudit-qt-libs-v2
fi

# One venv per requirements file, outside the synced tree (rsync --delete
# would remove it), rebuilt only when the requirements change.
key=$(sha256sum requirements.txt | cut -c1-12)
VENV="$HOME/.cache/linux-ci/xaudit-$PYTHON_VERSION-$key"
if [ ! -x "$VENV/bin/python" ]; then
  echo "# creating venv $VENV"
  uv venv -q --python "$PYTHON_VERSION" "$VENV"
  uv pip install -q --python "$VENV/bin/python" -r requirements.txt \
    pytest==9.2.0 pytest-timeout==2.4.0 ruff==0.17.4
fi
export PATH="$VENV/bin:$PATH"

echo "# lint"
ruff check .

echo "# Qt loads"
QT_QPA_PLATFORM=offscreen xvfb-run -a python - <<'PY'
from PySide6.QtWidgets import QApplication  # noqa: F401
from audit.driver import available
ok, why = available()
print(f"QtWebEngine available: {ok} {why}")
PY

echo "# tests"
QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu --disable-software-rasterizer" \
  xvfb-run -a python -m pytest -q -p no:cacheprovider "${@:-tests/}"
