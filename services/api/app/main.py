"""Compatibility entry point. The standalone API has no FastAPI runtime dependency."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standalone import main


if __name__ == "__main__":
    main()
