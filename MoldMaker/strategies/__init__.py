"""Strategy registry. Mold types without an entry here are not implemented yet."""
from typing import Dict, Optional

from .base import MoldStrategy
from .brush_on_mother import BrushOnMotherStrategy
from .core_cavity import CoreCavityStrategy
from .open_block import OpenBlockStrategy
from .silicone_box import SiliconeBoxStrategy
from .slip_cast_case import SlipCastCaseStrategy
from .two_part import TwoPartStrategy
from .vacuum_buck import VacuumBuckStrategy

_STRATEGIES: Dict[str, MoldStrategy] = {
    s.mold_type: s for s in (SiliconeBoxStrategy(), TwoPartStrategy(), OpenBlockStrategy(), BrushOnMotherStrategy(),
                             SlipCastCaseStrategy(), VacuumBuckStrategy(), CoreCavityStrategy())
}


def get_strategy(mold_type: str) -> Optional[MoldStrategy]:
    return _STRATEGIES.get(mold_type)


def implemented_types():
    return tuple(_STRATEGIES)
