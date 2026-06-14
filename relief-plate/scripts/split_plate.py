#!/usr/bin/env python3
"""
split_plate.py - if a relief plate is larger than the printer bed, cut it into a
grid of tiles joined by hidden bottom-dovetails (2 dovetails per seam).

Each tile = relief on top (z2..) sitting on a 2 mm bottom dovetail layer (z0-2).
The dovetail lives entirely in the bottom 2 mm, so the relief BUTTS STRAIGHT across
the seam (no zig-zag in the image) and the joint is hidden underneath. One side of
each seam gets TABS (no support), the other gets POCKETS (print with support).

Two modes:
  PLAN:  python3 split_plate.py PLAN IMG.png --size S --bed 256
         -> prints whether it fits, and if not the tile grid + the per-tile commands.
  TILE:  python3 split_plate.py TILE IMG.png OUTDIR --size S --relief R \
             --col C --row R [--bed 256 --mirror 1 --raised dark]
         -> builds ONE tile (relief + dovetail layer). Run once per tile.
         If the plate fits the bed, TILE just builds the whole plate (no dovetails).

Tile naming: tile_c{C}_r{R}.stl  (col 0 = left, row 0 = bottom, assembled).
"""
import sys, os, struct, math
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_relief as BR
import earcut as EC

HERE = os.path.dirname(os.path.abspath(__file__))
FIN = os.path.join(HERE, 'finalize_mesh.py')
ROOT_HW, TIP_HW, DEPTH, CLEAR = 2.5, 3.5, 8.0, 0.30   # dovetail geometry / clearance
DOVE_H = 2.0                                           # bottom dovetail-layer height
SLAB_BASE = 1.0                                        # relief-slab base (total base = DOVE_H + SLAB_BASE = 3 mm)
TARGET_PITCH = 0.18                                    # mesh pitch (mm) for tiles

# ---------- mesh helpers ----------
def _read(p):
    f = open(p, 'rb'); f.read(80); n = struct.unpack('<I', f.read(4))[0]; T = []
    for _ in range(n):
        d = struct.unpack('<12fH', f.read(50)); T.append(np.array(d[3:12]).reshape(3, 3))
    return T
def _write(T, p):
    def nrm(a, b, c):
        u = b-a; v = c-a; nn = np.cross(u, v); L = np.linalg.norm(nn) or 1.0; return nn/L
    with open(p, 'wb') as f:
        f.write(b'\0'*80); f.write(struct.pack('<I', len(T)))
        for a, b, c in T: f.write(struct.pack('<12fH', *nrm(a, b, c), *a, *b, *c, 0))
def _bounds(T):
    A = np.array(T).reshape(-1, 3); return A.min(0), A.max(0)
