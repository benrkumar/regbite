"""
Generate editorial cover images for the trending FSSAI blog posts.

Why these are drawn rather than sourced: the photographs in the news coverage
of these stories are licensed press images (agency and publication owned).
Republishing them on a commercial blog is infringement, and hotlinking is both
infringement and fragile. These covers are original, carry no licensing risk,
and match the site's design language — ink #121212, the #2B4874 -> #4F46E5
gradient, and the logo's dot-grid motif.

Output: 1200x630 (the Open Graph standard), so each doubles as the post's
featured image and its social share card.

    python scripts/generate_blog_covers.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
SS = 2                      # supersample for clean edges

INK = (18, 18, 18)
LIGHT = (250, 250, 250)
MUTED = (154, 154, 161)
B1 = (43, 72, 116)          # brand-1  #2B4874
B2 = (79, 70, 229)          # brand-2  #4F46E5
BAD = (220, 92, 92)
OK = (16, 185, 129)
WARN = (245, 158, 11)

FONTS = Path("C:/Windows/Fonts")


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient_band(d, box, c1, c2, horizontal=True):
    x0, y0, x1, y1 = box
    n = (x1 - x0) if horizontal else (y1 - y0)
    for i in range(n):
        t = i / max(1, n - 1)
        c = lerp(c1, c2, t)
        if horizontal:
            d.line([(x0 + i, y0), (x0 + i, y1)], fill=c)
        else:
            d.line([(x0, y0 + i), (x1, y0 + i)], fill=c)


def radial_glow(img, cx, cy, radius, colour, strength=0.30):
    """Soft indigo bloom, drawn as concentric alpha rings."""
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    g = ImageDraw.Draw(glow, "RGBA")
    steps = 60
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(radius * t)
        a = int(255 * strength * (1 - t) ** 2)
        g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour + (a,))
    img.alpha_composite(glow)


def dot_grid(d, ox, oy, cell, colour, alpha_rows):
    """The logo's 6x6 grid, corners dropped — brand continuity marker."""
    for ry, row in enumerate(alpha_rows):
        for rx, sz in enumerate(row):
            if not sz:
                continue
            cx, cy = ox + rx * cell, oy + ry * cell
            r = sz
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour)


GRID = [
    [0, 0, 4, 4, 0, 0],
    [0, 8, 8, 8, 8, 0],
    [4, 8, 13, 13, 8, 4],
    [4, 8, 13, 13, 8, 4],
    [0, 8, 8, 8, 8, 0],
    [0, 0, 4, 4, 0, 0],
]


