# -*- coding: utf-8 -*-
"""Premium 'prestige-drama' thumbnail (PIL, no key).

Cinematic grade (muted, slate-blue shadows + amber light) + vignette + film grain +
letterbox + elegant serif-italic quote with a soft glow + a gold tracked kicker.
A base image (one of the generated frames) plus a short hook -> 1280x720 JPEG.

Fonts are resolved from env or common locations, with a graceful fallback to PIL's
default face so it renders anywhere (deploy should bundle real fonts under
app/assets/fonts and point FABULA_FONT_* at them).
"""
import os, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

W, H = 1280, 720
GOLD = (206, 170, 104)
IVORY = (243, 236, 224)

_SERIF_CANDIDATES = [os.environ.get("FABULA_FONT_SERIF", ""),
                     r"C:\Windows\Fonts\georgiaz.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"]
_KICK_CANDIDATES = [os.environ.get("FABULA_FONT_KICKER", ""),
                    r"C:\Windows\Fonts\georgiab.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]


def _font(candidates, size):
    for p in candidates:
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _fit(draw, candidates, text, target_w, start, mn=18):
    s = start
    while s > mn:
        f = _font(candidates, s)
        if draw.textlength(text, font=f) <= target_w:
            return f
        s -= 2
    return _font(candidates, mn)


def make_thumbnail(base_path, quote_lines, out_path, kicker="", log=lambda m: None):
    im = Image.open(base_path).convert("RGB")
    sw, sh = im.size
    scale = max(W / sw, H / sh)
    nw, nh = int(sw * scale + .5), int(sh * scale + .5)
    im = im.resize((nw, nh), Image.LANCZOS)
    im = im.crop(((nw - W) // 2, int((nh - H) * 0.32), (nw - W) // 2 + W, int((nh - H) * 0.32) + H))

    im = ImageEnhance.Color(im).enhance(0.80)
    im = ImageEnhance.Contrast(im).enhance(1.14)
    im = ImageEnhance.Brightness(im).enhance(0.97)
    r, g, b = im.split(); lum = im.convert("L")
    sm = lum.point(lambda x: int((1 - x / 255) ** 1.5 * 255))
    hm = lum.point(lambda x: int((x / 255) ** 1.5 * 255))
    add = lambda ch, m, a: ImageChops.add(ch, m.point(lambda x: int(x / 255 * a)))
    sub = lambda ch, m, a: ImageChops.subtract(ch, m.point(lambda x: int(x / 255 * a)))
    b = add(b, sm, 26); r = sub(r, sm, 14)
    r = add(r, hm, 20); g = add(g, hm, 8); b = sub(b, hm, 18)
    im = Image.merge("RGB", (r, g, b))

    vig = Image.new("L", (W, H), 0); vd = ImageDraw.Draw(vig)
    vd.ellipse([-W * 0.28, -H * 0.30, W * 1.28, H * 1.34], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(180))
    im = Image.composite(im, ImageEnhance.Brightness(im).enhance(0.42), vig)

    random.seed(7)
    n = Image.effect_noise((W, H), 16).convert("L").point(lambda x: int((x - 128) * 0.12 + 128))
    im = ImageChops.overlay(im, Image.merge("RGB", (n, n, n)))

    scrim = Image.new("L", (1, H), 0)
    for y in range(H):
        t = max(0.0, (y - H * 0.40) / (H * 0.60)); scrim.putpixel((0, y), int(240 * (t ** 1.5)))
    scrim = scrim.resize((W, H))
    lg = Image.new("L", (W, 1), 0)
    for x in range(W):
        t = max(0.0, 1 - x / (W * 0.62)); lg.putpixel((x, 0), int(120 * (t ** 1.6)))
    scrim = ImageChops.lighter(scrim, lg.resize((W, H)))
    im = Image.composite(Image.new("RGB", (W, H), (10, 9, 14)), im, scrim)

    bar = 26; d0 = ImageDraw.Draw(im)
    d0.rectangle([0, 0, W, bar], fill=(0, 0, 0)); d0.rectangle([0, H - bar, W, H], fill=(0, 0, 0))
    draw = ImageDraw.Draw(im, "RGBA")

    def soft(x, y, text, font, fill, gr=12, stroke=1):
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        ld.text((x, y), text, font=font, fill=(0, 0, 0, 235), stroke_width=stroke + 3, stroke_fill=(0, 0, 0, 235))
        blur = layer.filter(ImageFilter.GaussianBlur(gr)); im.paste(blur, (0, 0), blur)
        ImageDraw.Draw(im, "RGBA").text((x, y), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=(12, 10, 8, 255))

    def tracked(x, y, text, font, fill, tr, gr=9):
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        cx = x
        for c in text:
            ld.text((cx, y), c, font=font, fill=(0, 0, 0, 230), stroke_width=4, stroke_fill=(0, 0, 0, 230))
            cx += ld.textlength(c, font=font) + tr
        blur = layer.filter(ImageFilter.GaussianBlur(gr)); im.paste(blur, (0, 0), blur)
        d2 = ImageDraw.Draw(im, "RGBA"); cx = x
        for c in text:
            d2.text((cx, y), c, font=font, fill=fill); cx += d2.textlength(c, font=font) + tr
        return cx

    M = 66; BOTTOM = H - bar - 40
    if isinstance(quote_lines, str):
        quote_lines = _wrap(quote_lines)
    l1, l2 = (quote_lines + ["", ""])[:2]
    tw = W - 2 * M
    fs = min(_fit(draw, _SERIF_CANDIDATES, l1 or "x", tw, 118).size,
             _fit(draw, _SERIF_CANDIDATES, l2 or "x", tw, 118).size)
    f1 = _font(_SERIF_CANDIDATES, fs); lh = int(fs * 1.06)
    y2 = BOTTOM - lh; y1 = y2 - lh
    if l1: soft(M, y1, l1, f1, IVORY)
    if l2: soft(M, y2, l2, f1, IVORY)
    if kicker:
        kf = _font(_KICK_CANDIDATES, 30); ky = y1 - 58
        endx = tracked(M, ky, kicker, kf, GOLD + (255,), 6)
        ImageDraw.Draw(im, "RGBA").line([M, ky + kf.size + 16, endx - 6, ky + kf.size + 16], fill=GOLD + (255,), width=2)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.convert("RGB").save(out_path, quality=94)
    log(f"thumbnail -> {os.path.basename(out_path)}")
    return out_path


def _wrap(text, max_len=18):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_len:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines[:2] if lines else [text]
