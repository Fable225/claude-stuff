#!/usr/bin/env python3
"""FX戦士くるみちゃん MAD — 「致瞬息萬變之物，及亙古不變之物」 (v2)

Frame-by-frame renderer (numpy + OpenCV + Pillow) synced to the osu! beatmap
of INTERNET YAMERO.

    python3 render.py still 150.2 out.png      # one frame
    python3 render.py chunk 0 4 out_dir        # render chunk k of n to mp4
    python3 render.py all out.mp4              # everything (multi-process)
"""
import math
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.environ.get("MAD_ASSETS", os.path.join(HERE, "assets"))
W, H, FPS = 1920, 1080, int(os.environ.get("MAD_FPS", 60))
DUR = 243.67
NF = int(DUR * FPS)

BAR = 60.0 / 185 * 4
BEAT = BAR / 4
T0 = 1.778


def bt(b):
    return T0 + b * BAR


def tb(t):
    return (t - T0) / BAR


# ════════════════════════ beatmap ════════════════════════
def load_map():
    sec, tp, ho = None, [], []
    for l in open(os.path.join(ASSETS, "map.osu"), encoding="utf8").read().split("\n"):
        l = l.strip()
        if l.startswith("["):
            sec = l
            continue
        if not l:
            continue
        p = l.split(",")
        if sec == "[TimingPoints]":
            tp.append((float(p[0]) / 1000, int(p[7]) & 1))
        elif sec == "[HitObjects]":
            ho.append(int(p[2]) / 1000)
    flashes, k = [], None
    for t, ki in tp:
        if ki and k is None:
            k = t
        if not ki and k is not None:
            if t - k < 1.5:
                flashes.append(k)
            k = None
    return np.array(ho), np.array(flashes)


HITS, FLASHES = load_map()


def env(times, t, tau):
    i = np.searchsorted(times, t + 1e-4) - 1
    if i < 0:
        return 0.0
    return math.exp(-(t - times[i]) / tau)


def pulse(t, tau=0.16):
    return env(HITS, t, tau)


def flash_env(t, tau=0.10):
    return env(FLASHES, t, tau)


def beat_env(t, tau=0.14):
    ph = ((t - T0) / BEAT) % 1.0
    return math.exp(-ph * BEAT / tau)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease5(x):
    x = clamp(x)
    return 1 - (1 - x) ** 5


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def back(x, s=1.9):
    """ease-out with overshoot (pop)"""
    x = clamp(x) - 1
    return 1 + x * x * ((s + 1) * x + s)


def lerp(a, b, x):
    return a + (b - a) * x


def rnd(*k):
    h = 0.0
    for i, v in enumerate(k):
        h += math.sin(v * 12.9898 + i * 78.233 + 1.0) * 43758.5453
    return h - math.floor(h)


# ════════════════════════ palette (BGR) ════════════════════════
def C(hexs):
    hexs = hexs.lstrip("#")
    return (int(hexs[4:6], 16), int(hexs[2:4], 16), int(hexs[0:2], 16))


PINK = C("ff6fa5")
PINK_L = C("ffc3da")
CREAM = C("fff6d6")
CYAN = C("7fe3e0")
MINT = C("9df2c9")
YELLOW = C("ffe45c")
INK = C("3a1b33")
PLUM = C("1c0d22")
RED = C("ff3d5a")
GREEN = C("3de08a")
WHITE = (255, 255, 255)
PURPLE = C("b06cff")


def rgb(c):
    return (c[2], c[1], c[0])


# ════════════════════════ fonts / text ════════════════════════
FD = os.path.join(ASSETS, "fonts")
FONTS = {
    "round": "ChironGoRoundTC_900Black.ttf",      # headings (zh + ja)
    "roundb": "ChironGoRoundTC_700Bold.ttf",      # subtitles / UI
    "roundm": "ChironGoRoundTC_500Medium.ttf",
    "min": "ShipporiMinchoB1_800ExtraBold.ttf",   # dramatic lines
    "pop": "MochiyPopOne_400Regular.ttf",         # shouts
    "wide": "Unbounded_900Black.ttf",             # years / big numerals
    "wideb": "Unbounded_700Bold.ttf",
    "lat": "Outfit_800ExtraBold.ttf",             # latin labels
    "num": "Rajdhani_700Bold.ttf",                # HUD numerals
    "px": "Silkscreen_400Regular.ttf",            # pixel UI
    "dot": "DotGothic16_400Regular.ttf",
    "serif": "NotoSerifTC_900Black.ttf",
}
FALLBACK = {"min": ["serif", "round"], "pop": ["round"], "wide": ["round"], "wideb": ["roundb"], "lat": ["round"],
            "num": ["roundb"], "px": ["roundb"], "dot": ["roundb"], "serif": ["round"], "round": ["serif"], "roundb": ["round"],
            "roundm": ["roundb"]}
_fc, _tc, _cm = {}, {}, {}


def font(name, size):
    k = (name, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(os.path.join(FD, FONTS[name]), size)
    return _fc[k]


def cmap(name):
    if name not in _cm:
        from fontTools.ttLib import TTFont
        _cm[name] = set(TTFont(os.path.join(FD, FONTS[name]), lazy=True).getBestCmap().keys())
    return _cm[name]


def pick(name, c):
    if c == " " or ord(c) in cmap(name):
        return name
    for fb in FALLBACK.get(name, []):
        if ord(c) in cmap(fb):
            return fb
    return name


def text(s, fname, size, fill=(255, 255, 255), stroke=0, sfill=(0, 0, 0), shadow=0, spacing=0, shcol=(0, 0, 0, 150)):
    """render text → BGRA sprite (cached).  colours are RGB tuples."""
    k = (s, fname, size, fill, stroke, sfill, shadow, spacing, shcol)
    if k in _tc:
        return _tc[k]
    f = font(fname, size)
    pad = stroke + abs(shadow) + 6
    fs = [pick(fname, c) for c in s]
    mixed = any(n != fname for n in fs)
    if spacing or mixed:
        ws = [font(n, size).getlength(c) for c, n in zip(s, fs)]
        tw_ = int(sum(ws) + spacing * (len(s) - 1))
    else:
        tw_ = int(f.getlength(s))
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (max(1, tw_) + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def draw(dx, dy, fill, stroke, sfill):
        if spacing or mixed:
            x = pad + dx
            for c, w_, n in zip(s, ws, fs):
                ff = font(n, size)
                d.text((x, pad + dy + asc - ff.getmetrics()[0]), c, font=ff, fill=fill, stroke_width=stroke, stroke_fill=sfill)
                x += w_ + spacing
        else:
            d.text((pad + dx, pad + dy), s, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill)

    if shadow:
        draw(shadow, shadow, shcol, stroke, shcol)
    if stroke and (spacing or mixed):
        draw(0, 0, sfill + (255,), stroke, sfill + (255,))
        draw(0, 0, fill + (255,), 0, None)
    else:
        draw(0, 0, fill + (255,), stroke, (sfill + (255,)) if stroke else None)
    a = np.array(im)
    a = np.ascontiguousarray(a[:, :, [2, 1, 0, 3]])
    if len(_tc) > 6000:
        _tc.clear()
    _tc[k] = a
    return a


def blit(fr, sp, x, y, alpha=1.0, scale=1.0, anchor="lt"):
    if alpha <= 0.003:
        return
    if scale != 1.0:
        nw, nh = max(1, int(sp.shape[1] * scale)), max(1, int(sp.shape[0] * scale))
        sp = cv2.resize(sp, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    h, w = sp.shape[:2]
    if anchor[0] == "c":
        x -= w / 2
    elif anchor[0] == "r":
        x -= w
    if anchor[1] == "m":
        y -= h / 2
    elif anchor[1] == "b":
        y -= h
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = sp[y0 - y:y1 - y, x0 - x:x1 - x]
    a = s[:, :, 3:4].astype(np.float32) * (alpha / 255.0)
    dst = fr[y0:y1, x0:x1]
    dst[:] = (dst * (1 - a) + s[:, :, :3] * a).astype(np.uint8)


def blit_solid(fr, sp, x, y, color, alpha=1.0, anchor="lt"):
    """blend a solid colour through a sprite's alpha (shadows / silhouettes)"""
    if alpha <= 0.003:
        return
    h, w = sp.shape[:2]
    if anchor[0] == "c":
        x -= w / 2
    if anchor[1] == "m":
        y -= h / 2
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    a = sp[y0 - y:y1 - y, x0 - x:x1 - x, 3:4].astype(np.float32) * (alpha / 255.0)
    dst = fr[y0:y1, x0:x1]
    dst[:] = (dst * (1 - a) + np.array(color, np.float32) * a).astype(np.uint8)


def put(fr, s, fname, size, x, y, fill=(255, 255, 255), alpha=1.0, anchor="lt", stroke=0, sfill=(0, 0, 0), shadow=0,
        scale=1.0, spacing=0, shcol=(0, 0, 0, 150)):
    blit(fr, text(s, fname, size, fill, stroke, sfill, shadow, spacing, shcol), x, y, alpha, scale, anchor)


def tw(s, fname, size, spacing=0):
    return text(s, fname, size, (255, 255, 255), 0, (0, 0, 0), 0, spacing).shape[1] - 12


def ktext(fr, s, fname, size, x, y, x_t, fill=(255, 255, 255), anchor="cm", stag=0.03, stroke=0, sfill=(0, 0, 0), shadow=0,
          spacing=0, rise=60, shcol=(0, 0, 0, 150), alpha=1.0):
    """kinetic text: characters pop in one after another (x_t = seconds since start)"""
    ws = [tw(c, fname, size) + spacing for c in s]
    total = sum(ws)
    cx = x - total / 2 if anchor[0] == "c" else (x - total if anchor[0] == "r" else x)
    for i, c in enumerate(s):
        k = (x_t - i * stag) / 0.16
        if k > 0 and c != " " and c != "　":
            e = back(k)
            sp = text(c, fname, size, fill, stroke, sfill, shadow, 0, shcol)
            blit(fr, sp, cx + ws[i] / 2, y + (1 - e) * rise, clamp(k * 3) * alpha, 0.6 + 0.4 * e, "c" + anchor[1])
        cx += ws[i]


# ════════════════════════ images ════════════════════════
_ic = {}
EP = "kurumi/ep/"
OFF = "kurumi/off/"
DECO = "kurumi/deco/"
H_ = "hist/"


def img(name):
    if name not in _ic:
        a = cv2.imread(os.path.join(ASSETS, name), cv2.IMREAD_UNCHANGED)
        if a is None:
            raise FileNotFoundError(name)
        if a.ndim == 2:
            a = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
        m = max(a.shape[:2])
        if m > 2400:
            s = 2400 / m
            a = cv2.resize(a, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        _ic[name] = a
    return _ic[name]


def crop(name, w, h, zoom=1.0, cx=0.5, cy=0.5, rot=0.0, ox=0.0, oy=0.0):
    """cover-fit an image into a w×h box with zoom / pan / rotation"""
    s = img(name)
    if s.shape[2] == 4:
        s = s[:, :, :3]
    sh, sw = s.shape[:2]
    sc = max(w / sw, h / sh) * zoom
    hw, hh = w / 2 / sc / sw, h / 2 / sc / sh
    cx = clamp(cx, hw, 1 - hw) if hw < 0.5 else 0.5
    cy = clamp(cy, hh, 1 - hh) if hh < 0.5 else 0.5
    M = cv2.getRotationMatrix2D((cx * sw, cy * sh), rot, sc)
    M[0, 2] += w / 2 - cx * sw + ox
    M[1, 2] += h / 2 - cy * sh + oy
    return cv2.warpAffine(s, M, (int(w), int(h)), flags=cv2.INTER_AREA if sc < 0.6 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def cover(name, zoom=1.0, cx=0.5, cy=0.5, rot=0.0, ox=0.0, oy=0.0):
    return crop(name, W, H, zoom, cx, cy, rot, ox, oy)


def sprite(name, height):
    k = ("sp", name, height)
    if k not in _ic:
        a = img(name)
        if a.shape[2] == 3:
            a = np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])
        s = height / a.shape[0]
        _ic[k] = cv2.resize(a, (max(1, int(a.shape[1] * s)), height), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    return _ic[k]


def sticker(name, height, outline=10, col=WHITE):
    """character cut-out with a die-cut outline"""
    k = ("st", name, height, outline, col)
    if k not in _ic:
        sp = sprite(name, height)
        pad = outline + 4
        a = cv2.copyMakeBorder(sp, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (outline * 2 + 1, outline * 2 + 1))
        dil = cv2.dilate(a[:, :, 3], ker)
        dil = cv2.GaussianBlur(dil, (0, 0), 1.2)
        out = np.zeros_like(a)
        out[:, :, :3] = col
        out[:, :, 3] = dil
        al = a[:, :, 3:4].astype(np.float32) / 255
        out[:, :, :3] = (out[:, :, :3] * (1 - al) + a[:, :, :3] * al).astype(np.uint8)
        _ic[k] = out
    return _ic[k]


def blurred(name, dark=0.45, sigma=28, zoom=1.15):
    k = ("bl", name, dark, sigma)
    if k not in _ic:
        f = cover(name, zoom)
        small = cv2.resize(f, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), sigma / 4)
        f = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
        _ic[k] = cv2.convertScaleAbs(f, alpha=dark)
    return _ic[k]


def place(fr, sp, cx, cy, scale=1.0, rot=0.0, alpha=1.0, shadow=0, shcol=PLUM, sha=0.35):
    """draw a sprite centred at (cx,cy) with scale/rotation and an offset hard shadow"""
    if alpha <= 0.003 or scale <= 0.01:
        return
    if abs(rot) > 0.05 or abs(scale - 1) > 0.004:
        h, w = sp.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, scale)
        cs, sn = abs(M[0, 0]), abs(M[0, 1])
        nw, nh = int(h * sn + w * cs) + 2, int(h * cs + w * sn) + 2
        M[0, 2] += nw / 2 - w / 2
        M[1, 2] += nh / 2 - h / 2
        sp = cv2.warpAffine(sp, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    if shadow:
        blit_solid(fr, sp, cx + shadow, cy + shadow, shcol, sha * alpha, "cm")
    blit(fr, sp, cx, cy, alpha, 1.0, "cm")


def tilt(sp, ay=0.0, ax=0.0, f=1.4):
    """pseudo-3D: rotate a sprite about its vertical (ay) / horizontal (ax) axis, degrees"""
    h, w = sp.shape[:2]
    ay, ax = math.radians(ay), math.radians(ax)
    F = f * max(w, h)
    pts = []
    for (x, y) in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        z = x * math.sin(ay)
        x1 = x * math.cos(ay)
        y1 = y * math.cos(ax) - z * math.sin(ax)
        z1 = y * math.sin(ax) + z * math.cos(ax)
        k = F / (F + z1)
        pts.append((x1 * k, y1 * k))
    pad = 40
    cw, ch = int(w * 1.15) + pad * 2, int(h * 1.15) + pad * 2
    dst = np.float32([(p[0] + cw / 2, p[1] + ch / 2) for p in pts])
    src = np.float32([(0, 0), (w, 0), (w, h), (0, h)])
    return cv2.warpPerspective(sp, cv2.getPerspectiveTransform(src, dst), (cw, ch), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))


# ════════════════════════ primitives / fx ════════════════════════
def rect(fr, x0, y0, x1, y1, color, alpha=1.0):
    x0, y0, x1, y1 = [int(v) for v in (max(0, x0), max(0, y0), min(W, x1), min(H, y1))]
    if x1 <= x0 or y1 <= y0:
        return
    if alpha >= 0.999:
        fr[y0:y1, x0:x1] = color
    else:
        r = fr[y0:y1, x0:x1]
        r[:] = (r * (1 - alpha) + np.array(color, np.float32) * alpha).astype(np.uint8)


def panel(w, h, r, fill, border=None, bw=0, alpha=255):
    """rounded rectangle sprite (cached)"""
    k = ("pn", int(w), int(h), r, fill, border, bw, alpha)
    if k not in _ic:
        w, h = int(w), int(h)
        ss = 3
        im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if border is not None and bw:
            d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=rgb(border) + (alpha,))
            d.rounded_rectangle((bw * ss, bw * ss, (w - bw) * ss - 1, (h - bw) * ss - 1), max(1, r - bw) * ss, fill=rgb(fill) + (alpha,))
        else:
            d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=rgb(fill) + (alpha,))
        im = im.resize((w, h), Image.LANCZOS)
        a = np.array(im)
        _ic[k] = np.ascontiguousarray(a[:, :, [2, 1, 0, 3]])
    return _ic[k]


