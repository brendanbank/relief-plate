# relief-plate

Convert a black-and-white image or painting into a **3D-printable relief printing
plate** (STL) for a rolling press / brayer — with automatic tiling (hidden
dovetail joints) for plates larger than the printer bed.

Dark areas of the image become a raised, uniform-height surface on a solid base;
white areas stay recessed. Roll ink across the top with a brayer and the raised
shapes transfer to paper under the press — like a 3D-printed linocut.

`relief-plate` is a **Claude Agent Skill**: the [`SKILL.md`](SKILL.md) manifest
tells the agent how to drive the scripts (asking the right sizing questions,
splitting oversized plates, building detail test tiles). The scripts also run
standalone — see [Usage](#usage).

## Install

It's an Agent Skill, so add it to a Claude client:

1. **Download or clone** this repo (or grab the `relief-plate.skill` bundle from
   the [latest release](https://github.com/brendanbank/relief-plate/releases)):
   ```bash
   git clone https://github.com/brendanbank/relief-plate.git
   ```
2. **Register it as a skill** — either through the client's
   **Settings → Capabilities** (point it at the folder / `.skill` bundle), or by
   placing the skill under your skills directory, e.g.:
   ```bash
   mkdir -p ~/.claude/skills
   cp -R relief-plate ~/.claude/skills/relief-plate   # must contain SKILL.md at its root
   ```

The skill loader expects `SKILL.md` at the root of the skill folder (it is, here).

## Requirements

- Python 3
- `numpy` and `Pillow`:
  ```bash
  pip install numpy pillow
  ```

## Usage

Input must be a **PNG** (lossless — never JPEG; compression speckle ruins edge
tracing), high resolution (≥2500 px on the long side), flattened, on a **white
background**, with **black = the parts to be raised/inked**.

**Build a plate:**
```bash
python3 scripts/build_relief.py INPUT.png OUT.stl \
    --size 230 --base 2 --relief 2 --mirror 1 --raised dark
```

**Plan a split** for a plate bigger than the bed (prints whether it fits, and if
not the tile grid + per-tile commands):
```bash
python3 scripts/split_plate.py PLAN INPUT.png --size 400 --bed 256
```

**Build one tile** (run once per tile from the plan):
```bash
python3 scripts/split_plate.py TILE INPUT.png OUTDIR \
    --size 400 --relief 2 --col 0 --row 0
```

**Detail test tiles** at production scale (print the trickiest regions first):
```bash
python3 scripts/build_tiles.py INPUT.png OUTDIR --size 230 --base 2 --relief 2 \
    --crop eye 560 1380 980 1700
```

### Splitting a large plate into tiles — and recombining them

When a plate is larger than the printer bed (~256 mm on the Bambu X2D), you don't
have to shrink the artwork. Split it into a grid of tiles that **dovetail back
together into one plate** after printing — the image stays full-size and the joints
are hidden.

1. **Plan** the grid. `PLAN` reports whether it fits and, if not, the grid plus one
   `TILE` command per tile (and which tiles need support):
   ```bash
   python3 scripts/split_plate.py PLAN INPUT.png --size 400 --bed 256
   # -> plate 400.0 x 266.7 mm | grid 2 x 2 = 4 tiles
   #      TILE --col 0 --row 0   (col 0 = left, row 0 = bottom)
   #      TILE --col 1 --row 0
   #      ...
   ```
2. **Build & print** each tile (`tile_c{C}_r{R}.stl`). Each tile is the relief slab
   sitting on a 2 mm bottom layer that carries the dovetails. Print every tile
   relief-up.
3. **Recombine.** Each shared seam has **two hidden bottom-dovetails**: one tile
   gets the **tabs**, the neighbour gets matching **pockets** (cut with clearance).
   Slot the tabs into the pockets and the tiles lock together edge-to-edge,
   reforming the full image as a single plate. Because the dovetails live entirely
   in the bottom 2 mm, the relief **butts straight across the seam** — the joint is
   invisible from the top (the inked/printing surface) and only shows underneath.
   Add a little glue in the pockets if you want the assembly permanent.

**Support:** tiles that carry a **pocket** edge must be printed **with support**
(support filament on the X2D aux nozzle); tiles with only **tabs** print without.
The `TILE` command prints which case each tile is — by convention, `right`/`top`
seams get tabs (no support) and `left`/`bottom` seams get pockets (support).

### `build_relief.py` flags

| Flag | Meaning | Default |
|------|---------|---------|
| `--size`   | Longest plate dimension in mm (detail scales with it) | `230` |
| `--base`   | Solid base thickness in mm | `2` |
| `--relief` | Raised relief height in mm (total height = base + relief) | `2` |
| `--mirror` | `1` mirrors left-right so the *pressed print* matches the artwork | `1` |
| `--raised` | `dark` = black raised (tonal art); `light` = engraved/negative look (line-art) | `dark` |

## Key constraints

- **0.4 mm nozzle is the detail floor.** Every raised line *and* every gap must
  end up **≥ ~0.45 mm** on the plate, or it merges when sliced.
- **Size the plate from its finest feature, not a target dimension.** The only
  levers for more detail are scaling the plate up or simplifying the densest area.
- **Raised vs. engraved:** use `--raised dark` for tonal portraits (black raised);
  `--raised light` for an engraved/negative (scratchboard) look, better for
  line-art.
- **Oversized plates auto-split** into a grid joined by hidden bottom-dovetails
  (the joint lives in the bottom 2 mm, so the relief butts straight across the
  seam and the dovetail is invisible from the top). Tiles with pockets print with
  support; tiles with only tabs print without.

Tuned for the **Bambu Lab X2D** (256 mm bed, 0.4 mm nozzle).

## Repository layout

```
SKILL.md                  # Agent Skill manifest (frontmatter + instructions + changelog)
LICENSE                   # MIT
README.md
requirements.txt
scripts/
  build_relief.py         # image → watertight relief STL (+ preview)
  split_plate.py          # cut oversized plates into dovetail-joined tiles (PLAN/TILE)
  build_tiles.py          # detail-region test tiles at production scale
  finalize_mesh.py        # dedupe + hole-fill + coherent outward normals (called by build)
  earcut.py               # polygon triangulation (ear-clipping with holes)
```

## Changelog

- **1.1.1** — correct author/copyright attribution to Brendan Bank; document how
  split tiles recombine via hidden dovetails.
- **1.1.0** — auto-split plates larger than the printer bed into dovetail-joined
  tiles (`split_plate.py`): hidden bottom-dovetails, 2 per seam, automatic
  tab/pocket assignment.
- **1.0.0** — initial release: image → watertight relief STL (`build_relief.py`),
  detail test tiles (`build_tiles.py`), watertight finalize, 0.4 mm nozzle sizing
  rules.

## License

MIT © Brendan Bank — see [LICENSE](LICENSE).
