"""Load the production-packaged FINCON v2.3 fix1 model artifact."""

import importlib.util
import os
from pathlib import Path
import sys


def model_path_fix1() -> Path:
    configured = os.getenv("FINCON_VER23_MODEL_PATH", "").strip()
    if configured:
        return Path(configured)
    repository_artifact = Path(__file__).resolve().parents[3] / "output" / "fincon_ver23_model_fix1.py"
    if repository_artifact.is_file():
        return repository_artifact
    return Path("/models/fincon_ver23_model_fix1.py")


def load_model_module_fix1():
    path = model_path_fix1()
    if not path.is_file():
        raise RuntimeError(f"FINCON ver2.3 fix1 model artifact is unavailable: {path}")
    spec = importlib.util.spec_from_file_location("fincon_ver23_model_fix1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load FINCON ver2.3 fix1 model artifact: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
