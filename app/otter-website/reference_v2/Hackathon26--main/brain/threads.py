"""Run blocking work on daemon threads.

concurrent.futures' worker threads are joined at interpreter exit, so a Gemini
call still in flight when the user pressed `q` kept the process alive until
the HTTP request finished (and Ctrl+C then printed a threading traceback).
Daemon threads are simply abandoned at exit, which is what we want for a
request whose answer nobody will read.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future
from typing import Any, Callable


def run_in_daemon(fn: Callable[..., Any], *args: Any, name: str = "worker", **kwargs: Any) -> Future:
    """Start `fn(*args, **kwargs)` on a daemon thread; the Future carries its result."""
    fut: Future = Future()

    def runner() -> None:
        if not fut.set_running_or_notify_cancel():
            return
        try:
            fut.set_result(fn(*args, **kwargs))
        except BaseException as e:  # deliver everything to the waiter, including KeyboardInterrupt
            fut.set_exception(e)

    threading.Thread(target=runner, name=name, daemon=True).start()
    return fut
