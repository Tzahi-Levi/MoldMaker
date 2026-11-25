"""Logging and error reporting helpers (Fusion-side; may import adsk)."""
import traceback

import adsk.core

from ... import config


def log(message: str, level: int = adsk.core.LogLevels.InfoLogLevel, force_console: bool = False) -> None:
    """Write to Fusion's log file; optionally also to the Text Commands console."""
    try:
        app = adsk.core.Application.get()
        app.log(f"{config.ADDIN_NAME}: {message}", level, adsk.core.LogTypes.FileLogType)
        if force_console or config.DEBUG:
            app.log(f"{config.ADDIN_NAME}: {message}", level, adsk.core.LogTypes.ConsoleLogType)
    except Exception:  # logging must never raise
        pass


def handle_error(name: str, show_message_box: bool = False) -> None:
    """Log the active exception's traceback; optionally show it to the user."""
    log(f"{name}\n{traceback.format_exc()}", adsk.core.LogLevels.ErrorLogLevel)
    if show_message_box:
        try:
            ui = adsk.core.Application.get().userInterface
            ui.messageBox(
                f"{config.ADDIN_NAME}: {name} failed.\n\n{traceback.format_exc()}",
                config.ADDIN_NAME,
            )
        except Exception:
            pass
