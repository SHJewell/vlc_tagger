"""
Instance - Numbers each running copy of the app (#1, #2, ...) so several can
run side by side with their own log file and a label in their window titles.

No project imports allowed in this file (it runs before logging is set up).
"""
import os
import tempfile

from PyQt5.QtCore import QLockFile

MAX_INSTANCES = 99

_number = 1
_lock = None    # held for the life of the process; released by the OS on exit


def claim() -> int:
    """Claim the lowest free instance number. Call once, at startup.

    Each number is a lock file in the temp folder. A lock left behind by a
    crashed instance is detected (its process is gone) and reused.
    """
    global _number, _lock
    lock_dir = os.path.join(tempfile.gettempdir(), 'vlc_tagger_instances')
    os.makedirs(lock_dir, exist_ok=True)

    for n in range(1, MAX_INSTANCES + 1):
        lock = QLockFile(os.path.join(lock_dir, f'instance_{n}.lock'))
        # 0 = only treat a lock as stale when its process is gone, never by
        # age (the default would let a long-running instance lose its number)
        lock.setStaleLockTime(0)
        if lock.tryLock(0):
            _number, _lock = n, lock
            return n

    _number = MAX_INSTANCES + 1     # all taken: run anyway, unnumbered lock
    return _number


def number() -> int:
    return _number


def title_suffix() -> str:
    """' #2', ' #3', ... for window titles; empty for the first instance"""
    return '' if _number == 1 else f' #{_number}'


def log_filename() -> str:
    """vlc_tagger.log for the first instance, vlc_tagger_2.log etc. after"""
    return 'vlc_tagger.log' if _number == 1 else f'vlc_tagger_{_number}.log'
