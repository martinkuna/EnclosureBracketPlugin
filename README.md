# Enclosure Bracket Generator

A Fusion 360 script that builds a parametric device-mounting tray for a
structured media enclosure — the same family of part as your UCG-Fiber bracket,
generalised so one script covers a Mac mini, a Pi, a hard drive, or anything
else square or rectangular.

It builds a **native Fusion timeline** — real sketches, real features, real user
parameters. Not an imported mesh or a dumb STEP body.

---

## Running it

1. `Utilities` → `ADD-INS` → `Scripts and Add-Ins` → `Scripts` tab → the green
   **+** → point it at the folder containing `EnclosureBracket.py`.
2. Open a **new, empty** design.
3. Edit the `PRESET` line and the `CFG` block at the top of the script, save.
4. Select the script and hit **Run**.

A dialog reports the resolved dimensions and any warnings. The bracket lands in
its own component named `Bracket_<preset>`.

> User parameters are document-wide. One bracket per document, or set
> `PARAM_PREFIX` (e.g. `'b2_'`) before generating a second one alongside it.

---

## The two hook styles

This was the main design problem, and it's worth understanding before you pick.

A **circular** hook that wraps a corner can only be slightly larger than the
device's own corner radius before the device's corner collides with it. Working
the geometry out, the hook's inner radius can exceed the device corner radius
by at most about **3.4 × the fit clearance** — with 0.4 mm clearance, roughly
1.4 mm. So on a device with near-square corners, a corner arc collapses to a
3–4 mm stub that grabs nothing.

Hence:

| `hook_style` | Shape | Tuned by | Use for |
|---|---|---|---|
| `'round'` | Arc wrapping the corner radius | `dev_corner_r` | Devices with genuinely rounded corners — UCG-Fiber, Mac mini |
| `'square'` | L-shaped wall, straight legs down each face | `hook_leg` | Near-square corners — Pi, HDDs, most enclosures |

In square style the hooks are built oversize and trimmed to the plate outline,
so their outer corners pick up the plate's corner radius automatically.

---

## Presets

| Key | Device | Style |
|---|---|---|
| `ucg_fiber` | UniFi Cloud Gateway Fiber | round |
| `mac_mini_m4` | Mac mini (M4, 2024) | round |
| `mac_mini_m2` | Mac mini (M1/M2) | round |
| `rpi5_case` | Pi 5 in official case | square |
| `rpi_bare` | Bare Pi 4B / 5 board | square |
| `hdd_35` | 3.5" drive | square |
| `hdd_25` | 2.5" drive / SSD | square |
| `custom` | Blank slate | square |

**Measure your device with calipers and correct the preset.** Several of these
are marked `[VERIFY DIMENSIONS]` in the file — I could not confirm them, and a
press-fit bracket is only as good as the numbers you feed it. The UCG-Fiber
entry in particular is a placeholder; you have the real part.

---

## Parameters

### Live in Fusion (`Modify` → `Change Parameters`)

These drive real sketch dimensions and feature extents, so edit and the model
rebuilds:

| Parameter | Meaning |
|---|---|
| `dev_w`, `dev_d`, `dev_h`, `dev_corner_r` | The device. `plate_l`/`plate_w` follow automatically |
| `fit_clear` | Per-side gap between device and hook inner face |
| `plate_t` | Plate thickness (5 mm) |
| `hook_t` | Hook wall thickness |
| `hook_h` | Wall height to the underside of the lip; `dev_h + hook_h_adj` |
| `hook_lip`, `hook_lip_h` | Retaining lip projection and its ramp height |
| `corner_r`, `hook_ir`, `hook_leg` | Corner and hook geometry |
| `waist_d_x`, `waist_d_y` | Scallop depth on each pair of edges |
| `center_l`, `center_w` | Central opening |
| **`slot_corner_len`, `slot_side_*_len`** | **Slot lengths — the ones you asked to be adjustable** |
| `slot_corner_x/y`, `slot_side_*_pos` | Slot positions |
| `slot_w` | Plunger shaft slot width (6.6) |
| `inset_w`, `inset_t` | Plunger lip pocket width (9.4) and material left under it (3) |
| `hook_fillet`, `base_chamfer` | Finishing |

### Requires a re-run (edit `CFG`, run again)

