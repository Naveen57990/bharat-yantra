from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"

# Vercel's function filesystem is read-only except for /tmp. These files are
# short-lived demo runs; durable records require an external database or blob.
RUNS_ROOT = (
    Path("/tmp") / "bharat-yantra" / "runs"
    if os.getenv("VERCEL")
    else DATA_ROOT / "runs"
)