def skew_plate(w, h, fill, sk=0.28):
    """parallelogram plate sprite"""
    k = ("sk", int(w), int(h), fill, sk)
    if k not in _ic:
        w, h = int(w), int(h)
        off = int(h * sk)
        a = np.zeros((h, w + off, 4), np.uint8)
        pts = np.array([[off, 0], [w + off, 0], [w, h], [0, h]], np.int32)
        cv2.fillPoly(a, [pts], fill + (255,), cv2.LINE_AA)
        _ic[k] = a
    return _ic[k]


def _masks():
    k = "masks"
    if k not in _ic:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        vig = np.clip(1.06 - 0.36 * r ** 2.4, 0, 1)
        scan = np.where((np.arange(H) % 3) == 0, 0.9, 1.0).astype(np.float32)[:, None]
        _ic[k] = (
            np.repeat((vig * 255).astype(np.uint8)[:, :, None], 3, 2),
            np.repeat(np.repeat((scan * 255).astype(np.uint8), W, 1)[:, :, None], 3, 2),
        )
    return _ic[k]


def vignette(fr):
    return cv2.multiply(fr, _masks()[0], scale=1 / 255.0)


def scanlines(fr):
    return cv2.multiply(fr, _masks()[1], scale=1 / 255.0)


def rgb_split(fr, dx, dy=0):
    dx, dy = int(dx), int(dy)
    if dx == 0 and dy == 0:
        return fr
    out = fr.copy()
    out[:, :, 2] = np.roll(fr[:, :, 2], (dy, dx), (0, 1))
    out[:, :, 0] = np.roll(fr[:, :, 0], (-dy, -dx), (0, 1))
    return out


def flash(fr, a, color=(255, 255, 255)):
    if a <= 0.004:
        return fr
    a = clamp(a)
    return cv2.addWeighted(fr, 1 - a, np.full_like(fr, color), a, 0)


def dim(fr, k):
    return cv2.convertScaleAbs(fr, alpha=k)


def tint(fr, color, a):
    if a <= 0:
        return fr
    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    col = np.dstack([cv2.convertScaleAbs(g, alpha=c / 255.0) for c in color])
    return cv2.addWeighted(fr, 1 - a, col, a, 0)


def duotone(fr, dark, light, a=1.0):
    """two-colour grade (graphic poster look)"""
    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    lut = np.zeros((256, 1, 3), np.uint8)
    ramp = np.linspace(0, 1, 256)
    for i in range(3):
        lut[:, 0, i] = (dark[i] + (light[i] - dark[i]) * ramp).astype(np.uint8)
    out = cv2.LUT(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR), lut)
    return out if a >= 1 else cv2.addWeighted(fr, 1 - a, out, a, 0)


def glitch(fr, t, amt):
    if amt <= 0.01:
        return fr
    out = fr.copy()
    n = int(3 + amt * 10)
    q = int(t * 30)
    for i in range(n):
        y = int(rnd(q, i) * H)
        hh = int(8 + rnd(q, i, 2) * 70 * amt)
        dx = int((rnd(q, i, 3) - 0.5) * 240 * amt)
        out[y:y + hh] = np.roll(fr[y:y + hh], dx, 1)
    return out


