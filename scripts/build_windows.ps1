# Windows build of XBrain Audit: dist\XBrain Audit\XBrain Audit.exe (window) and
# dist\XBrain Audit\xaudit.exe (command line and TUI), one folder.
#
# Run from anywhere, after creating the virtualenv described in README.md:
#
#     powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
#
# What `make rebuild` is on a Mac. Not a Makefile target because the Makefile
# is bash with macOS tools in it (PlistBuddy, ditto), and Windows has neither.
# Raise APP_VERSION in config.py before building, as on the Mac: the build
# reports the version it was built from.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "No virtualenv at $Root\venv. Create it first: py -3.13 -m venv venv; venv\Scripts\pip install -r requirements.txt"
}

Push-Location $Root
try {
    & $Python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not installed in venv: venv\Scripts\pip install pyinstaller"
    }
    $Version = (& $Python -c "import config; print(config.APP_VERSION)").Trim()
    Write-Host "Building XBrain Audit $Version ..."

    $Out = Join-Path $Root "dist\XBrain Audit"
    if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
    & $Python -m PyInstaller packaging\XBrainAudit-windows.spec --noconfirm --distpath dist
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

    # Read by app_entry._warn_if_stale: a binary built from other sources says so.
    Set-Content -Path (Join-Path $Out ".build_version") -Value $Version -NoNewline -Encoding ascii

    # The check the build is for: does the built program start and know its version?
    $Reported = (& (Join-Path $Out "xaudit.exe") --version).Trim()
    if ($Reported -ne "xaudit $Version") {
        throw "Built CLI reports '$Reported', expected 'xaudit $Version'"
    }
    Write-Host "XBrain Audit $Version built: $Out"
    Write-Host "  window:       $Out\XBrain Audit.exe"
    Write-Host "  command line: $Out\xaudit.exe   (no arguments opens the TUI)"
}
finally {
    Pop-Location
}
