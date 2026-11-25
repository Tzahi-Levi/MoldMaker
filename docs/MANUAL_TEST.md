# MoldMaker - manual tests in Fusion

Automated tests (no Fusion needed), from the repo root:

    python -m unittest discover -s tests -t .

## Install

1. Fusion > Utilities > Add-Ins > **Add-Ins** tab > green **+** > choose the `MoldMaker` folder (the one containing `MoldMaker.py`).
2. Select MoldMaker > **Run** (optionally tick *Run on Startup*).
3. The **Create Mold** button appears in SOLID > CREATE (or UTILITIES > ADD-INS if that panel is unavailable).
4. After editing code: **Stop**, then **Run** again (modules are purged on both).

Debug output: Fusion's *Text Commands* window (Utilities > Add-Ins > bug icon), or View > Show Text Commands.

## Phase 1 checklist (dialog + planning only, no geometry)

Test bodies: (1) 30 mm sphere, (2) box with a fillet, (3) L-bracket, (4) an imported organic STEP.

| # | Step | Expect |
|---|------|--------|
| 1 | Run the add-in | No error box; button visible; no errors in the text console |
| 2 | Stop, then Run again | No duplicate buttons; no error |
| 3 | Open the dialog with no body selected | OK is disabled |
| 4 | Select a body | OK enables (if compatibility has no errors) |
| 5 | Pick each casting material in turn | *Mold type* lists only that material's allowed types; *Mold material* lists recommended first; wall / draft / shrink / key / sprue / vent / bolt fields reset to the preset |
| 6 | Pewter + open block + PLA | Compatibility box shows a bold ERROR; OK disabled |
| 7 | Pewter + silicone box + PLA | Only a warning (the box is not in contact with the melt) |
| 8 | Polyurethane: switch mold type silicone box <-> two part | Wall changes 10 <-> 4 mm |
| 9 | Open block / vacuum buck | Registration, Pour, Clamping groups hidden |
| 10 | Silicone box | Tick *Two-part silicone mold*: Registration + Pour appear |
| 11 | Parting = Manual | Offset field enabled; Auto: disabled |
| 12 | Tick *Non-uniform* shrink | Three X/Y/Z fields appear; uniform field disabled |
| 13 | Tick *Export STL* | Folder button enabled; OK stays disabled until a folder is chosen |
| 14 | Press **Create** on each test body for *Two-part*, *Silicone box*, *Open block* | A message box with the plan: block size, parting height (mid-height in Phase 1, no section data yet), key/bolt counts, silicone volume + mass, warnings. **Nothing is added to the design / timeline** |
| 15 | Change *Pull direction* to +X and Create | Block dimensions swap consistently with the body's extents |
| 16 | Break `presets/materials.json` (e.g. delete a comma), open the dialog | A clear "cannot open: Invalid presets ..." message |
| 17 | Edit a preset value (e.g. wax shrink), reopen the dialog | New value is used without restarting the add-in |

Things I could not verify outside Fusion and want you to watch for:
- Fields inside groups are looked up with `inputs.itemById(...)` (expected to find nested children).
- Value inputs with unit `mm` / `deg` show and return values consistently (mm in the UI, internal cm/rad converted in `core/units.py`).
- The dropdown/selection filter strings (`SolidBodies`).

## Phase 2 checklist (silicone box + two-part geometry)

Run each test on: (1) 30 mm sphere, (2) box with a fillet, (3) L-bracket, (4) imported organic STEP.
Use *Cast platinum silicone > Two-part rigid mold* (PLA) and *Polyurethane > Silicone mold box*.
Then repeat once in **Parametric** and once in **Direct** design mode (Design > Capture Design History off).

| # | Check | Expect |
|---|-------|--------|
| 1 | Press Create (two-part, defaults) | Component `Mold - <body>` with children `Lower half`, `Upper half`; each holds one body `<body>_lower` / `<body>_upper`. Your original body is untouched |
| 2 | Parametric: look at the timeline | A single group `MoldMaker - Two-part rigid mold` containing the new items. Direct mode: no timeline, no error |
| 3 | Press Ctrl+Z once | The whole mold disappears (one undo step) |
| 4 | Lay-flat on | Upper half sits beside the lower half, parting faces both facing up, with a gap. Lay-flat off: halves stay stacked in place |
| 5 | Inspect each half (Inspect > Section Analysis, or body Properties) | Single lump; no floating islands. Look at the result message for "lumps" warnings |
| 6 | Show both halves stacked (lay-flat off) | Key bumps on the lower half fit the sockets in the upper half (0.3 mm clearance) |
| 7 | Look into the cavity from the top | Sprue channel and funnel reach the highest point of the cavity; for parts with several peaks, vent holes reach the other high points |
| 8 | Bolts | Through holes along the long edges, counterbore on top, hex nut traps on the bottom; none intersect the cavity |
| 9 | Result message | No "Cavity volume check" warning (removed volume within 2 % of expected). If shrink > 0 the expected volume includes it |
| 10 | Silicone box | One printed open-top box with a locating post under the master; message shows silicone volume and mass |
| 11 | Silicone box, tick *Two-part* | Extra component `Parting bed`: bed body (master embedded to the parting plane, key bumps) plus spout pin body |
| 12 | Output > Export STL, pick a folder, Create | Files `<body>_lower.stl`, `<body>_upper.stl` (or `_box`, `_bed`, ...) written; message lists the count |
| 13 | Run **Export Mold STL** and select the `Mold - ...` component | Same files, plus STEP when ticked |
| 14 | Set shrink 2 % and Create | Cavity is 2 % larger in each direction |
| 15 | Non-uniform shrink | Either works, or a clear error saying non-uniform scale is unsupported (the API may reject it) |
| 16 | Force a failure (e.g. a mesh body) | Error box with an actionable message; no leftover `Mold - ...` component |
| 17 | Body inside a sub-component, and pull -Z / +X | Cavity still lines up with the body; sprue points along the chosen pull direction |

