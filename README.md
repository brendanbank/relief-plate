# relief-plate

Turn a black-and-white image into a **3D-printable relief printing plate** — a
watertight STL you print, ink with a brayer, and run through a rolling/etching
press like a 3D-printed linocut.

Dark areas of the image become a raised, uniform-height surface on a solid base;
white areas stay recessed. Roll ink across the top with a brayer and the raised
shapes transfer to paper under the press.

This repository is packaged as a [Claude skill](relief-plate/SKILL.md): the
`SKILL.md` tells the agent how to drive the scripts (asking the right sizing
questions, splitting oversized plates, building detail test tiles). You can also
run the scripts directly — see [Usage](#usage) below.

## What it does

```
PNG image  ──►  build_relief.py  ──►  watertight relief STL  ──►  print → ink → press
```

The pipeline (in `scripts/build_relief.py`) bakes in the hard-won rules for
getting clean, printable detail on a 0.4 mm nozzle:

1. Threshold the image to a black/white mask.
2. OR-downsample (never erodes — keeps thin lines intact).
3. Close diagonal pinch points that would create a non-manifold mesh.
4. Trace smooth vector contours and classify raised vs. recessed regions.
5. Extrude **one solid height field** (solid base, steps only above the base).
6. Finalize to a watertight mesh with coherent outward normals — no slicer
   "floating regions" warning, no repair prompt.

It also writes `OUTPUT_preview.png` (black = the parts that will be raised/inked).

## Hardware

Tested end-to-end on a **Bambu Lab X2D** 3D printer. The defaults assume a
0.4 mm nozzle and the X2D's ~256 mm bed:

- Features and gaps below ~0.45 mm merge when sliced — size the plate from its
  **finest feature**, not a target dimension.
- Plates larger than the usable bed are auto-split into a grid of tiles joined by
  hidden **bottom-dovetails** (the joint lives in the bottom 2 mm, so the relief
  butts straight across the seam and the dovetail is invisible from the top).
  Tiles with pockets print with support (support filament on the X2D aux nozzle);
  tiles with only tabs print without support.

## Requirements

- Python 3 (tested on 3.10–3.13)
- `numpy` and `Pillow`

```bash
pip install -r requirements.txt
```

## Usage

Input must be a **PNG** (lossless — never JPEG; compression speckle ruins edge
tracing), high resolution (≥2500 px on the long side), flattened, on a **white
background**, with **black = the parts to be raised/inked**.

### Build a plate

```bash
python3 relief-plate/scripts/build_relief.py INPUT.png OUTPUT.stl \
    --size 230 --base 2 --relief 2 --mirror 1 --raised dark
```

| Flag | Meaning | Default |
|------|---------|---------|
| `--size`   | Longest plate dimension in mm (detail scales with it) | `230` |
| `--base`   | Solid base thickness in mm | `2` |
| `--relief` | Raised relief height in mm (total height = base + relief) | `2` |
| `--mirror` | `1` mirrors left-right so the *pressed print* matches the artwork | `1` |
| `--raised` | `dark` = black raised (tonal art); `light` = engraved/negative look (line-art) | `dark` |

### Split a plate larger than the bed

```bash
# Check whether it fits, and if not see the tile grid + per-tile commands:
python3 relief-plate/scripts/split_plate.py PLAN INPUT.png --size 320 --bed 256

# Build one tile (run once per tile):
python3 relief-plate/scripts/split_plate.py TILE INPUT.png OUTDIR \
    --size 320 --relief 2 --col 0 --row 0 --mirror 1 --raised dark
```

### Detail test tiles (recommended for detailed art)

Print small true-scale tiles of the trickiest regions first — far cheaper than
discovering merged detail on the full plate.

```bash
python3 relief-plate/scripts/build_tiles.py INPUT.png OUTDIR \
    --size 230 --base 2 --relief 2 \
    --crop eye 560 1380 980 1700 --crop strands 30 2000 400 3120
```

Each `--crop NAME x0 y0 x1 y1` is a pixel box in the source image; tiles are
built at the same physical scale as the full plate, un-mirrored to match the
source visually.

## Repository layout

```
relief-plate/
├── SKILL.md                  # Claude skill definition (agent instructions)
└── scripts/
    ├── build_relief.py       # image → watertight relief STL (+ preview)
    ├── split_plate.py        # cut oversized plates into dovetail-joined tiles
    ├── build_tiles.py        # detail-region test tiles at production scale
    ├── finalize_mesh.py      # dedupe + hole-fill + coherent normals (called by build)
    └── earcut.py             # polygon triangulation (ear-cutting with holes)
```

See [`relief-plate/SKILL.md`](relief-plate/SKILL.md) for the full order of
operations, sizing guidance, and the constraints/lessons behind the defaults.
