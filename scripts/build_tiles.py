#!/usr/bin/env python3
"""
build_tiles.py - cut detail regions out of the source image and build them as
standalone watertight test tiles at the SAME physical scale as the full plate.
Print these first to see exactly how the trickiest areas (eyes, fine strands)
come out before committing to the big plate.

Usage:
  python3 build_tiles.py INPUT.png OUTDIR --size 230 --base 2 --relief 2 \
      --crop NAME x0 y0 x1 y1  [--crop NAME2 ...]

  --size/--base/--relief must match the full plate so the tiles are true-scale.
  Each --crop is a pixel box (x0 y0 x1 y1) in the SOURCE image.
  Tiles are built UN-mirrored so they visually match the source for easy comparison.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_relief import build

def _argval(flag, default, cast=float):
    return cast(sys.argv[sys.argv.index(flag)+1]) if flag in sys.argv else default

if __name__ == '__main__':
    png, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    size = _argval('--size', 230.0); base = _argval('--base', 2.0); relief = _argval('--relief', 2.0)
    # find the full-plate long-side pixel count to derive the production pitch
    from build_relief import load_gray
    g = load_gray(png); long_px = max(g.shape)
    px_mm = size / long_px            # mm per source pixel at the chosen plate size
    crops = []
    a = sys.argv
    i = 0
    while i < len(a):
        if a[i] == '--crop':
            crops.append((a[i+1], int(a[i+2]), int(a[i+3]), int(a[i+4]), int(a[i+5]))); i += 6
        else:
            i += 1
    if not crops:
        print('no --crop given'); sys.exit(1)
    for name, x0, y0, x1, y1 in crops:
        # pick a factor so the crop keeps fine detail (~<=900 px long side after downsample)
        crop_long = max(x1-x0, y1-y0)
        factor = max(1, int(round(crop_long/900)))
        # tile physical size must use the SAME px->mm as the full plate:
        tile_size_mm = max(x1-x0, y1-y0) * px_mm
        out = os.path.join(outdir, f'test_{name}.stl')
        t0 = time.time()
        w, h, z = build(png, out, size_mm=tile_size_mm, base_mm=base, relief_mm=relief,
                        mirror=False, raised='dark', factor=factor, crop=(x0, y0, x1, y1))
        print(f'  test_{name}.stl  {w:.1f} x {h:.1f} x {z:.1f} mm  ({time.time()-t0:.1f}s)')
