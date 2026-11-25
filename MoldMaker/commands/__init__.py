"""Command registry. Add new command modules to `commands`."""
from .create_mold import entry as create_mold
from .export_mold import entry as export_mold

commands = [create_mold, export_mold]


def start() -> None:
    for command in commands:
        command.start()


def stop() -> None:
    for command in reversed(commands):
        command.stop()
