.PHONY: rebuild check version package rebuild-cli rebuild-app rebuild-all check-cli check-app update

SHELL := /bin/bash
VENV := venv
PY := $(VENV)/bin/python
PYINST := $(VENV)/bin/pyinstaller

# Read version from the single source of truth.
SOURCE_VERSION := $(shell $(PY) -c "import config; print(config.APP_VERSION)")

# One bundle. The window, the command line and the terminal interface are one
# executable that picks its role by the name it was started under (see
# app_entry.py); `xaudit` is a symlink into the app. A second, separate CLI
# bundle used to be built here, released beside the app and updated on its
# own - two copies of one program that could be two versions at once.
#
# The name has a space: quote `$(APP_DIR)` and `$(APP_EXE)` in every recipe,
# and never pass them through `$(notdir ...)` or another function that
# splits on whitespace.
APP_DIR  := dist/XBrain Audit.app
APP_EXE  := $(APP_DIR)/Contents/MacOS/XBrain Audit
APP_SPEC := packaging/XBrainAudit.spec

# --- version ---

version:
	@echo "$(SOURCE_VERSION)"

# --- check: is the built app up to date? ---

check:
	@PLIST_VER=$$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$(APP_DIR)/Contents/Info.plist" 2>/dev/null); \
	if [ "$$PLIST_VER" != "$(SOURCE_VERSION)" ]; then \
		echo "App is stale: built $$PLIST_VER, source $(SOURCE_VERSION)"; exit 1; \
	fi
	@echo "XBrain Audit $(SOURCE_VERSION) is up to date (window, CLI and TUI)"

# --- rebuild ---

rebuild:
	@echo "Building XBrain Audit $(SOURCE_VERSION) ..."
	rm -rf "$(APP_DIR)" dist/xanalyze-cli
	$(PYINST) $(APP_SPEC) --noconfirm --distpath dist
	@echo "XBrain Audit $(SOURCE_VERSION) built. Verify: '$(APP_EXE)' --version"
	@echo "Command line from it: '$(APP_EXE)' --install-cli"

# The old names, so scripts and habits keep working: there is one bundle now.
rebuild-cli rebuild-app rebuild-all: rebuild
check-cli check-app: check

# --- release artefact ---
#
# `XBrainAudit.app.zip` and its manifest are what `updater.py` looks for;
# `XAnalyze.app.zip` and `xanalyze-update-manifest.json` are the same app and
# the same signed manifest under the names an installed XAnalyze (0.73 and
# older) looks for. `scripts/package_release.sh` makes all of them, for this
# target and for the release workflow alike. Refuses to run over a stale
# bundle: publishing the previous version's archive under this version's tag
# is the one packaging mistake that cannot be spotted by looking at the
# release page.

package: check
	@echo "Packaging $(SOURCE_VERSION) ..."
	rm -f dist/xanalyze-cli-macos-*.tar.gz
	PYTHON="$(PY)" scripts/package_release.sh "$(SOURCE_VERSION)"
	@echo "Wrote:"
	@ls -lh dist/XBrainAudit.app.zip dist/XAnalyze.app.zip | awk '{print "  " $$NF "  " $$5}'
	@echo "The update manifest is unsigned unless UPDATE_SIGNING_KEY is set."
	@echo "Unsigned: a first launch of the app needs Control-click > Open until it is notarised."


# --- convenience ---

update: check
	@echo "Nothing to rebuild"
