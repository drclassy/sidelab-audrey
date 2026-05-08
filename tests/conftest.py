# Architected and built by classy+.
import sys
from pathlib import Path

sys.pycache_prefix = str(Path(__file__).parent.parent / ".cache" / "pycache")
