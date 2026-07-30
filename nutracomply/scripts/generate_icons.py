"""
Regenerate the Regbite favicon / app-icon set from the logo geometry.

Run manually; the outputs are committed. Not imported by the app.

    python scripts/generate_icons.py

Why this exists
---------------
The old favicon.ico was a single 16x16 downscale of the full 24-dot logo grid:
22 dark pixels out of 256, which reads as grey noise rather than a mark. A
24-dot halftone simply cannot survive 16px.

The fix is to step the mark down by size, and to invert at 16px so the tile
carries the ink instead of the dots:

    16px  -> 4 core dots, light on a solid ink tile   (~40% ink coverage)
    32px  -> 16 dots (outer ring dropped), ink on transparent
    48px+ -> all 24 dots, ink on transparent

Geometry matches app/templates/partials/_brand.html exactly.
"""

from pathlib import Path

from PIL import Image, ImageDraw

INK = (18, 18, 18)        # #121212 — the logo's only colour
LIGHT = (250, 250, 250)   # #FAFAFA

# Mark bounding box in source-logo pixel space.
VB_W, VB_H = 394.0, 415.0

# (cx, cy, r) — 6x6 grid, corners removed, diameters in a 1:2:3 ratio.
OUTER = [(155.5, 10.5), (238.5, 10.5), (10.5, 164), (383.5, 164),
         (10.5, 251), (383.5, 251), (155.5, 404.5), (238.5, 404.5)]
MID = [(72.5, 76.5), (155.5, 76.5), (238.5, 76.5), (321.5, 76.5),
       (72.5, 164), (321.5, 164), (72.5, 251), (321.5, 251),
       (72.5, 338.5), (155.5, 338.5), (238.5, 338.5), (321.5, 338.5)]
CORE = [(155.5, 164), (238.5, 164), (155.5, 251), (238.5, 251)]

R_OUTER, R_MID, R_CORE = 10.5, 20.5, 31.5

SS = 8  # supersample factor, downsampled with LANCZOS for clean antialiasing


def _dots(level: str):
    """level: 'full' (24) | 'mid' (16) | 'core' (4)"""
    if level == "core":
        return [(x, y, R_CORE) for x, y in CORE]
    d = [(x, y, R_MID) for x, y in MID] + [(x, y, R_CORE) for x, y in CORE]
    if level == "full":
        d = [(x, y, R_OUTER) for x, y in OUTER] + d
    return d


def render(size, level="full", fg=INK, bg=None, pad=0.0, tile_radius=None):
    """
    size         output edge in px (square)
    level        which dot set to draw
    fg           dot colour
    bg           None -> transparent; RGB tuple -> opaque background
    pad          fraction of the canvas to leave empty around the mark
    tile_radius  if set (fraction of size), draw a rounded-rect tile in `bg`
    """
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if bg is not None:
        if tile_radius:
            d.rounded_rectangle([0, 0, S - 1, S - 1],
                                radius=int(S * tile_radius), fill=bg + (255,))
        else:
            d.rectangle([0, 0, S, S], fill=bg + (255,))

    dots = _dots(level)
    # Fit the drawn dots' own bounding box (not the full grid) into the canvas,
    # so the 'core' variant scales up to fill rather than sitting tiny in the middle.
    xs0 = min(x - r for x, _, r in dots); xs1 = max(x + r for x, _, r in dots)
    ys0 = min(y - r for _, y, r in dots); ys1 = max(y + r for _, y, r in dots)
    bw, bh = xs1 - xs0, ys1 - ys0

    avail = S * (1.0 - 2 * pad)
    scale = avail / max(bw, bh)
    off_x = (S - bw * scale) / 2 - xs0 * scale
    off_y = (S - bh * scale) / 2 - ys0 * scale

    for cx, cy, r in dots:
        x, y, rr = cx * scale + off_x, cy * scale + off_y, r * scale
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fg + (255,))

    return img.resize((size, size), Image.LANCZOS)


def main():
    static = Path(__file__).resolve().parent.parent / "app" / "static"
    img_dir = static / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    # ── Browser favicons ────────────────────────────────────────────────
    # 16px inverts: 4 light dots on a solid ink tile. This is the key move —
    # ~40% ink coverage versus ~8% for the old full-grid downscale.
    f16 = render(16, "core", fg=LIGHT, bg=INK, pad=0.17, tile_radius=0.18)
    f32 = render(32, "mid", pad=0.06)
    f48 = render(48, "full", pad=0.04)

    f16.save(static / "favicon-16x16.png")
    f32.save(static / "favicon-32x32.png")
    f48.save(static / "favicon-48x48.png")

    # Multi-resolution ICO. The old file held a single 16x16, which is why
    # every context got the same bad downscale.
    f48.save(static / "favicon.ico", format="ICO",
             sizes=[(16, 16), (32, 32), (48, 48)])

    # ── Apple touch icon: opaque, no alpha (iOS composites black otherwise) ──
    apple = render(180, "full", bg=LIGHT, pad=0.12).convert("RGB")
    apple.save(static / "apple-touch-icon.png")

    # ── PWA icons ───────────────────────────────────────────────────────
    # 'any' stays transparent; 'maskable' must be opaque and inset into the
    # Android safe zone. Declaring "any maskable" on a transparent PNG is what
    # produced the black-blob icon.
    render(192, "full", pad=0.06).save(img_dir / "favicon-192.png")
    render(512, "full", pad=0.06).save(img_dir / "favicon-512.png")
    render(192, "full", bg=INK, fg=LIGHT, pad=0.20).convert("RGB").save(img_dir / "favicon-192-maskable.png")
    render(512, "full", bg=INK, fg=LIGHT, pad=0.20).convert("RGB").save(img_dir / "favicon-512-maskable.png")

    for p in ["favicon-16x16.png", "favicon-32x32.png", "favicon-48x48.png",
              "favicon.ico", "apple-touch-icon.png"]:
        print(f"  wrote {(static / p).relative_to(static.parent.parent)}")
    for p in ["favicon-192.png", "favicon-512.png",
              "favicon-192-maskable.png", "favicon-512-maskable.png"]:
        print(f"  wrote {(img_dir / p).relative_to(static.parent.parent)}")


if __name__ == "__main__":
    main()