Hook style, slot **count**, slot **angle**, strap and vent layout. These change
how many sketch entities exist, so they can't be a parameter tweak.

---

## Slot placement

Rather than a rule of thumb, the script **scans the actual plate region** — the
rounded rectangle minus the waist scallops, minus the central opening, minus
the hook footprints — and finds the longest run along each slot's axis with room
for the full 9.4 mm lip pocket plus `edge_margin`. Slots come out as long as the
material allows and no longer, which is what you asked for. Set
`corner_slot_len` / `side_slot_len` to override.

Corner slots are anchored at the **outboard** end of the usable run so they sit
on the corner pad rather than drifting toward the middle, and they are held
clear of the hook walls' footing — a pocket under a wall would leave it standing
on a 3 mm ledge and the plunger head would foul it.

Side slots try the X centreline first and fall back to Y (`side_slot_axis`:
`'auto'`, `'x'`, `'y'`, `'both'`). On a square device like a Mac mini there is
often only room on one axis.

Nothing is constrained to the On-Q hole pattern — as you asked, aligning slots
to real mounting points is left to you.

### Straps, extra slots, vents

```python
'straps': [{'axis': 'x', 'width': 25.0, 'thick': 3.5, 'offset': None}],

'extra_slots': [{'x': 0.0, 'y': 30.0, 'ang': 0.0, 'len': 30.0,
                 'width': 6.6, 'inset': True}],

'vents': True, 'vent_d': 6.0, 'vent_pitch': 10.0, 'vent_pattern': 'hex',
```

Vent holes are culled analytically against the plate outline, the waists, the
central opening and every slot pocket, so the pattern never breaks anything.

---

## FDM notes

Designed assuming the **worst case: a wall-mounted enclosure**, so the bracket
is vertical and the hooks carry real load.

- `hook_t` defaults to **2.8 mm** — seven perimeters at a 0.4 mm nozzle, so the
  walls are essentially solid regardless of infill.
- The lip is made with a **tapered extrude**, giving a ramp on the underside
  instead of a flat overhang. Keep `hook_lip ≤ hook_lip_h` and that ramp stays
  at or below 45°, so it prints without support. The outward half of the taper
  is trimmed off flush with the plate edge.
- `base_chamfer` (0.5 mm) relieves elephant's foot on the whole bottom face.
- Print flat on the plate, hooks up. No support needed at defaults.
- PETG or ASA over PLA — media enclosures get warm, and PLA creeps under
  sustained load. For a heavy device mounted vertically this matters.
- **Insertion is by flex**: the hooks spring apart as you push the device past
  the lips. If it's too stiff, drop `hook_lip` to 0.8; if the device rattles,
  reduce `hook_h_adj`. If you'd rather not flex it at all, set `hook_lip` to 0
  and add a strap.

---

## What was verified, and what wasn't

I have no Fusion 360 in this environment, so **the API calls are unrun**. What I
could check, I checked hard, with a separate harness (`verify.py`) that stubs
the Fusion API, re-derives the geometry, and tests it against independently
written predicates:

- Every slot pocket stays inside the true plate region, with margin
- No slot undercuts a hook wall's footing
- No two slot pockets collide
- Waist scallops blend tangentially into the corner arcs, cut exactly the depth
  requested, and never exceed a sane blend radius
- The device's own corner cannot foul a round hook
- Hook sweeps straddle both tangent points
- **2,300 randomised device sizes** from 45 × 40 mm to 260 × 220 mm, both hook
  styles, all passing

That found five real bugs, including a waist that cut 36 mm into each short edge
of a long plate, and corner-slot pockets that broke the outline on every
square-hook preset.

What that testing **cannot** tell us is whether Fusion accepts every API call —
particularly the mixed-unit parameter expressions, the sketch constraint sets,
and the geometric edge selection used for the fillets. Those are wrapped so
failures degrade to a warning in the summary dialog rather than killing the run,
and the error dialog names the stage that failed. Expect a round of iteration on
the first run; send me the message text and I'll fix it.

Two known soft spots:

- **Square style leaves a slight shoulder** where the waist meets the straight
  edge, rather than a tangent blend. Raising `plate_corner_r` softens it.
- **Sketch angular extents are baked in** — the hook sweep and slot angles come
  from the script rather than from driven dimensions. Radii, lengths, widths and
  positions are all live; angles need a re-run.
