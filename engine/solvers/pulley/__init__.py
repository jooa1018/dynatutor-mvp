from .atwood import AtwoodPulleySolver
from .table_hanging import TableHangingPulleySolver
from .incline_hanging import InclineHangingPulleySolver
from .massive_pulley import MassivePulleyAtwoodSolver

# Backward compatible alias used by older imports/tests.
PulleyTableHangingSolver = TableHangingPulleySolver

__all__ = [
    "AtwoodPulleySolver",
    "TableHangingPulleySolver",
    "PulleyTableHangingSolver",
    "InclineHangingPulleySolver",
    "MassivePulleyAtwoodSolver",
]
