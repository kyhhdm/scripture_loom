"""Run async coroutines safely from sync code under a gevent Celery worker.

Why this exists
---------------
Several chat models (`LiteLLM`, `Volcengine`) expose sync `batch_llm(...)` that
internally needs to drive an async coroutine (`abatch_llm(...)`). The original
implementation created a fresh asyncio loop per call with
`asyncio.new_event_loop()` + `run_until_complete(...)`.

Under the LLM Celery worker (`-P gevent -c 20`), all greenlets run in a single
OS thread. CPython 3.11 tracks asyncio's "running loop" in C-level
thread-local storage that gevent does **not** monkey-patch. So when one
greenlet is mid-`await` inside its loop, any other greenlet that calls
`run_until_complete` on its own loop immediately raises
``RuntimeError: Cannot run the event loop while another loop is running``.

Fix: keep **one** long-lived asyncio loop and dispatch coroutines to it via
`asyncio.run_coroutine_threadsafe`, instead of spinning up a per-call loop.
That call schedules onto the running loop and returns a
`concurrent.futures.Future` without ever touching the caller's running-loop
TLS, so the "another loop is running" collision can't happen. The submitting
greenlet blocks on that Future — gevent-patched `threading.Event` makes the
wait greenlet-friendly.

Note on the loop thread: under the gevent pool the loop runs on a greenlet, not
a real OS thread — ``get_original("threading", "Thread")`` returns the original
*class* but ``Thread.start()`` still resolves the patched
``_thread.start_new_thread`` at call time (see ``_real_thread_cls``). That is
fine here: asyncio-under-gevent drives gevent's hub-bound patched selectors, so
the loop belongs on the worker's hub thread, and correctness rests on the
single-loop + ``run_coroutine_threadsafe`` pattern above, not on the loop
running off-thread. (Where a real OS thread is genuinely required — surviving a
non-yielding greenlet — see ``mxlens.workers.base._spawn_real_thread``, used by
the lease heartbeat.)
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


def _real_thread_cls():
    """Return the ``Thread`` class used to host the background asyncio loop.

    Off the gevent pool this is the stdlib ``threading.Thread``. Under gevent it
    is ``get_original("threading", "Thread")`` — note that *starting* it still
    yields a greenlet (``Thread.start()`` resolves the patched
    ``_thread.start_new_thread`` at call time), which is intentional and correct
    for this loop; see the module docstring. This helper is NOT a way to get a
    real OS thread — use ``mxlens.workers.base._spawn_real_thread`` for that.
    """
    try:
        from gevent import monkey
        if monkey.is_module_patched("threading"):
            return monkey.get_original("threading", "Thread")
    except ImportError:
        pass
    return threading.Thread


_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_thread = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    if _loop is not None and _loop.is_running():
        return _loop

    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop

        loop = asyncio.new_event_loop()
        ready = threading.Event()

        def _run():
            asyncio.set_event_loop(loop)
            ready.set()
            try:
                loop.run_forever()
            finally:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()

        thread_cls = _real_thread_cls()
        t = thread_cls(target=_run, name="mxapi-aio-runner", daemon=True)
        t.start()
        ready.wait()

        _loop = loop
        _thread = t
        return loop


def run_coro(coro: Awaitable[T]) -> T:
    """Run ``coro`` on the shared background asyncio loop and return its result.

    Safe to call from sync code on any thread/greenlet. Exceptions raised
    inside the coroutine propagate to the caller.

    If the *waiting* thread/greenlet is interrupted (e.g. the soft-time-limit
    watchdog injects ``SoftTimeLimitExceeded`` into the greenlet parked in
    ``fut.result()``), cancel the in-flight coroutine before re-raising. The
    ``concurrent.futures.Future`` returned by ``run_coroutine_threadsafe`` is
    chained to the underlying asyncio task, so ``fut.cancel()`` requests
    cancellation on the loop thread. Without this the coroutine would run on as
    an orphan after Celery releases the task slot and lease — still issuing LLM
    requests and mutating model state (mxlens issue #31 review).
    """
    loop = _ensure_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return fut.result()
    except BaseException:
        fut.cancel()
        raise


def start() -> None:
    """Eagerly start the background loop thread.

    Optional — `run_coro` lazily starts it on first use. Call from a Celery
    ``worker_process_init`` hook to avoid first-task latency.
    """
    _ensure_loop()