API assumptions worth watching (first time they run in real Fusion):
- `BRepBody.pointContainment` speed (sampling takes a few seconds on complex bodies).
- `TemporaryBRepManager.transform` accepting a scale matrix, and Matrix3D `setCell` layout.
- `OrientedBoundingBox3D` orientation for boxes and hex nut traps.
- Base-feature creation inside a non-active sub-component.
- Timeline grouping of component + base-feature items.
- STL export of bodies below a nested occurrence.

## Phase 3 checklist (open block, preview, user parameters)

| # | Check | Expect |
|---|-------|--------|
| 1 | Open the dialog, select a body | A translucent blue block, an amber parting plane, green key bumps and red sprue/vent tools appear around the body (coarse, approximate) |
| 2 | Change wall / key diameter / pull direction / mold type | The preview updates after each change |
| 3 | Untick *Show preview* | Preview disappears; re-tick brings it back |
| 4 | Press Cancel | Preview graphics are gone, nothing was added to the design |
| 5 | Press Create | Preview vanishes and the real mold is built (preview never replaces it) |
| 6 | Preview with a very complex body | Dialog stays responsive (coarse sampling is cached per body and pull direction) |
| 7 | Open block: use a body with a flat back and pull direction out of that back (e.g. a plaque lying flat, pull +Z) | One component `Block` with a single body `<body>_block`; the cavity is open at the top and flush with the block top |
| 8 | Open block with draft 3 and a body with vertical walls | Result message warns that part of the surface has less than the requested draft |
| 9 | Open block, pull direction into the back / a domed back | Warns about undercuts |
| 10 | Output > *Create user parameters* on | Design > Change Parameters shows `MM_wall`, `MM_floor_top`, `MM_shrink_pct`, `MM_draft` (+ key/sprue/vent ones when used) with matching values and units |
| 11 | Run twice | Second run updates the same `MM_*` values instead of failing |
| 12 | Output > *Create user parameters* off | No `MM_*` parameters are created |
| 13 | Two-part on the L-bracket and the organic STEP | Parting height is auto-chosen at a wide section; a warning appears if undercuts are expected |
| 14 | Manual parting with an offset | Parting plane moves by that offset from mid-height (visible in the preview) |

Fusion API assumptions to watch in this phase:
- Custom graphics: `addBRepBody` plus `CustomGraphicsSolidColorEffect` honouring the alpha value (blocks should look translucent).
- Face normals: BRepFace evaluator normals combined with `isParamReversed` give the outward direction (if the draft warnings look inverted, this is the cause).
- The preview runs on every input change; if it feels slow, tell me the body size.

## Phase 4 checklist (brush-on mother mold, slip-cast case, vacuum buck)

The new **Shell / skin / plaster** group shows only the fields each type uses. Use a body that is solid and a few centimetres across.

