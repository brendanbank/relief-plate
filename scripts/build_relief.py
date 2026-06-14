#!/usr/bin/env python3
"""
build_relief.py - convert a black & white image into a watertight 3D relief
printing-plate STL (raised relief on a solid base).

Usage:
  python3 build_relief.py INPUT.png OUTPUT.stl \
      --size 230 --base 2 --relief 2 --mirror 1 --raised dark

Args:
  --size    longest plate dimension in mm (sizes the whole plate; detail scales with it)
  --base    solid base thickness in mm
  --relief  raised relief height in mm (total plate height = base + relief)
  --mirror  1 = mirror left-right (so the PRESSED print matches the artwork). 0 = no.
  --raised  'dark' (black areas raised, default) or 'light' (light areas raised / engrave look)

Pipeline (all the learnings baked in):
  threshold -> OR-downsample (never erode, keeps thin lines) -> close diagonal
  pinch points -> trace smooth vector contours -> classify regions by centroid
  majority -> extrude ONE solid height field (solid base, steps only above base)
  -> dedupe/fill/coherent-normals finalize (watertight, correct normals).
"""
import numpy as np, struct, os, sys, time
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import earcut as EC
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- helpers ----------
def load_gray(png):
    im = Image.open(png).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    return np.array(Image.alpha_composite(bg, im).convert('L'))

def sarea(p):
    x = p[:, 1]; y = p[:, 0]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)

def pip(pt, poly):
    y, x = pt; yy = poly[:, 0]; xx = poly[:, 1]; n = len(poly); ins = False; j = n - 1
    for i in range(n):
        if ((yy[i] > y) != (yy[j] > y)) and (x < (xx[j]-xx[i])*(y-yy[i])/(yy[j]-yy[i]+1e-12)+xx[i]):
            ins = not ins
        j = i
    return ins

def chaikin(p, it):
    p = np.array(p, float)
    for _ in range(it):
        a = p; b = np.roll(p, -1, 0); q = 0.75*a+0.25*b; r = 0.25*a+0.75*b
        o = np.empty((len(a)*2, 2)); o[0::2] = q; o[1::2] = r; p = o
    return p

def dp(pts, tol):
    n = len(pts)
    if n < 4: return pts
    keep = np.zeros(n, bool); keep[0] = keep[-1] = True; st = [(0, n-1)]
    while st:
        i, j = st.pop()
        if j <= i+1: continue
        a = pts[i]; b = pts[j]; ab = b-a; L = np.hypot(*ab)+1e-9
        seg = pts[i+1:j]-a; d = np.abs(ab[0]*seg[:, 1]-ab[1]*seg[:, 0])/L; k = int(np.argmax(d))
        if d[k] > tol:
            idx = i+1+k; keep[idx] = True; st.append((i, idx)); st.append((idx, j))
    return pts[keep]

def triangulate(outer, holes):
    pts = [(float(v[1]), float(v[0])) for v in outer]; hi = []
    for h in holes:
        hi.append(len(pts)); pts += [(float(v[1]), float(v[0])) for v in h]
    data = [c for xy in pts for c in xy]
    idx = EC.earcut(data, hi if hi else None, 2); P = np.array(pts)
    return [(P[idx[k]], P[idx[k+1]], P[idx[k+2]]) for k in range(0, len(idx), 3)]

