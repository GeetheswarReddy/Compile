"""Package runtime sources only; exclude local credentials, tools and frontend."""
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1])
for name in ("backend", "scripts", "seed", "infra"):
    shutil.copytree(root / name, target / name, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
