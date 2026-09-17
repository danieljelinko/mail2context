"What `just guard-status` reads: the mail-guard level file, if the guard is installed at all."
from pathlib import Path

__all__ = ['LEVEL_PATH', 'describe_guard']

LEVEL_PATH = Path('/etc/mail-guard/level')   # root-owned, world-readable; written only by `sudo mail-guard N`


def describe_guard(level_path: Path = LEVEL_PATH) -> str:
    "One line: the guard's level as its file states it, or that there is no guard."
    try: return f'guard level {level_path.read_text().strip()}'
    except OSError: return 'guard not installed — direct mode'
