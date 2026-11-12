"""Driving a real browser over a page, off screen.

`browser.py` builds the JavaScript and normalises what comes back;
`states.py` builds the state pass. This is the missing third of that job: the
thing that actually loads the page, waits for it to settle, runs each script
and collects the answers.

It exists because QtWebEngine is already in the application — the same
Chromium that paints the page preview — so the industry-standard engines run
with no Node, no Puppeteer and no new dependency.

Three properties of `QWebEnginePage.runJavaScript` shape everything here:

**It cannot await a promise.** `axe.run()` and `HTMLCS.process()` both settle
asynchronously, and handing their Promise to `runJavaScript` returns the
Promise object, not the result. So every script is wrapped to park its answer
on a global slot, and the slot is then polled. Polling reads worse than
awaiting and is the only thing that works.

**It is a callback, not a return value.** The whole run is therefore a small
state machine over one nested `QEventLoop`, rather than a sequence of calls.

**It has to be on the main thread.** QtWebEngine is not usable from a worker
thread, so this blocks the thread it is called on and pumps events while it
waits. In the window that means the UI stays responsive but the audit cannot
be moved to `ui/worker.py`; in the CLI it means nothing at all.

Everything this returns is already an `Issue`, deduplicated against the rule
families in `browser.py`, so a caller never learns which engine found what
unless it looks at `Issue.engine`.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from . import browser, states

#: How often a parked result is checked for. Short enough that a fast page
#: does not wait on the poll, long enough that a slow one is not hammered.
POLL_INTERVAL_MS = 120

#: Ceiling for one script. axe on a large page is genuinely slow (seconds),
#: so this is not tight; it exists so a page that never settles fails with a
#: recorded reason instead of hanging the caller forever.
SCRIPT_TIMEOUT_MS = 60_000

#: Ceiling for the load itself, separate from the scripts: a page that never
#: fires `loadFinished` is a different failure from one that loaded and then
#: broke an engine, and the report should be able to say which.
LOAD_TIMEOUT_MS = 30_000

COLOR_SCHEMES = ("light", "dark")
_DARK_FLAG = "--blink-settings=preferredColorScheme=0"
#: Light said out loud rather than left as Chromium's default. Chromium's
#: default is the operating system's theme: on a Windows 11 machine in dark
#: mode every audit without `--color-scheme` measured the page dark and
#: reported dark-only focus-ring failures as the light result.
_LIGHT_FLAG = "--blink-settings=preferredColorScheme=1"


def apply_color_scheme(scheme: str) -> None:
    """Tell Chromium which colour scheme pages should see, before it starts.

    A process-wide flag: Qt reads `QTWEBENGINE_CHROMIUM_FLAGS` when its
    browser process starts, so this has to run before the first page. A run
    that asks too late is caught by `BrowserAuditRunner`, which checks what
    the page actually sees and says so instead of reporting light as dark.
    """
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    flags = [flag for flag in flags if not flag.startswith("--blink-settings=preferredColorScheme")]
    flags.append(_DARK_FLAG if scheme == "dark" else _LIGHT_FLAG)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)


_SCHEME_SCRIPT = "matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'"


#: How long, past the settle wait, a page still marked `aria-busy="true"` is
#: given before it is measured anyway. A single-page app shows its skeleton
#: under `role="status" aria-busy="true"` while its data arrives; measured
#: then, Coach's /app had no `<h1>` and a card pointed at a heading that did
#: not exist yet. The page says when it is ready, so that is what is waited
#: for - bounded, because a spinner left busy by mistake must not stall a
#: crawl.
BUSY_WAIT_MS = 8_000
BUSY_POLL_MS = 250
#: Busy also while a finite animation is still running. Coach's landing
#: fades its scenes in, and `axe:color-contrast` measured "Екзамен" at
#: opacity below 1 on one run and not on the next. Infinite animations (a
#: spinner, a marquee) never end and are not waited for.
#:
#: Only a busy element a visitor can see counts. SharePoint Online keeps one
#: `[aria-busy="true"]` on every page: the search box's suggestions popup
#: (`role="listbox"`), empty and not rendered until somebody types. Counting
#: it made every page of a live intranet wait the full 8 s and then report
#: "still aria-busy, measured as it was" - a warning about nothing, on every
#: page, which teaches the reader to ignore the one that matters. Rendered
#: means: not under `aria-hidden="true"` or `hidden`, not
#: `display: none` / `visibility: hidden`, and a box with an area (or, for a
#: `display: contents` wrapper, a child that has one).
_BUSY_SCRIPT = """(function() {
  var EXCLUDED = /*XAUDIT_BUSY_EXCLUDE*/[];
  function excluded(el) {
    for (var x = 0; x < EXCLUDED.length; x++) {
      try { if (el.closest(EXCLUDED[x])) return true; } catch (e) {}
    }
    return false;
  }
  function boxed(el) {
    var rects = el.getClientRects();
    for (var i = 0; i < rects.length; i++) {
      if (rects[i].width > 0 && rects[i].height > 0) return true;
    }
    return false;
  }
  function rendered(el) {
    for (var n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (n.getAttribute('aria-hidden') === 'true' || n.hidden) return false;
    }
    var style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden'
        || style.visibility === 'collapse') return false;
    if (boxed(el)) return true;
    if (style.display !== 'contents') return false;
    var kids = el.children;
    for (var k = 0; k < kids.length; k++) {
      if (boxed(kids[k])) return true;
    }
    return false;
  }
  function named(el) {
    var role = el.getAttribute('role');
    var cls = (el.getAttribute('class') || '').trim().split(/\\s+/)[0];
    var r = el.getBoundingClientRect();
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
      + (!el.id && cls ? '.' + cls : '') + (role ? '[role=' + role + ']' : '')
      + ' ' + Math.round(r.width) + 'x' + Math.round(r.height);
  }
  var busy = document.querySelectorAll('[aria-busy="true"]');
  for (var b = 0; b < busy.length; b++) {
    if (rendered(busy[b]) && !excluded(busy[b])) return 'aria-busy ' + named(busy[b]);
  }
  if (!document.getAnimations) return false;
  var anims = document.getAnimations();
  for (var a = 0; a < anims.length; a++) {
    var an = anims[a];
    if (an.playState !== 'running' || !an.effect) continue;
    var end = an.effect.getComputedTiming().endTime;
    if (isFinite(end) && end > 0) {
      var target = an.effect.target;
      return 'animation ' + (target && target.tagName ? named(target) : '');
    }
  }
  return false;
})()"""

#: Lazy loading. SharePoint Online is believed to render a web part only
#: when it scrolls into view (HYPOTHESIS, see `audit.sharepoint_zones`), so
#: a page read without scrolling is missing everything below the fold - and
#: an audit of what is missing comes back clean. On a page that says it is
#: SharePoint (or when asked for), the page is scrolled to the bottom and
#: back, and the run waits until the number of canvas controls stops
#: changing. Bounded by `LAZY_WAIT_MS` in all, and by the runner's own
#: cancellation and deadline, which keep polling throughout.
LAZY_AUTO = "auto"
LAZY_ALWAYS = "always"
LAZY_NEVER = "never"
LAZY_MODES = (LAZY_AUTO, LAZY_ALWAYS, LAZY_NEVER)
LAZY_WAIT_MS = 15_000
LAZY_POLL_MS = 250
#: Equal answers in a row that count as "it stopped changing".
LAZY_STABLE_POLLS = 3
#: Is this page one whose web parts may load late? Read in the page, so the
#: decision needs no plumbing from the caller: the same check
#: `sharepoint_zones.is_sharepoint_page` makes on markup.
def busy_script(exclude=()) -> str:
    """`_BUSY_SCRIPT` that does not wait for what the audit leaves out.

    A region the run excludes (`BrowserAuditOptions.exclude`: the user's
    suppressions, and on SharePoint Microsoft's chrome) is not read, so its
    loading state cannot make what is read wrong. Measured live: Microsoft's
    comments region (`#CommentsWrapper`) keeps a viewport container
    `aria-busy` on subsite home pages for as long as one waits, and held
    four pages 8 s each with a warning about a region nobody audits.
    """
    import json

    selectors = [str(s) for s in (exclude or ()) if s]
    return _BUSY_SCRIPT.replace("/*XAUDIT_BUSY_EXCLUDE*/[]", json.dumps(selectors))


_LAZY_DETECT_SCRIPT = """(function() {
  return !!(window._spPageContextInfo || document.querySelector(
    '[data-sp-feature-tag], [data-sp-placeholder], #spPageChromeAppDiv'));
})()"""

#: How long to let a viewport resize reach the renderer before asking the
#: page anything. Measured rather than guessed: below ~100ms the first probe
#: after a resize still reports the previous width.
VIEWPORT_SETTLE_MS = 200

#: How long the page's own keydown handlers get after the one real Tab the
#: state pass starts with (`BrowserAuditRunner._prime_keyboard`).
KEYBOARD_PRIME_MS = 150

#: Chromium flags for a headless run. Set before QtWebEngine initialises or
#: they are ignored, which is why `ensure_headless_application` exists rather
#: than the caller doing this by hand.
HEADLESS_CHROMIUM_FLAGS = "--disable-gpu --disable-software-rasterizer --no-sandbox"

# Keep the Python wrapper alive for as long as QtWebEngine can use the
# application. A CLI render may be the first caller and has no window or test
# class holding the wrapper; letting it fall out of scope tears QApplication
# down underneath Chromium's browser thread.
_HEADLESS_APPLICATION = None


@dataclass
class PageAudit:
    """One page, as the browser saw it."""
    url: str
    issues: list = field(default_factory=list)
    #: Raw measurement payload (timings, transfer size, request counts), kept
    #: alongside the issues because a report shows the numbers as well as the
    #: findings derived from them.
    measurements: dict = field(default_factory=dict)
    #: Why the page could not be audited, if it could not. An empty string
    #: means the pass ran; the issues list may still be empty and that is a
    #: different statement.
    error: str = ""
    #: Per-script failures that did not stop the rest of the pass.
    engine_errors: dict = field(default_factory=dict)
    #: The DOM as the browser built it, when `capture_html` asked for it. Empty
    #: otherwise - and empty is not the same as "the page had no content",
    #: which is why it is not None.
    html: str = ""
    text_snapshot: dict = field(default_factory=dict)
    #: What the lazy-loading wait did, when it ran: `{"scrolled", "waited_ms",
    #: "canvas_controls", "stable"}`. Empty when the page did not ask for it.
    lazy: dict = field(default_factory=dict)


def ensure_headless_application():
    """A `QApplication` suitable for auditing with no screen.

    Returns the existing instance when the caller is the desktop app, so the
    window's own application is reused rather than a second one created (Qt
    permits exactly one).
    """
    global _HEADLESS_APPLICATION

    # Tests and callers that already own an offscreen QApplication still need
    # Chromium's headless flags before the first profile starts its browser
    # process. Returning the existing app before setting them made first-use
    # behaviour depend on which GUI test had created it.
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        additions = [flag for flag in HEADLESS_CHROMIUM_FLAGS.split()
                     if flag not in flags.split()]
        if additions:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
                f"{flags} {' '.join(additions)}").strip()

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    existing = QApplication.instance()
    if existing is not None:
        _HEADLESS_APPLICATION = existing
        from PySide6 import QtWebEngineCore  # noqa: F401
        return existing

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    from PySide6 import QtWebEngineCore  # noqa: F401

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    offscreen_fonts()
    if "preferredColorScheme" not in os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""):
        apply_color_scheme("light")
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    additions = [flag for flag in HEADLESS_CHROMIUM_FLAGS.split()
                 if flag not in flags.split()]
    if additions:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            f"{flags} {' '.join(additions)}").strip()
    _HEADLESS_APPLICATION = QApplication([])
    install_masking_message_handler()
    return _HEADLESS_APPLICATION


_MESSAGE_HANDLER_INSTALLED = False


def install_masking_message_handler() -> None:
    """Qt's own log lines, the page's console among them, masked on stderr.

    QtWebEngine forwards the page's console to stderr as `js: ...`, and a
    signed-in page logs its own addresses there - with the user's login and
    tokens in the query (see `privacy`). The default handler printed them as
    they were. This one prints the same line, through `privacy.mask_text`.
    Only for the headless application this module creates: the desktop app
    owns its own handler.
    """
    global _MESSAGE_HANDLER_INSTALLED
    if _MESSAGE_HANDLER_INSTALLED:
        return
    try:
        from PySide6.QtCore import qFormatLogMessage, qInstallMessageHandler
    except ImportError:  # pragma: no cover - an older binding: leave Qt's
        return

    def handler(mode, context, message):
        try:
            write_qt_message(qFormatLogMessage(mode, context, message))
        except Exception:  # noqa: BLE001 - a log line is never a crash
            pass

    qInstallMessageHandler(handler)
    _MESSAGE_HANDLER_INSTALLED = True


def write_qt_message(line: str, stream=None) -> None:
    """One Qt log line on stderr, masked."""
    from privacy import mask_text

    out = stream if stream is not None else sys.stderr
    out.write(mask_text(str(line)) + "\n")
    out.flush()


def offscreen_fonts() -> None:
    """Give Qt's offscreen platform the system fonts on Windows.

    The offscreen plugin does not ask Windows for fonts: it reads a font
    directory, by default one inside the Qt install that the PySide6 wheel
    does not ship. Measured on Windows 11: `QFontDatabase.families()` came
    back empty, every widget fell back to one generic face, and the window's
    layout was measured with metrics nothing on screen uses. macOS and
    Linux find their fonts through CoreText and fontconfig, so this is
    Windows only. Must run before the QApplication exists.
    """
    import sys

    if sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    if os.path.isdir(fonts):
        os.environ.setdefault("QT_QPA_FONTDIR", fonts)


def available() -> tuple:
    """`(usable, reason)` — whether a browser pass can run at all.

    Checked before a run rather than discovered during one: "QtWebEngine is
    not installed" and "this page has no problems" must never look the same
    in a report.
    """
    engines = browser.engines_available()
    if not engines["axe"] and not engines["htmlcs"]:
        return False, ("Neither axe-core nor HTML_CodeSniffer is present in "
                       "audit/vendor/ — reinstall or re-download them.")
    try:
        from PySide6.QtWebEngineCore import QWebEnginePage  # noqa: F401
    except ImportError as exc:
        return False, f"QtWebEngine is not available: {exc}"
    return True, ""


class _Slot:
    """One parked script result, and the polling around it."""

    def __init__(self, page, name: str, script: str, on_done):
        self.page = page
        self.name = name
        self.script = script
        self.on_done = on_done
        self.elapsed = 0
        self.world_id = 1 if name in ("text", "measurements") else 0

    def start(self) -> None:
        # `String(v)` because a script may resolve to something that is
        # already a string (measurements) or to a JSON string from a promise
        # (axe, HTMLCS); the Python side parses either the same way.
        wrapped = f"""
