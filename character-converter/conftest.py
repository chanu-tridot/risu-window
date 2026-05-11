"""Make `md_to_json` importable when pytest is invoked from the repo root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
