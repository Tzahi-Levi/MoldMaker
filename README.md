# MoldMaker — mold generator add-in for Autodesk Fusion

[![Tests](https://github.com/Tzahi-Levi/MoldMaker/actions/workflows/tests.yml/badge.svg)](https://github.com/Tzahi-Levi/MoldMaker/actions/workflows/tests.yml)

MoldMaker builds casting and molding molds around a solid body you select. You choose the
**casting material** (silicone, resin, plaster, injection plastic, slip, …) and the **mold type**; the
add-in fills in sensible defaults (wall, draft, shrinkage, sprue, vents…) from a preset library, warns
about incompatible combinations, and generates the mold parts as 3D-printable bodies.

- Pure Python, standard library only, no pip installs.
- Never touches your original body: it works on copies.
- One **Ctrl+Z** undoes the whole mold. In parametric designs the steps are grouped in the timeline
  as `MoldMaker - <mold type>`.

> Status: all five build phases are written and unit-tested (158 tests), but the Fusion-specific
> parts have not all been verified in Fusion yet. See [docs/MANUAL_TEST.md](docs/MANUAL_TEST.md) for the
> checklists, and please report any error text you see.

---------------------------------------------------------------------------------------------------

## 1. Install

1. Copy the whole `MoldMaker` folder (the one containing `MoldMaker.py` and `MoldMaker.manifest`) to
   Fusion's add-ins folder:
   `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   (macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`).
   Alternatively, in Fusion choose **Utilities → Add-Ins → Scripts and Add-Ins → Add-Ins tab → green "+"**
   and pick the folder.
2. In the Add-Ins tab select **MoldMaker** and press **Run**. Tick **Run on Startup** to load it
   automatically.
3. Two commands appear in the **Solid** workspace: **Create** panel → *MoldMaker: Create Mold* and
   *MoldMaker: Export Mold STL* (also under Utilities → Add-Ins).

To reload after editing the code: select MoldMaker → **Stop**, then **Run** again. The add-in purges its
own modules on stop, so edits are picked up.

## 2. Quick start

1. Open a **Design** document (see *Limitations* for Part Design) containing the solid body to mold.
2. Run **MoldMaker: Create Mold**.
3. Select the **Target body**.
4. Pick the **Casting material** — the **Mold type** list is filtered to what suits that material, and the
   **Mold material** list shows recommended materials first.
5. Read the **Compatibility** box. Errors block the **Create** button; warnings do not.
6. Adjust anything you like (defaults come from the presets), watch the **preview** in the viewport,
   and press **Create**.
7. A message summarises the plan (block size, parting height, number of keys/vents/bolts, expected
   volumes) plus any warnings found while building.

The result is a component **`Mold - <body name>`** with one sub-component per part (for example
*Lower half* and *Upper half*).

## 3. Mold types

| Mold type | What you get | Typical use |
|-----------|--------------|-------------|
| **Silicone mold box** | A printed open box (walls + floor) sized for the part; reports silicone volume and weight. Optional two-part variant with a parting bed. | Pour silicone around a master to make a flexible mold |
| **Two-part rigid mold** | Block minus the part, split at a parting plane into *Lower half* and *Upper half*, with keys, sprue, vents and bolt holes | Resin, wax, plaster, soap… cast into a printed rigid mold |
| **Open block** | One block with the cavity open at the top face (the part needs a flat back); runs a draft/undercut check | Flat-backed parts: soap, concrete, chocolate |
| **Brush-on mother mold** | *Silicone skin* around the master, plus a two-part printed *Mother* shell with flange, keys and bolts | Large parts, saves silicone |
| **Slip-cast case** | Shrink-enlarged *Master with well*, a *Plaster mold (reference)*, and printed *Lower/Upper case* shells; reports plaster and water grams (10:7) | Ceramic slip casting |
| **Vacuum buck** | A hollow male *Buck* on a base flange with 0.8 mm vent holes at recesses | Vacuum forming |
| **Core/cavity** | *Core insert* + *Cavity insert* with leader-pin holes, counterbored bolts, sprue/runner/gate, 0.05 mm parting-line vent slots, draft check | Injection or compression molding in aluminum or high-temp SLA |

## 4. Casting and mold materials

Casting materials (21): silicone for molds (platinum/tin), silicone casting (platinum/tin), polyurethane,
epoxy, polyester, plaster, concrete, wax, low-melt pewter, chocolate/food, soap, injection ABS/PP/HDPE/PLA,
plastisol, vacuum forming, slip casting, compression.

Mold materials (9): PLA, PETG, ABS/ASA, PP, SLA standard, SLA high-temp, high-temp silicone, aluminum, plaster.

The compatibility check looks at the casting temperature versus the mold material's heat limit, forbidden
pairs (for example PLA with hot casting material), and release/cure notes. For indirect molds (silicone box,
brush-on, slip case) the printed part only holds the silicone/plaster, so temperature problems are
shown as warnings instead of errors.

All numbers live in `MoldMaker/presets/materials.json`. Values marked with a dagger in the notes are estimates:
edit them to match your material datasheets.

## 5. The dialog, field by field

Fields appear only when they apply to the selected mold type.

**Top**
- *Target body* — the solid (BRep) body to mold. Mesh bodies are not supported: run **Convert Mesh** first.
- *Casting material / Mold type / Mold material* — see above.
- *Show preview* — draws the block, parting plane, keys and sprue/vent tools in the viewport. It is a quick
  approximation; the real result is computed on Create.

**Block**
- *Wall thickness*, *Floor/top thickness* — material around the cavity.
- *Draft angle* — checked against the part (and applied in Core/cavity if you enable it).
- *Pull direction* — ±X, ±Y or ±Z: the direction the mold opens/the part is pulled.
- *Parting* — **Auto** picks the height that gives the best silhouette coverage; **Manual** lets you offset
  it from mid-height with *Parting offset*.
- *Two-part silicone mold* — silicone box only.

**Shrinkage** — uniform percent, or tick *Non-uniform* to enter X/Y/Z separately (world axes). The cavity is the
part scaled up by this amount.

**Shell / skin / plaster** (only the fields for your mold type)
- Brush-on: *skin thickness*, *shell thickness*, *flange width*.
- Slip case: *plaster thickness*, *printed case wall*, *slip well height*, *slip well diameter* (0 = auto).
- Vacuum buck: *shell thickness*, *flange width*, *vent hole diameter*.
- Core/cavity: *leader pin diameter*, *insert size step* (plan size rounded up to a multiple, 0 = off),
  *gate diameter*, *vent slot depth/width*, plus two experimental options: **Parting from Silhouette Split**
  and **Apply draft to cavity walls**.

**Registration** — key type (sphere / cone / none), count (2 or 4), diameter, clearance. Keys are placed near
the corners and kept clear of the cavity.

**Pour** — sprue on top or at the edge, diameter, funnel diameter; automatic vents at air-trap high points.

**Clamping** — bolts with counterbore on top and a hex nut trap underneath (M3/M4/M5…), count.

**Output** — lay the upper half flat next to the lower half, create `MM_*` user parameters, optionally
export one STL per part when you press Create (choose a folder first).

## 6. Typical workflows

**Two-part rigid mold for resin**
1. Casting: *Polyurethane resin*, mold type *Two-part rigid mold*, material *PETG* or *SLA*.
2. Leave parting on Auto; check the message for "undercuts" warnings. If it warns, try another pull direction
   or set the parting height manually.
3. Create, then print *Lower half* and *Upper half*. Keys align the halves, bolts clamp them, pour through the
   sprue, and vents let air escape.

**Silicone mold of a master**
1. Casting: *Silicone for molds*, mold type *Silicone mold box*.
2. The result message gives the silicone volume and weight to mix. Print the box, fix the master inside, pour.

**Injection/compression insert pair**
1. Casting: *Injection – ABS*, mold type *Core/cavity*, material *aluminum* (printed PLA/PETG are rejected).
2. Set a draft angle of 1–2° (a zero draft warns).
3. Choose *Edge* sprue to get a runner and a gate; zoom in afterward and verify the gate opens into the cavity.
4. Print or machine the *Core insert* and *Cavity insert*; fit steel dowel pins in the leader-pin holes.

## 7. Exporting STL files

- Tick *Export STL per part on OK* in the Output group, or run **MoldMaker: Export Mold STL** any time: select a
  `Mold - …` occurrence, choose mesh refinement and a folder. Every body inside is written as an STL
  (optional STEP too).

## 8. Understanding the warnings

| Message | What to do |
|---------|-----------|
| Cavity volume check: removed X but expected Y | The master may have voids, be non-manifold, or poke out of the block. Repair the body or increase the wall |
| Best planar parting plane only spans N % of the silhouette | The part has undercuts for this pull direction: change direction or the parting height |
| N % of the part surface is an undercut / has less than the requested draft | Add draft to the part, change direction, or accept it for soft molds |
| Could not place … key / bolt | Increase wall thickness or reduce key/bolt size |
| Offset … failed; using an approximate scaled shape | Fusion could not offset the shape; thickness is exact only along the bounding-box axes |
| N separate lumps | Floating islands in a result: check the master for thin features |
| Silhouette Split could not find a loop | The planar parting height from the section scan was used instead |

## 9. Limitations (read these)

- **Part Design documents** can hold only one component. MoldMaker then adds the parts as separate bodies named
  `Mold - <body> - <part>`, and offsets use the approximate scaled shape. Use a normal **Design** document for
  the full result.
- **Mesh bodies** are not supported (convert them to solids first).
- **Parting is a flat plane.** The Silhouette option only chooses its height; it does not build a curved parting
  surface.
- The mold is built from temporary bodies, so changing a user parameter afterward does **not** regenerate it.
  Re-run the command instead. The `MM_*` parameters are for documentation.
- Splits use boolean half-space cuts rather than the Split Body feature. Key chamfers are not applied.
- Slip case: no keys (natches are formed by hand in the clay bed); the printed case is open on the parting side.
- Vacuum buck: male bucks only.
- Draft application in Core/cavity is best effort: if Fusion refuses, you get a warning. Adding draft to the master
  before running MoldMaker is more reliable.
- Very large or complex bodies can make the preview and sampling slow; turn the preview off in that case.

## 10. Troubleshooting

- **Error dialog with a traceback** — copy the whole text. Details are also written to the Fusion text-command log
  (View → Show Text Commands) with `MoldMaker` in the lines.
- **Nothing happens on Create** — the Create button is disabled until a body is selected, the compatibility check has
  no errors, and all values are valid (for example, an export folder when STL export is ticked).
- **Stray "MoldMaker scratch" component** — the add-in creates and deletes it during offsets; if you find one after
  an error, delete it, and tell me what happened.
- **Add-in not listed** — the folder must be named `MoldMaker` and contain `MoldMaker.py` and `MoldMaker.manifest`.

## 11. For developers

```
MoldMaker/
  MoldMaker.py, MoldMaker.manifest, config.py
  commands/        create_mold (dialog), export_mold
  core/            pure logic: units, model, presets, compat, layout, parting, draft, ui_rules, userparams
  strategies/      one planner+builder per mold type (pure; talks to Fusion through an adapter)
  fusion/          adapter.py (all adsk geometry calls), preview.py (custom graphics)
  presets/         materials.json
  lib/fusion360utils/   event handler helpers
tests/             unittest suite (no Fusion needed)
docs/MANUAL_TEST.md    what to check in Fusion, per phase
```

- Units: Fusion's internal unit is cm; presets and plans use mm/degrees. Conversion happens only in
  `core/units.py` (and the adapter's coordinate helpers).
- `core/` and `strategies/` must not `import adsk` (enforced by a test), so planning logic is testable without Fusion.
- Run the tests from the repository root: `python -m unittest discover -s tests -t .`
- To add a mold type: write `strategies/<name>.py` (a `plan()` that returns a `MoldPlan` and a `build(plan, adapter)`),
  register it in `strategies/__init__.py`, add UI visibility in `core/ui_rules.py`, and add the type to the
  `allowed_mold_types` of the materials in `presets/materials.json`.

## License

MIT, see [LICENSE](LICENSE).