(function() {{
  window.__xaudit = window.__xaudit || {{}};
  window.__xaudit[{_js(self.name)}] = null;
  try {{
    Promise.resolve({self.script}).then(
      function(value) {{ window.__xaudit[{_js(self.name)}] = String(value); }},
      function(err) {{ window.__xaudit[{_js(self.name)}] = JSON.stringify({{error: String(err)}}); }}
    );
  }} catch (err) {{
    window.__xaudit[{_js(self.name)}] = JSON.stringify({{error: String(err)}});
  }}
  return true;
}})()
"""
        self.page.runJavaScript(wrapped, self.world_id, lambda _result: self._poll())

    def _poll(self) -> None:
        from PySide6.QtCore import QTimer

        def read(value):
            if value:
                self.on_done(self.name, value)
                return
            self.elapsed += POLL_INTERVAL_MS
            if self.elapsed >= SCRIPT_TIMEOUT_MS:
                self.on_done(self.name, None)
                return
            QTimer.singleShot(POLL_INTERVAL_MS, self._poll)

        self.page.runJavaScript(f"window.__xaudit && window.__xaudit[{_js(self.name)}]", self.world_id, read)


class BrowserAuditRunner:
    """Runs the browser pass over pages, one at a time, reusing one page.

    One page rather than one per URL: creating a `QWebEnginePage` spins up a
    renderer process, and a crawl of thirty pages would spend most of its time
    starting and stopping Chromium.
    """

    def __init__(self, options: browser.BrowserAuditOptions | None = None,
                 profile=None, cancelled=None, lazy_scroll: str = LAZY_AUTO):
        self.options = options or browser.BrowserAuditOptions()
        self._profile = profile
        if lazy_scroll not in LAZY_MODES:
            raise ValueError(f"lazy_scroll must be one of {LAZY_MODES}")
        #: Whether to scroll the page so lazily rendered parts exist before
        #: it is read: `auto` does it on SharePoint pages only.
        self._lazy_scroll = lazy_scroll
        self._page = None
        #: The widget that gives the page a size, when one was asked for.
        #: A page with no view has a viewport of 0x0, and a page that
        #: believes it is 0 pixels wide matches every `max-width` media
        #: query there is - which is how a "responsive" audit can produce
        #: three identical mobile-shaped answers and look like it worked.
        self._view = None
        self._viewport = self.options.viewport
        self._cancelled = cancelled or (lambda: False)

    # ------------------------------------------------------------- lifecycle

    def _get_page(self):
        if self._page is not None:
            return self._page
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineScript

        profile = self._profile
        if profile is None:
            # An off-the-record profile: auditing someone's site must not leave
            # its cookies and cache in the user's own browsing profile.
            profile = QWebEngineProfile(None)
            self._profile = profile
        page = QWebEnginePage(profile, None)
        if self._viewport:
            page = self._attach_view(page)
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        # The point of this pass is to see what a visitor sees, which includes
        # what JavaScript writes; but nothing here should be able to open a
        # window, and a page off the network must never reach the local disk.
        # `allow_local_files` is the one exception, and only for a file the
        # user picked themselves - see `BrowserAuditOptions`.
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                              bool(self.options.allow_local_files))
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        if self.options.run_measurements:
            from .vitals import bootstrap_script
            script = QWebEngineScript()
            script.setName("xaudit-web-vitals")
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            script.setRunsOnSubFrames(False)
            script.setSourceCode(bootstrap_script())
            page.scripts().insert(script)
        self._page = page
        return page

    def _attach_view(self, page):
        """Give the page a real, sized viewport without putting a window on
        anyone's screen.

        `WA_DontShowOnScreen` is the whole trick: the widget goes through
        show(), so it acquires a size, a layout and a compositor - which is
        what `window.innerWidth` and every media query read - but the window
        system never maps it. Without `show()` the size stays 0x0 no matter
        what `resize()` was called with; without the attribute, running an
        audit from the desktop app would flash a second window in the user's
        face for every page.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        view.setPage(page)
        width, height = self._viewport
        view.resize(int(width), int(height))
        view.show()
        self._view = view
        self._give_focus(view)
        return page

    @staticmethod
    def _give_focus(view) -> None:
        """Let the hidden view have window focus, when nobody else does.

        Chromium matches `:focus` only in a document whose window is active.
        An unshown view never was, so `el.focus()` set `activeElement` and
        changed no style - and `focus-not-visible` plus the two focus checks
        beside it had nothing to read in every command-line audit. They said
        so to nobody: the result looked like a page with no focus problems.

        **Only when no other window is active.** In the desktop app the main
        window is the active one, and handing focus to an unseen widget would
        deactivate it under the user's hands. There the checks stay unmeasured
        and say so (`state:focus-not-measured`), which is the honest outcome
        of a pass that must not steal the keyboard.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        import warnings

        active = QApplication.activeWindow()
        if active is not None and active is not view:
            return
        view.activateWindow()
        view.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        # `activateWindow()` alone does nothing on the offscreen platform: no
        # window system exists to grant it. Qt's own bookkeeping is what
        # Chromium reads, and `setActiveWindow` is the call that writes it. It
        # is marked deprecated; nothing replaces it for a widget that is never
        # mapped, so the warning is silenced here and nowhere else.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            QApplication.setActiveWindow(view)
        _pump(300)

    def _verify_traps(self, payload):
        """Keep a `keyboard-trap` only if real keys cannot leave it.

        The state script flags an element whose Tab keydown is cancelled. That
        is how a trap starts, and also how every roving-tabindex widget works:
        Fluent's FocusZone, a menu, a tab list cancel Tab and move focus
        themselves - out of the widget. On a live intranet the custom
        header's links were flagged that way. WCAG 2.1.2 asks whether focus
        can *leave*, so that is what is tried, with trusted key presses:
        Tab up to the number of focusable elements in the widget plus a
        margin, then Shift+Tab as many times. Focus reaching anything outside
        the widget, or the page itself, is a way out. Only an element no key
        got out of is kept, marked as verified that way. Without a view to
        send keys to, the finding is kept as the script had it.
        """
        import json

        if self._view is None or not payload or "keyboard-trap" not in str(payload):
            return payload
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return payload
        findings = data.get("findings") or []
        kept = []
        checked = 0
        for finding in findings:
            if finding.get("rule") != "keyboard-trap":
                kept.append(finding)
                continue
            if checked >= TRAP_CHECKS or not finding.get("dom_path"):
                kept.append(finding)
                continue
            checked += 1
            verdict = self._trap_with_real_keys(finding["dom_path"])
            if verdict is None:
                kept.append(finding)          # could not be tried: as found
            elif verdict:
                finding["verified"] = "real Tab and Shift+Tab did not leave it"
                kept.append(finding)
        data["findings"] = kept
        return json.dumps(data)

    def _trap_with_real_keys(self, path: str):
        """True: no key left the widget; False: one did; None: not tried."""
        import json

        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        prepared = _run_js(self._page, _TRAP_PREPARE % json.dumps(path))
        try:
            prepared = json.loads(prepared) if prepared else None
        except (TypeError, ValueError):
            prepared = None
        if not prepared or not prepared.get("ok"):
            _run_js(self._page, _TRAP_CLEANUP)
            return None
        limit = int(prepared.get("limit") or 3)
        target = self._view.focusProxy() or self._view
        escaped = False
        try:
            for modifier in (Qt.KeyboardModifier.NoModifier,
                             Qt.KeyboardModifier.ShiftModifier):
                if _run_js(self._page, _TRAP_REFOCUS) is not True:
                    # Focus could not be put back on the element: nothing
                    # this tries afterwards would say anything about it.
                    return None
                for _press in range(limit):
                    key = Qt.Key.Key_Backtab if modifier else Qt.Key.Key_Tab
                    QTest.keyClick(target, key, modifier)
                    _pump(TRAP_KEY_MS)
                    where = _run_js(self._page, _TRAP_WHERE)
                    if where in ("out", "gone"):
                        escaped = True
                        break
                if escaped:
                    break
        finally:
            _run_js(self._page, _TRAP_CLEANUP)
        return not escaped

    def _prime_keyboard(self) -> bool:
        """Press Tab once, natively, before the state pass reads focus.

        Many component libraries show a focus ring only after they have seen
        a keyboard: Fluent UI, which SharePoint and every SPFx part built on
        it use, puts `ms-Fabric--isFocusVisible` on the page on the first
        trusted Tab and draws its rings under that class. The state pass
        moves focus with `el.focus()`, which is not a key press, so on a live
        intranet every Fluent button read as having no visible focus. One
        real Tab is what a keyboard user's visit starts with; it moves focus
        and activates nothing. Returns whether it was sent (a page with no
        view has no window to receive it).
        """
        if self._view is None:
            return False
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtTest import QTest

            target = self._view.focusProxy() or self._view
            QTest.keyClick(target, Qt.Key.Key_Tab)
        except Exception:  # noqa: BLE001 - a missing key press must not stop the pass
            return False
        return True

    def set_viewport(self, width: int, height: int) -> None:
        """Resize the page's viewport, for the next `audit()` call.

        The resize has to reach the renderer process before the page is asked
        anything, and that happens on the event loop rather than on this
        line - hence the short pump. Cheap: it is once per breakpoint, not
        once per page.
        """
        self._viewport = (int(width), int(height))
        if self._page is None:
            return
        if self._view is None:
            self._page = self._attach_view(self._page)
        else:
            self._view.resize(int(width), int(height))
        _pump(VIEWPORT_SETTLE_MS)

    def close(self) -> None:
        # Order matters: Qt warns "Release of profile requested but
        # WebEnginePage still not deleted" and can crash if the profile outlives
        # its page only in Python's eyes.
        view, self._view = self._view, None
        if view is not None:
            # The view before the page it shows: a view left holding a
            # deleted page is the same class of crash as a profile left
            # holding a deleted page.
            view.setPage(None)
            view.deleteLater()
        page, self._page = self._page, None
        if page is not None:
            page.deleteLater()
            # `deleteLater` only queues the deletion; dropping the profile in
            # the same breath drops it while the page is still alive on the
            # C++ side, which Qt warns about and can crash on. One turn of the
            # event loop is enough for the queued deletion to happen.
            from PySide6.QtCore import QCoreApplication, QEvent
            app = QCoreApplication.instance()
            if app is not None:
                # `DeferredDelete` explicitly: a plain `processEvents` does
                # not run deferred deletions outside the event loop level that
                # posted them, so the page would still be alive here.
                app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        self._profile = None

    # ----------------------------------------------------------------- audit

    def audit(self, url: str) -> PageAudit:
        """Load one page, run every enabled pass, and return the findings."""
        from dataclasses import replace
        from .vitals import repeat_summary
        count = self.options.performance_repeats if self.options.run_measurements else 1
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError("performance_repeats must be between 1 and 10")
        result = self._audit(url, load=True, options=self.options)
        if count == 1 or result.error:
            return result
        samples = [dict(result.measurements)]
        repeat_options = replace(self.options, run_axe=False, run_htmlcs=False,
                                 run_states=False, capture_html=False, capture_text=False)
        for index in range(2, count + 1):
            if self._cancelled():
                result.engine_errors["repeats"] = "cancelled"
                break
            sample = self._audit(url, load=True, options=repeat_options)
            sample.measurements.setdefault("conditions", {})["repeatIndex"] = index
            samples.append(sample.measurements)
            if sample.error or sample.engine_errors:
                result.engine_errors[f"repeat:{index}"] = sample.error or str(sample.engine_errors)
        result.measurements["repeats"] = {**repeat_summary(samples),
            "requested_runs": count, "completed_runs": len(samples), "runs": samples,
            "cache_policy": "fresh navigations sharing the same profile and HTTP cache"}
        return result

    def audit_loaded(self, url: str,
                     options: browser.BrowserAuditOptions | None = None) -> PageAudit:
        """Audit the page already loaded after a viewport change.

        Responsive checks need a new layout, not a new navigation. Keeping
        those two operations separate is what makes four widths one browser
        snapshot rather than four unrelated responses from a dynamic site.
        """
        if self._page is None:
            return PageAudit(url=url, error="no page is loaded")
        return self._audit(url, load=False, options=options or self.options)

    def _run_scenario(self, actions, on_done, finished):
        """Deliver real Qt pointer/keyboard inputs only to explicitly named targets."""
        from PySide6.QtCore import QPoint, Qt, QTimer
        from PySide6.QtTest import QTest
        from .vitals import validate_scenario

        evidence = []
        queue = list(validate_scenario(actions))
        initial_url = self._page.url().toString()

        def next_action():
            if finished():
                return
            if not queue:
                on_done(evidence)
                return
            action = queue.pop(0)
            selector = _js(action["selector"])
            script = f"""(function() {{
              const nodes = document.querySelectorAll({selector});
              if (nodes.length !== 1) return JSON.stringify({{error:'selector must match exactly one element'}});
              const node = nodes[0], rect = node.getBoundingClientRect();
              const x = rect.left + rect.width/2, y = rect.top + rect.height/2;
              if (!rect.width || !rect.height || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight)
                return JSON.stringify({{error:'target is outside the visible viewport'}});
              const hit = document.elementFromPoint(x, y);
              if (!hit || (hit !== node && !node.contains(hit)))
                return JSON.stringify({{error:'target is covered by another element'}});
              node.focus();
              return JSON.stringify({{x:x, y:y}});
            }})()"""

            def ready(value):
                if finished():
                    return
                record = dict(action)
                try:
                    coordinates = _parse(value)
                    if coordinates.get("error"):
                        raise ValueError(coordinates["error"])
                    if not self._view or "x" not in coordinates:
                        raise ValueError("native input target unavailable")
                    target = self._view.focusProxy() or self._view
                    target.setFocus()
                    if action["action"] == "click":
                        QTest.mouseClick(target, Qt.MouseButton.LeftButton,
                                         pos=QPoint(round(coordinates["x"]), round(coordinates["y"])))
                    else:
                        key = {"Enter": Qt.Key.Key_Return, "Space": Qt.Key.Key_Space,
                               "Tab": Qt.Key.Key_Tab, "Escape": Qt.Key.Key_Escape,
                               "ArrowDown": Qt.Key.Key_Down, "ArrowUp": Qt.Key.Key_Up}[action["key"]]
                        QTest.keyClick(target, key)
                    record.update(status="checked", transport="Qt native input")
                except Exception as exc:  # callback errors must complete the audit
                    record.update(status="error", reason=str(exc))
                evidence.append(record)

                def settled():
                    if self._page.url().toString() != initial_url:
                        record.update(status="error", reason="scenario changed navigation")
                        queue.clear()
                    next_action()
                QTimer.singleShot(action["wait_ms"], settled)

            self._page.runJavaScript(script, 1, ready)
        next_action()

    def _audit(self, url: str, *, load: bool,
               options: browser.BrowserAuditOptions) -> PageAudit:
        """Run one browser probe, navigating only when `load` is true."""
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        usable, reason = available()
        if not usable:
            return PageAudit(url=url, error=reason)

        if type(options.settle_ms) is not int or not 0 <= options.settle_ms <= 60_000:
            return PageAudit(url=url, error="settle_ms must be between 0 and 60000")
        try:
            page = self._get_page()
        except Exception as exc:
            return PageAudit(url=url, error=f"browser preparation failed: {exc}")
        result = PageAudit(url=url)
        loop = QEventLoop()
        state = {"loaded": None if load else True, "finished": False}

        def finish():
            if not state["finished"]:
                state["finished"] = True
                loop.quit()

        def on_load(ok: bool):
            if state["loaded"] is not None:
                return
            state["loaded"] = bool(ok)
            if not ok:
                result.error = "the page did not load"
                finish()
                return
            # The settle wait is the difference between auditing the site and
            # auditing its loading skeleton. The lazy scroll goes first, the
            # busy wait after it: SharePoint marks a part below the fold
            # `aria-busy` (its viewport container, `div#vpc_...[role=region]`)
            # until it has been scrolled into view. Waited for in the other
            # order, the comments and the footer of every page held the run
            # 8 s and were reported "still aria-busy" - measured live on six
            # of twelve modern pages.
            QTimer.singleShot(options.settle_ms,
                              lambda: settle_lazy(wait_until_idle))

        payloads: dict = {}
        #: Active `_Slot`s, kept alive against garbage collection. See
        #: `next_script` below for why this cannot be a local in the loop.
        live: list = []
        scenario_evidence = []
        pending = [name for name, enabled in (
            ("measurements", options.run_measurements),
            ("axe", options.run_axe and browser.engines_available()["axe"]),
            ("htmlcs", options.run_htmlcs and browser.engines_available()["htmlcs"]),
            ("states", options.run_states),
            ("html", options.capture_html and not options.capture_text),
            ("text", options.capture_text),
        ) if enabled]

        def on_script_done(name: str, value):
            if state["finished"]:
                return
            if value is None:
                result.engine_errors[name] = f"timed out after {SCRIPT_TIMEOUT_MS // 1000}s"
            else:
                payloads[name] = value
            if name in pending:
                pending.remove(name)
            if not pending:
                finish()

        busy = {"waited_ms": 0, "still_busy": False, "scheme": None,
                "element": ""}

        def wait_until_idle():
            if state["finished"]:
                return
            if busy["scheme"] is None:
                def seen(scheme):
                    busy["scheme"] = scheme if scheme in COLOR_SCHEMES else "unknown"
                    wait_until_idle()
                page.runJavaScript(_SCHEME_SCRIPT, 0, seen)
                return

            def answered(is_busy):
                if state["finished"]:
                    return
                if is_busy and busy["waited_ms"] < BUSY_WAIT_MS:
                    busy["waited_ms"] += BUSY_POLL_MS
                    QTimer.singleShot(BUSY_POLL_MS, wait_until_idle)
                    return
                busy["still_busy"] = bool(is_busy)
                # What held it, so the report can be checked: `aria-busy
                # div#feed[role=status] 640x200` or `animation ...`.
                busy["element"] = is_busy if isinstance(is_busy, str) else ""
                run_scripts()

            page.runJavaScript(
                busy_script(getattr(options, "exclude", None) or ()), 0, answered)

        def settle_lazy(then):
            """Scroll lazily rendered parts into existence, then go on."""
            from .sharepoint_zones import (CANVAS_COUNT_SCRIPT,
                                           SCROLL_DONE_SCRIPT, SCROLL_SCRIPT)

            mode = self._lazy_scroll
            if mode == LAZY_NEVER:
                then()
                return
            lazy = {"waited_ms": 0, "last": None, "same": 0}

            def proceed(stable: bool):
                result.lazy = {"scrolled": True, "waited_ms": lazy["waited_ms"],
                               "canvas_controls": lazy["last"] or 0,
                               "stable": stable}
                then()

            def counted(value):
                if state["finished"]:
                    return
                # A JavaScript number arrives as a float through Qt.
                count = (int(value) if isinstance(value, (int, float))
                         and not isinstance(value, bool) else 0)
                lazy["same"] = lazy["same"] + 1 if count == lazy["last"] else 0
                lazy["last"] = count
                if lazy["same"] >= LAZY_STABLE_POLLS - 1:
                    proceed(True)
                elif lazy["waited_ms"] >= LAZY_WAIT_MS:
                    proceed(False)
                else:
                    lazy["waited_ms"] += LAZY_POLL_MS
                    QTimer.singleShot(LAZY_POLL_MS, lambda: page.runJavaScript(
                        CANVAS_COUNT_SCRIPT, 0, counted))

            def scrolled(done):
                if state["finished"]:
                    return
                if done is True or lazy["waited_ms"] >= LAZY_WAIT_MS:
                    page.runJavaScript(CANVAS_COUNT_SCRIPT, 0, counted)
                    return
                lazy["waited_ms"] += LAZY_POLL_MS
                QTimer.singleShot(LAZY_POLL_MS, lambda: page.runJavaScript(
                    SCROLL_DONE_SCRIPT, 0, scrolled))

            def detected(is_lazy_page):
                if state["finished"]:
                    return
                if not (is_lazy_page or mode == LAZY_ALWAYS):
                    then()
                    return
                page.runJavaScript(SCROLL_SCRIPT, 0,
                                   lambda _started: scrolled(False))

            page.runJavaScript(_LAZY_DETECT_SCRIPT, 0, detected)

        def run_scripts():
            from text_extraction import TEXT_SNAPSHOT_SCRIPT
            if not pending:
                finish()
                return
            scripts = {
                "axe": lambda: browser.axe_script(options),
                "htmlcs": lambda: browser.htmlcs_script(
                    exclude=getattr(options, "exclude", None) or ()),
                "measurements": lambda: browser.MEASUREMENT_SCRIPT,
                "states": lambda: states.state_script(
                    getattr(options, "exclude", None) or ()),
                "html": lambda: browser.HTML_SCRIPT,
                "text": lambda: TEXT_SNAPSHOT_SCRIPT.replace(
                    'const scope = ""; // XAUDIT_SCOPE',
                    'const scope = ' + _js(options.text_within) + ';'),
            }
            # Sequentially, not in parallel: axe and the state pass both walk
            # the whole DOM, and the state pass moves focus around. Running
            # them at once would have each measuring the other's side effects.
            queue = list(pending)

            def next_script(*_args):
                if state["finished"] or not queue:
                    return
                name = queue.pop(0)
                try:
                    source = scripts[name]()
                except Exception as exc:  # noqa: BLE001 - a callback must not leave the loop parked
                    result.engine_errors[name] = f"script preparation failed: {exc}"
                    if name in pending:
                        pending.remove(name)
                    if not pending:
                        finish()
                    else:
                        QTimer.singleShot(0, next_script)
                    return
                def script_done(n, v):
                    if n != "states":
                        on_script_done(n, v)
                        next_script()
                        return
                    # Out of the result callback first: the trap check waits
                    # on further `runJavaScript` answers, and Qt does not
                    # deliver them while this callback is still running.
                    QTimer.singleShot(0, lambda: (
                        on_script_done(n, self._verify_traps(v)), next_script()))

                slot = _Slot(page, name, source, script_done)
                # Held for the length of the run. Without this the only
                # reference to the slot is the callback Qt is holding, and Qt
                # drops that as soon as it fires: the slot is then collected
                # between one poll and the next, the next poll is never
                # scheduled, and the pass hangs until its timeout with no
                # error to show for it (cost one debugging session to find).
                live.append(slot)
                if name == "states" and self._prime_keyboard():
                    # Let the page's keydown handlers run before it is read.
                    QTimer.singleShot(KEYBOARD_PRIME_MS, slot.start)
                else:
                    slot.start()

            if options.run_measurements and options.performance_scenario:
                def scenario_done(evidence):
                    scenario_evidence.extend(evidence)
                    if any(entry.get("reason") == "scenario changed navigation" for entry in evidence):
                        result.error = "performance scenario changed navigation"
                        result.measurements = {"conditions": {"scenario": evidence, "scope": "invalidated navigation"}}
                        finish()
                        return
                    next_script()
                try:
                    self._run_scenario(options.performance_scenario, scenario_done,
                                       lambda: state["finished"])
                except Exception as exc:
                    result.engine_errors["scenario"] = str(exc)
                    next_script()
            else:
                next_script()

        cancel_timer = QTimer()
        cancel_timer.setInterval(50)

        def stop_if_cancelled():
            if not self._cancelled():
                return
            result.error = "cancelled"
            try:
                page.triggerAction(page.WebAction.Stop)
            except (AttributeError, RuntimeError):
                pass
            finish()

        cancel_timer.timeout.connect(stop_if_cancelled)
        cancel_timer.start()

        if load:
            page.loadFinished.connect(on_load)
            QTimer.singleShot(LOAD_TIMEOUT_MS, lambda: (
                result.error or setattr(
                    result, "error", "the page did not finish loading in time"),
                finish(),
            ) if state["loaded"] is None else None)
            page.setUrl(QUrl(url))
        else:
            QTimer.singleShot(options.settle_ms, wait_until_idle)
        loop.exec()
        cancel_timer.stop()
        if load:
            try:
                page.loadFinished.disconnect(on_load)
            except (RuntimeError, TypeError):
                pass

        if result.error:
            return result

        issues = []
        if "axe" in payloads:
            issues += browser.issues_from_axe(payloads["axe"], url, options.disabled_rules)
        if "htmlcs" in payloads:
            issues += browser.issues_from_htmlcs(payloads["htmlcs"], url)
        if "measurements" in payloads:
            from .vitals import vendor_identity
            result.measurements = _parse(payloads["measurements"])
            if result.measurements.get("error"):
                result.engine_errors["measurements"] = str(result.measurements["error"])
            if result.measurements:
                result.measurements.setdefault("conditions", {}).update({
                    "settleMs": options.settle_ms, "navigationLoaded": load,
                    "busyWaitMs": busy["waited_ms"], "stillBusy": busy["still_busy"],
                    "colorScheme": busy["scheme"],
                    "profile": "session" if self._profile and not self._profile.isOffTheRecord()
                               else "off-the-record",
                    "httpCache": "shared profile cache, not forcibly cleared",
                    "webVitals": vendor_identity(),
                    "scenario": scenario_evidence,
                })
                failures = [entry for entry in scenario_evidence if entry["status"] == "error"]
                if failures:
                    result.engine_errors["scenario"] = "; ".join(
                        f"{entry['selector']}: {entry['reason']}" for entry in failures)
            issues += browser.issues_from_measurements(result.measurements, url)
        wanted = getattr(options, "color_scheme", "light") or "light"
        if busy["scheme"] not in (None, wanted):
            # Asked for one scheme and measured another: the flag reached
            # Chromium too late. Said, because a "dark" report of the light
            # theme is the worst kind of wrong - confident.
            result.engine_errors["color_scheme"] = (
                f"asked for {wanted}, the page saw {busy['scheme']}")
        if busy["still_busy"]:
            # Measured anyway, and said: what follows may describe a skeleton.
            held = f" ({busy['element']})" if busy["element"] else ""
            result.engine_errors["busy"] = (
                f"the page was still aria-busy after {BUSY_WAIT_MS // 1000}s"
                f"{held}; it was measured as it was")
        if "states" in payloads:
            issues += states.issues_from_states(payloads["states"], url)
        if "html" in payloads:
            # A string, not JSON: the other scripts return structures, this one
            # returns the document, and putting it through the same parser
            # would only be a way to lose it.
            result.html = payloads["html"] if isinstance(payloads["html"], str) else ""
        if "text" in payloads:
            result.text_snapshot = _parse(payloads["text"])
            if options.capture_html:
                result.html = result.text_snapshot.pop("main_html", "")

        # One finding per problem, whoever found it: the same missing `alt`
        # reported by our rule, by axe and by HTML_CodeSniffer is one row that
        # names its corroboration, not three rows.
        # The rendered document goes with them: whether two findings are about
        # one element or two is a question only the page can answer.
        result.issues = browser.deduplicate(issues, markup=result.html)
        return result


def session_profile(host: str, parent=None):
    """A persistent QtWebEngine profile for a host the person signed in to.

    The default profile for an audit is off-the-record on purpose: reading
    somebody's site must not leave its cookies in the user's own browsing
    data. A signed-in run is the one case where that is exactly what is
    wanted, and only for the host it was created for - so the profile is
    named after the host and stored under this app's own directory. See
    `site_session` for where, and for how it is forgotten.

    Returns `None` when there is no stored session for the host, which keeps
    every caller's normal path unchanged: no session, no persistent profile.
    """
    import site_session

    host = site_session.host_of(host) or host
    if not host or not site_session.has_session(host):
        return None
    return open_session_profile(host, parent=parent)


#: One profile per host for the life of the process.
#:
#: Not a cache for speed. A `QWebEngineProfile` must outlive every page made
#: from it, and a profile parented to a dialog is destroyed when the dialog
#: is - in whatever order Qt happens to destroy the children, which is how
#: "Release of profile requested but WebEnginePage still not deleted. Expect
#: troubles!" appears on a perfectly ordinary close. Keeping it here means
#: the profile outlives the window by construction, and reopening the sign-in
#: window for the same host reuses the session rather than racing it.
_SESSION_PROFILES: dict = {}


def open_session_profile(host: str, parent=None):
    """The same profile, created if it does not exist yet.

    Split from `session_profile` because signing in is the one moment the
    profile has to be brought into being; every other caller must not create
    a session as a side effect of looking for one.

    `parent` is accepted and deliberately ignored - see `_SESSION_PROFILES`.
    """
    from PySide6.QtWebEngineCore import QWebEngineProfile

    import site_session

    host = site_session.host_of(host) or host
    existing = _SESSION_PROFILES.get(host)
    if existing is not None:
        return existing
    path = site_session.profile_dir(host, create=True)
    profile = QWebEngineProfile(f"xaudit-{host}")
    profile.setPersistentStoragePath(str(path))
    profile.setCachePath(str(path / "cache"))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    _SESSION_PROFILES[host] = profile
    return profile


#: How long `release_session_profile` waits for Chromium to let go of the
#: profile's files after the profile is deleted. The database is closed on a
#: background thread, so the deletion returning is not the file being free.
RELEASE_WAIT_MS = 3000


def release_session_profile(host: str) -> bool:
    """Close this host's cached profile, so its files can be read again.

    Why: once QtWebEngine holds a profile, Windows refuses every other open
    of its `Cookies` file, and the cookie store never reports a cookie it
    restored from disk. The sign-in window therefore reads the file *before*
    it opens the profile - which a process that already opened it (a browser
    pass, an earlier sign-in window) makes impossible for as long as
    `_SESSION_PROFILES` keeps it. Called right before the window opens; the
    window then creates the profile afresh.

    Refuses (returns `False`, keeps the profile) while a page still uses it:
    deleting a profile under a live page is the crash Qt warns about, and a
    live page means a run is reading the site right now. `True` when nothing
    of this host is held any more, including when nothing was.
    """
    import site_session

    host = site_session.host_of(host) or host
    profile = _SESSION_PROFILES.get(host)
    if profile is None:
        return True
    from PySide6.QtCore import QCoreApplication, QEvent

    app = QCoreApplication.instance()
    if app is not None:
        # Pages already given up (`deleteLater`) are still alive until the
        # deferred deletions run; see `BrowserAuditRunner.close`.
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    if _pages_of(profile):
        return False
    del _SESSION_PROFILES[host]
    try:
        import shiboken6

        if shiboken6.isValid(profile):
            # Explicitly, not by dropping the reference: a sign-in window
            # that already closed can still hold one as an attribute.
            shiboken6.delete(profile)
    except Exception:  # noqa: BLE001 - a profile already gone is the goal
        pass
    del profile
    _wait_until_free(site_session.profile_dir(host), RELEASE_WAIT_MS)
    return True


def _pages_of(profile) -> list:
    """The live pages made from `profile`, as Python knows them.

    Qt has no "pages of this profile" question; every page here is made from
    Python, so the garbage collector's view is the complete one.
    """
    import gc

    import shiboken6
    from PySide6.QtWebEngineCore import QWebEnginePage

    pages = []
    for obj in gc.get_objects():
        try:
            if (isinstance(obj, QWebEnginePage) and shiboken6.isValid(obj)
                    and obj.profile() is profile):
                pages.append(obj)
        except Exception:  # noqa: BLE001 - a half-deleted wrapper is not a user
            continue
    return pages


def _wait_until_free(folder, milliseconds: int) -> None:
    """Pump the event loop until the profile's cookie files open, or time out."""
    import time

    candidates = [folder / "Cookies", folder / "Network" / "Cookies"]
    deadline = time.monotonic() + milliseconds / 1000
    while True:
        free = True
        for path in candidates:
            if not path.is_file():
                continue
            try:
                with open(path, "rb"):
                    pass
            except OSError:
                free = False
        if free or time.monotonic() >= deadline:
            return
        _pump(50)


