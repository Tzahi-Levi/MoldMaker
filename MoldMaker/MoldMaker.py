"""MoldMaker add-in entry point (Fusion calls run()/stop()).

Module purging: this file purges every previously imported MoldMaker module
*before* importing its own submodules, so each Run picks up edited code
instead of stale entries in sys.modules. stop() purges again after cleanup.
"""
import sys

_PKG = (__package__ or __name__).split(".")[0]


def _purge_modules(include_self: bool = False) -> None:
    """Remove MoldMaker submodules (and optionally the package itself)."""
    for name in list(sys.modules):
        if name.startswith(_PKG + "."):
            del sys.modules[name]
    if include_self:
        sys.modules.pop(_PKG, None)


# Executed on every fresh import of this file == every "Run" of the add-in.
_purge_modules()

from .lib import fusion360utils as futil  # noqa: E402
from . import commands  # noqa: E402


def run(context):
    try:
        commands.start()
    except Exception:
        futil.handle_error("run", show_message_box=True)


def stop(context):
    try:
        futil.clear_handlers()
        commands.stop()
    except Exception:
        futil.handle_error("stop", show_message_box=True)
    finally:
        _purge_modules(include_self=True)
