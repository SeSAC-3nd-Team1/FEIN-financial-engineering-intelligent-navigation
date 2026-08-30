"""Load the model artifact owned by the repository output directory."""

import importlib.util
import os
from pathlib import Path
import sys


def _model_path() -> Path:
    configured = os.getenv("FINCON_VER23_MODEL_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "output" / "fincon_ver23_model.py"


def load_model_module():
    path = _model_path()
    if not path.is_file():
        raise RuntimeError(f"FINCON ver2.3 model artifact is unavailable: {path}")
    spec = importlib.util.spec_from_file_location("fincon_ver23_model", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load FINCON ver2.3 model artifact: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