class html_renderer:
    """A `render(url) -> html` callable backed by one browser, as a context.

    A context manager because the browser is expensive to start and must be
    shut down deliberately: one profile for the whole crawl rather than one per
    page, and the profile released before the process exits (Qt warns, loudly
    and correctly, about a profile still in use).

    Must be used from the thread that owns the Qt application - QtWebEngine
    has no other mode - so a caller on a worker thread renders before or after
    its own work, not inside it.
    """

    def __init__(self, settle_ms: int = 1200, allow_local_files: bool = False,
                 session_host: str = "", within: str = "",
                 lazy_scroll: str = LAZY_AUTO):
        self.options = browser.BrowserAuditOptions(
            run_axe=False, run_htmlcs=False, run_measurements=False,
            run_states=False, capture_html=True, capture_text=True, settle_ms=settle_ms,
            allow_local_files=allow_local_files,
            text_within=within,
        )
        #: Render as the person who signed in, when they did. Empty - the
        #: normal case - keeps the off-the-record profile.
        self.session_host = session_host or ""
        self.lazy_scroll = lazy_scroll
        self.runner = None
        #: `time.monotonic()` past which the page in progress is abandoned,
        #: or None. Checked by the runner's own cancellation poll, on the Qt
        #: thread - see `__call__`.
        self._deadline = None

    def _expired(self) -> bool:
        import time

        return self._deadline is not None and time.monotonic() >= self._deadline

    def __enter__(self):
        ensure_headless_application()
        profile = session_profile(self.session_host) if self.session_host else None
        self.runner = BrowserAuditRunner(self.options, profile=profile,
                                         cancelled=self._expired,
                                         lazy_scroll=self.lazy_scroll)
        return self

    def __exit__(self, *_exc):
        if self.runner is not None:
            self.runner.close()
            self.runner = None
        return False

    def __call__(self, url: str, timeout: float | None = None) -> str:
        """Render `url`; with `timeout`, give up on it after that many seconds.

        The timeout is a deadline the runner polls from its own event loop,
        not a signal: this runs on the Qt thread, which nothing outside may
        interrupt, and `SIGALRM` - what the crawler used before - does not
        exist on Windows and cannot be set off the main thread anywhere.
        """
        import time

        if self.runner is None:
            raise RuntimeError("html_renderer used outside its context")
        self._deadline = time.monotonic() + timeout if timeout else None
        try:
            result = self.runner.audit(url)
        finally:
            timed_out = self._expired()
            self._deadline = None
        if timed_out and result.error == "cancelled":
            raise TimeoutError(f"render timed out after {timeout}s")
        if result.error:
            # Raised rather than returned empty: the crawler records the reason
            # against the page, and "" would be indistinguishable from a page
            # that rendered to nothing.
            raise RuntimeError(result.error)
        from text_extraction import RenderedHTML
        snapshot = getattr(result, "text_snapshot", {}) or {"error": getattr(result, "engine_errors", {}).get("text", "text snapshot unavailable")}
        if not result.html:
            raise RuntimeError(snapshot.get("error", "rendered text snapshot unavailable"))
        return RenderedHTML(result.html or "", snapshot)


