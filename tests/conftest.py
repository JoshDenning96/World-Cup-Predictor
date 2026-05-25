import sys
from pathlib import Path

# Ensure the project's `src` directory is importable when running pytest
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
