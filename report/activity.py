"""Evidence that a render is still working, instead of a clock.

A fixed print ceiling and no ceiling at all are the same design error seen
from two sides, and this project shipped both in turn:

* 30 seconds killed a 158-page report that finished in 108 when left alone.
  The run had already spent 46 minutes crawling and auditing, and wrote
  nothing at all.
* `RENDER_TIMEOUT_MS = 0` fixed that by removing the ceiling - and with it
  the floor. A render process that dies now hangs the writer forever, with
  no entry in any log.

Elapsed time was never the thing worth measuring. A render that has been
going for ten minutes and is still consuming CPU is healthy; one that has
been silent for forty seconds with a dead render process is not, and the
elapsed time does not distinguish them. So this watches for *progress* and
stops on *its absence*, which is a different question with a different answer.

Three sources of evidence, in the order they are trusted:

1. **The render process died.** `renderProcessTerminated` is Qt answering,
   and the answer will not change on a retry.
2. **Load progress moved.** Only meaningful while loading; `printToPdf`
   emits nothing, which is exactly why the third source exists.
3. **The render process used more CPU than at the last poll.** This is the
   only progress signal available during printing. Read with `ps`, because
   the alternative is a new dependency for one number.

When no pid is available, or `ps` will not answer, the watch says so in its
reason rather than quietly degrading into the fixed timer this module exists
to replace.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time

#: How long a render may show no progress of any kind before it is stopped.
#: Tens of seconds rather than a few, because on Linux `ps` reports CPU time
#: in whole seconds: a renderer doing a little work each second has to be
#: given long enough for that work to round up to something.
STALL_SECONDS = 45.0

#: How often progress is checked. Each poll runs one `ps`, so this trades a
#: subprocess a second against how promptly a genuine stall is noticed.
POLL_SECONDS = 1.5


def cpu_seconds(pid: int) -> float | None:
    """CPU time consumed by `pid`, or None when that cannot be read.

    None and 0.0 are different answers and the caller depends on it: 0.0 is
    "measured, and it has done nothing", None is "not measured". Treating
    the second as the first would report a stall the moment `ps` was missing.
    """
    if not pid or pid <= 0:
        return None
    if sys.platform == "win32":
        # Windows has no `ps`, and the one Git for Windows puts on PATH is
        # MSYS's, which knows neither `-o cputime=` nor Windows pids.
        return _windows_cpu_seconds(pid)
    if not shutil.which("ps"):
        return None
    try:
        out = subprocess.run(["ps", "-o", "cputime=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_cputime(out.stdout)


def _windows_cpu_seconds(pid: int) -> float | None:
    """Kernel plus user time of `pid` from `GetProcessTimes`, or None."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:  # pragma: no cover - ctypes ships with CPython
        return None

    query_limited_information = 0x1000
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return None
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (
        ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    try:
        handle = kernel32.OpenProcess(query_limited_information, False, int(pid))
    except (OverflowError, ctypes.ArgumentError):
        return None
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None

        def ticks(filetime) -> int:
            return (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime

        _created, _exited, kernel, user = times
        # FILETIME counts 100-nanosecond intervals.
        return (ticks(kernel) + ticks(user)) / 10_000_000
    finally:
        kernel32.CloseHandle(handle)


def parse_cputime(raw: str) -> float | None:
    """`[[HH:]MM:]SS[.cc]` to seconds.

    darwin prints centiseconds, Linux whole seconds, and a long-lived process
    grows an hours field - so all three shapes are parsed rather than the one
    the developer's machine happens to produce.
    """
    text = (raw or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        return None
    try:
        seconds = float(parts[-1])
    except ValueError:
        return None
    if len(parts) >= 2:
        try:
            seconds += int(parts[-2]) * 60
        except ValueError:
            return None
    if len(parts) == 3:
        try:
            seconds += int(parts[0]) * 3600
        except ValueError:
            return None
    return seconds


class Stalled(RuntimeError):
    """No progress of any kind for the stall window.

    Distinct from a load that failed: this one means nobody answered, so the
    caller may reasonably try once against a fresh page.
    """


class RenderProcessGone(RuntimeError):
    """The render process died. Not retried - Qt answered."""


class ActivityWatch:
    """Progress evidence for one render.

    Deliberately not a `QObject` and deliberately importing Qt only inside
    `attach`: the parsing and the decision logic are the parts worth testing,
    and requiring a `QApplication` to test them would mean they were not.
    """

    def __init__(self, *, stall_seconds: float = STALL_SECONDS,
                 poll_seconds: float = POLL_SECONDS, clock=time.monotonic):
        self.stall_seconds = stall_seconds
        self.poll_seconds = poll_seconds
        self._clock = clock
        self._pid = 0
        self._progress = -1
        self._cpu: float | None = None
        #: False once a poll has failed to read CPU time. Reported, because a
        #: stall found without this signal is a weaker claim than one found
        #: with it, and the message has to be able to say which it was.
        self.observable = False
        self._last_movement = clock()
        self._phase = "loading"
        self._timer = None
        self._page = None
        self._on_stop = None
        self.stopped_because: Exception | None = None

    # ------------------------------------------------------------- phases
    def set_phase(self, phase: str) -> None:
        """Entering a phase is itself progress: something happened."""
        self._phase = phase
        self._last_movement = self._clock()

    def note_progress(self, value: int) -> None:
        if value != self._progress:
            self._progress = value
            self._last_movement = self._clock()

    # -------------------------------------------------------------- poll
    def poll(self) -> Exception | None:
        """One check. Returns the reason to stop, or None to keep going."""
        cpu = cpu_seconds(self._pid)
        if cpu is None:
            self.observable = False
        else:
            self.observable = True
            if self._cpu is None or cpu > self._cpu:
                self._cpu = cpu
                self._last_movement = self._clock()
        idle = self._clock() - self._last_movement
        if idle < self.stall_seconds:
            return None
        return Stalled(self.stall_message(idle))

    def stall_message(self, idle: float) -> str:
        watched = ("no output and no CPU time from the render process"
                   if self.observable
                   else "no output, and the render process could not be "
                        "watched for CPU time")
        return (f"the report stalled while {self._phase}: {watched} "
                f"for {idle:.0f}s")

    # -------------------------------------------------------------- Qt
    def attach(self, page, on_stop) -> None:
        """Start watching `page`, calling `on_stop(reason)` when it should end.

        `on_stop` is called at most once; the watch stops itself first, so a
        handler that tears the page down cannot be re-entered by a later tick.
        """
        from PySide6.QtCore import QTimer

        self._page = page
        self._on_stop = on_stop
        self._pid = self._read_pid(page)
        self._cpu = cpu_seconds(self._pid)
        self.observable = self._cpu is not None
        self._last_movement = self._clock()

        try:
            page.loadProgress.connect(self.note_progress)
        except (AttributeError, RuntimeError):
            pass
        try:
            page.renderProcessTerminated.connect(self._on_render_gone)
        except (AttributeError, RuntimeError):
            pass

        self._timer = QTimer()
        self._timer.setInterval(int(self.poll_seconds * 1000))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _read_pid(self, page) -> int:
        # The pid only exists once the render process is up, which for a
        # fresh page is after the first load starts. Zero here is normal and
        # is retried on every poll rather than treated as unobservable.
        try:
            return int(page.renderProcessPid() or 0)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return 0

    def _tick(self) -> None:
        if self._pid <= 0 and self._page is not None:
            self._pid = self._read_pid(self._page)
        reason = self.poll()
        if reason is not None:
            self._stop_with(reason)

    def _on_render_gone(self, status, exit_code) -> None:
        kind = getattr(status, "name", str(status))
        self._stop_with(RenderProcessGone(
            f"the render process ended while {self._phase} "
            f"({kind}, exit code {exit_code})"))

    def _stop_with(self, reason: Exception) -> None:
        if self.stopped_because is not None:
            return
        self.stopped_because = reason
        self.detach()
        if self._on_stop is not None:
            self._on_stop(reason)

    def detach(self) -> None:
        timer, self._timer = self._timer, None
        if timer is not None:
            timer.stop()
            try:
                timer.timeout.disconnect(self._tick)
            except (RuntimeError, TypeError):
                pass
        page, self._page = self._page, None
        if page is None:
            return
        for signal, slot in ((getattr(page, "loadProgress", None),
                              self.note_progress),
                             (getattr(page, "renderProcessTerminated", None),
                              self._on_render_gone)):
            if signal is None:
                continue
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
