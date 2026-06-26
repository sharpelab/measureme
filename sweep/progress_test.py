import time

from sweep.progress import interruptible_sleep


def test_interruptible_sleep_zero_returns_immediately() -> None:
    start = time.monotonic()
    interruptible_sleep(0.0)
    assert time.monotonic() - start < 0.5


def test_interruptible_sleep_waits_roughly_total() -> None:
    start = time.monotonic()
    interruptible_sleep(0.05, chunk=0.01, show_progress=False)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05
    assert elapsed < 1.0


def test_interruptible_sleep_breaks_on_should_stop() -> None:
    start = time.monotonic()
    interruptible_sleep(10.0, chunk=0.01, show_progress=False, should_stop=lambda: True)
    assert time.monotonic() - start < 0.5