def wrap(d, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def base_canvas():
    """
    Returns an RGB image on purpose.

    Pillow only alpha-BLENDS an ImageDraw(mode="RGBA") operation when the target
    image is RGB. Draw the same translucent fill onto an RGBA image and it
    REPLACES the pixel, alpha included — which is why every frosted panel first
    came out as solid white with white text on top of it. So: composite the
    glows while we still have an alpha channel, then flatten to RGB and do all
    subsequent drawing against that.
    """
    img = Image.new("RGBA", (W * SS, H * SS), INK + (255,))
    radial_glow(img, int(W * SS * 0.72), int(H * SS * 0.30), int(W * SS * 0.55), B2, 0.34)
    radial_glow(img, int(W * SS * 0.10), int(H * SS * 0.95), int(W * SS * 0.40), B1, 0.30)
    return img.convert("RGB")


def finish(img, tag, headline, sub, draw_art):
    # mode="RGBA" on an RGB image = real alpha blending (see base_canvas).
    d = ImageDraw.Draw(img, "RGBA")
    s = SS

    f_tag = font("segoeuib.ttf", 20 * s)
    f_h = font("seguibl.ttf", 62 * s)
    f_sub = font("segoeuib.ttf", 25 * s)
    f_brand = font("seguibl.ttf", 27 * s)

    # art panel on the right
    draw_art(d, img, s)

    # eyebrow tag
    tx, ty = 64 * s, 70 * s
    tw = d.textlength(tag, font=f_tag)
    d.rounded_rectangle([tx, ty, tx + tw + 34 * s, ty + 42 * s],
                        radius=21 * s, fill=(255, 255, 255, 30),
                        outline=(255, 255, 255, 90), width=2 * s)
    d.ellipse([tx + 15 * s, ty + 18 * s, tx + 21 * s, ty + 24 * s], fill=B2)
    d.text((tx + 28 * s, ty + 9 * s), tag, font=f_tag, fill=LIGHT)

    # headline
    y = 150 * s
    for line in wrap(d, headline, f_h, 620 * s):
        d.text((64 * s, y), line, font=f_h, fill=LIGHT)
        y += 74 * s

    # subhead
    y += 12 * s
    for line in wrap(d, sub, f_sub, 600 * s):
        d.text((64 * s, y), line, font=f_sub, fill=MUTED)
        y += 34 * s

    # brand lockup, bottom-left
    by = H * s - 92 * s
    dot_grid(d, 66 * s, by + 4 * s, 11 * s, LIGHT, GRID)
    d.text((150 * s, by + 6 * s), "regbite", font=f_brand, fill=LIGHT)
    d.text((150 * s, by + 44 * s), "Navneet · Chief Regulatory Expert",
           font=font("segoeuib.ttf", 17 * s), fill=MUTED)

    # gradient rule along the bottom
    gradient_band(d, (0, H * s - 10 * s, W * s, H * s), B1, B2)

    return img.resize((W, H), Image.LANCZOS)


# ── per-article artwork ─────────────────────────────────────────────────────

def art_energy(d, img, s):
    """A can with the words ENERGY DRINK struck through."""
    cx, cy = 900 * s, 300 * s
    w, h = 150 * s, 300 * s
    d.rounded_rectangle([cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2],
                        radius=26 * s, fill=(255, 255, 255, 18),
                        outline=LIGHT + (200,), width=3 * s)
    # can lid
    d.rounded_rectangle([cx - w // 2 + 12 * s, cy - h // 2 - 10 * s,
                         cx + w // 2 - 12 * s, cy - h // 2 + 16 * s],
                        radius=10 * s, fill=LIGHT + (170,))
    # label band
    d.rectangle([cx - w // 2, cy - 34 * s, cx + w // 2, cy + 40 * s], fill=(255, 255, 255, 30))
    f = font("seguibl.ttf", 22 * s)
    for i, word in enumerate(["ENERGY", "DRINK"]):
        tw = d.textlength(word, font=f)
        d.text((cx - tw / 2, cy - 28 * s + i * 30 * s), word, font=f, fill=LIGHT)
    # strike-through
    d.line([cx - w // 2 - 26 * s, cy + 52 * s, cx + w // 2 + 26 * s, cy - 46 * s],
           fill=BAD, width=9 * s)
    # 90-day chip
    chip = "90 DAYS"
    fc = font("seguibl.ttf", 21 * s)
    tw = d.textlength(chip, font=fc)
    bx, by = cx - tw / 2 - 20 * s, cy + h // 2 + 30 * s
    d.rounded_rectangle([bx, by, bx + tw + 40 * s, by + 44 * s], radius=22 * s, fill=BAD)
    d.text((bx + 20 * s, by + 10 * s), chip, font=fc, fill=(255, 255, 255))


def art_liquor(d, img, s):
    """A bottle beside a calendar whose date has moved."""
    cx, cy = 900 * s, 290 * s
    # bottle
    d.rounded_rectangle([cx - 34 * s, cy - 150 * s, cx + 34 * s, cy - 96 * s],
                        radius=14 * s, fill=(255, 255, 255, 22), outline=LIGHT + (190,), width=3 * s)
    d.rounded_rectangle([cx - 74 * s, cy - 100 * s, cx + 74 * s, cy + 150 * s],
                        radius=26 * s, fill=(255, 255, 255, 18), outline=LIGHT + (200,), width=3 * s)
    d.rectangle([cx - 74 * s, cy - 20 * s, cx + 74 * s, cy + 66 * s], fill=(255, 255, 255, 32))
    # a struck date on the label
    f = font("seguibl.ttf", 20 * s)
    old, new = "1 JAN", "1 JUL"
    tw = d.textlength(old, font=f)
    d.text((cx - tw / 2, cy - 12 * s), old, font=f, fill=MUTED)
    d.line([cx - tw / 2 - 8 * s, cy - 2 * s, cx + tw / 2 + 8 * s, cy - 2 * s], fill=BAD, width=4 * s)
    tw2 = d.textlength(new, font=f)
    d.text((cx - tw2 / 2, cy + 30 * s), new, font=f, fill=LIGHT)
    # enforcement stamp
    chip = "ENFORCED"
    fc = font("seguibl.ttf", 20 * s)
    tw = d.textlength(chip, font=fc)
    bx, by = cx - tw / 2 - 20 * s, cy + 180 * s
    d.rounded_rectangle([bx, by, bx + tw + 40 * s, by + 42 * s], radius=21 * s, fill=BAD)
    d.text((bx + 20 * s, by + 9 * s), chip, font=fc, fill=(255, 255, 255))


def art_protein(d, img, s):
    """A tub with a declared-vs-measured bar comparison."""
    cx, cy = 890 * s, 270 * s
    d.rounded_rectangle([cx - 96 * s, cy - 110 * s, cx + 96 * s, cy + 120 * s],
                        radius=22 * s, fill=(255, 255, 255, 18), outline=LIGHT + (200,), width=3 * s)
    d.rounded_rectangle([cx - 78 * s, cy - 136 * s, cx + 78 * s, cy - 104 * s],
                        radius=14 * s, fill=LIGHT + (170,))
    f = font("seguibl.ttf", 19 * s)
    lbl = "PROTEIN"
    tw = d.textlength(lbl, font=f)
    d.text((cx - tw / 2, cy - 78 * s), lbl, font=f, fill=LIGHT)

    # declared vs measured bars
    fb = font("segoeuib.ttf", 16 * s)
    bx = cx - 68 * s
    for i, (name, frac, col) in enumerate([("DECLARED", 1.0, LIGHT), ("MEASURED", 0.68, BAD)]):
        by = cy - 26 * s + i * 52 * s
        d.text((bx, by), name, font=fb, fill=MUTED)
        d.rounded_rectangle([bx, by + 22 * s, bx + 136 * s, by + 36 * s],
                            radius=7 * s, fill=(255, 255, 255, 34))
        d.rounded_rectangle([bx, by + 22 * s, bx + int(136 * s * frac), by + 36 * s],
                            radius=7 * s, fill=col)


def art_fopnl(d, img, s):
    """A front-of-pack panel with an HFSS mark landing on it."""
    cx, cy = 895 * s, 285 * s
    d.rounded_rectangle([cx - 118 * s, cy - 150 * s, cx + 118 * s, cy + 150 * s],
                        radius=22 * s, fill=(255, 255, 255, 16), outline=LIGHT + (190,), width=3 * s)
    f = font("segoeuib.ttf", 16 * s)
    d.text((cx - 96 * s, cy - 126 * s), "FRONT OF PACK", font=f, fill=MUTED)
    # placeholder content lines
    for i in range(3):
        y = cy - 92 * s + i * 20 * s
        d.rounded_rectangle([cx - 96 * s, y, cx + 40 * s - i * 26 * s, y + 9 * s],
                            radius=5 * s, fill=(255, 255, 255, 46))
    # the mark
    mx, my = cx, cy + 34 * s
    d.rounded_rectangle([mx - 84 * s, my - 46 * s, mx + 84 * s, my + 76 * s],
                        radius=16 * s, fill=WARN)
    fw = font("seguibl.ttf", 30 * s)
    for i, line in enumerate(["HIGH IN", "SUGAR"]):
        tw = d.textlength(line, font=fw)
        d.text((mx - tw / 2, my - 34 * s + i * 34 * s), line, font=fw, fill=(40, 30, 0))
    # "pending" chip
    chip = "NOT YET NOTIFIED"
    fc = font("seguibl.ttf", 17 * s)
    tw = d.textlength(chip, font=fc)
    bx, by = cx - tw / 2 - 18 * s, cy + 176 * s
    d.rounded_rectangle([bx, by, bx + tw + 36 * s, by + 38 * s], radius=19 * s,
                        fill=(255, 255, 255, 30), outline=LIGHT + (140,), width=2 * s)
    d.text((bx + 18 * s, by + 8 * s), chip, font=fc, fill=LIGHT)



def art_licence(d, img, s):
    """A licence card whose expiry has become an infinity symbol."""
    cx, cy = 895 * s, 285 * s
    d.rounded_rectangle([cx - 120 * s, cy - 86 * s, cx + 120 * s, cy + 86 * s],
                        radius=18 * s, fill=(255, 255, 255, 18),
                        outline=LIGHT + (200,), width=3 * s)
    f = font("segoeuib.ttf", 15 * s)
    d.text((cx - 100 * s, cy - 66 * s), "FSSAI LICENCE", font=f, fill=MUTED)
    fn = font("seguibl.ttf", 21 * s)
    d.text((cx - 100 * s, cy - 40 * s), "1001904200 0241", font=fn, fill=LIGHT)
    d.text((cx - 100 * s, cy + 6 * s), "VALID UNTIL", font=f, fill=MUTED)
    # infinity, drawn as two rings
    ix, iy = cx - 96 * s, cy + 44 * s
    for off in (0, 30 * s):
        d.ellipse([ix + off, iy, ix + off + 30 * s, iy + 26 * s],
                  outline=OK, width=5 * s)
    chip = "FEE STILL DUE"
    fc = font("seguibl.ttf", 18 * s)
    tw = d.textlength(chip, font=fc)
    bx, by = cx - tw / 2 - 18 * s, cy + 116 * s
    d.rounded_rectangle([bx, by, bx + tw + 36 * s, by + 40 * s], radius=20 * s, fill=WARN)
    d.text((bx + 18 * s, by + 9 * s), chip, font=fc, fill=(45, 33, 0))


def art_claims(d, img, s):
    """A pack panel with 100% NATURAL struck through."""
    cx, cy = 895 * s, 280 * s
    d.rounded_rectangle([cx - 110 * s, cy - 130 * s, cx + 110 * s, cy + 130 * s],
                        radius=20 * s, fill=(255, 255, 255, 16),
                        outline=LIGHT + (190,), width=3 * s)
    fw = font("seguibl.ttf", 27 * s)
    for i, line in enumerate(["100%", "NATURAL"]):
        tw = d.textlength(line, font=fw)
        d.text((cx - tw / 2, cy - 56 * s + i * 34 * s), line, font=fw, fill=LIGHT)
    d.line([cx - 96 * s, cy + 6 * s, cx + 96 * s, cy - 44 * s], fill=BAD, width=8 * s)
    fs = font("segoeuib.ttf", 15 * s)
    for i, t in enumerate(["substantiate", "or remove"]):
        tw = d.textlength(t, font=fs)
        d.text((cx - tw / 2, cy + 44 * s + i * 22 * s), t, font=fs, fill=MUTED)
    chip = "UP TO ₹10 LAKH"
    fc = font("seguibl.ttf", 18 * s)
    tw = d.textlength(chip, font=fc)
    bx, by = cx - tw / 2 - 18 * s, cy + 158 * s
    d.rounded_rectangle([bx, by, bx + tw + 36 * s, by + 40 * s], radius=20 * s, fill=BAD)
    d.text((bx + 18 * s, by + 9 * s), chip, font=fc, fill=(255, 255, 255))


def art_packaging(d, img, s):
    """A bottle with unknown substances migrating out of the wall."""
    cx, cy = 895 * s, 275 * s
    d.rounded_rectangle([cx - 60 * s, cy - 120 * s, cx + 60 * s, cy + 120 * s],
                        radius=22 * s, fill=(255, 255, 255, 16),
                        outline=LIGHT + (200,), width=3 * s)
    d.rounded_rectangle([cx - 34 * s, cy - 142 * s, cx + 34 * s, cy - 114 * s],
                        radius=10 * s, fill=LIGHT + (160,))
    # migrating particles
    for i, (dx, dy, r) in enumerate([(84, -60, 7), (110, -18, 5), (96, 30, 8), (122, 74, 5)]):
        d.ellipse([cx + dx * s - r * s, cy + dy * s - r * s,
                   cx + dx * s + r * s, cy + dy * s + r * s], fill=WARN)
    f = font("seguibl.ttf", 24 * s)
    d.text((cx + 76 * s, cy + 104 * s), "NIAS", font=f, fill=WARN)
    fs = font("segoeuib.ttf", 14 * s)
    d.text((cx + 76 * s, cy + 134 * s), "not in your recipe", font=fs, fill=MUTED)
    chip = "DRAFT"
    fc = font("seguibl.ttf", 18 * s)
    tw = d.textlength(chip, font=fc)
    bx, by = cx - 60 * s, cy + 156 * s
    d.rounded_rectangle([bx, by, bx + tw + 36 * s, by + 40 * s], radius=20 * s,
                        fill=(255, 255, 255, 26), outline=LIGHT + (140,), width=2 * s)
    d.text((bx + 18 * s, by + 9 * s), chip, font=fc, fill=LIGHT)


def art_labelling(d, img, s):
    """A calendar pinned to 1 July."""
    cx, cy = 895 * s, 280 * s
    d.rounded_rectangle([cx - 100 * s, cy - 110 * s, cx + 100 * s, cy + 110 * s],
                        radius=20 * s, fill=(255, 255, 255, 16),
                        outline=LIGHT + (200,), width=3 * s)
    # calendar header band
    d.rounded_rectangle([cx - 100 * s, cy - 110 * s, cx + 100 * s, cy - 62 * s],
                        radius=20 * s, fill=(79, 70, 229, 210))
    fh = font("seguibl.ttf", 20 * s)
    tw = d.textlength("JULY", font=fh)
    d.text((cx - tw / 2, cy - 100 * s), "JULY", font=fh, fill=LIGHT)
    fd = font("seguibl.ttf", 62 * s)
    tw = d.textlength("1", font=fd)
    d.text((cx - tw / 2, cy - 42 * s), "1", font=fd, fill=LIGHT)
    fs = font("segoeuib.ttf", 15 * s)
    tw = d.textlength("every year", font=fs)
    d.text((cx - tw / 2, cy + 40 * s), "every year", font=fs, fill=MUTED)
    chip = "IN FORCE 2027"
    fc = font("seguibl.ttf", 17 * s)
    tw = d.textlength(chip, font=fc)
    bx, by = cx - tw / 2 - 18 * s, cy + 136 * s
    d.rounded_rectangle([bx, by, bx + tw + 36 * s, by + 38 * s], radius=19 * s,
                        fill=(255, 255, 255, 26), outline=LIGHT + (140,), width=2 * s)
    d.text((bx + 18 * s, by + 8 * s), chip, font=fc, fill=LIGHT)


COVERS = [
    ("blog-energy-drink.png", "FSSAI Compliance",
     "The drinks weren’t banned. The word was.",
     "FSSAI orders “energy drink” off the label — and why every “immunity booster” is exposed by the same logic.",
     art_energy),
    ("blog-liquor-crackdown.png", "Enforcement",
     "An extension is not amnesty.",
     "Old Monk, Royal Challenge and Bagpiper variants prohibited weeks after a deadline FSSAI had already moved.",
     art_liquor),
    ("blog-protein.png", "Nutraceuticals",
     "Your declared protein has to survive a lab test.",
     "FSSAI is preparing stricter rules for protein supplements. Four things to fix while it is still cheap.",
     art_protein),
    ("blog-fopnl.png", "Regulatory Intelligence",
     "“Coming soon” since 2022.",
     "Front-of-pack labelling is still un-notified. What to prepare — and what not to spend money on yet.",
     art_fopnl),
    ("blog-licensing.png", "FSSAI Compliance",
     "Perpetual is not permanent.",
     "Licences no longer expire — but the annual fee still falls due, and nothing prompts you any more.",
     art_licence),
    ("blog-claims.png", "Nutraceuticals",
     "“100% Natural” is now a liability.",
     "Absolute claims need unequivocal substantiation. Penalties run to ₹10 lakh per offence.",
     art_claims),
    ("blog-packaging.png", "Regulatory Intelligence",
     "The substances you never added.",
     "FSSAI's draft packaging amendment defines NIAS — and you cannot check them against your own recipe.",
     art_packaging),
    ("blog-labelling.png", "FSSAI Compliance",
     "One deadline for everything.",
     "FSSAI is consolidating labelling enforcement onto 1 July each year. Batch your artwork around it.",
     art_labelling),
]


def main():
    out = Path(__file__).resolve().parent.parent / "app" / "static" / "img" / "blog"
    out.mkdir(parents=True, exist_ok=True)
    for fname, tag, headline, sub, art in COVERS:
        img = finish(base_canvas(), tag, headline, sub, art)
        img.save(out / fname, quality=92)
        print(f"  wrote static/img/blog/{fname}  {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