# ---------- core ----------
def build(png, out_stl, size_mm=230.0, base_mm=2.0, relief_mm=2.0,
          mirror=True, raised='dark', factor=None, crop=None,
          preview=True, thresh=128):
    g = load_gray(png)
    if crop:
        g = g[crop[1]:crop[3], crop[0]:crop[2]]
    dark = g < thresh
    m_full = dark if raised == 'dark' else ~dark
    if factor is None:                         # keep mesh sane: ~1300 px long side
        factor = max(1, int(round(max(m_full.shape) / 1300)))
    f = factor; H = (m_full.shape[0]//f)*f; W = (m_full.shape[1]//f)*f
    m = m_full[:H, :W].reshape(H//f, f, W//f, f).any(axis=(1, 3))
    if mirror:
        m = np.fliplr(m)
    # Force the outermost 1 px to BASE (recessed), never raised. This is NOT a raised rim: the
    # edge sits at base height (invisible/flush). It guarantees a clean rectangular perimeter so
    # the explicit plate-outline (added after tracing) has no features touching it -> no T-junction
    # between the base top and the perimeter wall. Clips at most ~one downsampled pixel of any
    # edge-touching art (a desirable print margin), and adds no border that wasn't in the image.
    m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = False
    for _ in range(8):                               # close diagonal pinch points (non-manifold source)
        A = m[:-1, :-1] & m[1:, 1:] & ~m[:-1, 1:] & ~m[1:, :-1]
        B = m[:-1, 1:] & m[1:, :-1] & ~m[:-1, :-1] & ~m[1:, 1:]; ch = 0
        if A.any(): rr, cc = np.where(A); m[rr, cc+1] = True; ch += len(rr)
        if B.any(): rr, cc = np.where(B); m[rr, cc] = True; ch += len(rr)
        if ch == 0: break
    ROWS, COLS = m.shape
    pitch = size_mm / max(ROWS, COLS)

    # trace boundary -> loops
    mask = np.zeros((ROWS+2, COLS+2), bool); mask[1:-1, 1:-1] = m
    hd = mask[:-1, :] != mask[1:, :]; vi, vj = np.where(hd); He = np.stack([vi+1, vj, vi+1, vj+1], 1)
    vd = mask[:, :-1] != mask[:, 1:]; wi, wj = np.where(vd); Ve = np.stack([wi, wj+1, wi+1, wj+1], 1)
    E = np.vstack([He, Ve]); adj = defaultdict(list)
    for y0, x0, y1, x1 in E:
        a = (int(y0), int(x0)); b = (int(y1), int(x1)); adj[a].append(b); adj[b].append(a)
    def ek(a, b): return (a, b) if a <= b else (b, a)
    used = set(); loops = []
    for s in list(adj.keys()):
        while True:
            nx = None
            for nb in adj[s]:
                if ek(s, nb) not in used: nx = nb; break
            if nx is None: break
            lp = [s]; used.add(ek(s, nx)); cur = nx; prev = s
            while cur != s:
                lp.append(cur); pk = None
                for nb in adj[cur]:
                    if nb != prev and ek(cur, nb) not in used: pk = nb; break
                if pk is None:
                    for nb in adj[cur]:
                        if ek(cur, nb) not in used: pk = nb; break
                if pk is None: break
                used.add(ek(cur, pk)); prev = cur; cur = pk
            if len(lp) >= 4: loops.append(lp)

    polys = []
    for l in loops:
        p = dp(chaikin(l, 2), 0.5)
        if len(p) >= 3: polys.append(p)
    # Add the plate outline as an explicit outermost region. The contour tracer only emits
    # loops where the raised mask CHANGES, so a white background that reaches the plate edge
    # produces no perimeter loop and the solid base under it would be missing. This rectangle
    # (forced to base height below) guarantees a full solid base WITHOUT any raised rim.
    plate_rect = np.array([[1, 1], [1, COLS+1], [ROWS+1, COLS+1], [ROWS+1, 1]], float)
    polys.append(plate_rect); plate_idx = len(polys) - 1
    areas = np.array([abs(sarea(p)) for p in polys])

    def rep(p):
        for k in range(0, len(p), max(1, len(p)//12)):
            a = p[k]; b = p[(k+1) % len(p)]; mid = (a+b)/2
            nr = np.array([-(b[1]-a[1]), (b[0]-a[0])]); nr = nr/(np.hypot(*nr)+1e-9)
            for sc in (0.3, 0.6, 1.0, 2.0):
                for sg in (1, -1):
                    q = mid+sg*sc*nr
                    if pip((q[0], q[1]), p): return (q[0], q[1])
        c = p.mean(0); return (c[0], c[1])
    reps = [rep(p) for p in polys]
    parent = [-1]*len(polys); pa = [1e18]*len(polys)
    for i in range(len(polys)):
        for j in range(len(polys)):
            if j != i and pip(reps[i], polys[j]) and areas[j] < pa[i]:
                pa[i] = areas[j]; parent[i] = j
    # the plate rectangle is always the root; every otherwise-top-level region nests in it
    parent[plate_idx] = -1
    for i in range(len(polys)):
        if i != plate_idx and parent[i] == -1: parent[i] = plate_idx
    children = [[j for j in range(len(polys)) if parent[j] == i] for i in range(len(polys))]

    rtris = []; cb = []
    for i, p in enumerate(polys):
        tl = triangulate(p, [polys[j] for j in children[i]]); rtris.append(tl); ab = aw = 0.0
        # AREA-weighted vote (not per-triangle count). A complex region's boundary traces
        # the silhouette of the raised line-work, so earcut emits hundreds of tiny sliver
        # triangles hugging that edge whose centroids round onto raised pixels. Counting
        # triangles equally lets those slivers outvote the few huge interior triangles and
        # a large background region flips to "raised" (solid-fill artifact). Weighting by
        # triangle area makes the true interior decide.
        for a, b, c in tl:
            cx = (a[0]+b[0]+c[0])/3; cy = (a[1]+b[1]+c[1])/3
            tarea = abs((b[0]-a[0])*(c[1]-a[1]) - (c[0]-a[0])*(b[1]-a[1])) * 0.5
            yi = min(max(int(cy), 0), ROWS-1); xi = min(max(int(cx), 0), COLS-1)
            if m[yi, xi]: ab += tarea
            else: aw += tarea
        cb.append(ab >= aw)
    cb[plate_idx] = False        # the plate outline is the base reference: always at base height

    zt = base_mm + relief_mm; zb = base_mm
    def hof(i): return zt if cb[i] else zb
    # Merge same-height nesting: a region at the same height as its parent only produces
    # coplanar duplicate faces and the T-junction seams that break watertightness. Drop it
    # (the parent covers its area) and reparent its children to the nearest kept ancestor, so
    # every height step is represented exactly once -> one clean manifold solid.
    keep = [True]*len(polys)
    for i in range(len(polys)):
        if parent[i] != -1 and hof(i) == hof(parent[i]): keep[i] = False
    keep[plate_idx] = True
    def eff_parent(i):
        p = parent[i]
        while p != -1 and not keep[p]: p = parent[p]
        return p
    eff_children = [[] for _ in range(len(polys))]
    for j in range(len(polys)):
        if keep[j]:
            ep = eff_parent(j)
            if ep != -1: eff_children[ep].append(j)
    tris = []
    def tri(a, b, c): tris.append((a, b, c))
    def quad(a, b, c, d): tri(a, b, c); tri(a, c, d)
    def XY(v): return (v[1]*pitch, (ROWS-v[0])*pitch)
    # bottom: the whole plate has material down to z=0 everywhere, so the underside is one
    # clean rectangle with no holes -> render it once, avoiding per-region triangulation slivers.
    for A, B, C in triangulate(polys[plate_idx], []):
        a = (A[0]*pitch, (ROWS-A[1])*pitch); b = (B[0]*pitch, (ROWS-B[1])*pitch); c = (C[0]*pitch, (ROWS-C[1])*pitch)
        tri((a[0], a[1], 0), (c[0], c[1], 0), (b[0], b[1], 0))
    for i, p in enumerate(polys):                       # tops (stepped surface) per kept region
        if not keep[i]: continue
        tl = triangulate(p, [polys[j] for j in eff_children[i]]); h = hof(i)
        for A, B, C in tl:
            a = (A[0]*pitch, (ROWS-A[1])*pitch); b = (B[0]*pitch, (ROWS-B[1])*pitch); c = (C[0]*pitch, (ROWS-C[1])*pitch)
            tri((a[0], a[1], h), (b[0], b[1], h), (c[0], c[1], h))
    for i, p in enumerate(polys):
        if not keep[i]: continue
        ep = eff_parent(i)
        hi_in = hof(i); ho = hof(ep) if ep != -1 else 0.0
        if hi_in == ho: continue
        lo = min(hi_in, ho); hi = max(hi_in, ho); n = len(p)
        for k in range(n):
            a = XY(p[k]); b = XY(p[(k+1) % n])
            quad((a[0], a[1], lo), (b[0], b[1], lo), (b[0], b[1], hi), (a[0], a[1], hi))

    def nrm(a, b, c):
        u = np.subtract(b, a); v = np.subtract(c, a); nn = np.cross(u, v); L = np.linalg.norm(nn) or 1.0
        return nn/L
    with open(out_stl, 'wb') as fo:
        fo.write(b'\0'*80); fo.write(struct.pack('<I', len(tris)))
        for a, b, c in tris:
            fo.write(struct.pack('<12fH', *nrm(a, b, c), *a, *b, *c, 0))
    # finalize with the SAME interpreter (so numpy/Pillow from this env are available); surface
    # failures instead of silently shipping an un-welded, non-watertight mesh.
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(HERE, 'finalize_mesh.py'), out_stl],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write('WARNING: finalize_mesh failed (mesh not watertight):\n' + r.stderr)

    if preview:
        val = Image.new('L', (COLS, ROWS), 255); dv = ImageDraw.Draw(val)
        for i, tl in enumerate(rtris):
            if not cb[i]: continue
            for a, b, c in tl:
                dv.polygon([(a[0], a[1]), (b[0], b[1]), (c[0], c[1])], fill=0)
        png_out = os.path.splitext(out_stl)[0] + '_preview.png'
        arr = np.array(val).astype(float); rs = arr < 127
        edge = np.array(Image.fromarray((rs*255).astype('uint8')).filter(ImageFilter.FIND_EDGES)).astype(float)/255
        Image.fromarray((np.where(rs, 30, 235).astype(float)-edge*50).clip(0, 255).astype('uint8')).save(png_out)
    return (COLS*pitch, ROWS*pitch, zt)


def _argval(flag, default, cast=float):
    if flag in sys.argv:
        return cast(sys.argv[sys.argv.index(flag)+1])
    return default

if __name__ == '__main__':
    png, out = sys.argv[1], sys.argv[2]
    t0 = time.time()
    w, h, z = build(png, out,
                    size_mm=_argval('--size', 230.0),
                    base_mm=_argval('--base', 2.0),
                    relief_mm=_argval('--relief', 2.0),
                    mirror=bool(int(_argval('--mirror', 1, int))),
                    raised=_argval('--raised', 'dark', str))
    print(f'OK {os.path.basename(out)}  {w:.1f} x {h:.1f} x {z:.1f} mm  ({time.time()-t0:.1f}s)')
