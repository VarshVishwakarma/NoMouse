"""NoMouse launcher. Equivalent to ``python -m nomouse``."""
from nomouse.app import run

if __name__ == "__main__":
    raise SystemExit(run())
