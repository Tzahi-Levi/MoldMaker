"""Event-handler helper.

Fusion drops a handler as soon as Python garbage-collects it, so every handler
is stored in a list. Global `handlers` live for the add-in lifetime; pass a
`local_handlers` list for handlers that only live as long as one command.
"""
import sys
from typing import Callable, List, Optional

import adsk.core

from .general_utils import handle_error

handlers: List[object] = []


def add_handler(
    event: adsk.core.Event,
    callback: Callable,
    *,
    name: Optional[str] = None,
    local_handlers: Optional[list] = None,
):
    """Attach `callback` to `event`, wrapped in try/except, and keep it referenced."""
    module = sys.modules[event.__module__]
    handler_type = module.__dict__[event.add.__annotations__["handler"]]
    handler = _define_handler(handler_type, callback, name)()
    (local_handlers if local_handlers is not None else handlers).append(handler)
    event.add(handler)
    return handler


def clear_handlers() -> None:
    global handlers
    handlers = []


def _define_handler(handler_type, callback: Callable, name: Optional[str]):
    handler_name = name or handler_type.__name__

    class Handler(handler_type):
        def __init__(self):
            super().__init__()

        def notify(self, args):
            try:
                callback(args)
            except Exception:
                handle_error(handler_name, show_message_box=True)

    return Handler
