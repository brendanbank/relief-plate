---
name: relief-plate
description: >-
  Convert a black & white image or painting (e.g. exported from Adobe
  Fresco/Photoshop) into a 3D-printable RELIEF PRINTING PLATE as a watertight
  STL, for printing on a rolling press / etching press with a brayer (like a
  3D-printed linocut). Use whenever the user wants to turn a picture, portrait,
  line-art, or logo into a printable relief/stamp/plate, or mentions "relief
  plate", "printing plate", "rolling press", "brayer", "linocut", "engraving
  plate", or "image to STL relief". Produces raised relief on a solid base.
metadata:
  version: "1.1.0"
  author: Barbara
  tested-on: "Bambu Lab X2D (0.4 mm nozzle, ~256 mm bed)"
---

# Relief printing plate from an image

<!-- Changelog
  1.1.0 - auto-split plates larger than the printer bed into dovetail-joined tiles
          (split_plate.py); hidden bottom-dovetails, 2 per seam, auto tab/pocket.
  1.0.0 - initial: image -> watertight relief STL (build_relief), detail test tiles
          (build_tiles), watertight finalize, 0.4 mm nozzle sizing rules.
-->


Turns a high-contrast B&W image into a watertight relief plate STL: dark areas
become a raised, uniform-height surface on a solid base; you roll ink on top with
a brayer and run it through the press.

## Order of operations (do these in order)

### 1. Get the input image
- Need a **PNG** (lossless; never JPEG — compression speckle ruins edge tracing).
- High resolution = the detail ceiling. Ask the user to export from Photoshop at
  **300+ ppi / ≥2500 px on the long side**, flattened, **white background**.
- **Black = the parts to be raised/inked**, white = recessed background.
- The script auto-flattens any alpha onto white and thresholds at 128.

### 2. ALWAYS run this Q&A first (use AskUserQuestion)
Before building anything, ask the user these **three** questions (one tool call,
three questions). Do not assume — always ask:

1. **Plate size** (longest dimension, mm). This is the most important answer
   because detail scales with it. Guidance to give: with a 0.4 mm nozzle, every
   raised line AND every gap must end up **≥ ~0.45 mm** on the plate, or it merges
   when sliced. Size the plate from the *finest feature*, not a target size.
   Offer options like ~150 mm, ~230 mm (good for detailed portraits), and Custom.
   Note the bed limit (~256 mm).
2. **Base height** (mm) — the solid backing under the relief. Offer 2 mm
   (recommended), 3 mm, Custom.
3. **Relief height** (mm) — how far the inked areas rise above the base. Offer
   2 mm (recommended), 1 mm, Custom. (Total plate thickness = base + relief.)

Sensible defaults if the user defers: size 230, base 2, relief 2.
Two more settings have safe defaults — only ask if the user seems to want control:
- **Mirror** (default ON): mirrors left-right so the *pressed print* matches the
  artwork. Keep ON for press printing.
- **Raised tone** (default `dark`): black areas raised. Use `light` for an
  engraved/negative (scratchboard) look — better for line-art, inverts tones on
  tonal portraits.

### 3. Build the plate
```
python3 scripts/build_relief.py INPUT.png OUTPUT.stl \
    --size <S> --base <B> --relief <R> --mirror 1 --raised dark
```
The script does the whole pipeline and finalizes to a watertight mesh:
threshold → OR-downsample (never erodes, keeps thin lines) → close diagonal pinch
points → trace smooth vector contours → classify regions → extrude ONE solid
height field (solid base, steps only above the base) → dedupe + hole-fill +
coherent outward normals. It also writes `OUTPUT_preview.png` (black = raised).

### 4. Verify and report
The build prints the final size (W × H × total height). The mesh is already
watertight with correct normals (no Bambu "floating regions" warning, no repair
prompt). Show the user the preview and the dimensions.

### 4b. If the plate is larger than the printer bed, SPLIT it into tiles
The Bambu X2D bed is ~256 mm. If the chosen plate size exceeds the usable bed, the
plate must be cut into a grid of tiles joined by hidden **bottom-dovetails** (the
joint lives in the bottom 2 mm, so the relief butts straight across the seam and the
dovetail is invisible from the top). Two dovetails per seam; one side gets tabs (no
support), the other gets pockets (print with support).

First, plan:
```
python3 scripts/split_plate.py PLAN INPUT.png --size <S> --bed 256
```
This prints whether it FITS (single plate) or the tile grid (e.g. "2 x 3 = 6 tiles")
plus a `TILE --col C --row R` line per tile. If it fits, just build normally (step 3).

If it must split, build each tile (run once per tile — each is one relief build, so
do them as separate commands to stay responsive):
```
python3 scripts/split_plate.py TILE INPUT.png OUTDIR --size <S> --relief <R> \
    --col C --row R --mirror 1 --raised dark
```
Output: `tile_c{C}_r{R}.stl` (col 0 = left, row 0 = bottom, assembled). Each tile is
2 mm dovetail layer + 1 mm base + relief on top (so total base = 3 mm). The command
prints whether that tile needs **support** (it does whenever it has a pocket edge).
Report the grid and the per-tile support map to the user. Tabs auto-mate with
pockets, so assembled the tiles reform the full image with the joints underneath.

Notes:
- `--bed` defaults to 256 and `--margin` to 18 mm (leaves room for the dovetail tab
  protrusion + a brim); lower the effective usable size by raising `--margin`.
- Print every tile **relief-up**. Tiles with pockets: enable support (support
  filament on the X2D aux nozzle). Tiles with only tabs: no support.
- Each tile STL is two shells (relief slab + dovetail layer touching at z=2) that
  the slicer unions into one solid.

### 5. Offer detail test tiles (recommended for detailed art)
Printing small true-scale tiles of the trickiest regions first is much cheaper
than discovering merged detail on the full plate. Identify detail regions (eyes,
fine strands) by their pixel boxes in the source and run:
```
python3 scripts/build_tiles.py INPUT.png OUTDIR --size <S> --base <B> --relief <R> \
    --crop eye 560 1380 980 1700 --crop strands 30 2000 400 3120
```
Tiles are built at the **same physical scale** as the full plate, so they predict
the real result exactly. They are un-mirrored to match the source visually.

## Hard constraints / lessons (keep in mind)
- **0.4 mm nozzle is the detail floor.** Features/gaps below ~0.45 mm merge when
  sliced. The only levers are: scale the plate up, or simplify the densest detail.
  (Do not assume a finer nozzle is available — ask if relevant.)
- **Never erode/open the mask** — it deletes thin lines. The script uses OR-
  downsampling on purpose.
- **One solid height field**, never overlapping base + relief bodies (that makes
  the base print hollow).
- **Coherent outward normals + watertight** are required or the slicer warns about
  floating regions. The finalize step handles this; don't skip it.
- For tonal portraits use raised (`dark`); for line-art consider engraved (`light`).

## Files
- `scripts/build_relief.py` — image → watertight relief STL (+ preview)
- `scripts/split_plate.py` — if larger than the bed, cut into dovetail-joined tiles
  (PLAN to check the grid, TILE to build each)
- `scripts/build_tiles.py` — detail-region test tiles at production scale
- `scripts/finalize_mesh.py` — dedupe + hole-fill + coherent normals (called by build)
- `scripts/earcut.py` — polygon triangulation (ear-cutting with holes)

Requires Python with `numpy` and `Pillow`.