| # | Check | Expect |
|---|-------|--------|
| 1 | Silicone for molds > *Brush-on silicone + mother mold*, press Create | Components `Mother lower`, `Mother upper` and `Silicone skin` under `Mold - <body>`. The skin body wraps the master about 4 mm thick |
| 2 | Look at the mother halves | Hollow shell about 4 mm thick around the skin, a flange around the parting plane, key bumps/sockets and bolt holes on the flange (none touching the shell) |
| 3 | Offset fallback | If the result message says *Offset ... failed ... approximate scaled shape*, note which body and send me the text. Thickness is then exact only along the bounding-box axes |
| 4 | Brush-on: skin 1 mm / shell 2 mm | Warnings about thin skin and shell |
| 5 | Slip casting > *Slip-cast plaster case*, shrink 12 % | Components `Lower case`, `Upper case`, `Master with well`, `Plaster mold (reference)` |
| 6 | Master with well | Body is 12 % larger than yours with a cylinder (the slip well) on its highest point, 25 mm tall |
| 7 | Cases | Printed shell 2.4 mm thick around each plaster half, open on the parting side |
| 8 | Result message | Plaster powder and water grams in the ratio 10 : 7 by weight; the plaster volume is measured from the real cut |
| 9 | Slip well diameter 0 / 30 | Auto size / exactly 30 mm; a warning when the well is nearly as wide as the part |
| 10 | Vacuum forming > *Vacuum-forming buck* on a part with a recess | Component `Buck` with base flange, hollow interior (about 2 mm walls) open downward through the flange |
| 11 | Look at the recess | A 0.8 mm vent hole at the bottom of each pit, through the shell into the hollow. Convex or flat parts get none |
| 12 | Buck on a part with vertical walls | Message says part of the surface has less than the requested draft (4.5 deg male) |
| 13 | Buck on a part with a mushroom shape | Message reports undercut faces |
| 14 | Dialog preview for each of the three types | Block/flange outline shows; no keys/sprue for slip and buck |
| 15 | Single Ctrl+Z after each build | Mold, scratch components and timeline items all vanish; no `MoldMaker scratch` component is left behind |

Fusion API assumptions to watch in this phase:
- `OffsetFacesFeatures` on a scratch body, including its sign convention (outward is checked by volume) and the throw-away component being removable.
- Inward offsets of thin or filleted parts often fail in any CAD: expect the fallback warning on organic bodies.
- Timeline grouping after scratch components were created and deleted.

## Phase 5 checklist (core/cavity, silhouette parting, draft application)

Pick *Injection ABS* (or compression) with mold material *aluminum* or *SLA high temp*. The Shell group now holds the core/cavity fields.

| # | Check | Expect |
|---|-------|--------|
| 1 | Injection ABS > *Core/cavity*, Create on a box-like part | Components `Core insert` and `Cavity insert` under `Mold - <body>`. Plan size in u and v is a multiple of 5 mm |
| 2 | Insert size step 0 | The block is exactly part + wall on each side |
| 3 | Leader pins | Round holes (6 mm default) at the corners: snug in the core insert, 0.3 mm larger in the cavity insert, 12 mm deep. No printed bumps |
| 4 | Counterbored bolts | Counterbore on top of the cavity insert, hex nut trap on the bottom of the core insert |
| 5 | Sprue location *Top* | Direct sprue and funnel, no runner or gate |
| 6 | Sprue location *Edge* | Runner of the sprue diameter in the parting plane from a block face, stopping about 2 mm short of the cavity, and a 1.5 mm gate cylinder bridging into the cavity. Zoom in: the gate must open into the cavity |
| 7 | Vent slots | Flat 4 mm wide, 0.05 mm deep slots in the parting face of the core insert from a high point to the block edge. Zoom in hard; also check the slot is not blocked by the funnel or a pin |
| 8 | Draft angle 0 | Warning: injection parts need 1-2 deg |
| 9 | Part with vertical walls, draft 2 deg | Message: some surface has less than the requested draft; the report is per half (faces above the plane pull up, faces below pull down) |
| 10 | Part with an undercut | Message reports the undercut percentage |
| 11 | *Parting from Silhouette Split* on a rounded part | Parting plane sits at the median height of the silhouette loop. If Fusion refuses, the message says the planar height from the section scan was used and `MoldMaker scratch` is gone |
| 12 | Same option on a part whose silhouette wanders | Warning with the deviation in mm |
| 13 | *Apply draft to cavity walls* (draft 2 deg) | Either each insert shows a Draft feature in its timeline and the cavity opens toward the parting plane, or a warning says why it was not applied. Send me the warning text |
| 14 | Lay flat | The cavity insert is flipped next to the core insert, cavity facing up, with pin holes still lined up |
| 15 | Ctrl+Z once | Everything gone, including scratch components |
| 16 | Select a mesh body | It cannot be selected; the tooltip says to run Convert Mesh first |

Fusion API assumptions to watch in this phase:
- `SilhouetteSplitFeatures.createInput(bodies, axis, False)` signature and result (the probe is wrapped in try/except; the log shows the real error if it differs).
- `DraftFeatures.createInput(faces, planeFace, True)`, `setSingleAngle`, `isDirectionFlipped`; the direction is verified by the volume going down.
- `OrientedBoundingBox3D` with a length direction that is not axis-aligned (vent slots, gate runner).
- After lay-flat, the draft code maps faces back through the 180 degree rotation about u; if the cavity walls are not found you get a warning, not a crash.

Mesh bodies (investigation result): `BRepBody.pointContainment`, face evaluators and temporary-body booleans only exist for BRep bodies, so a `MeshBody` cannot be sampled or cut. Fusion's own *Convert Mesh* (Mesh tab, faceted or prismatic) turns it into a solid first; MoldMaker does not do that for you because it creates thousands of faces and a feature the user should choose settings for. The selection tooltip says so.