#: At most this many trap candidates are tried with real keys on one page.
TRAP_CHECKS = 6
#: How long the page gets to react to one real key press.
TRAP_KEY_MS = 60

#: Find the flagged element by its recorded path, mark the widget it belongs
#: to, focus the element. The widget is the nearest ancestor that manages
#: focus itself (an ARIA composite role, a dialog, a Fluent FocusZone), else
#: its grandparent. Returns how many key presses are enough to leave it.
_TRAP_PREPARE = """(function(path) {
  var steps = path.split('/');
  if (steps[0] !== 'html') return null;
  var node = document.documentElement;
  for (var i = 1; i < steps.length; i++) {
    var cut = steps[i].lastIndexOf(':');
    var child = node.children[+steps[i].slice(cut + 1)];
    if (!child || child.tagName.toLowerCase() !== steps[i].slice(0, cut)) return null;
    node = child;
  }
  var widget = node.closest('[role=dialog],[role=alertdialog],[aria-modal=true],[role=toolbar],' +
      '[role=menu],[role=menubar],[role=tablist],[role=listbox],[role=grid],[role=tree],' +
      '[role=radiogroup],[data-focuszone-id]')
    || (node.parentElement && node.parentElement.parentElement) || node.parentElement || node;
  Array.prototype.forEach.call(document.querySelectorAll('[data-xa-trap]'),
    function(e) { e.removeAttribute('data-xa-trap'); });
  widget.setAttribute('data-xa-trap', '');
  window.__xaTrapStart = node;
  var count = widget.querySelectorAll('a[href],button,input,select,textarea,summary,[tabindex]').length;
  try { node.focus({preventScroll: true}); } catch (e) {}
  return JSON.stringify({ok: document.activeElement === node, limit: Math.min(count + 3, 60)});
})(%s)"""
_TRAP_REFOCUS = """(function() {
  var start = window.__xaTrapStart;
  try { if (start) start.focus({preventScroll: true}); } catch (e) {}
  return document.activeElement === start;
})()"""
_TRAP_WHERE = """(function() {
  var widget = document.querySelector('[data-xa-trap]');
  var active = document.activeElement;
  if (!widget) return 'gone';
  if (!active || active === document.body || active === document.documentElement) return 'out';
  return widget.contains(active) ? 'in' : 'out';
})()"""
_TRAP_CLEANUP = """(function() {
  Array.prototype.forEach.call(document.querySelectorAll('[data-xa-trap]'),
    function(e) { e.removeAttribute('data-xa-trap'); });
  var start = window.__xaTrapStart;
  window.__xaTrapStart = null;
  try { if (start && document.activeElement === start) start.blur(); } catch (e) {}
  return true;
})()"""


def _run_js(page, script: str, timeout_ms: int = 2000):
    """Run `script` in the page and wait for its answer, on this thread."""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    box = {}

    def answered(value):
        box["value"] = value
        loop.quit()

    page.runJavaScript(script, 1, answered)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return box.get("value")


def _pump(milliseconds: int) -> None:
    """Run the event loop for a fixed time, on the caller's thread."""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def audit_urls(urls, options: browser.BrowserAuditOptions | None = None,
               progress=None) -> list:
    """Convenience for the CLI: audit several pages with one browser.

    Creates a headless `QApplication` when there is none, so a script can call
    this without knowing that Qt is involved. progress, if given, is called as
    progress(page_number, url) before each page so a long run can show life.
    """
    ensure_headless_application()
    runner = BrowserAuditRunner(options)
    try:
        results = []
        for i, url in enumerate(urls, 1):
            if progress:
                progress(i, url)
            results.append(runner.audit(url))
        return results
    finally:
        runner.close()


def _js(value: str) -> str:
    import json
    return json.dumps(value)


def _parse(payload: str) -> dict:
    import json
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
