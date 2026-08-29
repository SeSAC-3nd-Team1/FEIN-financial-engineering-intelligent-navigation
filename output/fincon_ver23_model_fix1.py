"""Fixed FINCON portfolio model with portfolio-level cash-buffer enforcement."""

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path


_path = Path(__file__).with_name("fincon_ver23_model.py")
_spec = importlib.util.spec_from_file_location("fincon_ver23_model_base", _path)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load base model: {_path}")
_base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _base
_spec.loader.exec_module(_base)

PositionInput = _base.PositionInput
PlannedOrder = _base.PlannedOrder
ModelPlan = _base.ModelPlan
MODEL_VERSION = "fincon-ver23-v1-fix1"


class FinConVer23Model(_base.FinConVer23Model):
    """Preserve the base algorithm while enforcing cash at portfolio level."""

    def plan(self, **kwargs):
        cash_buffer = Decimal(kwargs["cash_buffer"])
        investable = Decimal("1") - cash_buffer
        targets = {key: Decimal(value) for key, value in kwargs["target_weights"].items()}
        total = sum(targets.values(), Decimal("0"))
        if total > investable and total > 0:
            scale = investable / total
            targets = {key: value * scale for key, value in targets.items()}
        kwargs["target_weights"] = targets
        return super().plan(**kwargs)