def _extrude(outer, z0, z1):
    pts = [(float(x), float(y)) for (x, y) in outer]
    idx = EC.earcut([c for xy in pts for c in xy], None, 2); T = []
    for k in range(0, len(idx), 3):
        a, b, c = pts[idx[k]], pts[idx[k+1]], pts[idx[k+2]]
        T.append(np.array([(a[0], a[1], z1), (b[0], b[1], z1), (c[0], c[1], z1)]))
        T.append(np.array([(a[0], a[1], z0), (c[0], c[1], z0), (b[0], b[1], z0)]))
    n = len(outer)
    for i in range(n):
        a = outer[i]; b = outer[(i+1) % n]
        T.append(np.array([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1)]))
        T.append(np.array([(a[0], a[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)]))
    return T
def _build_poly(W, L, feat):
    ed = {'bottom': ((0, 0), (1, 0), (0, -1)), 'right': ((W, 0), (0, 1), (1, 0)),
          'top': ((W, L), (-1, 0), (0, 1)), 'left': ((0, L), (0, -1), (-1, 0))}
    poly = []
    for e in ['bottom', 'right', 'top', 'left']:
        (sx, sy), (dx, dy), (ox, oy) = ed[e]
        s = np.array([sx, sy], float); d = np.array([dx, dy], float); o = np.array([ox, oy], float)
        fs = []
        for coord, kind in feat.get(e, []):
            pos = coord if e in ('bottom', 'right') else (W-coord if e == 'top' else L-coord)
            fs.append((pos, kind))
        fs.sort(); poly.append(tuple(s))
        for pos, kind in fs:
            base = s + d*pos
            if kind == 'tab':
                poly += [tuple(base-d*ROOT_HW), tuple(base-d*TIP_HW+o*DEPTH),
                         tuple(base+d*TIP_HW+o*DEPTH), tuple(base+d*ROOT_HW)]
            else:
                rhw, thw = ROOT_HW+CLEAR, TIP_HW+CLEAR
                poly += [tuple(base-d*rhw), tuple(base-d*thw-o*DEPTH),
                         tuple(base+d*thw-o*DEPTH), tuple(base+d*rhw)]
    return poly

# ---------- planning ----------
def plate_dims(png, size_mm):
    W, H = Image.open(png).size
    return (size_mm*W/H, size_mm) if H >= W else (size_mm, size_mm*H/W)
def grid(png, size_mm, usable):
    pw, ph = plate_dims(png, size_mm)
    return pw, ph, max(1, math.ceil(pw/usable - 1e-6)), max(1, math.ceil(ph/usable - 1e-6))
def _dove_positions(length, n=2, inset=None):
    if inset is None: inset = min(20.0, length*0.25)
    if n == 2: return [inset, length-inset]
    return list(np.linspace(inset, length-inset, n))

def _argval(flag, default, cast=float):
    return cast(sys.argv[sys.argv.index(flag)+1]) if flag in sys.argv else default

# ---------- main ----------
mode = sys.argv[1]; png = sys.argv[2]
size = _argval('--size', 230.0); relief = _argval('--relief', 2.0)
bed = _argval('--bed', 256.0); margin = _argval('--margin', 18.0); usable = bed - margin
mirror = bool(int(_argval('--mirror', 1, int))); raised = _argval('--raised', 'dark', str)

if mode == 'PLAN':
    pw, ph, nc, nr = grid(png, size, usable)
    print(f'plate {pw:.1f} x {ph:.1f} mm | bed {bed:.0f} (usable {usable:.0f}) | grid {nc} x {nr} = {nc*nr} tiles')
    if nc*nr == 1:
        print('FITS the bed -> single plate, no split/dovetails needed.')
    else:
        print(f'tile ~ {pw/nc:.1f} x {ph/nr:.1f} mm + {DOVE_H:.0f} mm dovetail layer. Build each:')
        for r in range(nr):
            for c in range(nc):
                print(f'  TILE --col {c} --row {r}')

elif mode == 'TILE':
    outdir = sys.argv[3]; os.makedirs(outdir, exist_ok=True)
    c = int(_argval('--col', 0, int)); r = int(_argval('--row', 0, int))
    pw, ph, nc, nr = grid(png, size, usable)
    W, H = Image.open(png).size
    if nc*nr == 1:
        BR.build(png, os.path.join(outdir, 'plate.stl'), size_mm=size,
                 base_mm=_argval('--base', 3.0), relief_mm=relief, mirror=mirror, raised=raised)
        print('single plate built (fits the bed) ->', os.path.join(outdir, 'plate.stl'))
        sys.exit()
    bw, bh = W/nc, H/nr
    # assembled (c,r): col 0=left, row 0=bottom. mirror flips cols; Y-flip handles rows.
    x0, x1 = int(round((nc-1-c)*bw)), int(round((nc-c)*bw))
    y0, y1 = int(round((nr-1-r)*bh)), int(round((nr-r)*bh))
    tile_long = max(x1-x0, y1-y0)
    pitch_full = size/max(W, H)
    tile_size_mm = tile_long*pitch_full
    factor = max(1, int(round(TARGET_PITCH/pitch_full)))
    slab = os.path.join(outdir, f'_slab_c{c}_r{r}.stl')
    BR.build(png, slab, size_mm=tile_size_mm, base_mm=SLAB_BASE, relief_mm=relief,
             mirror=mirror, raised=raised, crop=(x0, y0, x1, y1), factor=factor, preview=False)
    # tile footprint
    Tslab = _read(slab); mn, mx = _bounds(Tslab); Wt, Lt = mx[0]-mn[0], mx[1]-mn[1]
    # features: tab where a neighbour exists on that side (right/top), pocket on (left/bottom)
    feat = {}
    if c < nc-1: feat['right'] = [(y, 'tab') for y in _dove_positions(Lt)]
    if c > 0:    feat['left'] = [(y, 'pocket') for y in _dove_positions(Lt)]
    if r < nr-1: feat['top'] = [(x, 'tab') for x in _dove_positions(Wt)]
    if r > 0:    feat['bottom'] = [(x, 'pocket') for x in _dove_positions(Wt)]
    top = [t+np.array([0, 0, DOVE_H]) for t in Tslab]          # relief slab -> z2..
    tmp = os.path.join(outdir, f'_lay_c{c}_r{r}.stl')
    _write(_extrude(_build_poly(Wt, Lt, feat), 0.0, DOVE_H), tmp)
    os.system(f'python3 "{FIN}" "{tmp}" >/dev/null 2>&1')
    out = os.path.join(outdir, f'tile_c{c}_r{r}.stl')
    _write(top + _read(tmp), out)
    has_pocket = ('left' in feat) or ('bottom' in feat)
    print(f'tile c{c} r{r}: {Wt:.1f} x {Lt:.1f} mm, '
          f'{"SUPPORT under pockets" if has_pocket else "no support needed"} -> {out}')
    for f in (slab, tmp):
        try: os.remove(f)
        except OSError: pass
else:
    print('usage: split_plate.py PLAN|TILE ...')
