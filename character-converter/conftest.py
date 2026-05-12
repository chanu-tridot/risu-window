"""Make `merger`, `assembler`, `main` importable from tests/ regardless of cwd."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
