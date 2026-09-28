"""Live progress for the BMA cron, on stdout.

WHY `print` AND NOT `logging`
    Two reasons, both learned the hard way on this job.

    * A Lambda that is about to hit its timeout tells you nothing through the
      logger if the handler never returns: `logging` output is emitted, but a
      run that is *stuck* is exactly the run you need to read, and the useful
      question is "which step was it on at minute 9". A line printed as each
      step starts answers that; a summary logged at the end never arrives.
    * stdout is block-buffered when it is not a terminal — which is every
      Lambda, every `nohup`, every CI job. Without `flush=True` the whole run's
      output appears at once, at the end, which is the one moment it is no
      longer needed. Every print here flushes.

    CloudWatch captures stdout from a Lambda exactly as it captures the logger,
    so nothing is lost by choosing the one that shows up while the run is still
    going.

WHAT A LINE LOOKS LIKE
    [BMA   12.4s] sheets.read          ranges=11 cells=93k
    [BMA  215.9s] sheets.read          done in 203.5s
"""

import time

#: Set once per run so every line shares an origin, which makes the gaps
#: between lines readable as durations without any arithmetic.
_START = None


def reset(label='BMA'):
    """Begin a run. Returns the start time."""
    global _START
    _START = time.time()
    print(f'[{label}] ---- start ----', flush=True)
    return _START


def elapsed():
    return 0.0 if _START is None else time.time() - _START


def step(stage, detail='', label='BMA'):
    """One progress line. Never raises — progress must not break the job."""
    try:
        print(f'[{label} {elapsed():7.1f}s] {stage:<22} {detail}', flush=True)
    except Exception:
        pass


class timed:
    """Context manager printing a line on entry and on exit, with a duration.

    Used around the calls that dominate this job — a single `values.get` on
    this workbook has been measured at 203 s, because the `Master-*` tabs hold
    ~450,000 formula cells that Sheets recalculates before serving a read that
    follows a write. Knowing which call is sitting there is the whole point.
    """

    def __init__(self, stage, detail='', label='BMA'):
        self.stage, self.detail, self.label = stage, detail, label

    def __enter__(self):
        self.t0 = time.time()
        step(self.stage, self.detail, self.label)
        return self

    def __exit__(self, exc_type, exc, tb):
        took = time.time() - self.t0
        if exc_type is None:
            step(self.stage, f'done in {took:.1f}s', self.label)
        else:
            step(self.stage, f'FAILED after {took:.1f}s: {exc}', self.label)
        return False


def cells(ranges):
    """Rough cell count for a list of (range, values), for the progress line."""
    n = 0
    for _rng, values in ranges:
        for row in values:
            n += len(row)
    return n


def human(n):
    return f'{n / 1000:.0f}k' if n >= 1000 else str(n)
