"""Strategy base class. plan() is pure; build() talks to Fusion only through the adapter."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Tuple

from ..core import parting
from ..core.model import BodyInfo, MoldParams, MoldPlan, PullFrame, frame_for


class MoldStrategy(ABC):
    mold_type: str = ""
    builds: bool = False  # True once build() creates geometry for this mold type

    @abstractmethod
    def plan(self, params: MoldParams, body: BodyInfo) -> MoldPlan:
        """Compute everything about the mold from numbers only (no adsk)."""

    def build(self, plan: MoldPlan, adapter: Any) -> None:
        """Create geometry through `adapter` (fusion/adapter.py) and call adapter.commit()."""
        raise NotImplementedError(f"Geometry for '{self.mold_type}' is not implemented yet.")

    # ---- shared helpers -------------------------------------------------
    @staticmethod
    def prepare(params: MoldParams, body: BodyInfo) -> Tuple[PullFrame, BodyInfo, float]:
        """Return (frame, shrink-scaled body info, expected cavity volume in mm3)."""
        problems = params.validate()
        if problems:
            raise ValueError("Invalid mold parameters:\n  - " + "\n  - ".join(problems))
        frame = frame_for(params.pull_dir)
        fu, fv, fw = frame.local_factors(params.shrink_factors_world())
        info = parting.complete_info(body).scaled(fu, fv, fw)
        return frame, info, body.volume_mm3 * fu * fv * fw
