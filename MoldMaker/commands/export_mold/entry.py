"""Export Mold command: write every body below a selected mold component as STL files.

Filenames are "<body>_<part>.stl" (the bodies are already named that way).
"""
import adsk.core
import adsk.fusion

from ... import config
from ...fusion import adapter as fusion_adapter
from ...lib import fusion360utils as futil

CMD_ID = "moldmaker_export_mold"
CMD_NAME = "Export Mold STL"
CMD_DESCRIPTION = "Export every part of a mold component as STL."

app = adsk.core.Application.get()
ui = app.userInterface
local_handlers: list = []


def start() -> None:
    existing = ui.commandDefinitions.itemById(CMD_ID)
    if existing:
        existing.deleteMe()
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESCRIPTION)
    futil.add_handler(cmd_def.commandCreated, command_created)
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
    for panel_id in config.PANEL_IDS:
        panel = workspace.toolbarPanels.itemById(panel_id)
        if panel:
            if not panel.controls.itemById(CMD_ID):
                panel.controls.addCommand(cmd_def)
            break


def stop() -> None:
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
    for panel_id in config.PANEL_IDS:
        panel = workspace.toolbarPanels.itemById(panel_id)
        control = panel.controls.itemById(CMD_ID) if panel else None
        if control:
            control.deleteMe()
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    cmd = args.command
    cmd.okButtonText = "Export"
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput("mold", "Mold component", "Select the 'Mold - ...' component")
    sel.addSelectionFilter("Occurrences")
    sel.setSelectionLimits(1, 1)
    dd = inputs.addDropDownCommandInput("mesh", "Mesh refinement", adsk.core.DropDownStyles.TextListDropDownStyle)
    for label in ("Low", "Medium", "High"):
        dd.listItems.add(label, label == "Medium")
    inputs.addBoolValueInput("step", "Also export STEP", True, "", False)
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, lambda a: local_handlers.clear(), local_handlers=local_handlers)


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    inputs = args.command.commandInputs
    occ = adsk.fusion.Occurrence.cast(inputs.itemById("mold").selection(0).entity)
    dlg = ui.createFolderDialog()
    dlg.title = "Folder for exported files"
    if dlg.showDialog() != adsk.core.DialogResults.DialogOK:
        return
    design = adsk.fusion.Design.cast(app.activeProduct)
    files = fusion_adapter.export_occurrence_tree(
        design, occ, dlg.folder, inputs.itemById("mesh").selectedItem.name.lower(), inputs.itemById("step").value)
    ui.messageBox(f"Exported {len(files)} file(s) to\n{dlg.folder}", CMD_NAME)
