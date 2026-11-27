"""Allow ``python -m nomouse`` as an alternative to ``python main.py``."""
from nomouse.app import run

if __name__ == "__main__":
    raise SystemExit(run())