def bloom(fr, amt=0.5, thr=150):
    s = cv2.resize(fr, (W // 6, H // 6), interpolation=cv2.INTER_AREA)
    s = cv2.subtract(s, np.full_like(s, thr))
    s = cv2.GaussianBlur(s, (0, 0), 5)
    s = cv2.resize(s, (W, H), interpolation=cv2.INTER_LINEAR)
    return cv2.add(fr, cv2.convertScaleAbs(s, alpha=amt * 2.2))


def mblur(fr, k, vertical=False):
    k = int(k)
    if k < 3:
        return fr
    return cv2.blur(fr, (1, k) if vertical else (k, 1))


def zoomblur(fr, amt):
    """radial blur for impacts"""
    if amt <= 0.004:
        return fr
    acc = fr.astype(np.uint16)
    n = 4
    for i in range(1, n):
        s = 1 + amt * i / n
        M = np.float32([[s, 0, (1 - s) * W / 2], [0, s, (1 - s) * H / 2]])
        acc += cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return (acc // n).astype(np.uint8)


def shake(fr, amp, t):
    if amp < 0.6:
        return fr
    q = int(t * FPS)
    dx, dy = (rnd(q, 1) - 0.5) * 2 * amp, (rnd(q, 2) - 0.5) * 2 * amp
    M = np.float32([[1.02, 0, dx - 0.01 * W], [0, 1.02, dy - 0.01 * H]])
    return cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def ring(fr, cx, cy, x, col=WHITE, rmax=900, th=10, dur=0.45):
    """expanding shockwave ring, x = seconds since the hit"""
    if x < 0 or x > dur:
        return
    k = ease(x / dur)
    ov = fr.copy()
    cv2.circle(ov, (int(cx), int(cy)), int(rmax * k), col, max(1, int(th * (1 - k)) + 1), cv2.LINE_AA)
    cv2.addWeighted(ov, 1 - k, fr, k, 0, fr)


def burst(fr, cx, cy, x, col=YELLOW, n=14, r0=120, r1=520, dur=0.3):
    """radial accent lines popping out on a hit"""
    if x < 0 or x > dur:
        return
    k = ease(x / dur)
    for i in range(n):
        a = i / n * math.tau + 0.2
        ra, rb = lerp(r0, r1, k), lerp(r0, r1, k) + (1 - k) * 110
        cv2.line(fr, (int(cx + math.cos(a) * ra), int(cy + math.sin(a) * ra)), (int(cx + math.cos(a) * rb), int(cy + math.sin(a) * rb)),
                 col, int(3 + 9 * (1 - k)), cv2.LINE_AA)


def speedlines(fr, t, col, n=22, speed=3000, alpha=0.5):
    ov = fr.copy()
    for i in range(n):
        yy = int(rnd(i, 5) * H)
        ln = 200 + rnd(i, 6) * 700
        xx = (rnd(i, 7) * (W + ln) + t * (speed + 1800 * rnd(i, 8))) % (W + ln) - ln
        cv2.line(ov, (int(xx), yy), (int(xx + ln), yy), col, 3)
    cv2.addWeighted(ov, alpha, fr, 1 - alpha, 0, fr)


def halftone(col, a=110):
    k = ("ht", col, a)
    if k not in _ic:
        im = np.zeros((H, W, 4), np.uint8)
        for j, y in enumerate(range(0, H + 40, 34)):
            for x in range(0, W + 40, 34):
                r = int(13 * clamp(1.15 - y / H))
                if r > 0:
                    cv2.circle(im, (x + (17 if j % 2 else 0), y), r, col + (a,), -1, cv2.LINE_AA)
        _ic[k] = im
    return _ic[k]


# ════════════════════════ backgrounds ════════════════════════
DECOS = ["common_deco_yen.png", "common_deco_dollar.png", "common_deco_euro.png", "common_deco_star-y.png", "common_deco_kira-b.png",
         "common_deco_yen-r.png", "common_deco_star-b.png", "common_deco_kira.png", "common_deco_star-r.png", "common_deco_kira-g.png"]


def bg_desk(t, hue=0, deco=1.0, candles=True):
    """pastel desktop: gradient + drifting grid + floating currency / stars + candle strip"""
    k = ("desk", hue)
    if k not in _ic:
        tops = [C("ffe3ee"), C("e3f6ff"), C("fff4d0"), C("ecdcff")]
        bots = [C("ffc0d9"), C("bfe9f5"), C("ffd9a8"), C("d2b6ff")]
        g = np.linspace(0, 1, H + 96, dtype=np.float32)[:, None, None]
        base = (np.array(tops[hue], np.float32) * (1 - g) + np.array(bots[hue], np.float32) * g)
        base = np.ascontiguousarray(np.repeat(base, W + 96, 1).astype(np.uint8))
        for x in range(0, W + 96, 48):
            cv2.line(base, (x, 0), (x, H + 96), WHITE, 2)
        for y in range(0, H + 96, 48):
            cv2.line(base, (0, y), (W + 96, y), WHITE, 2)
        _ic[k] = base
    o = int(t * 34) % 48
    fr = _ic[k][o:o + H, o:o + W].copy()
    if candles:
        c = sprite(DECO + "top_bg_rousoku.png", 520)
        cw = c.shape[1]
        off = int(t * 60) % cw
        for x in range(-off, W, cw):
            blit(fr, c, x, H - 470, 0.55)
    if deco > 0:
        for i in range(12):
            nm = DECOS[i % len(DECOS)]
            sz = int(70 + 110 * rnd(i, 3))
            sp = sprite(DECO + nm, sz)
            x = rnd(i, 1) * W + 40 * math.sin(t * 0.6 + i)
            y = (rnd(i, 2) * (H + 300) - t * (26 + 30 * rnd(i, 4))) % (H + 300) - 150
            place(fr, sp, x, y, 1.0, 14 * math.sin(t * 0.9 + i * 2), 0.8 * deco)
    return fr


def bg_dark(t, col=RED, speed=1.0, horizon=0.56, base=None):
    """dark stage: gradient + perspective grid floor rushing toward the camera"""
    k = ("dk", base)
    if k not in _ic:
        top, bot = (base or (C("12061a"), C("3a1030")))
        g = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        _ic[k] = np.ascontiguousarray(np.repeat((np.array(top, np.float32) * (1 - g) + np.array(bot, np.float32) * g), W, 1).astype(np.uint8))
    fr = _ic[k].copy()
    hy = int(H * horizon)
    ov = fr.copy()
    ph = (t * speed * 1.4) % 1.0
    for i in range(14):
        z = (i + ph) / 14
        y = int(hy + (H - hy) * z ** 2.4)
        cv2.line(ov, (0, y), (W, y), col, 2, cv2.LINE_AA)
    for i in range(-14, 15):
        cv2.line(ov, (W // 2 + i * 26, hy), (W // 2 + i * 420, H), col, 2, cv2.LINE_AA)
    cv2.addWeighted(ov, 0.5, fr, 0.5, 0, fr)
    return fr


def falling_candles(fr, t, col=RED, n=16, alpha=0.6):
    ov = fr.copy()
    for i in range(n):
        x = int(rnd(i, 11) * W)
        hh = 60 + rnd(i, 12) * 240
        sp_ = 500 + 900 * rnd(i, 13)
        y = (rnd(i, 14) * (H + 400) + t * sp_) % (H + 400) - 200
        w_ = 16 + int(18 * rnd(i, 15))
        cv2.line(ov, (x, int(y - hh * 0.4)), (x, int(y + hh * 1.4)), col, 3)
        cv2.rectangle(ov, (x - w_ // 2, int(y)), (x + w_ // 2, int(y + hh)), col, -1)
    cv2.addWeighted(ov, alpha, fr, 1 - alpha, 0, fr)


# ════════════════════════ windows (official-site style UI) ════════════════════════
TH_LIGHT = dict(border=PINK, bar=PINK, body=CREAM, title=(255, 255, 255))
TH_CYAN = dict(border=C("38b9c7"), bar=C("38b9c7"), body=C("f1fdff"), title=(255, 255, 255))
TH_DARK = dict(border=RED, bar=RED, body=C("26101f"), title=(255, 255, 255))
BAR_H, BW = 50, 7


def blit_sp(dst, sp, x, y):
    """blit BGRA sprite onto a BGRA sprite (keeps dst alpha)"""
    h, w = sp.shape[:2]
    x, y = int(x), int(y)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(dst.shape[1], x + w), min(dst.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = sp[y0 - y:y1 - y, x0 - x:x1 - x]
    a = s[:, :, 3:4].astype(np.float32) / 255
    d = dst[y0:y1, x0:x1]
    d[:, :, :3] = (d[:, :, :3] * (1 - a) + s[:, :, :3] * a).astype(np.uint8)


def chrome(w, h, title, th):
    k = ("ch", int(w), int(h), title, th["border"], th["body"])
    if k not in _ic:
        w, h = int(w), int(h)
        sp = panel(w, h, 22, th["body"], th["border"], BW).copy()
        barp = panel(w, BAR_H + 24, 22, th["bar"])
        sp[:BAR_H, :, :3] = barp[:BAR_H, :, :3]
        blit_sp(sp, text(title, "roundb", 26, th["title"]), 22, 4)
        for i, nm in enumerate(("common_deco_win-min.png", "common_deco_win-max.png", "common_deco_win-close.png")):
            blit_sp(sp, sprite(DECO + nm, 32), w - 46 - (2 - i) * 40, 9)
        _ic[k] = sp
    return _ic[k]


def win_inner(w, h):
    return int(w) - 2 * BW, int(h) - BAR_H - BW


def win(fr, cx, cy, w, h, title, content=None, th=TH_LIGHT, k=1.0, rot=0.0, alpha=1.0, shadow=16, draw=None):
    """a desktop window.  content: BGR image sized win_inner(w,h); draw: callback(sprite, x0, y0, iw, ih)"""
    if k <= 0.01:
        return
    sp = chrome(w, h, title, th).copy()
    iw, ih = win_inner(w, h)
    if content is not None:
        sp[BAR_H:BAR_H + ih, BW:BW + iw, :3] = content
    if draw is not None:
        draw(sp, BW, BAR_H, iw, ih)
    place(fr, sp, cx, cy, k, rot, alpha, shadow, th["border"] if th is not TH_DARK else PLUM, 0.45)


def wpop(x, d=0.22):
    """window pop-in scale from seconds-since-open"""
    return back(x / d) if x > 0 else 0.0


def dialog(fr, cx, cy, title, lines, th=TH_DARK, k=1.0, rot=0.0, icon="!", w=640, big=None):
    h = 150 + 46 * len(lines) + (90 if big else 0)

    def d(sp, x0, y0, iw, ih):
        col = (255, 255, 255) if th is TH_DARK else rgb(INK)
        cv2.circle(sp, (x0 + 62, y0 + 62), 34, th["border"] + (255,), -1, cv2.LINE_AA)
        blit_sp(sp, text(icon, "lat", 50, (255, 255, 255)), x0 + 62 - tw(icon, "lat", 50) / 2 - 6, y0 + 22)
        for i, l in enumerate(lines):
            blit_sp(sp, text(l, "roundb", 32, col), x0 + 116, y0 + 22 + i * 46)
        if big:
            blit_sp(sp, text(big[0], "wide", 62, big[1]), x0 + 30, y0 + 30 + 46 * len(lines))
    win(fr, cx, cy, w, h, title, None, th, k, rot, draw=d)


# ════════════════════════ story HUD (pair / price / balance) ════════════════════════
# (start bar, pair, owner)
SEGS = [(0, "AUD/JPY", "くるみ"), (78, "GBP/USD", "芽吹"), (82, "USD/JPY", "芽吹"), (102, "AUD/JPY", "くるみ")]
PRICE_KF = [
    (0.0, 95.20), (bt(10), 95.30), (bt(12), 94.70), (bt(14), 94.55), (bt(16), 95.60), (bt(18), 96.10), (bt(26), 97.30),
    (bt(34), 99.40), (bt(38), 98.60), (bt(42), 96.90), (bt(46), 95.40), (bt(50), 94.05), (bt(52), 93.60), (bt(56), 93.20),
    (bt(58), 93.90), (bt(62), 96.30), (bt(70), 96.80), (bt(78), 97.40),
]
GBP_KF = [(bt(78), 1.2510), (bt(80), 1.2650), (bt(82), 1.2380)]
USD_KF = [(bt(82), 109.20), (bt(85), 110.02), (bt(88), 109.40), (bt(92), 108.10), (bt(94), 107.60), (bt(96), 105.20), (bt(100), 103.40),
          (bt(102), 103.5)]
BAL_KF = [
    (0.0, 0), (bt(8), 0), (bt(9), 100_000), (bt(10), 100_000), (bt(12), 81_000), (bt(14), 74_000), (bt(16), 131_000), (bt(18), 152_000),
    (bt(26), 420_000), (bt(34), 962_000), (bt(38), 810_000), (bt(42), 380_000), (bt(44), 96_000), (bt(44.5), 3_096_000),
    (bt(50), 2_310_000), (bt(56), 1_640_000), (bt(58), 2_100_000), (bt(62), 3_480_000), (bt(68), 3_480_000), (bt(69), 0), (bt(72), 0),
    (bt(73), 500_000), (bt(76), 905_000), (bt(78), 905_000),
]
MEB_KF = [(bt(78), 1_000_000), (bt(80), 1_520_000), (bt(82), 640_000), (bt(83), 1_140_000), (bt(86), 890_000), (bt(90), 560_000),
          (bt(94), 310_000), (bt(96), 60_000), (bt(97), 0), (DUR, 0)]


def kf(tbl, t):
    if t <= tbl[0][0]:
        return tbl[0][1]
    for i in range(len(tbl) - 1):
        if t <= tbl[i + 1][0]:
            a, b = tbl[i], tbl[i + 1]
            return lerp(a[1], b[1], (t - a[0]) / max(1e-6, b[0] - a[0]))
    return tbl[-1][1]


def seg(t):
    b = tb(t)
    cur = SEGS[0]
    for s in SEGS:
        if b >= s[0]:
            cur = s
    return cur


def price(t, pair=None):
    pair = pair or seg(t)[1]
    n = 0.16 * math.sin(t * 2.1) + 0.11 * math.sin(t * 5.3 + 1) + 0.07 * math.sin(t * 11.7 + 2) + 0.05 * math.sin(t * 23.1)
    if pair == "GBP/USD":
        return kf(GBP_KF, t) + n * 0.004
    if pair == "USD/JPY":
        return kf(USD_KF, t) + n
    return kf(PRICE_KF, min(t, bt(78))) + n


def balance(t):
    b = kf(MEB_KF, t) if seg(t)[2] == "芽吹" else kf(BAL_KF, min(t, bt(78)))
    if b > 0:
        b *= 1 + 0.010 * math.sin(t * 7.3) + 0.006 * math.sin(t * 17.1)
    return int(b)


def yen(v, sign=False):
    s = f"{abs(v):,}"
    if sign:
        return ("+" if v >= 0 else "−") + "¥" + s
    return ("−" if v < 0 else "") + "¥" + s


def candles(sp, x, y, w, h, t, span=12.0, n=38, line=None, dark=False, lw=2):
    """draw live candles into any BGR(A) array"""
    s0 = bt(seg(t)[0])
    pair = seg(t)[1]
    dt = span / n
    k0 = math.floor(t / dt)
    cs = []
    for i in range(n):
        ta = (k0 - n + 1 + i) * dt
        tb_ = min(t, ta + dt)
        if tb_ <= ta or ta < s0:
            continue
        ps = [price(ta + (tb_ - ta) * j / 5, pair) for j in range(6)]
        cs.append((i, ps[0], ps[-1], max(ps), min(ps)))
    if not cs:
        return
    hi = max(c[3] for c in cs)
    lo = min(c[4] for c in cs)
    if line is not None:
        lo, hi = min(lo, line - 0.25), max(hi, line + 0.25)
    padv = (hi - lo) * 0.12 + 1e-6
    hi, lo = hi + padv, lo - padv

    def Y(p):
        return int(y + h * (1 - (p - lo) / (hi - lo)))

    cw = w / n
    up, dn = (GREEN, RED) if dark else (C("27c37a"), C("ff4d73"))
    four = sp.shape[2] == 4
    for i, o, c, hh, ll in cs:
        col = (up if c >= o else dn) + ((255,) if four else ())
        xc = int(x + i * cw + cw / 2)
        cv2.line(sp, (xc, Y(hh)), (xc, Y(ll)), col, lw, cv2.LINE_AA)
        cv2.rectangle(sp, (int(x + i * cw + 2), min(Y(o), Y(c))), (int(x + i * cw + cw - 2), max(Y(o), Y(c)) + 1), col, -1)
    if line is not None:
        yy = Y(line)
        col = YELLOW + ((255,) if four else ())
        for xx in range(int(x), int(x + w), 24):
            cv2.line(sp, (xx, yy), (xx + 13, yy), col, 3)
        if four:
            blit_sp(sp, text(f"防衛線 {line:.2f}", "roundb", 22, rgb(YELLOW)), x + 6, yy - 34)


def chart_win(fr, cx, cy, w, h, t, k=1.0, rot=0.0, line=None, dark=False, title=None):
    th = TH_DARK if dark else TH_CYAN
    pair = seg(t)[1]

    def d(sp, x0, y0, iw, ih):
        p = price(t)
        upc = price(t) >= price(t - 0.4)
        col = rgb(GREEN if dark else C("17a866")) if upc else rgb(RED)
        ps = f"{p:.4f}" if pair == "GBP/USD" else f"{p:.3f}"
        blit_sp(sp, text(ps, "num", 46, col), x0 + 14, y0 + 2)
        blit_sp(sp, text("▲" if upc else "▼", "roundb", 24, col), x0 + 14 + tw(ps, "num", 46) + 16, y0 + 16)
        candles(sp, x0 + 10, y0 + 64, iw - 20, ih - 76, t, line=line, dark=dark, lw=3)
    win(fr, cx, cy, w, h, title or f"{pair}  ×25", None, th, k, rot, draw=d)


def hud(fr, t, a=1.0, dark=False, chapter=None):
    """top status bar: chapter tag · pair/price · account balance"""
    if a <= 0.01:
        return
    pair, owner = seg(t)[1], seg(t)[2]
    p = price(t)
    upc = price(t) >= price(t - 0.4)
    col = rgb(GREEN if dark else C("12a060")) if upc else rgb(RED)
    base = PLUM if dark else WHITE
    fg = (255, 255, 255) if dark else rgb(INK)
    b = balance(t)
    x = W - 40
    wbal = 470
    blit(fr, panel(wbal, 60, 30, base, RED if dark else PINK, 4), x - wbal, 26, 0.94 * a)
    put(fr, f"{owner}の口座", "roundb", 24, x - wbal + 26, 38, fg, a)
    put(fr, yen(b), "num", 44, x - 24, 28, fg if b > 0 else rgb(RED), a, "rt")
    x -= wbal + 16
    wp = 380
    blit(fr, panel(wp, 60, 30, base, RED if dark else C("38b9c7"), 4), x - wp, 26, 0.94 * a)
    put(fr, pair, "lat", 26, x - wp + 26, 39, fg, a)
    put(fr, f"{p:.4f}" if pair == "GBP/USD" else f"{p:.3f}", "num", 44, x - 58, 28, col, a, "rt")
    put(fr, "▲" if upc else "▼", "roundb", 22, x - 46, 42, col, a)
    if chapter:
        no, name = chapter
        wn = tw(name, "round", 30) + 150
        blit(fr, panel(wn, 60, 30, INK if not dark else RED), 40, 26, 0.94 * a)
        put(fr, no, "wideb", 22, 64, 43, rgb(YELLOW), a)
        put(fr, name, "round", 30, 64 + 78, 34, (255, 255, 255), a)


def narr(fr, t, t0, s, dur=2.4, y=H - 132, hi=None, size=48):
    """the one narration line (Traditional Chinese), bottom centre.  {…} = highlighted"""
    x = t - t0
    if x < 0 or x > dur:
        return
    a = ease(x / 0.14) * (1 - smooth((x - dur + 0.18) / 0.18))
    parts, cur, on = [], "", False
    for ch in s:
        if ch == "{":
            if cur:
                parts.append((cur, on))
            cur, on = "", True
        elif ch == "}":
            if cur:
                parts.append((cur, on))
            cur, on = "", False
        else:
            cur += ch
    if cur:
        parts.append((cur, on))
    hi = hi or rgb(YELLOW)
    ws = [tw(p, "roundb", size) for p, _ in parts]
    total = sum(ws)
    pw, ph = total + 96, size + 44
    off = (1 - ease5(x / 0.22)) * 46
    blit(fr, panel(pw, ph, ph // 2, PLUM), W / 2 - pw / 2, y + off, 0.86 * a)
    blit(fr, panel(12, ph - 28, 6, PINK), W / 2 - pw / 2 + 22, y + off + 14, a)
    xx = W / 2 - total / 2 + 8
    for (p, on), w_ in zip(parts, ws):
        put(fr, p, "roundb", size, xx - 6, y + off + 14, hi if on else (255, 255, 255), a)
        xx += w_


def chapter_card(fr, t, t0, no, name, sub, col=PINK, dur=1.25):
    """big chapter stinger that wipes across at the start of a chapter"""
    x = t - t0
    if x < 0 or x > dur:
        return
    kin = ease5(x / 0.22)
    kout = ease5((x - dur + 0.22) / 0.22)
    xoff = (1 - kin) * -W + kout * W
    blit(fr, skew_plate(W + 500, 330, col), -300 + xoff, H / 2 - 165)
    band2 = skew_plate(W + 500, 26, INK)
    blit(fr, band2, -300 + xoff * 1.3, H / 2 - 205)
    blit(fr, band2, -300 + xoff * 0.7, H / 2 + 180)
    put(fr, no, "wide", 190, 150 + xoff * 1.15, H / 2 - 10, (255, 255, 255), 0.35, "lm")
    put(fr, name, "round", 150, W / 2 + 120 + xoff * 0.9, H / 2 - 36, (255, 255, 255), 1, "cm", shadow=7, shcol=rgb(INK) + (255,))
    put(fr, sub, "lat", 44, W / 2 + 120 + xoff * 0.8, H / 2 + 96, rgb(INK), 1, "cm", spacing=10)


def shout(fr, s, x, y, xt, col=PINK, size=120, rot=-6, fill=(255, 255, 255)):
    """JP accent word on a skewed plate, popping in"""
    if xt < 0:
        return
    k = back(xt / 0.16)
    tx = text(s, "pop", size, fill)
    pl = skew_plate(tx.shape[1] + 50, tx.shape[0] - 6, col).copy()
    blit_sp(pl, tx, 44, -6)
    place(fr, pl, x, y, 0.5 + 0.5 * k, rot + (1 - k) * 14, clamp(xt * 12), 10, INK, 0.9)


def bubble(fr, n, x, y, xt, rot=-8, size=210):
    """official chart-sound speech bubble (1 ぐぐぐっ 2 ぐ 3 ぐーー 4 や、やば… 5 あ… 6 ストン…)"""
    if xt < 0:
        return
    sp = sprite(DECO + f"common_omp_f-{n}.png", size)
    place(fr, sp, x, y + 6 * math.sin(xt * 9), back(xt / 0.18, 2.6), rot + 4 * math.sin(xt * 7), clamp(xt * 12), 8, PINK, 0.35)


def cut_fx(fr, x, d=1, amt=1.0):
    """whip-in on a cut: motion blur + slide during the first 0.1 s"""
    if x >= 0.11:
        return fr
    k = 1 - ease(x / 0.11)
    M = np.float32([[1, 0, d * k * 320 * amt], [0, 1, 0]])
    fr = cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return mblur(fr, 90 * k * amt)


def finish(fr, t, split=0.0, fl=0.0, flcol=WHITE, blm=0.0, vig=True, scan=False, gl=0.0, zb=0.0, sh=0.0, light=False, inv=False):
    if inv and flash_env(t, 0.1) > 0.72:
        fr = cv2.bitwise_not(fr)           # 2-frame negative "impact frame" on beatmap accents
    if light:
        blm = 0.0
    if zb > 0:
        fr = zoomblur(fr, zb)
    if sh > 0:
        fr = shake(fr, sh, t)
    if gl > 0:
        fr = glitch(fr, t, gl)
    if split > 0.5:
        fr = rgb_split(fr, split)
    if blm > 0:
        fr = bloom(fr, blm)
    if vig:
        fr = cv2.addWeighted(fr, 0.6, vignette(fr), 0.4, 0) if light else vignette(fr)
    if scan:
        fr = scanlines(fr)
    return flash(fr, fl, flcol)


# ════════════════════════ PROLOGUE  (bars 0–10) ════════════════════════
def s_intro(t):
    b = tb(t)
    fr = bg_desk(t, 0, deco=0.7)
    if b < 2:
        x = t - 0.2
        lines = ["FX口座　開設中 …", "本人確認 ……………… OK", "入金 ¥100,000 ……… OK", "レバレッジ ×25 …… OK", "相場へ、ようこそ。"]

        def d(sp, x0, y0, iw, ih):
            for i, l in enumerate(lines):
                ts = 0.35 + i * 0.6
                if x > ts:
                    n = int((x - ts) * 40)
                    blit_sp(sp, text(l[:n], "dot", 44, rgb(INK) if i < 4 else rgb(PINK)), x0 + 44, y0 + 34 + i * 74)
            if int(t * 3) % 2 == 0:
                cv2.rectangle(sp, (x0 + 44, y0 + 34 + 5 * 74), (x0 + 70, y0 + 34 + 5 * 74 + 44), PINK + (255,), -1)
        win(fr, W / 2, H / 2 + 10, 1040, 560, "FX_account_setup.exe", None, TH_LIGHT, wpop(x), -1.5, draw=d)
        blit(fr, sprite(DECO + "common_logo.png", 150), W - 60, H - 50, 0.95, 1.0, "rb")
        put(fr, "INTERNET YAMERO  ×  FX戦士くるみちゃん  MAD", "lat", 28, 60, H - 76, rgb(INK), 0.8, spacing=3)
        return finish(fr, t, fl=0.5 * flash_env(t), gl=0.5 * flash_env(t, 0.2), light=True)
    wins = [
        (2, EP + "01_3.jpg", "お母さん.jpg", (520, 420), -4, (880, 600), (0.5, 0.36)),
        (4, EP + "01_1.jpg", "2008.jpg", (1330, 600), 3, (860, 580), (0.5, 0.42)),
        (6, EP + "01_4.jpg", "FXトレード日誌.txt", (700, 600), 2, (900, 600), (0.6, 0.5)),
        (8, EP + "01_5.jpg", "福賀くるみ.jpg", (W / 2, 500), -2, (1240, 760), (0.6, 0.4)),
    ]
    for b0, im, title, pos, rot, size, cen in wins:
        vis = (b0 < 6 and b0 <= b < 6) or (b0 == 6 and 6 <= b < 8) or (b0 == 8 and b >= 8)
        if vis:
            x = t - bt(b0)
            iw, ih = win_inner(*size)
            z = 1.06 + 0.05 * x / (2 * BAR)
            win(fr, pos[0], pos[1], size[0], size[1], title, crop(im, iw, ih, z, cen[0], cen[1]), TH_LIGHT if b0 != 4 else TH_DARK,
                wpop(x), rot + 2 * math.sin(t * 1.3 + b0))
    if 4 <= b < 6:
        x = t - bt(4)
        dialog(fr, 700, 800, "損失確定", ["お母さんの口座"], TH_DARK, wpop(x - 0.12), -3, "!", 700, big=("−¥20,000,000", rgb(RED)))
        ring(fr, 1330, 600, x, RED)
    if 6 <= b < 8:
        x = t - bt(6)
        st = sticker(OFF + "character_main_kurumi.png", 900)
        place(fr, st, 1500 + (1 - ease5(x / 0.3)) * 600, 620, 1.0, 4, 1, 18, PINK, 0.35)
    lines = [(2, "媽媽她——玩 FX。"), (4, "然後，把 {2000 萬日圓} 賠光了。"), (6, "所以，{由我來贏回來。}"), (8, "{福賀久留美}，大學生。今天，開戶。")]
    cur = [l for l in lines if b >= l[0]][-1]
    narr(fr, t, bt(cur[0]), cur[1], dur=2 * BAR - 0.05)
    if b >= 9:
        x = t - bt(9)
        shout(fr, "いざ、戦場へ！", W / 2, 520, x, PINK, 170, -5)
        burst(fr, W / 2, 520, x, YELLOW, 16, 380, 900)
    return finish(fr, t, split=10 * flash_env(t, 0.12), fl=0.7 * flash_env(t, 0.09), light=True)


# ════════════════════════ CH.1 初陣  (bars 10–18) ════════════════════════
def s_build(t):
    b = tb(t)
    fr = bg_desk(t, 1)
    ph = min(int((b - 10) / 2), 3)
    t0 = bt(10 + ph * 2)
    x = t - t0
    shots = [("02_4", "第一筆交易。", "買い！", MINT, (0.5, 0.42)), ("02_1", "馬上就被{套牢}了。", "含み損…", PURPLE, (0.45, 0.4)),
             ("03_4", "但行情——{奇蹟般地反轉！}", "反転！", CYAN, (0.62, 0.45)), ("03_1", "{獲利了結！}從此三個月，連戰連勝。", "利確♡", PINK, (0.5, 0.42))]
    im, line, sh_, col, cen = shots[ph]
    size = (1120, 700)
    iw, ih = win_inner(*size)
    d = 1 if ph % 2 == 0 else -1
    win(fr, W / 2 - d * 250 + (1 - ease5(x / 0.25)) * d * -500, 520, size[0], size[1], f"trade_{ph + 1:02d}.mp4",
        crop(EP + im + ".jpg", iw, ih, 1.06 + 0.06 * x / (2 * BAR) + 0.03 * pulse(t), cen[0], cen[1]), TH_LIGHT, wpop(x), d * -2.5)
    chart_win(fr, W / 2 + d * 520, 640, 620, 420, t, wpop(x - 0.08), d * 3)
    bubble(fr, [2, 6, 1, 3][ph], W / 2 + d * 760, 880, x - BEAT * 2, d * 8)
    shout(fr, sh_, W / 2 + d * 500, 330, x - 0.1, col, 120, d * 5, rgb(INK) if col in (MINT, CYAN) else (255, 255, 255))
    if ph == 3:
        burst(fr, W / 2 + d * 500, 330, x - 0.1, YELLOW)
    if b >= 17:
        fr = zoomblur(fr, 0.12 * (b - 17))
    chapter_card(fr, t, bt(10), "01", "初陣", "FIRST TRADE", PINK)
    narr(fr, t, t0, line, dur=2 * BAR - 0.05)
    hud(fr, t, chapter=("CH.1", "初陣"))
    fl = 0.5 * flash_env(t) + (clamp((b - 17.7) * 3.3) if b > 17.7 else 0)
    return finish(fr, t, split=5 * pulse(t), fl=fl, light=True)


# ════════════════════════ TITLE + ROLL CALL  (bars 18–26) ════════════════════════
CHARS = [
    ("kurumi", "福賀くるみ", "KURUMI FUKUGA", "要贏回媽媽輸掉的 2000 萬", C("ff7fb0"), C("ffd0e2")),
    ("mochiko", "小金萌智子", "MOCHIKO KOGANE", "投資同好・惡魔的耳語", C("b467f0"), C("e7ccff")),
    ("mebuki", "山師芽吹", "MEBUKI YAMASHI", "夢想是不工作就賺錢", C("ffb21e"), C("fff0b8")),
    ("yasuko", "高根やす子", "YASUKO TAKANE", "投資部落客「阿菲醬」", C("ff4a5e"), C("ffd0d4")),
]


def s_drop1(t):
    b = tb(t)
    p = pulse(t)
    if b < 20:
        x = t - bt(18)
        fr = cover(OFF + "top_visual_visual1.jpg", 1.03 + 0.14 * math.exp(-x / 0.3) + 0.03 * beat_env(t), 0.5, lerp(0.40, 0.5, x / (2 * BAR)),
                   rot=1.2 * math.sin(t * 9) * p)
        blit(fr, halftone(WHITE), 0, 0, 0.5)
        logo = sprite(DECO + "common_logo.png", 560)
        s = back(x / 0.2, 2.6) * (1 + 0.035 * beat_env(t))
        pl = panel(logo.shape[1] + 150, logo.shape[0] + 110, 60, WHITE, PINK, 12)
        place(fr, pl, W / 2, 470, s, -2, 1, 20, PINK, 0.6)
        place(fr, logo, W / 2, 470, s, -2)
        ring(fr, W / 2, 470, x, WHITE, 1300, 26, 0.5)
        burst(fr, W / 2, 470, x, YELLOW, 18, 420, 1000)
        a2 = t - bt(19)
        if a2 > 0:
            ktext(fr, "致瞬息萬變之物，及亙古不變之物", "min", 74, W / 2, 900, a2, (255, 255, 255), stag=0.035, shadow=5,
                  shcol=rgb(INK) + (255,), stroke=3, sfill=rgb(INK))
        return finish(fr, t, split=8 * p, fl=0.9 * math.exp(-x / 0.14), blm=0.4, zb=0.12 * math.exp(-x / 0.12))
    if b < 24:
        i = int(b - 20)
        key, ja, en, zh, col, col2 = CHARS[i]
        x = t - bt(20 + i)
        d = 1 if i % 2 == 0 else -1
        fr = np.empty((H, W, 3), np.uint8)
        fr[:] = col2
        off = int(t * 520) % 160
        for k_ in range(-3, 18):
            pts = np.array([[k_ * 160 + off, 0], [k_ * 160 + 80 + off, 0], [k_ * 160 - 220 + off, H], [k_ * 160 - 300 + off, H]], np.int32)
            cv2.fillPoly(fr, [pts], WHITE)
        px = W / 2 + d * 420
        sl = (1 - ease5(x / 0.2)) * d * 900
        pts = np.array([[px - 520 + sl, 0], [px + 380 + sl, 0], [px + 520 + sl, H], [px - 380 + sl, H]], np.int32)
        cv2.fillPoly(fr, [pts], col, cv2.LINE_AA)
        blit(fr, halftone(WHITE, 80), 0, 0, 0.6)
        st = sticker(OFF + f"character_main_{key}.png", 1420, 12)
        place(fr, st, px + sl * 0.6, 760 - 24 * p, 1.0 + 0.03 * math.exp(-x / 0.1), d * 2, 1, 22, INK, 0.25)
        tx = W / 2 - d * 430
        put(fr, f"0{i + 1}", "wide", 300, tx + d * 60, 250, rgb(col), 0.28, "cm")
        put(fr, en, "lat", 46, tx, 330, rgb(INK), 1, "cm", spacing=9)
        ktext(fr, ja, "round", 150, tx, 470, x, rgb(INK), stag=0.035)
        zs = text(zh, "roundb", 46, (255, 255, 255))
        pl = panel(zs.shape[1] + 70, 84, 42, col)
        place(fr, pl, tx, 640, back((x - 0.12) / 0.2), 0, clamp((x - 0.12) * 10))
        blit(fr, zs, tx, 640, clamp((x - 0.16) * 10), 1.0, "cm")
        for j in range(3):
            sp = sprite(DECO + ["common_deco_kira-b.png", "common_deco_star-y.png", "common_deco_kira.png"][j], 90 + 30 * j)
            place(fr, sp, tx - 380 + j * 380, 180 + 120 * (j % 2) + 620 * (j == 1), back((x - 0.1 * j) / 0.25), 20 * math.sin(t * 3 + j))
        hud(fr, t)
        fr = cut_fx(fr, x, d)
        return finish(fr, t, split=6 * p, fl=0.45 * math.exp(-x / 0.08), light=True)
    x = t - bt(24)
    fr = cover(OFF + "music_jk.jpg", 1.06 + 0.07 * math.exp(-x / 0.2) + 0.03 * beat_env(t), 0.5, lerp(0.3, 0.42, x / (2 * BAR)))
    blit(fr, halftone(WHITE), 0, 0, 0.45)
    shout(fr, "レバレッジあるから", W / 2 - 60, 400, x, PINK, 130, -5)
    y = t - bt(24.5)
    shout(fr, "大丈夫ぅ♪", W / 2 + 80, 620, y, YELLOW, 210, -5, rgb(INK))
    burst(fr, W / 2 + 80, 620, y, WHITE, 16, 380, 900)
    narr(fr, t, bt(24.5), "「有槓桿，所以沒問題♪」", dur=1.5 * BAR)
    hud(fr, t)
    return finish(fr, t, split=7 * p, fl=0.5 * math.exp(-x / 0.1) + 0.5 * flash_env(t), light=True)


# ════════════════════════ story shots (shared by CH.2 – CH.5) ════════════════════════
def shot_full(t, t0, dur, im, cen=(0.5, 0.42), z0=1.06, z1=1.16, d=1, grade=None, punch=0.06, sh=0.0, jump=True):
    x = t - t0
    k = clamp(x / dur)
    step = 0.09 * (2 - int(x / 0.055)) if x < 0.165 else 0.0          # 3-step zoom-out on entry
    jz = 0.16 if (jump and dur > 1.5 * BAR and x >= dur / 2) else 0.0   # jump-cut closer half-way
    fr = cover(EP + im + ".jpg", lerp(z0, z1, k) + step + jz + punch * math.exp(-x / 0.13) + 0.02 * pulse(t),
               cen[0] - 0.02 * d * (1 - k), cen[1] - (0.03 if jz else 0),
               rot=d * 0.7 * (1 - k), ox=(rnd(int(t * FPS), 1) - 0.5) * sh, oy=(rnd(int(t * FPS), 2) - 0.5) * sh)
    if grade:
        fr = duotone(fr, grade[0], grade[1], grade[2])
    if jz and x - dur / 2 < 0.05:
        fr = flash(fr, 0.55)
    return cut_fx(fr, x, d)


def shot_win(t, t0, dur, im, bg, cen=(0.5, 0.42), d=1, th=TH_LIGHT, title="", side=None, size=(1180, 740)):
    """still inside a window over a designed background, with an optional side widget"""
    x = t - t0
    k = clamp(x / dur)
    fr = bg
    iw, ih = win_inner(*size)
    cx = W / 2 - d * (230 if side else 0)
    win(fr, cx + (1 - ease5(x / 0.24)) * d * -420, 520 + 6 * math.sin(t * 1.4), size[0], size[1], title,
        crop(EP + im + ".jpg", iw, ih, 1.05 + 0.07 * k + 0.03 * pulse(t), cen[0], cen[1]), th, wpop(x), d * -2 + 0.6 * math.sin(t * 1.1))
    if side:
        side(fr, W / 2 + d * 560, x, d)
    return fr


# CH.2 槓桿 — (bar, image, narration, accent, layout)
CH2 = [
    (26, "05_3", "三個月。帳戶穩穩地成長。", None, "win"),
    (28, "02_2", "萌智子：「要不要試試{澳幣／日圓}？」", "豪ドル円", "full"),
    (30, "01_3", "那是——媽媽當年賠掉 2000 萬的{同一個貨幣對}。", None, "win"),
    (32, "02_3", "惡魔的耳語。她開了{超高槓桿}。", "全力ロング！", "full"),
    (34, "03_1", "帳戶餘額，眼看就要突破 {100 萬}！", "100万円！", "win"),
    (36, "07_5", "有未實現獲利的日子，最棒了♡", None, "full"),
    (38, "02_1", "……然後，行情{反轉}了。", "あれ？", "full"),
    (40, "03_2", "未實現獲利，變成了{未實現虧損}。", "含み損", "full"),
]


def s_ch2(t):
    b = tb(t)
    i = max(j for j, c in enumerate(CH2) if b >= c[0])
    b0, im, line, acc, lay = CH2[i]
    t0 = bt(b0)
    x = t - t0
    d = 1 if i % 2 == 0 else -1
    bad = i >= 6
    cen = {"02_3": (0.5, 0.36), "01_3": (0.5, 0.36), "03_2": (0.5, 0.5), "02_2": (0.6, 0.4)}.get(im, (0.5, 0.42))
    if lay == "win":
        def side(fr, sx, xx, dd):
            chart_win(fr, sx, 640, 600, 430, t, wpop(xx - 0.08), dd * 3)
            bubble(fr, 3 if im != "01_3" else 5, sx + dd * 210, 900, xx - BEAT * 3, dd * 8)
            if im == "03_1":
                sp = sprite(DECO + "common_deco_yen.png", 230)
                place(fr, sp, sx, 250, back((xx - 0.15) / 0.25), 12 * math.sin(t * 4), 1, 10, PINK, 0.4)
        fr = shot_win(t, t0, 2 * BAR, im, bg_desk(t, [0, 2, 1][i % 3]), cen, d, TH_LIGHT, f"kurumi_{b0}.mp4", side)
    else:
        fr = shot_full(t, t0, 2 * BAR, im, cen, d=d, grade=(C("2a1040"), C("ffd9ee"), 0.35) if bad else None)
        if not bad:
            blit(fr, halftone(WHITE, 70), 0, 0, 0.35)
    if acc:
        col = PURPLE if bad else [PINK, CYAN, YELLOW][i % 3]
        shout(fr, acc, W / 2 + d * 520, 300 if lay == "win" else 250, x - 0.12, col, 120, d * 5,
              rgb(INK) if col in (CYAN, YELLOW) else (255, 255, 255))
    if b0 == 34:
        burst(fr, W / 2 + d * 520, 300, x - 0.12, YELLOW)
    chapter_card(fr, t, bt(26), "02", "槓桿", "LEVERAGE ×25", C("38b9c7"))
    narr(fr, t, t0, line, dur=2 * BAR - 0.05)
    hud(fr, t, chapter=("CH.2", "槓桿"))
    return finish(fr, t, split=4 * pulse(t) + (6 if bad else 0) * flash_env(t), fl=0.35 * math.exp(-x / 0.09) + 0.3 * flash_env(t), blm=0.22,
                  light=(lay == "win"), inv=bad)


# CH.3 含み損
CH3 = [
    (42, "02_5", "保證金，快撐不住了。", "やばい…"),
    (44, "02_6", "她偷拿了爸爸藏在衣櫃的 {300 萬日圓}——入金。", None),
    (46, "06_3", "「跌破 {94 圓}，就停損。」她這麼決定。", None),
    (48, "03_4", "可是她沒有停損。她{加碼做多}。", "ナンピン！"),
    (50, "03_5", "{94 圓，失守。}", "割れた"),
    (52, "03_3", "剩下的，只有向神祈禱。", "神様…"),
    (54, "02_5", "「再也不敢了。就這一次，救救我。」", None),
    (56, "04_6", "線圖上的每一根 K 線，都像在審判她。", None),
]
G_BAD = (C("1a0626"), C("ffb8cf"), 0.5)


def s_ch3(t):
    b = tb(t)
    i = max(j for j, c in enumerate(CH3) if b >= c[0])
    b0, im, line, acc = CH3[i]
    t0 = bt(b0)
    x = t - t0
    d = 1 if i % 2 == 0 else -1
    cen = {"03_3": (0.5, 0.5), "02_6": (0.5, 0.45)}.get(im, (0.5, 0.42))
    fr = shot_full(t, t0, 2 * BAR, im, cen, d=d, grade=G_BAD if im != "03_3" else None, sh=5 * pulse(t))
    falling_candles(fr, t, RED, 10, alpha=0.35)
    line94 = 94.0 if 46 <= b0 <= 56 else None
    chart_win(fr, W - 400 if d > 0 else 400, 700, 660, 440, t, wpop(x - 0.05), -d * 2.5, line=line94, dark=True)
    bubble(fr, [4, 2, 5, 6, 6, 5, 4, 6][i], (W - 150) if d > 0 else 150, 470, x - BEAT * 4, -d * 8, 190)
    if b0 == 44:
        dialog(fr, W / 2 - 300, 420, "入金完了", ["お父さんのタンス預金"], TH_LIGHT, wpop(x - 0.1), -3, "¥", 720, big=("+¥3,000,000", rgb(C("12a060"))))
        ring(fr, W / 2 - 300, 420, x - 0.1, YELLOW)
    if acc:
        shout(fr, acc, 520 if d > 0 else W - 520, 280, x - 0.12, RED, 130, d * -5)
    chapter_card(fr, t, bt(42), "03", "含み損", "UNREALIZED LOSS", RED)
    narr(fr, t, t0, line, dur=2 * BAR - 0.05)
    hud(fr, t, dark=True, chapter=("CH.3", "含み損"))
    return finish(fr, t, split=5 * pulse(t) + 8 * flash_env(t), fl=0.35 * math.exp(-x / 0.09) + 0.3 * flash_env(t), blm=0.2,
                  sh=(8 if b0 == 50 else 0) * math.exp(-x / 0.3), inv=True)


def s_relief(t):
    """bars 58–62 (quiet): the market comes back"""
    b = tb(t)
    i = 0 if b < 60 else 1
    t0 = bt(58 + 2 * i)
    x = t - t0
    im, line = [("03_1", "——行情，回來了。"), ("07_5", "沒有套牢的日子，最棒了♡　把 300 萬放回去就好。")][i]
    fr = shot_win(t, t0, 2 * BAR, im, bg_desk(t, 2), (0.5, 0.42), 1 if i == 0 else -1, TH_LIGHT, "含み損ゼロ.mp4",
                  lambda f, sx, xx, dd: chart_win(f, sx, 640, 600, 430, t, wpop(xx - 0.08), dd * 3))
    if i == 0:
        shout(fr, "助かった…！", W / 2 + 520, 300, x - 0.15, MINT, 110, 5, rgb(INK))
    else:
        shout(fr, "サイコ〜♡", W / 2 - 520, 300, x - 0.15, PINK, 120, -5)
    narr(fr, t, t0, line, dur=2 * BAR - 0.05, size=44 if i else 48)
    hud(fr, t, chapter=("CH.3", "含み損"))
    return finish(fr, t, fl=0.6 * math.exp(-x / 0.14), light=True)


# CH.4 引退 (bars 62–70, bass kicks only)
CH4 = [
    (62, "06_3", "爸爸：「衣櫃裡的 300 萬……{被偷了。}」", None),
    (64, "04_2", "鈔票，從她手裡掉了下來。", "バレた"),
    (66, "04_6", "「{別再碰 FX 了。}」爸爸哭著求她。", None),
    (68, "04_3", "她終於看見自己的瘋狂——決定，{FX 引退}。", None),
]


def s_ch4(t):
    b = tb(t)
    i = max(j for j, c in enumerate(CH4) if b >= c[0])
    b0, im, line, acc = CH4[i]
    t0 = bt(b0)
    x = t - t0
    be = beat_env(t, 0.12)
    d = 1 if i % 2 == 0 else -1
    fr = shot_full(t, t0, 2 * BAR, im, (0.5, 0.45), z0=1.08 + 0.05 * be, z1=1.2 + 0.05 * be, d=d, grade=(C("0d0616"), C("b9c8ff"), 0.6),
                   sh=14 * be)
    fr = dim(fr, 0.72 + 0.28 * be)
    if acc:
        shout(fr, acc, W / 2 + 500, 300, x - 0.1, RED, 140, 6)
    if b0 == 68:
        y = t - bt(69)
        if y > 0:
            st = text("FX 引退", "round", 250, rgb(RED))
            pl = panel(st.shape[1] + 80, st.shape[0] + 10, 30, WHITE, RED, 16)
            k = clamp(back(y / 0.14, 3.0))
            place(fr, pl, W / 2, 470, 2.2 - 1.2 * k, -9, clamp(y * 14), 18, PLUM, 0.6)
            place(fr, st, W / 2, 470, 2.2 - 1.2 * k, -9, clamp(y * 14))
            ring(fr, W / 2, 470, y, RED, 1200, 20)
    chapter_card(fr, t, bt(62), "04", "引退", "RETIREMENT", C("5568ff"))
    narr(fr, t, t0, line, dur=2 * BAR - 0.05)
    hud(fr, t, dark=True, chapter=("CH.4", "引退"))
    return finish(fr, t, split=12 * be, fl=0.4 * flash_env(t) + 0.3 * math.exp(-x / 0.08), flcol=C("b9c8ff"), blm=0.15)


# CH.5 再発 (bars 70–94, hardcore): relapse → battle → Mebuki's margin call
CH5 = [
    (70, 1, "06_3", "可是——", None),
    (71, 1, "05_3", "腦袋裡，全是行情。", "相場…"),
    (72, 2, "04_3", "「{另一個自己}」告訴她：帳戶裡，又有錢了。", "入金済み"),
    (74, 2, "07_3", "芽吹提議的{「超級投資對決」}，開打。", "投資バトル！"),
    (76, 1, "06_2", "やす子：歐元／美元，停損出場。", "損切り"),
    (77, 1, "03_1", "久留美：放空歐元／美元，{+40 萬}。", "+40万"),
    (78, 2, "06_6", "芽吹不聽勸——英鎊／美元，{100 手全力做多}。", "全力ロング！"),
    (80, 1, "07_2", "數據公布，瞬間大賺！", "爆益！"),
    (81, 1, "06_4", "……然後，全部吐了回去。", "逆行"),
    (82, 1, "07_1", "她把{生活費}也存進了保證金。", "生活費…"),
    (83, 1, "07_4", "美元／日圓，還在漲。芽吹越來越焦急。", None),
    (84, 1, "06_1", "「強制平倉什麼的，人家才不要……」", "ヤダもん"),
]


def s_ch5(t):
    b = tb(t)
    i = max(j for j, c in enumerate(CH5) if b >= c[0])
    b0, nb, im, line, acc = CH5[i]
    t0 = bt(b0)
    x = t - t0
    p = pulse(t)
    d = 1 if i % 2 == 0 else -1
    k = (b - 70) / 15
    bright = 74 <= b0 < 78 or b0 == 80
    cen = {"07_4": (0.6, 0.4), "07_3": (0.5, 0.5), "05_5": (0.5, 0.38)}.get(im, (0.5, 0.42))
    grade = None if bright else (C("16051f"), C("ffb0c4"), 0.35 + 0.25 * k)
    fr = shot_full(t, t0, nb * BAR, im, cen, z0=1.1, z1=1.2, d=d, grade=grade, punch=0.1, sh=6 + 12 * p * k)
    if bright:
        blit(fr, halftone(WHITE, 70), 0, 0, 0.35)
    else:
        falling_candles(fr, t, RED, 12, alpha=0.3 + 0.2 * k)
    if b >= 78:
        ml = lerp(420, 104, clamp((b - 78) / 16) ** 0.8) + 3 * math.sin(t * 13)
        if 80 <= b < 81:
            ml += 300
        blit(fr, panel(640, 128, 24, PLUM, RED, 5), 40, 104, 0.92)
        put(fr, "証拠金維持率", "roundb", 30, 66, 118, (255, 255, 255))
        put(fr, f"{ml:5.1f}%", "num", 72, 660, 100, rgb(RED) if ml < 160 else rgb(YELLOW), 1, "rt")
        rect(fr, 66, 196, 654, 214, C("5a2a48"))
        rect(fr, 66, 196, 66 + 588 * clamp((ml - 100) / 320), 214, RED if ml < 160 else YELLOW)
        chart_win(fr, W - 380, 760, 640, 400, t, 1.0, -2, dark=True)
    if acc:
        col = [PINK, CYAN, YELLOW][i % 3] if bright else RED
        shout(fr, acc, W / 2 + d * 480, 330, x - 0.06, col, 140, d * 6, rgb(INK) if col in (YELLOW, CYAN) else (255, 255, 255))
    chapter_card(fr, t, bt(70), "05", "再発", "RELAPSE", PURPLE, dur=1.0)
    narr(fr, t, t0, line, dur=nb * BAR - 0.04, size=44)
    hud(fr, t, dark=not bright, chapter=("CH.5", "再発"))
    return finish(fr, t, split=4 + 9 * p * (0.4 + k), fl=0.4 * flash_env(t) + 0.3 * math.exp(-x / 0.06), blm=0.2, gl=0.18 * p * k, inv=True)


def s_hold(t):
    """bar 85: one bar of held breath"""
    x = t - bt(85)
    fr = cover(EP + "07_1.jpg", 1.22 + 0.06 * x, 0.5, 0.4)
    fr = duotone(fr, C("0a0412"), C("ffffff"), 0.9)
    fr = dim(fr, 0.6)
    put(fr, "USD/JPY", "lat", 60, W / 2, 300, (255, 255, 255), 0.9, "cm", spacing=14)
    put(fr, "110.00", "wide", 250, W / 2, 500, rgb(RED), 1, "cm", scale=1 + 0.2 * math.exp(-x / 0.1))
    narr(fr, t, bt(85), "美元／日圓，站上 {110 圓}——", dur=BAR)
    hud(fr, t, dark=True, chapter=("CH.5", "再発"))
    return finish(fr, t, fl=0.8 * math.exp(-x / 0.1), scan=True)


PRAY = [("03_3", "神様、お願い。", "神啊，拜託了。"), ("05_3", "もう二度と、しませんから。", "我再也不敢了。"),
        ("03_3", "今回だけ。", "就這一次。"), ("07_1", "今回だけ、助けて。", "就這一次，救救我。"),
        ("03_3", "お願い。", "拜託。"), ("06_4", "お願い。", "拜託。"), ("03_3", "お願いお願いお願い", "拜託拜託拜託"), ("04_6", "——110円から、急落。", "——從 110 圓，急墜。")]


def s_pray(t):
    """bars 86–94: prayer"""
    b = tb(t)
    bi = min(7, int(b - 86))
    t0 = bt(86 + bi)
    x = t - t0
    im, ja, zh = PRAY[bi]
    last = bi == 7
    fr = shot_full(t, t0, BAR, im, (0.5, 0.45), z0=1.1, z1=1.22 + 0.04 * bi, d=1 if bi % 2 else -1,
                   grade=(C("12041c"), C("ffc0d2"), 0.4) if im != "03_3" else None, punch=0.1, sh=8 * pulse(t))
    ktext(fr, ja, "min", 120 + bi * 5, W / 2, H / 2 - 50, x, (255, 255, 255), stag=0.02, stroke=6,
          sfill=rgb(C("b0124a") if not last else C("1b2bd0")), shadow=6)
    narr(fr, t, t0, zh, dur=BAR - 0.03)
    chart_win(fr, W - 380, 250, 620, 380, t, 1.0, 2, dark=True)
    hud(fr, t, dark=True, chapter=("CH.5", "再発"))
    return finish(fr, t, split=3 + 12 * flash_env(t, 0.1), fl=0.6 * flash_env(t) + (clamp((b - 93.5) * 2) ** 2 if b > 93.5 else 0), blm=0.3,
                  inv=True)


def losscut_scene(t, t0, spin=1.0, fall=1.0, k=1.0, dy=0.0):
    x = t - t0
    bg = cover(OFF + "top_losscut_losscut_bg.jpg", 1.5 + 0.08 * math.sin(x * 0.7), 0.5, 0.5, rot=-x * 26 * spin)
    sp = sprite(OFF + "top_losscut_losscut_kurumi.png", 1500)
    sc = max(0.42, (1.05 - 0.035 * x * fall) * k) * 1880 / 1500
    M = cv2.getRotationMatrix2D((sp.shape[1] / 2, sp.shape[0] / 2), math.sin(x * 0.9) * 7 + x * 2.5 * fall, sc)
    M[0, 2] += W / 2 + 30 * math.sin(x * 1.3) - sp.shape[1] / 2
    M[1, 2] += H / 2 + dy + 20 * math.cos(x * 1.1) - sp.shape[0] / 2
    lay = cv2.warpAffine(sp, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    blit(bg, lay, 0, 0)
    return bg


def s_drop2(t):
    """bars 94–102: 強制ロスカット — error dialogs cascade over the falling Kurumi"""
    b = tb(t)
    x = t - bt(94)
    p = pulse(t)
    if b < 100:
        fr = losscut_scene(t, bt(94), k=0.78, dy=120)
        fr = dim(fr, 0.8 + 0.2 * p)
        falling_candles(fr, t, RED, 22, alpha=0.5)
        nb = int(x / BEAT)
        for j in range(max(0, nb - 9), nb + 1):
            xx = x - j * BEAT
            cx = 330 + (j * 263) % 1260
            cy = 240 + (j * 157) % 520
            dialog(fr, cx, cy, "ERROR", ["強制ロスカット", "証拠金維持率 < 100%"], TH_DARK, wpop(xx, 0.14), (rnd(j) - 0.5) * 10, "×", 560)
        sp = sprite(OFF + "top_losscut_losscut_txt.png", 190)
        blit(fr, panel(sp.shape[1] + 120, 250, 40, PLUM), W / 2, H / 2 - 20, 0.86, 1.0, "cm")
        blit(fr, sp, W / 2, H / 2 - 20, 1.0, 1 + 0.9 * math.exp(-x / 0.12) + 0.04 * beat_env(t), "cm")
        ring(fr, W / 2, H / 2, x, RED, 1400, 30, 0.6)
        narr(fr, t, bt(94), "{強制平倉。}每一個 FX 戰士，都躲不掉的結局。", dur=6 * BAR)
        hud(fr, t, dark=True, chapter=("CH.5", "再発"))
        return finish(fr, t, split=4 + 11 * p, fl=0.95 * math.exp(-x / 0.18) + 0.4 * flash_env(t), gl=0.35 * p, blm=0.3,
                      zb=0.2 * math.exp(-x / 0.15), sh=18 * math.exp(-x / 0.4))
    y = t - bt(100)
    fr = np.zeros((H, W, 3), np.uint8)
    fr[:] = PLUM
    cv2.line(fr, (0, H // 2), (int(W * clamp(y / (BAR * 1.2))), H // 2), RED, 5, cv2.LINE_AA)
    put(fr, "口座残高", "round", 70, W / 2, H / 2 - 190, (255, 255, 255), ease(y / 0.1), "cm", spacing=16)
    put(fr, "¥0", "wide", 200, W / 2, H / 2 + 150, rgb(RED), ease(y / 0.1), "cm")
    narr(fr, t, bt(100), "帳戶餘額：{¥0}", dur=2 * BAR)
    return finish(fr, t, fl=0.6 * flash_env(t, 0.05), gl=0.8 * flash_env(t, 0.06), scan=True)


# ════════════════════════ CH.6 為什麼  (bars 102–137) ════════════════════════
def s_after(t):
    """bars 102–110: and still she opens the chart tomorrow"""
    b = tb(t)
    tbl = [(102, "04_3", "即使如此——"), (104, "05_5", "明天，她們還是會打開線圖。"), (106, "03_6", "為什麼？"), (108, "07_6", "為什麼人，總是重蹈覆轍？")]
    cur = [c for c in tbl if b >= c[0]][-1]
    b0, im, line = cur
    t0 = bt(b0)
    x = t - t0
    fe = flash_env(t, 0.07)
    fr = shot_full(t, t0, 2 * BAR, im, (0.5, 0.42), grade=(C("120618"), C("f3d6ff"), 0.6), punch=0.03)
    fr = dim(fr, 0.62 + 0.2 * fe)
    ktext(fr, line, "min", 120 if len(line) < 12 else 104, W / 2, H / 2 + 40, x, (255, 255, 255), stag=0.04, shadow=6, stroke=4, sfill=rgb(PLUM))
    chapter_card(fr, t, bt(102), "06", "為什麼", "WHY?", INK, dur=1.0)
    out = finish(fr, t, split=8 * fe, fl=0.3 * fe + 0.5 * math.exp(-x / 0.12), blm=0.25)
    if b > 109.6:
        out = dim(out, 1 - smooth((b - 109.6) / 0.4))
    return out


def s_mirror(t):
    """bars 110–121 (quiet): mother and daughter, the same face"""
    b = tb(t)
    x = t - bt(110)
    fr = np.zeros((H, W, 3), np.uint8)
    fr[:] = PLUM
    kl = ease5(x / 0.9)
    kr = ease5((t - bt(113)) / 0.9)
    pw, ph = 820, 760
    for side, im, k_, lab, yr in ((-1, "01_1", kl, "媽媽", "2008"), (1, "03_5", kr, "女兒", "幾年後")):
        if k_ <= 0:
            continue
        c = crop(EP + im + ".jpg", pw, ph, 1.08 + 0.02 * math.sin(t * 0.5), 0.5, 0.42)
        c = duotone(c, C("140a22"), C("ffd0e0") if side < 0 else C("d0e8ff"), 0.75)
        cx = W / 2 + side * 440
        sp = np.dstack([c, np.full((ph, pw), 255, np.uint8)])
        sp = tilt(sp, side * -14 * (1 - 0.3 * math.sin(t * 0.6)))
        place(fr, sp, cx + side * (1 - k_) * 700, 450, 1.0, 0, k_, 18, PINK if side < 0 else CYAN, 0.5)
        put(fr, yr, "wide", 60, cx - 150, 880, (255, 255, 255), k_, "cm")
        put(fr, lab, "min", 70, cx + 150, 880, rgb(PINK_L if side < 0 else CYAN), k_, "cm", spacing=20)
    lines = [(110, "先是，媽媽。"), (113, "然後，是女兒。"), (116, "同一個貨幣對。{同一張臉。}"), (118.5, "這，不只是她們家的故事。")]
    cur = [l for l in lines if b >= l[0]][-1]
    nxt = [l[0] for l in lines if l[0] > cur[0]]
    narr(fr, t, bt(cur[0]), cur[1], dur=((nxt[0] if nxt else 121) - cur[0]) * BAR - 0.05, y=H - 120)
    if b >= 116:
        y = t - bt(116)
        put(fr, "＝", "wide", 170, W / 2, 450, rgb(YELLOW), ease(y / 0.2), "cm", scale=1 + 0.3 * math.exp(-y / 0.15))
    fr = finish(fr, t, blm=0.3, scan=True)
    if b < 110.4:
        fr = dim(fr, smooth((b - 110) / 0.4))
    return fr


def odometer(fr, cx, y, val, size=250, col=(255, 255, 255), tile=INK, accent=PINK, alpha=1.0):
    """4-digit mechanical counter.  `val` may be fractional: digits roll continuously."""
    dw = int(size * 0.86)
    dh = int(size * 1.08)
    gap = int(size * 0.06)
    total = 4 * dw + 3 * gap
    x = cx - total / 2
    v = max(0.0, val)
    wheels = []
    carry = v - math.floor(v)
    whole = int(math.floor(v))
    for i in range(4):
        d = whole // (10 ** i) % 10
        wheels.append((d, carry))
        carry = carry if d == 9 else 0.0
    wheels = wheels[::-1]
    y = int(y)
    for i, (d0, fr_) in enumerate(wheels):
        bx = int(x + i * (dw + gap))
        blit(fr, panel(dw, dh, int(size * 0.1), tile), bx, y, 0.96 * alpha)
        x0, y0, x1, y1 = max(0, bx), max(0, y), min(W, bx + dw), min(H, y + dh)
        if x1 <= x0 or y1 <= y0:
            continue
        tmp = fr[y0:y1, x0:x1]
        for dd, off in ((d0, -fr_ * dh), ((d0 + 1) % 10, (1 - fr_) * dh)):
            if abs(off) >= dh:
                continue
            sp = text(str(dd), "wide", size, col)
            hh, ww = sp.shape[:2]
            xx = bx + (dw - ww) // 2 - x0
            yy = int(y + (dh - hh) // 2 + off) - y0
            ya, yb = max(0, yy), min(y1 - y0, yy + hh)
            xa, xb = max(0, xx), min(x1 - x0, xx + ww)
            if yb > ya and xb > xa:
                s = sp[ya - yy:yb - yy, xa - xx:xb - xx]
                al = s[:, :, 3:4].astype(np.float32) / 255 * alpha
                reg = tmp[ya:yb, xa:xb]
                reg[:] = (reg * (1 - al) + s[:, :, :3] * al).astype(np.uint8)
        rect(fr, bx, y + dh - int(size * 0.07), bx + dw, y + dh, accent, alpha)
        rect(fr, bx, y + dh // 2 - 1, bx + dw, y + dh // 2 + 1, PLUM, 0.35 * alpha)


def s_rewind(t):
    """bars 121–137: rewind to 1637 — only the counter runs backwards, no event is shown yet"""
    b = tb(t)
    k = clamp((b - 121) / 15.2)
    yr = 2026 - (2026 - 1637) * (smooth(k) ** 1.15)
    spd = 0.6 + 2.6 * math.sin(math.pi * clamp(k)) ** 0.8
    fr = bg_dark(-t * spd, PURPLE, 1.0, 0.5, (C("0d0618"), C("2a1048")))
    speedlines(fr, -t, PURPLE, 26, 3600 * spd, 0.35)
    strip = ["07_5", "06_4", "05_3", "04_6", "03_5", "03_1", "02_4", "02_1", "01_5", "01_1", "01_3"]
    fw, fh, gapx = 420, 236, 40
    pitch = fw + gapx
    off = (t * 1500 * spd)
    for row, (yy, dirn) in enumerate(((150, 1), (H - 150, -1))):
        base = int(off // pitch)
        fracx = off % pitch
        for i in range(-1, 7):
            j = (i - base * dirn + row * 3) % len(strip)
            xx = i * pitch + fracx * dirn
            k_ = ("thumb", strip[j])
            if k_ not in _ic:
                _ic[k_] = duotone(crop(EP + strip[j] + ".jpg", fw, fh), C("180a2a"), C("e9c8ff"))
            x0, x1 = int(max(0, xx)), int(min(W, xx + fw))
            if x1 > x0:
                reg = fr[yy - fh // 2:yy + fh // 2, x0:x1]
                src = _ic[k_][:, x0 - int(xx):x1 - int(xx)]
                if src.shape[1] == reg.shape[1]:
                    cv2.addWeighted(src, 0.85, reg, 0.15, 0, reg)
    fr = mblur(fr, 6 + 12 * spd)
    fe = flash_env(t, 0.1)
    odometer(fr, W / 2, 380, yr, 250, (255, 255, 255), INK, PINK)
    put(fr, "◀◀ REWIND", "lat", 56, W / 2, 300, rgb(YELLOW), 0.6 + 0.4 * (int(t * 4) % 2), "cm", spacing=16)
    lines = [(121, "把時間，往回轉——"), (125, "十年前。一百年前。再往前。"), (129, "人類史上的每一次「這次不一樣」。"), (133, "從 {389 年前}，開始算起。")]
    cur = [l for l in lines if b >= l[0]][-1]
    narr(fr, t, bt(cur[0]), cur[1], dur=4 * BAR - 0.05, y=H - 120)
    if b >= 133:
        y = t - bt(133)
        ktext(fr, "泡沫里程表", "min", 130, W / 2, 760, y, (255, 255, 255), stag=0.07, shadow=6, spacing=24)
        put(fr, "BUBBLE ODOMETER", "wideb", 44, W / 2, 860, rgb(PINK), ease((y - 0.5) / 0.3), "cm", spacing=14)
    chapter_card(fr, t, bt(121), "07", "倒帶", "REWIND", PURPLE, dur=1.0)
    fl = 0.5 * fe
    if b > 136.5:
        fl = max(fl, (b - 136.5) * 2)
    return finish(fr, t, split=3 + 10 * fe + 10 * max(0, b - 136), fl=fl, blm=0.4, scan=True, gl=0.25 * fe)


# ════════════════════════ CH.8 泡沫里程表  (2:59.5 – 3:19.9) ════════════════════════
TL_B0 = 137
# (beats, year, zh title, en, one line, image, object word, accent colour)
EVENTS = [
    (6, 1637, "鬱金香狂熱", "TULIP MANIA", "一顆球莖，換一棟運河豪宅。", "tulip.jpg", "鬱金香", C("ff6b6b")),
    (5, 1720, "南海泡沫", "SOUTH SEA BUBBLE", "牛頓：「我算不出人的瘋狂。」", "southsea.jpg", "南海股票", C("ffb14e")),
    (5, 1846, "鐵路狂熱", "RAILWAY MANIA", "一年核准 9,500 英里新鐵路。", "railway.png", "鐵路股", C("e8d9a0")),
    (5, 1929, "華爾街大崩盤", "THE GREAT CRASH", "道瓊指數：−89%。", "crash1929.jpg", "美股", C("d9d9e8")),
    (5, 1989, "日本泡沫經濟", "JAPAN BUBBLE", "日經 38,915 點。34 年後才再見。", "japan.jpg", "土地", C("ff5d8f")),
    (5, 2000, "網路泡沫", "DOT-COM BUBBLE", "那斯達克：−78%。", "dotcom.jpg", ".com", C("5cc8ff")),
    (5, 2008, "金融海嘯", "LEHMAN SHOCK", "澳幣／日圓 104 → 55。媽媽的 2000 萬。", "lehman2.jpg", "次級房貸", C("ffe45c")),
    (4, 2015, "瑞郎黑天鵝", "SNB SHOCK", "歐元／瑞郎：數分鐘 −30%。", "snb.jpg", "瑞士法郎", C("ff5a5a")),
    (4, 2017, "比特幣狂潮", "CRYPTO MANIA", "$19,783 → 一年後 −84%。", "bitcoin.jpg", "比特幣", C("ffb11f")),
    (4, 2021, "迷因股狂熱", "MEME STOCKS", "GameStop：$17 → $483。", "gamestop.jpg", "迷因股", C("ff4d4d")),
    (4, 2021, "NFT 狂熱", "NFT MANIA", "一張 JPEG：6,930 萬美元。", "nft3.jpg", "JPEG", C("c58bff")),
    (4, 2022, "LUNA・FTX 崩潰", "CRYPTO WINTER", "400 億美元，一週歸零。", "ftx.jpg", "LUNA", C("6fd3ff")),
    (7, 2023, "AI 泡沫？", "AI BOOM", "輝達市值：5 兆美元。「這次不一樣。」", "ai.png", "GPU", C("7dffb0")),
]
_acc = 0
EV_T = []
for _e in EVENTS:
    EV_T.append(bt(TL_B0) + _acc * BEAT)
    _acc += _e[0]
TL_END = bt(TL_B0) + _acc * BEAT          # = bar 152.75 → 3:19.9


def bubble_curve(x):
    if x < 0.72:
        u = x / 0.72
        return 0.06 + 0.94 * (0.25 * u + 0.75 * u ** 4.2)
    u = (x - 0.72) / 0.28
    return 0.12 + 0.88 * math.exp(-u * 6.5) + 0.07 * math.exp(-((u - 0.42) / 0.09) ** 2)


def draw_curve(fr, x, y, w, h, prog, col, thick=4, stop_at_peak=False, wob=0.0, seed=0, fillc=None):
    n = 110
    pts = []
    lim = 0.72 if stop_at_peak else 1.0
    for i in range(n + 1):
        u = i / n
        if u > prog or u > lim + 1e-6:
            break
        v = bubble_curve(u) + wob * (0.03 * math.sin(u * 37 + seed) + 0.018 * math.sin(u * 91 + seed * 2.3))
        pts.append((int(x + u * w), int(y + h - v * h)))
    if len(pts) > 1:
        if fillc is not None:
            x0, x1 = pts[0][0], pts[-1][0] + 1
            y0, y1 = int(y - 4), int(y + h) + 1
            reg = fr[max(0, y0):y1, x0:x1]
            ov = reg.copy()
            poly = np.array([(p[0] - x0, p[1] - max(0, y0)) for p in pts] + [(pts[-1][0] - x0, y1), (0, y1)], np.int32)
            cv2.fillPoly(ov, [poly], fillc)
            cv2.addWeighted(ov, 0.28, reg, 0.72, 0, reg)
        cv2.polylines(fr, [np.array(pts, np.int32)], False, col, thick, cv2.LINE_AA)
    return pts[-1] if pts else None


RAIL_X0, RAIL_X1, RAIL_Y = 130, W - 130, H - 70


def rail(fr, idx, prog, a=1.0, done=False):
    n = len(EVENTS)
    xs = [RAIL_X0 + (RAIL_X1 - RAIL_X0) * i / (n - 1) for i in range(n)]
    rect(fr, 0, RAIL_Y - 52, W, H, PLUM, 0.82 * a)
    rect(fr, RAIL_X0, RAIL_Y - 3, RAIL_X1, RAIL_Y + 3, C("5a3a66"), a)
    xe = xs[idx] + ((xs[idx + 1] - xs[idx]) * prog if idx < n - 1 else 0)
    if done:
        xe = RAIL_X1
    rect(fr, RAIL_X0, RAIL_Y - 4, xe, RAIL_Y + 4, PINK, a)
    for i, xx in enumerate(xs):
        lab = str(EVENTS[i][1]) if i != n - 1 else "AI"
        if i < idx or done:
            cv2.circle(fr, (int(xx), RAIL_Y), 9, PINK, -1, cv2.LINE_AA)
            put(fr, lab, "num", 26, xx, RAIL_Y + 14, rgb(PINK_L), a, "ct")
        elif i == idx:
            cv2.circle(fr, (int(xx), RAIL_Y), 19, WHITE, -1, cv2.LINE_AA)
            cv2.circle(fr, (int(xx), RAIL_Y), 12, EVENTS[i][7], -1, cv2.LINE_AA)
            put(fr, lab, "num", 36, xx, RAIL_Y + 10, (255, 255, 255), a, "ct")
        else:
            cv2.circle(fr, (int(xx), RAIL_Y), 6, C("5a3a66"), -1, cv2.LINE_AA)
            put(fr, lab, "num", 24, xx, RAIL_Y + 14, rgb(C("8a6a96")), a, "ct")


def photo_card(name, bw, bh, zoom, cx, cy, col):
    s = img(name)
    if s.shape[2] == 4:
        s = s[:, :, :3]
    h, w = s.shape[:2]
    sc = min(bw / w, bh / h)
    cw, ch = int(w * sc), int(h * sc)
    scz = max(cw / w, ch / h) * zoom
    M = np.array([[scz, 0, cw / 2 - cx * w * scz], [0, scz, ch / 2 - cy * h * scz]], np.float32)
    inner = cv2.warpAffine(s, M, (cw, ch), flags=cv2.INTER_AREA if scz < 0.7 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    bd = 16
    card = np.full((ch + bd * 2 + 14, cw + bd * 2, 4), 255, np.uint8)
    card[:, :, :3] = C("fbf6f2")
    card[bd:bd + ch, bd:bd + cw, :3] = inner
    card[ch + bd * 2:, :, :3] = col
    return card


def s_timeline(t):
    idx = max(i for i, s in enumerate(EV_T) if t >= s)
    beats, year, zh, en, line, im, _, col = EVENTS[idx]
    t0 = EV_T[idx]
    dur = beats * BEAT
    x = t - t0
    k = clamp(x / dur)
    p = pulse(t)
    be = beat_env(t, 0.1)
    is_ai = idx == len(EVENTS) - 1
    name = H_ + im
    d = 1 if idx % 2 == 0 else -1

    fr = blurred(name, 0.34).copy()
    ov = bg_dark(t, col, 2.2, 0.60)
    fr = cv2.addWeighted(fr, 0.62, ov, 0.5, 0)
    speedlines(fr, t, col, 14, 5200, 0.22)


    card = photo_card(name, 960, 700, lerp(1.0, 1.08, k) + 0.035 * be, 0.5, lerp(0.47, 0.53, k), col)
    fl_ = 1 - ease5(x / 0.2)
    card = tilt(card, d * (-78 * fl_ - 9 + 4 * math.sin(t * 2.2)), 3 * math.sin(t * 1.7))
    place(fr, card, 590 + d * fl_ * -260, 470, 1.0 + 0.03 * be, d * -1.5, clamp(x * 14), 22, PLUM, 0.6)

    rx = 1130
    put(fr, f"{idx + 1:02d}", "wide", 44, rx, 92, rgb(col))
    put(fr, f"/ {len(EVENTS):02d}　泡沫里程表", "roundb", 30, rx + 86, 100, (255, 255, 255), 0.85)
    if is_ai:
        seg_ = dur / 4
        yb = min(3, int(x / seg_))
        yv = 2022 + yb + ease5((x - yb * seg_) / 0.16)
    else:
        prev = EVENTS[idx - 1][1] if idx else 1600
        yv = prev + (year - prev) * ease5(x / 0.2)
        if abs(yv - year) < 0.02:
            yv = year
    odometer(fr, rx + 330, 160, yv, 176, (255, 255, 255), INK, col)
    ktext(fr, zh, "min", 100 if len(zh) <= 6 else 84, rx - 4, 440, x - 0.05, (255, 255, 255), "lm", stag=0.022, shadow=5, rise=40)
    a1 = ease((x - 0.12) / 0.16)
    blit(fr, skew_plate(tw(en, "lat", 38, 5) + 60, 56, col), rx - 6 + (1 - a1) * -60, 508, a1)
    put(fr, en, "lat", 38, rx + 28 + (1 - a1) * -60, 508, rgb(PLUM), a1, spacing=5)
    parts = [line]
    if len(line) > 15 and "。" in line[:-1]:
        cut = line.index("。") + 1
        parts = [line[:cut], line[cut:]]
    for j, pt in enumerate(parts):
        aj = ease((x - 0.2 - 0.1 * j) / 0.18)
        put(fr, pt, "roundb", 42, rx, 590 + j * 56 + (1 - aj) * 24, (255, 255, 255) if j == 0 else rgb(YELLOW), aj, shadow=3)

    gx, gy, gw, gh = rx, 730 if len(parts) > 1 else 700, 650, 180 if len(parts) > 1 else 205
    blit(fr, panel(gw + 40, gh + 44, 20, PLUM), gx - 20, gy - 22, 0.72)
    end = draw_curve(fr, gx, gy, gw, gh, clamp(k * 1.08), col, 6, stop_at_peak=is_ai, wob=1.0, seed=idx * 3.1, fillc=col)
    if end:
        cv2.circle(fr, end, 11, WHITE, -1, cv2.LINE_AA)
        if is_ai and k * 1.08 >= 0.72:
            for j in range(8):
                if (j + int(t * 8)) % 2 == 0:
                    cv2.circle(fr, (end[0] + 26 + j * 22, end[1] + int(8 * math.sin(j + t * 6))), 5, WHITE, -1, cv2.LINE_AA)
            put(fr, "？", "min", 150, end[0] + 120, end[1] + 96, (255, 255, 255), 1, "cm", scale=1 + 0.2 * be, shadow=5)
    rail(fr, idx, k)

    if idx < 4:
        fr = tint(fr, C("ecd3a8"), 0.14)
    fr = cut_fx(fr, x, d, 0.8)
    return finish(fr, t, split=2 + 5 * p, fl=0.8 * math.exp(-x / 0.08), blm=0.35, zb=0.1 * math.exp(-x / 0.07), gl=0.12 * p if is_ai else 0)


# ════════════════════════ CH.9 瞬息萬變 / 亙古不變  (bars 153–169) ════════════════════════
def s_changing(t):
    """bars 153–157: the object changes every beat (words only)"""
    x = t - bt(153)
    if x < 0:
        return np.full((H, W, 3), 255, np.uint8)
    nbt = int(x / BEAT)
    words = [e[6] for e in EVENTS] + ["？？？"]
    col = EVENTS[min(nbt, len(EVENTS) - 1)][7]
    fr = bg_dark(t, col, 2.6, 0.5, (C("12061a"), C("2a1038")))
    speedlines(fr, t, col, 26, 5200, 0.4)
    put(fr, "瞬息萬變之物", "min", 96, W / 2, 150, (255, 255, 255), 1, "cm", spacing=14, shadow=5)
    put(fr, "THINGS EVER-CHANGING", "wideb", 34, W / 2, 240, rgb(PINK), 1, "cm", spacing=10)
    if nbt < len(words):
        wx = x - nbt * BEAT
        w_ = words[nbt]
        yr = str(EVENTS[nbt][1]) if nbt < len(EVENTS) - 1 else ("NOW" if nbt == len(EVENTS) - 1 else "NEXT")
        put(fr, yr, "wide", 90, W / 2, 400, rgb(col), 1, "cm")
        tx = text(w_, "round", 260 if len(w_) <= 4 else 200, rgb(PLUM))
        pl = skew_plate(tx.shape[1] + 120, tx.shape[0] - 30, col)
        k = back(wx / 0.1, 2.4)
        place(fr, pl, W / 2, 660, 0.7 + 0.3 * k, -4 + (nbt % 2) * 8, 1, 14, WHITE, 0.9)
        place(fr, tx, W / 2, 650, 0.7 + 0.3 * k, -4 + (nbt % 2) * 8)
        ring(fr, W / 2, 660, wx, col, 1100, 14, 0.3)
    else:
        wx = x - len(words) * BEAT
        ktext(fr, "標的，一直在變。", "min", 170, W / 2, 640, wx, (255, 255, 255), stag=0.03, shadow=7)
    rail(fr, len(EVENTS) - 1, 1, done=True)
    return finish(fr, t, split=3 + 7 * pulse(t), fl=0.3 * beat_env(t, 0.06) + 0.9 * math.exp(-x / 0.12), blm=0.35)


def s_unchanging(t):
    """bars 157–161: thirteen bubbles, one curve"""
    b = tb(t)
    x = t - bt(157)
    fr = dim(cover(OFF + "top_losscut_losscut_bg.jpg", 1.5, 0.5, 0.5, rot=-t * 14), 0.32)
    put(fr, "亙古不變之物", "min", 96, W / 2, 130, (255, 255, 255), 1, "cm", spacing=14, shadow=5)
    put(fr, "THINGS THAT NEVER CHANGE", "wideb", 34, W / 2, 220, rgb(CYAN), 1, "cm", spacing=10)
    gx, gy, gw, gh = 250, 300, 1420, 560
    blit(fr, panel(gw + 70, gh + 70, 30, PLUM), gx - 35, gy - 35, 0.6)
    n = len(EVENTS)
    for i in range(n):
        ts = i * BAR / 5.2
        if x < ts:
            break
        pr = clamp((x - ts) / (BAR * 0.9))
        end = draw_curve(fr, gx, gy, gw, gh, pr, EVENTS[i][7], 3, stop_at_peak=(i == n - 1), wob=1.0, seed=i * 3.1)
        if end and pr < 1:
            cv2.circle(fr, end, 8, WHITE, -1, cv2.LINE_AA)
            put(fr, str(EVENTS[i][1]) if i < n - 1 else "AI ？", "num", 40, end[0] + 14, end[1] - 50, rgb(EVENTS[i][7]), 1)
    if b >= 160:
        pr = clamp((t - bt(160)) / (BAR * 0.8))
        end = draw_curve(fr, gx, gy, gw, gh, pr, PINK, 10, wob=0.0, fillc=PINK)
        if end:
            cv2.circle(fr, end, 14, WHITE, -1, cv2.LINE_AA)
            blit(fr, sprite(DECO + "character_thumb_kurumi.png", 96), min(end[0] + 20, gx + gw - 120), max(gy, end[1] - 110))
    caps = [(157, "十三個泡沫，"), (158.5, "疊起來，是同一條線。"), (160, "久留美的帳戶，也是。")]
    cur = [c for c in caps if b >= c[0]][-1]
    cx_ = t - bt(cur[0])
    ktext(fr, cur[1], "min", 100, W / 2, 965, cx_, (255, 255, 255), stag=0.03, shadow=6)
    return finish(fr, t, split=2 + 5 * pulse(t),
                  fl=0.8 * math.exp(-x / 0.12) + 0.25 * flash_env(t) + 0.5 * math.exp(-cx_ / 0.08) * (cur[0] != 157), blm=0.4)


GREED = ["02_3", "03_1", "02_4", "05_3", "04_2", "07_2", "02_2", "06_6", "04_4", "05_6", "07_5", "04_1", "03_4", "06_5", "07_3", "04_5"]
FEAR = ["01_1", "03_5", "02_5", "04_6", "01_6", "06_4", "03_6", "05_1", "07_1", "02_1", "03_2", "06_1", "07_4", "02_6", "05_2", "06_3"]


def big_word(fr, zh, en, col, x, y=H / 2):
    tx = text(zh, "min", 330, (255, 255, 255))
    pl = skew_plate(tx.shape[1] + 140, tx.shape[0] - 60, col)
    k = back(x / 0.12, 2.4)
    place(fr, pl, W / 2, y - 10, 0.7 + 0.3 * k, -5, 1, 16, PLUM, 0.9)
    place(fr, tx, W / 2, y - 26, 0.7 + 0.3 * k, -5)
    put(fr, en, "wide", 70, W / 2, y + 250, (255, 255, 255), 1, "cm", spacing=30, shadow=5)


def s_human(t):
    """bars 161–169: greed / fear / 'this time is different' / losscut"""
    b = tb(t)
    p = pulse(t)
    zb = 0.0
    half = BEAT / 2
    if b < 162:
        i = int((t - bt(161)) / half)
        t0 = bt(161) + i * half
        fr = cover(EP + GREED[i % 16] + ".jpg", 1.12 + 0.07 * math.exp(-(t - t0) / 0.06), 0.5, 0.42, rot=(rnd(i) - 0.5) * 4)
        fr = duotone(fr, C("5a2a00"), C("fff2a8"), 0.55)
        big_word(fr, "貪婪", "GREED", C("ff9d1e"), t - bt(161))
        zb = 0.14 * math.exp(-(t - bt(161)) / 0.1)
    elif b < 163:
        i = int((t - bt(162)) / half)
        t0 = bt(162) + i * half
        fr = cover(EP + FEAR[i % 16] + ".jpg", 1.12 + 0.07 * math.exp(-(t - t0) / 0.06), 0.5, 0.42, rot=(rnd(i) - 0.5) * 5,
                   ox=(rnd(int(t * FPS)) - 0.5) * 24)
        fr = duotone(fr, C("06041c"), C("b8c4ff"), 0.6)
        big_word(fr, "恐懼", "FEAR", C("3848e0"), t - bt(162))
        zb = 0.14 * math.exp(-(t - bt(162)) / 0.1)
    elif b < 165:
        mix = [v for pair in zip(GREED, FEAR) for v in pair]
        i = int((t - bt(163)) / half)
        t0 = bt(163) + i * half
        fr = cover(EP + mix[i % len(mix)] + ".jpg", 1.12 + 0.07 * math.exp(-(t - t0) / 0.05), 0.5, 0.42, rot=(rnd(i) - 0.5) * 6)
        fr = duotone(fr, C("06041c"), C("b8c4ff"), 0.6) if i % 2 else duotone(fr, C("5a2a00"), C("fff2a8"), 0.5)
        y = t - bt(163)
        ktext(fr, "「這次不一樣。」", "min", 200, W / 2, H / 2 - 70, y, (255, 255, 255), stag=0.03, stroke=8, sfill=rgb(C("9a22c8")), shadow=8)
        if b >= 164:
            y2 = t - bt(164)
            tx = text("——每一次，都一樣。", "min", 120, rgb(PLUM))
            pl = skew_plate(tx.shape[1] + 90, tx.shape[0] - 20, YELLOW)
            k = back(y2 / 0.14)
            place(fr, pl, W / 2, H / 2 + 190, 0.7 + 0.3 * k, -3, 1, 12, PLUM, 0.9)
            place(fr, tx, W / 2, H / 2 + 184, 0.7 + 0.3 * k, -3)
    else:
        x = t - bt(165)
        fr = losscut_scene(t, bt(165), spin=1.6, fall=1.6, k=0.8, dy=-60)
        falling_candles(fr, t, RED, 16, alpha=0.4)
        sp = sprite(OFF + "top_losscut_losscut_txt.png", 150)
        blit(fr, sp, W / 2, 750, 1.0, 1 + 0.8 * math.exp(-x / 0.12) + 0.05 * beat_env(t), "cm")
        y = x - BAR
        if y > 0:
            ktext(fr, "人，亙古不變。", "min", 170, W / 2, 930, y, (255, 255, 255), stag=0.04, stroke=6, sfill=rgb(C("8a0020")), shadow=7)
        zb = 0.2 * math.exp(-x / 0.14)
        if b >= 168:
            fr = flash(fr, smooth(b - 168) * 0.9)
    sec0 = max(s for s in (bt(161), bt(162), bt(163), bt(165)) if t >= s)
    return finish(fr, t, split=3 + 9 * p, fl=0.85 * math.exp(-(t - sec0) / 0.12) + 0.35 * flash_env(t), gl=0.2 * p, blm=0.3, zb=zb)


def s_title(t):
    """bars 169–178: 致瞬息萬變之物 (a new image on every flash, faster and faster) ， 及亙古不變之物 (one image, unmoved)"""
    b = tb(t)
    fe = flash_env(t, 0.06)
    i = int(np.searchsorted(FLASHES, t + 1e-4))
    allimgs = GREED + FEAR
    if b < 173:
        name = allimgs[(i * 7) % len(allimgs)]
        fr = cover(EP + name + ".jpg", 1.12 + 0.05 * fe, 0.5, 0.42)
        fr = duotone(fr, C("1a0826"), [C("ffd0e2"), C("d0f2ff"), C("fff0b8"), C("e7ccff")][i % 4], 0.8)
        fr = dim(fr, 0.7)
        x = t - bt(169)
        put(fr, "致", "min", 130, W / 2, 290, rgb(PINK_L), 1, "cm", shadow=5)
        ktext(fr, "瞬息萬變之物，", "min", 220, W / 2, 520, x, (255, 255, 255), stag=0.045, shadow=9, spacing=6)
        put(fr, "TO THINGS EVER-CHANGING,", "wideb", 44, W / 2, 720, rgb(PINK_L), ease((x - 0.4) / 0.3), "cm", spacing=12)
        return finish(fr, t, split=3 + 9 * fe, fl=0.8 * math.exp(-x / 0.14) + 0.2 * fe, blm=0.3)
    x = t - bt(173)
    fr = losscut_scene(t, bt(173), spin=0.5, fall=0.25, k=0.72, dy=-110)
    fr = dim(fr, 0.8)
    put(fr, "及", "min", 130, W / 2, 680, rgb(CYAN), 1, "cm", shadow=5)
    ktext(fr, "亙古不變之物。", "min", 220, W / 2, 860, x, (255, 255, 255), stag=0.045, shadow=9, spacing=6)
    put(fr, "AND THINGS THAT NEVER CHANGE.", "wideb", 44, W / 2, 1010, rgb(CYAN), ease((x - 0.4) / 0.3), "cm", spacing=12)
    k = clamp((b - 175) / 3)
    out = finish(fr, t, split=2 + 7 * fe, fl=0.8 * math.exp(-x / 0.14) + (0.2 + 0.2 * k) * fe, blm=0.3)
    if b > 177.5:
        out = flash(out, smooth((b - 177.5) / 0.5))
    return out


CREDITS = [
    "FX戦士くるみちゃん　©でむにゃん・炭酸だいすき／KADOKAWA／「FX戦士くるみちゃん」製作委員会",
    "Music：INTERNET YAMERO — Aiobahn feat. KOTOKO（NEEDY GIRL OVERDOSE）",
    "Sync：osu! beatmap by NeonMarijuana [INTERNET ANGEL]",
    "歷史圖片：Wikimedia Commons（詳見 SOURCES.md）",
    "Fan-made MAD ・ 非營利二次創作",
]


def s_end(t):
    b = tb(t)
    x = t - bt(178)
    if b < 182:
        fr = np.zeros((H, W, 3), np.uint8)
        fr[:] = C("fbf3f6")
        ktext(fr, "致瞬息萬變之物，", "min", 136, W / 2, 400, x - 0.2, rgb(INK), stag=0.05, rise=20, spacing=8)
        ktext(fr, "及亙古不變之物。", "min", 136, W / 2, 590, x - BAR * 0.9, rgb(INK), stag=0.05, rise=20, spacing=8)
        put(fr, "To things ever-changing, and things that never change.", "lat", 34, W / 2, 760, rgb(C("b07a98")), ease((x - BAR * 1.6) / 0.8), "cm",
            spacing=2)
        blit(fr, sprite(DECO + "common_logo.png", 120), W / 2, 930, ease((x - BAR * 2) / 0.8), 1.0, "cm")
        fr = flash(fr, 1 - smooth(x / 0.5))
        if b > 181.6:
            fr = dim(fr, 1 - smooth((b - 181.6) / 0.4))
        return fr
    y = t - bt(182)
    fr = bg_desk(t, 0, deco=0.6)
    iw, ih = win_inner(1040, 640)
    win(fr, W / 2, 380, 1040, 640, "tomorrow.mp4", crop(EP + "07_5.jpg", iw, ih, 1.05 + 0.012 * y, 0.5, 0.4), TH_LIGHT, wpop(y - 0.1), -1.5)
    narr(fr, t, bt(182) + 0.5, "明天，市場依然會開盤。", dur=20, y=H - 350)
    blit(fr, panel(W - 200, 232, 30, PLUM), 100, H - 250, 0.8 * ease((y - 1.0) / 0.5))
    for i, c in enumerate(CREDITS):
        put(fr, c, "roundm", 26, W / 2, H - 234 + i * 42, (240, 230, 242), ease((y - 1.1 - i * 0.12) / 0.4), "ct")
    fr = vignette(fr)
    return dim(fr, min(smooth(y / 0.5), 1 - smooth((t - (DUR - 2.2)) / 1.9)))


SECTIONS = [
    (0, s_intro), (10, s_build), (18, s_drop1), (26, s_ch2), (42, s_ch3), (58, s_relief), (62, s_ch4), (70, s_ch5), (85, s_hold),
    (86, s_pray), (94, s_drop2), (102, s_after), (110, s_mirror), (121, s_rewind), (137, s_timeline), (153, s_changing),
    (157, s_unchanging), (161, s_human), (169, s_title), (178, s_end),
]


def render(t):
    b = tb(t)
    fn = SECTIONS[0][1]
    for b0, f in SECTIONS:
        if b >= b0 - 1e-6:
            fn = f
    if fn is s_timeline and t >= TL_END:
        fn = s_changing            # last quarter-bar before 153: white hand-over, no event on screen
    fr = fn(t)
    if t < 0.5:
        fr = dim(fr, smooth(t / 0.5))
    return fr


def render_chunk(k, n, outdir):
    f0, f1 = NF * k // n, NF * (k + 1) // n
    out = os.path.join(outdir, f"chunk_{k:02d}.mp4")
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-g", str(FPS * 2), out],
        stdin=subprocess.PIPE)
    for i in range(f0, f1):
        fr = render((i + 0.5) / FPS)
        p.stdin.write(np.ascontiguousarray(fr).tobytes())
        if (i - f0) % 150 == 0:
            print(f"chunk {k}: {i - f0}/{f1 - f0}", flush=True)
    p.stdin.close()
    p.wait()
    return out


def main():
    cmd = sys.argv[1]
    if cmd == "still":
        cv2.imwrite(sys.argv[3], render(float(sys.argv[2])))
    elif cmd == "chunk":
        render_chunk(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    elif cmd == "all":
        out = sys.argv[2]
        n = int(os.environ.get("MAD_JOBS", os.cpu_count() or 4))
        tmp = out + ".chunks"
        os.makedirs(tmp, exist_ok=True)
        ps = [subprocess.Popen([sys.executable, os.path.abspath(__file__), "chunk", str(k), str(n), tmp]) for k in range(n)]
        if any(p.wait() for p in ps):
            sys.exit("chunk failed")
        with open(os.path.join(tmp, "list.txt"), "w") as f:
            for k in range(n):
                f.write(f"file 'chunk_{k:02d}.mp4'\n")
        subprocess.check_call(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(tmp, "list.txt"),
             "-i", os.path.join(ASSETS, "audio.mp3"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
             "-shortest", "-movflags", "+faststart", out])
        print("wrote", out)


if __name__ == "__main__":
    main()
