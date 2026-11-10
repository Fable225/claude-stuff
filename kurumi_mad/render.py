#!/usr/bin/env python3
"""FX戦士くるみちゃん MAD — "致瞬息萬變之物，及亙古不變之物"

Frame-by-frame renderer (numpy + OpenCV + Pillow) synced to the osu! beatmap
of INTERNET YAMERO.  Usage:

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
    """time (s) of bar b"""
    return T0 + b * BAR


def tb(t):
    return (t - T0) / BAR


# ───────────────────────── beatmap ─────────────────────────
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
    """decaying envelope: 1 right on an event, exp decay after"""
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


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, x):
    return a + (b - a) * x


def rnd(*k):
    """deterministic hash → [0,1)"""
    h = 0.0
    for i, v in enumerate(k):
        h += math.sin(v * 12.9898 + i * 78.233 + 1.0) * 43758.5453
    return h - math.floor(h)


# ───────────────────────── fonts / text ─────────────────────────
FD = os.path.join(ASSETS, "fonts")
FONTS = {
    "sans": "NotoSansTC_900Black.ttf",
    "sansb": "NotoSansTC_700Bold.ttf",
    "sansm": "NotoSansTC_500Medium.ttf",
    "jp": "NotoSansJP_900Black.ttf",
    "serif": "NotoSerifTC_900Black.ttf",
    "serifm": "NotoSerifTC_600SemiBold.ttf",
    "dot": "DotGothic16_400Regular.ttf",
    "dela": "DelaGothicOne_400Regular.ttf",
    "bebas": "BebasNeue_400Regular.ttf",
    "mono": "JetBrainsMono_700Bold.ttf",
    "jpb": "NotoSansJP_700Bold.ttf",
}
FALLBACK = {"jp": ["sans"], "jpb": ["sansb"], "sans": ["jp"], "sansb": ["jpb"], "sansm": ["jpb"], "serif": ["sans", "jp"],
            "serifm": ["sansb", "jpb"], "dela": ["jp", "sans"], "dot": ["jpb", "sansb"], "bebas": ["sans", "jp"], "mono": ["jpb", "sansb"]}
_fc, _tc, _cm = {}, {}, {}


def cmap(name):
    if name not in _cm:
        from fontTools.ttLib import TTFont
        _cm[name] = set(TTFont(os.path.join(FD, FONTS[name]), lazy=True).getBestCmap().keys())
    return _cm[name]


def pick(name, c):
    """font name that actually has glyph c"""
    if c == " " or ord(c) in cmap(name):
        return name
    for fb in FALLBACK.get(name, []):
        if ord(c) in cmap(fb):
            return fb
    return name


def font(name, size):
    k = (name, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(os.path.join(FD, FONTS[name]), size)
    return _fc[k]


def text(s, fname, size, fill=(255, 255, 255), stroke=0, sfill=(0, 0, 0), shadow=0, spacing=0):
    """render text → BGRA uint8 sprite (cached)"""
    k = (s, fname, size, fill, stroke, sfill, shadow, spacing)
    if k in _tc:
        return _tc[k]
    f = font(fname, size)
    pad = stroke + shadow + 6
    fs = [pick(fname, c) for c in s]
    mixed = any(n != fname for n in fs)
    if spacing or mixed:
        ws = [font(n, size).getlength(c) for c, n in zip(s, fs)]
        tw = int(sum(ws) + spacing * (len(s) - 1))
    else:
        tw = int(f.getlength(s))
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (tw + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
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
        draw(shadow, shadow, (0, 0, 0, 170), stroke, (0, 0, 0, 170))
    if stroke and (spacing or mixed):
        draw(0, 0, sfill + (255,), stroke, sfill + (255,))
        draw(0, 0, fill + (255,), 0, None)
    else:
        draw(0, 0, fill + (255,), stroke, sfill + (255,))
    a = np.array(im)
    a = np.ascontiguousarray(a[:, :, [2, 1, 0, 3]])
    _tc[k] = a
    return a


def blit(fr, sp, x, y, alpha=1.0, scale=1.0, anchor="lt"):
    """alpha-composite BGRA sprite onto frame. anchor: l/c/r + t/m/b"""
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


def put(fr, s, fname, size, x, y, fill=(255, 255, 255), alpha=1.0, anchor="lt", stroke=0,
        sfill=(0, 0, 0), shadow=0, scale=1.0, spacing=0):
    blit(fr, text(s, fname, size, fill, stroke, sfill, shadow, spacing), x, y, alpha, scale, anchor)


# ───────────────────────── images ─────────────────────────
_ic = {}


def img(name):
    """load asset image → BGR or BGRA uint8 (cached, capped to 2400px)"""
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


def cover(name, zoom=1.0, cx=0.5, cy=0.5, rot=0.0, ox=0.0, oy=0.0, src=None):
    """image filling the frame (cover fit) with zoom / pan / rotation / pixel offset"""
    s = img(name) if src is None else src
    if s.shape[2] == 4:
        s = s[:, :, :3]
    h, w = s.shape[:2]
    sc = max(W / w, H / h) * zoom
    # keep the view inside the image where possible
    hw, hh = W / 2 / sc / w, H / 2 / sc / h
    cx = clamp(cx, hw, 1 - hw) if hw < 0.5 else 0.5
    cy = clamp(cy, hh, 1 - hh) if hh < 0.5 else 0.5
    M = cv2.getRotationMatrix2D((cx * w, cy * h), rot, sc)
    M[0, 2] += W / 2 - cx * w + ox
    M[1, 2] += H / 2 - cy * h + oy
    return cv2.warpAffine(s, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def sprite(name, height):
    """RGBA asset scaled to a given height (cached)"""
    k = ("sp", name, height)
    if k not in _ic:
        a = img(name)
        if a.shape[2] == 3:
            a = np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])
        s = height / a.shape[0]
        _ic[k] = cv2.resize(a, (max(1, int(a.shape[1] * s)), height), interpolation=cv2.INTER_AREA)
    return _ic[k]


def blurred(name, dark=0.45, sigma=28):
    k = ("bl", name, dark, sigma)
    if k not in _ic:
        f = cover(name, 1.15)
        small = cv2.resize(f, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), sigma / 4)
        f = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
        _ic[k] = cv2.convertScaleAbs(f, alpha=dark)
    return _ic[k]


# ───────────────────────── effects ─────────────────────────
def _masks():
    k = "masks"
    if k not in _ic:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        vig = np.clip(1.08 - 0.42 * r ** 2.2, 0, 1)
        scan = np.where((np.arange(H) % 3) == 0, 0.86, 1.0).astype(np.float32)[:, None]
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
    """multiply-ish tint towards a BGR color"""
    if a <= 0:
        return fr
    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    col = np.dstack([cv2.convertScaleAbs(g, alpha=c / 255.0) for c in color])
    return cv2.addWeighted(fr, 1 - a, col, a, 0)


def glitch(fr, t, amt):
    """horizontal slice displacement"""
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


def rect(fr, x0, y0, x1, y1, color, alpha=1.0):
    x0, y0, x1, y1 = [int(v) for v in (max(0, x0), max(0, y0), min(W, x1), min(H, y1))]
    if x1 <= x0 or y1 <= y0:
        return
    if alpha >= 0.999:
        fr[y0:y1, x0:x1] = color
    else:
        r = fr[y0:y1, x0:x1]
        r[:] = (r * (1 - alpha) + np.array(color, np.float32) * alpha).astype(np.uint8)


PINK = (180, 105, 255)     # BGR
MAGENTA = (200, 60, 255)
CYAN = (255, 230, 90)
YELLOW = (80, 235, 255)
RED = (60, 50, 255)
GREEN = (140, 230, 60)
WHITE = (255, 255, 255)
INK = (24, 12, 28)


def rgb(c):
    return (c[2], c[1], c[0])


# ───────────────────────── Kurumi's account (story HUD) ─────────────────────────
# AUD/JPY keyframes (time, price) — her "position" through the song
PRICE_KF = [
    (0.0, 95.20), (bt(10), 95.30), (bt(18), 97.90), (bt(25), 98.60), (bt(34), 99.40),
    (bt(42), 98.70), (bt(50), 98.10), (bt(58), 97.20), (bt(62), 96.40), (bt(70), 95.10),
    (bt(78), 94.35), (bt(85), 94.02), (bt(86), 94.20), (bt(90), 93.95), (bt(94), 93.60),
    (bt(96), 91.40), (bt(100), 88.70), (bt(110), 88.90), (DUR, 89.5),
]
BAL_KF = [
    (0.0, 0), (bt(8), 0), (bt(10), 100_000), (bt(18), 1_000_000), (bt(25), 1_240_000),
    (bt(34), 1_610_000), (bt(42), 1_480_000), (bt(50), 1_350_000), (bt(58), 1_020_000),
    (bt(60), 4_020_000), (bt(70), 2_900_000), (bt(78), 1_950_000), (bt(85), 1_120_000),
    (bt(90), 760_000), (bt(94), 410_000), (bt(96), 96_000), (bt(97), 0), (DUR, 0),
]


def kf(tbl, t):
    for i in range(len(tbl) - 1):
        if t <= tbl[i + 1][0]:
            a, b = tbl[i], tbl[i + 1]
            return lerp(a[1], b[1], (t - a[0]) / max(1e-6, b[0] - a[0]))
    return tbl[-1][1]


def price(t):
    n = 0.16 * math.sin(t * 2.1) + 0.11 * math.sin(t * 5.3 + 1) + 0.07 * math.sin(t * 11.7 + 2) + 0.05 * math.sin(t * 23.1)
    return kf(PRICE_KF, t) + n


def balance(t):
    b = kf(BAL_KF, t)
    if b > 0:
        b *= 1 + 0.012 * math.sin(t * 7.3) + 0.008 * math.sin(t * 17.1)
    return int(b)


def yen(v, sign=False):
    s = f"{abs(v):,}"
    if sign:
        return ("+" if v >= 0 else "−") + "¥" + s
    return ("−" if v < 0 else "") + "¥" + s


def chart(fr, t, x, y, w, h, span=14.0, alpha=0.85, line94=False):
    """live AUD/JPY candles for the last `span` seconds"""
    rect(fr, x, y, x + w, y + h, (18, 10, 22), 0.62 * alpha)
    n = 42
    dt = span / n
    k0 = math.floor(t / dt)
    cs = []
    for i in range(n):
        ta = (k0 - n + 1 + i) * dt
        tb_ = min(t, ta + dt)
        if tb_ <= ta or ta < 0:
            continue
        ps = [price(ta + (tb_ - ta) * j / 6) for j in range(7)]
        cs.append((i, ps[0], ps[-1], max(ps), min(ps)))
    if not cs:
        return
    hi = max(c[3] for c in cs) + 0.15
    lo = min(c[4] for c in cs) - 0.15
    if line94:
        lo = min(lo, 93.8)
        hi = max(hi, 94.2)

    def Y(p):
        return int(y + 8 + (h - 16) * (1 - (p - lo) / (hi - lo)))

    cw = w / n
    ov = fr[y:y + h, x:x + w].copy()
    for i, o, c, hh, ll in cs:
        col = (120, 220, 80) if c >= o else (80, 70, 255)
        xc = int(i * cw + cw / 2)
        cv2.line(ov, (xc, Y(hh) - y), (xc, Y(ll) - y), col, 2, cv2.LINE_AA)
        cv2.rectangle(ov, (int(i * cw + 2), min(Y(o), Y(c)) - y), (int(i * cw + cw - 2), max(Y(o), Y(c)) - y + 1), col, -1)
    if line94 and lo < 94 < hi:
        yy = Y(94.0) - y
        for xx in range(0, w, 22):
            cv2.line(ov, (xx, yy), (xx + 12, yy), (80, 235, 255), 2)
    fr[y:y + h, x:x + w] = cv2.addWeighted(fr[y:y + h, x:x + w], 1 - alpha, ov, alpha, 0)
    if line94 and lo < 94 < hi:
        put(fr, "防衛線 94.00", "jpb", 22, x + 8, Y(94.0) - 30, rgb(YELLOW), alpha)


def hud(fr, t, a=1.0, line94=False, big=False):
    """trading HUD: pair + price + balance + mini chart"""
    if a <= 0.01:
        return
    p = price(t)
    up = price(t) >= price(t - 0.4)
    col = rgb(GREEN) if up else rgb(RED)
    rect(fr, 0, 0, W, 64, (18, 10, 22), 0.72 * a)
    put(fr, "AUD/JPY", "mono", 30, 36, 12, (255, 255, 255), a)
    put(fr, f"{p:6.3f}", "mono", 38, 190, 6, col, a)
    put(fr, "▲" if up else "▼", "sansb", 24, 345, 16, col, a)
    put(fr, "LEVERAGE ×25", "mono", 22, 420, 20, (255, 160, 220), a * 0.9)
    b = balance(t)
    put(fr, "口座残高", "jpb", 24, W - 420, 16, (220, 200, 230), a)
    put(fr, yen(b), "mono", 38, W - 36, 6, (255, 255, 255) if b > 0 else rgb(RED), a, anchor="rt")
    cw, ch = (620, 250) if big else (460, 170)
    chart(fr, t, W - cw - 36, H - ch - 40, cw, ch, alpha=0.85 * a, line94=line94)


def caption(fr, t, t0, ja, zh, dur=2.4, y=H - 150):
    """lower-left caption: Japanese original (pixel font) + Traditional Chinese"""
    x = t - t0
    if x < 0 or x > dur:
        return
    a = ease(x / 0.18) * (1 - smooth((x - dur + 0.25) / 0.25))
    off = (1 - ease(x / 0.25)) * 40
    if ja:
        sp = text(ja, "jp", 44, (255, 255, 255), 5, rgb(INK))
        rect(fr, 36 - off, y - 8, 36 - off + 10, y + 126, PINK, a)
        blit(fr, sp, 58 - off, y - 14, a)
        put(fr, zh, "sansb", 36, 62 - off, y + 62, (255, 214, 240), a, stroke=4, sfill=rgb(INK))
    else:
        rect(fr, 36 - off, y + 30, 36 - off + 10, y + 112, PINK, a)
        put(fr, zh, "sans", 52, 58 - off, y + 30, (255, 255, 255), a, stroke=5, sfill=rgb(INK))


def base_fx(fr, t, split=0.0, vig=True):
    """shared finishing pass"""
    fl = flash_env(t)
    if split > 0:
        fr = rgb_split(fr, split)
    if vig:
        fr = vignette(fr)
    return fr, fl


def still(name, t, t0, dur, zoom0=1.06, zoom1=1.16, pan=(0.5, 0.5, 0.5, 0.5), punch=0.0, shake=0.0, rot=0.0):
    """Ken-Burns still with beat punch + shake"""
    x = clamp((t - t0) / dur)
    z = lerp(zoom0, zoom1, x) + punch
    ox = (rnd(int(t * FPS), 1) - 0.5) * 2 * shake
    oy = (rnd(int(t * FPS), 2) - 0.5) * 2 * shake
    return cover(name, z, lerp(pan[0], pan[2], x), lerp(pan[1], pan[3], x), rot, ox, oy)


def seq(items, t, t0, step):
    """pick item by time step → (item, index, local start)"""
    i = int((t - t0) / step)
    i = max(0, min(len(items) - 1, i)) if len(items) else 0
    return items[i], i, t0 + i * step


EP = "kurumi/ep/"
OFF = "kurumi/off/"

# ───────────────────────── PART 1 : Kurumi's own bubble ─────────────────────────


def s_intro(t):
    """bars 0–10: boot + premise.  hits on bars 2,4,6,8,9,9.5…"""
    b = tb(t)
    fr = np.zeros((H, W, 3), np.uint8)
    cards = [
        (2, EP + "01_3.jpg", "お母さんが、FXで", "媽媽她，玩 FX——", (0.5, 0.35, 0.5, 0.4)),
        (4, EP + "01_1.jpg", "2000万円、溶かした。", "把 2000 萬日圓，賠光了。", (0.5, 0.4, 0.5, 0.45)),
        (6, EP + "01_4.jpg", "だから、私が取り返す。", "所以，由我來贏回來。", (0.6, 0.5, 0.55, 0.5)),
        (8, EP + "01_5.jpg", "福賀くるみ、大学生。", "福賀久留美，大學生。", (0.6, 0.4, 0.55, 0.4)),
    ]
    if b < 2:
        # boot screen
        x = t / bt(2)
        fr[:] = (14, 8, 18)
        lines = ["> FX口座 開設中 ...", "> 本人確認 ............ OK", "> 入金 ¥100,000 ........ OK", "> レバレッジ ×25 ....... OK", "> 相場へ ようこそ。"]
        for i, l in enumerate(lines):
            ts = 0.35 + i * 0.62
            if t > ts:
                n = int((t - ts) * 42)
                put(fr, l[:n], "dot", 44, 150, 300 + i * 78, (255, 150, 215) if i < 4 else (255, 255, 255))
        if int(t * 3) % 2 == 0:
            rect(fr, 150, 300 + 5 * 78 + 8, 176, 300 + 5 * 78 + 50, PINK)
        put(fr, "INTERNET YAMERO  ×  FX戦士くるみちゃん", "dot", 30, W / 2, H - 110, (150, 110, 160), 0.9, "ct")
        fr = glitch(fr, t, 0.9 * flash_env(t, 0.25))
        fr = scanlines(fr)
        return flash(fr, 0.5 * flash_env(t))
    cur = None
    for c in cards:
        if b >= c[0]:
            cur = c
    b0, name, ja, zh, pan = cur
    t0 = bt(b0)
    if b < 9:
        x = t - t0
        f = still(name, t, t0, BAR * 2, 1.05, 1.13, pan, punch=0.10 * math.exp(-x / 0.12))
        hold = 1.0 if b0 == 8 else lerp(1.0, 0.55, smooth((x - BAR) / (BAR * 0.6)))
        f = dim(f, hold)
        if b0 == 4:
            f = tint(f, (255, 80, 60), 0.25)
        fr = f
        caption(fr, t, t0, ja, zh, dur=BAR * 2 if b0 != 8 else BAR)
        if b0 == 4:
            put(fr, "−¥20,000,000", "mono", 150, W / 2, 250, rgb(RED), ease(x / 0.1), "cm", stroke=8, sfill=(20, 0, 10),
                scale=1 + 0.25 * math.exp(-x / 0.1))
    else:
        # bar 9–10 stutter
        cuts = [(9.0, EP + "02_2.jpg"), (9.5, EP + "02_4.jpg"), (9.69, EP + "03_1.jpg"), (9.75, EP + "02_3.jpg"), (9.875, EP + "05_3.jpg")]
        nm = [c for c in cuts if b >= c[0]][-1]
        x = t - bt(nm[0])
        fr = still(nm[1], t, bt(nm[0]), 0.5, 1.1, 1.2, punch=0.12 * math.exp(-x / 0.08))
        put(fr, "いざ、戦場へ。", "jp", 120, W / 2, H / 2 - 60, (255, 255, 255), 1, "cm", stroke=10, sfill=rgb(INK))
        put(fr, "那麼——前往戰場。", "sans", 60, W / 2, H / 2 + 70, (255, 214, 240), 1, "cm", stroke=6, sfill=rgb(INK))
    fr = rgb_split(fr, 14 * flash_env(t, 0.12))
    fr = scanlines(vignette(fr))
    return flash(fr, 0.75 * flash_env(t, 0.09))


BUILD = ["02_2", "02_4", "05_3", "03_1", "04_2", "04_4", "07_5", "04_1", "07_3", "06_6", "04_5", "05_5", "06_5", "03_4", "02_3", "05_6"]


def s_build(t):
    """bars 10–18: winning streak, balance ×10"""
    b = tb(t)
    if b < 17:
        name, i, t0 = seq(BUILD, t, bt(10), BEAT * 2)
        step = BEAT * 2
    else:
        name, i, t0 = seq(BUILD[::-1], t, bt(17), BEAT / 2)
        step = BEAT / 2
    x = t - t0
    d = 1 if i % 2 == 0 else -1
    fr = still(EP + name + ".jpg", t, t0, step, 1.08, 1.16, (0.5 - 0.03 * d, 0.45, 0.5 + 0.03 * d, 0.45),
               punch=0.07 * math.exp(-x / 0.1) + 0.03 * pulse(t))
    k = (b - 10) / 8
    # rising profit counter
    pl = int(lerp(0, 900_000, k ** 1.6))
    put(fr, "含み益", "jp", 54, 70, 150, (255, 255, 255), 1, stroke=5, sfill=rgb(INK))
    put(fr, yen(pl, True), "mono", 120, 60, 210, rgb(GREEN), 1, stroke=8, sfill=(0, 30, 10), scale=1 + 0.06 * pulse(t))
    words = ["買い！", "ロング！", "利確♡", "勝てる！", "天才かも", "もっと！", "レバ上げ↑", "億り人"]
    wi = int((b - 10) * 1) % len(words)
    wx = t - bt(10 + int(b - 10))
    if b < 17:
        put(fr, words[wi], "dela", 130, W - 90, H - 330, (255, 240, 120), ease(wx / 0.08), "rb", stroke=10, sfill=(200, 30, 120),
            scale=1 + 0.3 * math.exp(-wx / 0.1))
    hud(fr, t)
    fr = rgb_split(fr, 6 * pulse(t) + 22 * max(0, b - 17))
    fr = vignette(fr)
    fl = 0.5 * flash_env(t)
    if b > 17.75:
        fl = max(fl, (b - 17.75) * 4)
    return flash(fr, fl)


CHARS = [
    ("kurumi", "福賀くるみ", "KURUMI FUKUGA", "要贏回媽媽輸掉的 2000 萬", (190, 120, 255), "母の2000万を取り返す"),
    ("mochiko", "小金萌智子", "MOCHIKO KOGANE", "投資同好，惡魔的耳語", (230, 80, 190), "くるみの投資友達"),
    ("mebuki", "山師芽吹", "MEBUKI YAMASHI", "夢想是不工作就賺錢", (80, 210, 250), "働かずに稼ぎたい"),
    ("yasuko", "高根やす子", "YASUKO TAKANE", "投資部落客「阿菲醬」", (70, 60, 235), "投資ブロガー「あふぃちゃん」"),
]


def s_drop1(t):
    """bars 18–26: title + character roll call"""
    b = tb(t)
    p = pulse(t)
    if b < 20:
        x = t - bt(18)
        fr = cover(OFF + "top_visual_visual1.jpg", 1.02 + 0.10 * math.exp(-x / 0.25) + 0.035 * beat_env(t), 0.5, lerp(0.42, 0.52, x / (2 * BAR)),
                   rot=1.5 * math.sin(t * 9) * p)
        fr = dim(fr, 0.82)
        s = 1 + 0.5 * math.exp(-x / 0.09) + 0.04 * beat_env(t)
        put(fr, "FX戦士", "dela", 150, W / 2, 330, (255, 255, 255), 1, "cm", stroke=14, sfill=(255, 60, 160), scale=s, shadow=8)
        put(fr, "くるみちゃん", "dela", 230, W / 2, 560, (255, 110, 190), 1, "cm", stroke=16, sfill=(255, 255, 255), scale=s, shadow=10)
        a2 = ease((x - BEAT * 2) / 0.15)
        put(fr, "M A D", "bebas", 110, W / 2, 770, (255, 240, 120), a2, "cm", stroke=6, sfill=rgb(INK), spacing=30)
        put(fr, "致瞬息萬變之物，及亙古不變之物", "serif", 50, W / 2, 880, (255, 255, 255), ease((x - BAR) / 0.3), "cm", stroke=5, sfill=rgb(INK))
    elif b < 24:
        i = int(b - 20)
        key, ja, en, zh, col, tag = CHARS[i]
        t0 = bt(20 + i)
        x = t - t0
        fr = np.empty((H, W, 3), np.uint8)
        fr[:] = col
        # moving stripes
        off = int(t * 500) % 160
        for k in range(-2, 16):
            pts = np.array([[k * 160 + off, 0], [k * 160 + 80 + off, 0], [k * 160 - 220 + off, H], [k * 160 - 300 + off, H]], np.int32)
            cv2.fillPoly(fr, [pts], tuple(int(c * 0.86) for c in col))
        d = 1 if i % 2 == 0 else -1
        sp = sprite(OFF + f"character_main_{key}.png", 1500)
        cx = W / 2 + d * (430 - 900 * (1 - ease(x / 0.16)))
        blit(fr, sp, cx + 14, 70 + 14, 0.35, 1.0, "ct") if False else None
        blit(fr, sp, cx, 40 - 30 * p, 1.0, 1.0 + 0.03 * math.exp(-x / 0.1), "ct")
        tx = W / 2 - d * 430
        ax = "cm"
        put(fr, en, "bebas", 74, tx, 300, (255, 255, 255), 0.9, ax, spacing=8)
        put(fr, ja, "dela", 150, tx, 450, (255, 255, 255), 1, ax, stroke=12, sfill=rgb(INK), scale=1 + 0.25 * math.exp(-x / 0.09))
        put(fr, zh, "sans", 52, tx, 690, (255, 250, 200), ease((x - 0.2) / 0.2), ax, stroke=6, sfill=rgb(INK))
        put(fr, tag, "jp", 50, tx, 600, (255, 255, 255), 1, ax, stroke=5, sfill=rgb(INK))
    else:
        x = t - bt(24)
        fr = cover(OFF + "music_jk.jpg", 1.05 + 0.06 * math.exp(-x / 0.2) + 0.03 * beat_env(t), 0.5, lerp(0.3, 0.42, x / (2 * BAR)))
        if b >= 25:
            y = t - bt(25)
            put(fr, "レバレッジあるから", "dela", 120, W / 2, 400, (255, 255, 255), 1, "cm", stroke=12, sfill=(255, 60, 160),
                scale=1 + 0.3 * math.exp(-y / 0.1))
            put(fr, "大丈夫ぅ♪", "dela", 200, W / 2, 620, (255, 240, 120), ease((y - BEAT * 2) / 0.05), "cm", stroke=14, sfill=(255, 60, 160),
                scale=1 + 0.3 * math.exp(-max(0, y - BEAT * 2) / 0.1))
            put(fr, "有槓桿所以沒問題♪", "sans", 60, W / 2, 800, (255, 255, 255), ease((y - BEAT * 2) / 0.1), "cm", stroke=6, sfill=rgb(INK))
    hud(fr, t)
    fr = rgb_split(fr, 9 * p)
    fr = vignette(fr)
    return flash(fr, 0.6 * flash_env(t) + (0.8 * math.exp(-(t - bt(18)) / 0.12) if b < 19 else 0))


VERSE_A = [
    # (bar, image, ja, zh, pan)
    (26, "02_2", "第2話　レバレッジあるから大丈夫ぅ♪", "初次交易就翻盤獲利——三個月，連戰連勝。", (0.55, 0.4, 0.5, 0.42)),
    (28, "02_4", "口座残高、100万円が見えてきた！", "帳戶餘額，眼看就要突破 100 萬！", (0.5, 0.4, 0.55, 0.45)),
    (30, "02_3", "「豪ドル円、やってみない？」", "「要不要試試……澳幣兌日圓？」", (0.5, 0.35, 0.5, 0.42)),
    (32, "03_4", "お母さんと、同じ通貨ペア。", "那是和媽媽當年一樣的貨幣對。", (0.6, 0.45, 0.5, 0.45)),
    (34, "03_1", "超高倍率で、全力ロング！", "超高槓桿，全力做多！", (0.5, 0.4, 0.5, 0.45)),
    (36, "07_5", "含み益って、サイコ〜♡", "有未實現獲利的日子，最棒了♡", (0.5, 0.35, 0.5, 0.42)),
    (38, "02_1", "……あれ？", "……咦？", (0.45, 0.4, 0.5, 0.42)),
    (40, "03_2", "含み損。", "未實現虧損。", (0.5, 0.5, 0.55, 0.45)),
]
VERSE_B = [
    (42, "04_1", "山師芽吹「働かずに稼ぎたい！」", "山師芽吹：「我想不工作就賺錢！」", (0.5, 0.4, 0.5, 0.45)),
    (44, "06_2", "高根やす子、投資ブロガー。", "高根やす子，投資部落客「阿菲醬」。", (0.45, 0.4, 0.5, 0.42)),
    (46, "05_4", "クセ強FX戦士、集結。", "個性強烈的 FX 戰士們，集結。", (0.5, 0.5, 0.5, 0.5)),
    (48, "07_3", "「スーパー投資バトル」開幕！", "「超級投資對決」開打！", (0.5, 0.45, 0.5, 0.5)),
    (50, "05_6", "経済指標には注目ですっ！", "經濟數據發表，請務必留意！", (0.5, 0.5, 0.6, 0.45)),
    (52, "06_6", "100枚、全力ロング！", "100 手，全力做多！", (0.5, 0.4, 0.5, 0.45)),
    (54, "06_1", "えっ、逆行……？", "咦，行情反著走……？", (0.5, 0.4, 0.5, 0.42)),
    (56, "06_4", "生活費まで、入金した。", "連生活費，都存進了保證金。", (0.5, 0.4, 0.5, 0.45)),
]


def s_verse(t, tbl):
    b = tb(t)
    cur = [c for c in tbl if b >= c[0]][-1]
    b0, name, ja, zh, pan = cur
    t0 = bt(b0)
    x = t - t0
    i = tbl.index(cur)
    fr = still(EP + name + ".jpg", t, t0, 2 * BAR, 1.06, 1.15, pan, punch=0.06 * math.exp(-x / 0.14) + 0.022 * pulse(t),
               rot=(0.6 if i % 2 else -0.6) * (1 - x / (2 * BAR)))
    if name in ("02_1", "03_2", "06_1", "06_4"):
        fr = tint(fr, (255, 110, 90), 0.22)
    caption(fr, t, t0, ja, zh, dur=2 * BAR - 0.05)
    hud(fr, t)
    fr = rgb_split(fr, 5 * pulse(t))
    fr = vignette(fr)
    return flash(fr, 0.45 * math.exp(-x / 0.1) + 0.4 * flash_env(t))


def s_break1(t):
    """bars 58–62 (quiet): the 3,000,000 yen from dad's closet"""
    b = tb(t)
    t0 = bt(58)
    x = t - t0
    name = "05_2" if b < 60 else "06_3"
    tt = t0 if b < 60 else bt(60)
    fr = still(EP + name + ".jpg", t, tt, 2 * BAR, 1.05, 1.12, (0.5, 0.45, 0.55, 0.45))
    fr = dim(fr, 0.8)
    if b < 60:
        caption(fr, t, bt(58), "第3話　損切りしなきゃ、だめ……？", "非停損不可嗎……？", dur=2 * BAR)
    else:
        y = t - bt(60)
        caption(fr, t, bt(60), "お父さんのタンス預金、300万円。", "爸爸藏在衣櫃裡的 300 萬日圓——入金。", dur=2 * BAR)
        put(fr, "+¥3,000,000", "mono", 110, W / 2, 330, rgb(YELLOW), ease(y / 0.15), "cm", stroke=8, sfill=rgb(INK),
            scale=1 + 0.2 * math.exp(-y / 0.12))
        put(fr, "強制ロスカット、回避。", "jp", 56, W / 2, 450, (255, 255, 255), ease((y - 0.6) / 0.3), "cm", stroke=5, sfill=rgb(INK))
    hud(fr, t, line94=True)
    fr = vignette(scanlines(fr))
    return flash(fr, 0.5 * math.exp(-(t - tt) / 0.15))


PANIC = ["02_5", "03_5", "06_4", "07_1", "01_1", "04_6", "01_6", "05_1", "03_6", "02_1", "03_2", "07_4"]


def s_kicks(t):
    """bars 62–70: bass kicks only — unrealised loss grows on every kick"""
    b = tb(t)
    name, i, t0 = seq(["02_5", "03_5", "06_4", "07_1"], t, bt(62), 2 * BAR)
    be = beat_env(t, 0.12)
    fr = still(EP + name + ".jpg", t, t0, 2 * BAR, 1.08, 1.2, (0.5, 0.42, 0.5, 0.42), punch=0.09 * be, shake=16 * be)
    fr = tint(fr, (70, 40, 230), 0.55)
    fr = dim(fr, 0.75 + 0.25 * be)
    nb = int((t - bt(62)) / BEAT)
    loss = -int(180_000 + nb * 58_000 + 21_000 * rnd(nb))
    put(fr, "含み損", "jp", 70, W / 2, 300, (255, 255, 255), 1, "cm", stroke=6, sfill=(40, 0, 10))
    put(fr, yen(loss, True), "mono", 190, W / 2, 470, rgb(RED), 1, "cm", stroke=10, sfill=(30, 0, 8), scale=1 + 0.16 * be)
    caps = [("94円を割ったら、損切りする。", "跌破 94 圓，就停損。"), ("……まだ、戻るかも。", "……說不定，還會漲回來。"),
            ("追加ロング。", "加碼做多。"), ("神様。", "神啊。")]
    caption(fr, t, t0, caps[i][0], caps[i][1], dur=2 * BAR - 0.05)
    hud(fr, t, line94=True, big=True)
    fr = rgb_split(fr, 18 * be)
    fr = vignette(fr)
    return flash(fr, 0.5 * flash_env(t), (60, 40, 255))


def s_hardcore(t):
    """bars 70–85: full panic"""
    b = tb(t)
    step = BEAT * 2 if b < 78 else BEAT
    base = bt(70) if b < 78 else bt(78)
    lst = PANIC if b < 78 else PANIC[::-1] + PANIC[3:]
    name, i, t0 = seq(lst, t, base, step)
    x = t - t0
    p = pulse(t)
    fr = still(EP + name + ".jpg", t, t0, step, 1.1, 1.22, (0.5, 0.42, 0.5, 0.42), punch=0.1 * math.exp(-x / 0.08), shake=10 + 14 * p,
               rot=(rnd(i, 7) - 0.5) * 5)
    k = (b - 70) / 15
    fr = tint(fr, (70, 40, 230), 0.25 + 0.3 * k)
    # margin level meter
    ml = lerp(312, 101, k ** 0.8) + 3 * math.sin(t * 13)
    rect(fr, 60, 130, 760, 250, (18, 10, 22), 0.7)
    put(fr, "証拠金維持率", "jpb", 34, 80, 142, (255, 255, 255))
    put(fr, f"{ml:5.1f}%", "mono", 64, 740, 150, rgb(RED) if ml < 150 else rgb(YELLOW), 1, "rt")
    rect(fr, 80, 222, 740, 238, (60, 40, 70))
    rect(fr, 80, 222, 80 + 660 * clamp((ml - 100) / 220), 238, RED if ml < 150 else YELLOW)
    words = ["戻れ", "戻って", "お願い", "なんで", "まだ", "ナンピン", "祈り", "無理", "嘘", "やだ", "助けて", "損切り…?", "できない", "あと少し", "神様"]
    wi = int((t - bt(70)) / BEAT) % len(words)
    wx = t - (bt(70) + int((t - bt(70)) / BEAT) * BEAT)
    px = 300 + rnd(wi, int(b)) * (W - 900)
    py = 380 + rnd(wi, int(b), 3) * 330
    put(fr, words[wi], "dela", 170, px, py, (255, 255, 255), 1, "lt", stroke=12, sfill=(230, 20, 70), scale=1 + 0.35 * math.exp(-wx / 0.07))
    hud(fr, t, line94=True, big=True)
    fr = glitch(fr, t, 0.22 * p + 0.25 * k * p)
    fr = rgb_split(fr, 5 + 12 * p)
    fr = vignette(fr)
    return flash(fr, 0.5 * flash_env(t) + 0.2 * math.exp(-x / 0.05), (255, 255, 255))


def s_prebreak(t):
    """bar 85: hold breath"""
    x = t - bt(85)
    fr = cover(EP + "03_5.jpg", 1.25 + 0.05 * x, 0.5, 0.4)
    fr = tint(fr, (255, 255, 255), 0.85)
    fr = dim(fr, 0.55)
    put(fr, "ロスカットまで", "jp", 80, W / 2, 400, (255, 255, 255), 1, "cm", stroke=6, sfill=rgb(INK))
    put(fr, "あと 0.02 円", "mono", 170, W / 2, 560, rgb(RED), 1, "cm", stroke=8, sfill=rgb(INK))
    put(fr, "距離強制平倉，只剩 0.02 圓。", "sans", 54, W / 2, 720, (255, 220, 240), 1, "cm", stroke=5, sfill=rgb(INK))
    hud(fr, t, line94=True, big=True)
    return flash(scanlines(vignette(fr)), 0.8 * math.exp(-x / 0.1))


def s_pray(t):
    """bars 86–94: prayer (loud bars) / silence (soft bars) alternating"""
    b = tb(t)
    bi = int(b - 86)
    t0 = bt(86 + bi)
    x = t - t0
    imgs = ["03_3", "05_3", "03_3", "04_3", "03_3", "02_6", "03_3", "04_6"]
    fr = still(EP + imgs[bi] + ".jpg", t, t0, BAR, 1.08, 1.2 + 0.05 * bi, (0.5, 0.45, 0.5, 0.45), punch=0.08 * math.exp(-x / 0.1),
               shake=6 * pulse(t), rot=(bi % 2 * 2 - 1) * 1.2)
    pr = [("神様、お願い。", "神啊，拜託了。"), ("もう二度と、しませんから。", "我再也不敢了。"),
          ("今回だけ。", "就這一次。"), ("今回だけ、助けて。", "就這一次，救救我。"),
          ("上がれ。", "漲啊。"), ("上がれ。", "漲啊。"), ("上がれ上がれ上がれ", "漲啊漲啊漲啊"), ("——94.00、割れ。", "——94.00，失守。")]
    ja, zh = pr[bi]
    s = 1 + 0.25 * math.exp(-x / 0.1)
    put(fr, ja, "jp", 110 + bi * 6, W / 2, H / 2 - 40, (255, 255, 255), 1, "cm", stroke=10, sfill=(200, 20, 90) if bi < 7 else (20, 0, 200), scale=s)
    put(fr, zh, "sans", 60, W / 2, H / 2 + 100, (255, 230, 245), 1, "cm", stroke=6, sfill=rgb(INK))
    hud(fr, t, line94=True, big=True)
    fr = rgb_split(fr, 3 + 14 * flash_env(t, 0.1))
    fr = vignette(fr)
    return flash(fr, 0.7 * flash_env(t) + (clamp((b - 93.5) * 2) ** 2 if b > 93.5 else 0))


def losscut_scene(t, t0, spin=1.0, fall=1.0, k=1.0, dy=0.0):
    """official 強制ロスカット art: rotating vortex + falling Kurumi"""
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
    """bars 94–102: 強制ロスカット"""
    b = tb(t)
    x = t - bt(94)
    p = pulse(t)
    if b < 100:
        fr = losscut_scene(t, bt(94), k=0.78, dy=215)
        fr = dim(fr, 0.85 + 0.15 * p)
        sp = sprite(OFF + "top_losscut_losscut_txt.png", 170)
        s = 1 + 0.9 * math.exp(-x / 0.12) + 0.05 * beat_env(t)
        blit(fr, sp, W / 2, 170, 1.0, s, "cm")
        put(fr, "強制平倉", "serif", 84, W / 2, 296, (255, 255, 255), ease((x - BAR) / 0.2), "cm", stroke=6, sfill=(120, 0, 30))
        # balance draining
        bl = balance(t)
        put(fr, "口座残高", "jp", 50, W / 2, 850, (255, 255, 255), 1, "cm", stroke=5, sfill=rgb(INK))
        put(fr, yen(bl), "mono", 130, W / 2, 950, rgb(RED), 1, "cm", stroke=8, sfill=rgb(INK), scale=1 + 0.08 * p)
        hud(fr, t, line94=True, big=False)
        fr = glitch(fr, t, 0.4 * p)
        fr = rgb_split(fr, 4 + 11 * p)
        fr = vignette(fr)
        return flash(fr, 0.95 * math.exp(-x / 0.18) + 0.4 * flash_env(t))
    # bars 100–102: flatline
    y = t - bt(100)
    fr = np.zeros((H, W, 3), np.uint8)
    fr[:] = (14, 8, 18)
    cv2.line(fr, (0, H // 2), (int(W * clamp(y / (BAR * 1.2))), H // 2), (80, 70, 255), 4, cv2.LINE_AA)
    put(fr, "口座残高　¥0", "dot", 110, W / 2, H / 2 - 150, (255, 255, 255), ease(y / 0.1), "cm")
    put(fr, "帳戶餘額　¥0", "sans", 54, W / 2, H / 2 + 110, (255, 150, 200), ease((y - 0.4) / 0.2), "cm")
    fr = glitch(fr, t, 0.8 * flash_env(t, 0.06))
    fr = scanlines(fr)
    return flash(fr, 0.6 * flash_env(t, 0.05))


def s_after(t):
    """bars 102–110: aftermath → question that opens the timeline"""
    b = tb(t)
    tbl = [
        (102, "04_3", "それでも、やめられない。", "即使如此，還是戒不掉。"),
        (104, "04_6", "FXをやめろ、と泣かれても。", "即使被哭著求「別再碰 FX 了」。"),
        (106, "03_6", "なぜ人は、同じ過ちを繰り返すのか。", "為什麼人，總是重蹈覆轍？"),
        (108, "07_6", "——389年前から、ずっとそうだった。", "——早在 389 年前，就一直是這樣了。"),
    ]
    cur = [c for c in tbl if b >= c[0]][-1]
    b0, name, ja, zh = cur
    t0 = bt(b0)
    x = t - t0
    fe = flash_env(t, 0.07)
    fr = still(EP + name + ".jpg", t, t0, 2 * BAR, 1.06, 1.16, (0.5, 0.45, 0.5, 0.42), punch=0.035 * fe)
    fr = tint(fr, (255, 200, 190), 0.35)
    fr = dim(fr, 0.7 + 0.2 * fe)
    put(fr, ja, "jp", 64, W / 2, H / 2 + 170, (255, 255, 255), ease(x / 0.2), "cm", stroke=6, sfill=rgb(INK))
    put(fr, zh, "serif", 84, W / 2, H / 2 + 280, (255, 225, 240), ease((x - 0.15) / 0.25), "cm", stroke=6, sfill=rgb(INK))
    hud(fr, t, a=clamp(1 - (b - 106) / 2))
    fr = rgb_split(fr, 10 * fe)
    fr = vignette(fr)
    out = flash(fr, 0.35 * fe + 0.5 * math.exp(-x / 0.12))
    if b > 109.6:
        out = dim(out, 1 - smooth((b - 109.6) / 0.4))
    return out


# ───────────────────────── PART 2 : the bubble odometer ─────────────────────────
H_ = "hist/"
# (start bar, bars, year, zh title, en, line1, line2, image, object word)
EVENTS = [
    (110, 4, 1637, "鬱金香狂熱", "TULIP MANIA · 荷蘭", "一顆球莖，換一棟阿姆斯特丹的運河豪宅。", "1637 年 2 月——買家，一夜之間消失。", "tulip.jpg", "鬱金香"),
    (114, 4, 1720, "南海泡沫", "SOUTH SEA BUBBLE · 英國", "牛頓：「我算得出天體的運行，", "卻算不出人們的瘋狂。」", "southsea.jpg", "南海股票"),
    (118, 3, 1846, "鐵路狂熱", "RAILWAY MANIA · 英國", "國會一年核准 9,500 英里新鐵路。", "「鐵路大王」哈德遜，就此出軌。", "railway.png", "鐵路股"),
    (121, 2, 1929, "華爾街大崩盤", "THE GREAT CRASH · 美國", "「股價已站上永久的高原。」", "道瓊指數，隨後下跌 89%。", "crash1929.jpg", "美股"),
    (123, 2, 1989, "日本泡沫經濟", "BUBBLE ECONOMY · 日本", "日經指數 38,915 點。", "再次見到它，是 34 年後。", "japan.jpg", "土地與日股"),
    (125, 2, 2000, "網路泡沫", "DOT-COM BUBBLE", "公司名加上 .com，股價就起飛。", "那斯達克指數：−78%。", "dotcom.jpg", ".com"),
    (127, 2, 2008, "金融海嘯", "LEHMAN SHOCK", "158 年的雷曼兄弟，一個週末破產。", "澳幣／日圓 104 → 55。媽媽的 2000 萬。", "lehman2.jpg", "次級房貸"),
    (129, 2, 2015, "瑞郎黑天鵝", "SNB SHOCK · 瑞士", "央行一紙聲明，歐元／瑞郎瞬間 −30%。", "停損單，根本來不及成交。", "snb.jpg", "瑞士法郎"),
    (131, 2, 2017, "比特幣・ICO 狂潮", "CRYPTO MANIA", "$1,000 → $19,783，只花了一年。", "再過一年：−84%。", "bitcoin.jpg", "比特幣"),
    (133, 2, 2021, "迷因股狂熱", "MEME STOCKS · GAMESTOP", "$17 → $483，不到一個月。", "「鑽石手，抱到月球。」", "gamestop.jpg", "迷因股"),
    (135, 1, 2021, "NFT 狂熱", "NFT MANIA", "一張 JPEG：6,930 萬美元。", "", "nft3.jpg", "JPEG"),
    (136, 1, 2022, "LUNA・FTX 崩潰", "CRYPTO WINTER", "400 億美元，一週歸零。", "", "ftx.jpg", "LUNA"),
    (137, 4, 2023, "AI 泡沫？", "AI BOOM · 進行中", "輝達市值，突破 5 兆美元。", "「這次不一樣。」——每一次，都有人這麼說。", "ai.png", "GPU"),
]
EV_COL = [(120, 160, 255), (120, 200, 255), (150, 220, 230), (200, 200, 200), (140, 140, 255), (255, 200, 120), (255, 170, 90),
          (120, 120, 255), (60, 190, 255), (90, 90, 255), (255, 120, 200), (255, 220, 100), (120, 255, 170)]


def bubble_curve(x):
    """the one curve: slow rise → parabolic → peak at 0.72 → crash → dead-cat → flat"""
    if x < 0.72:
        u = x / 0.72
        return 0.06 + 0.94 * (0.25 * u + 0.75 * u ** 4.2)
    u = (x - 0.72) / 0.28
    return 0.12 + 0.88 * math.exp(-u * 6.5) + 0.07 * math.exp(-((u - 0.42) / 0.09) ** 2)


def draw_curve(fr, x, y, w, h, prog, col, thick=4, stop_at_peak=False, wob=0.0, seed=0):
    n = 110
    pts = []
    lim = 0.72 if stop_at_peak else 1.0
    for i in range(n + 1):
        u = i / n
        if u > prog or u > lim + 1e-6:
            break
        v = bubble_curve(u) + wob * (0.035 * math.sin(u * 37 + seed) + 0.02 * math.sin(u * 91 + seed * 2.3))
        pts.append((int(x + u * w), int(y + h - v * h)))
    if len(pts) > 1:
        cv2.polylines(fr, [np.array(pts, np.int32)], False, col, thick, cv2.LINE_AA)
    return pts[-1] if pts else None


def odometer(fr, x, y, val_from, val_to, k, size=250, col=(255, 255, 255)):
    """mechanical 4-digit year counter: digits roll from val_from to val_to as k 0→1"""
    f = "bebas"
    dw = int(size * 0.52)
    dh = int(size * 0.92)
    a, b = f"{val_from:04d}", f"{val_to:04d}"
    for i in range(4):
        bx = x + i * (dw + 10)
        rect(fr, bx, y, bx + dw, y + dh, (26, 16, 30), 0.9)
        rect(fr, bx, y, bx + dw, y + 4, (120, 100, 130), 0.9)
        rect(fr, bx, y + dh - 4, bx + dw, y + dh, (10, 6, 12), 0.9)
        da, db = int(a[i]), int(b[i])
        kk = ease(clamp(k * 1.6 - (3 - i) * 0.12))
        if da == db:
            kk = 1.0
        # roll upward through intermediate digits
        steps = (db - da) % 10
        pos = da + steps * kk
        d0 = int(math.floor(pos)) % 10
        d1 = (d0 + 1) % 10
        fr_ = pos - math.floor(pos)
        sub = fr[y:y + dh, bx:bx + dw]
        tmp = np.zeros((dh, dw, 3), np.uint8)
        tmp[:] = sub
        for d, off in ((d0, -fr_ * dh), (d1, (1 - fr_) * dh)):
            sp = text(str(d), f, size, col)
            hh, ww = sp.shape[:2]
            xx = (dw - ww) // 2
            yy = int((dh - hh) // 2 + off + size * 0.04)
            y0, y1 = max(0, yy), min(dh, yy + hh)
            if y1 > y0:
                s = sp[y0 - yy:y1 - yy]
                al = s[:, :, 3:4].astype(np.float32) / 255
                reg = tmp[y0:y1, xx:xx + ww]
                reg[:] = (reg * (1 - al) + s[:, :, :3] * al).astype(np.uint8)
        fr[y:y + dh, bx:bx + dw] = tmp
        rect(fr, bx, y + dh // 2 - 1, bx + dw, y + dh // 2 + 1, (10, 6, 12), 0.35)
    return x + 4 * (dw + 10)


RAIL_X0, RAIL_X1, RAIL_Y = 110, W - 110, H - 78


def rail(fr, idx, prog, a=1.0, done=False):
    """milestone rail: 13 evenly spaced nodes"""
    n = len(EVENTS)
    xs = [RAIL_X0 + (RAIL_X1 - RAIL_X0) * i / (n - 1) for i in range(n)]
    rect(fr, 0, RAIL_Y - 46, W, H, (14, 8, 18), 0.78 * a)
    rect(fr, RAIL_X0, RAIL_Y - 2, RAIL_X1, RAIL_Y + 2, (90, 70, 100), a)
    xe = xs[idx] + ((xs[idx + 1] - xs[idx]) * prog if idx < n - 1 else 0)
    if done:
        xe = RAIL_X1
    rect(fr, RAIL_X0, RAIL_Y - 3, xe, RAIL_Y + 3, PINK, a)
    for i, xx in enumerate(xs):
        yr = EVENTS[i][2]
        lab = str(yr) if i != n - 1 else "AI"
        if i < idx or done:
            cv2.circle(fr, (int(xx), RAIL_Y), 8, PINK, -1, cv2.LINE_AA)
            put(fr, lab, "mono", 22, xx, RAIL_Y + 16, (200, 150, 190), a, "ct")
        elif i == idx:
            cv2.circle(fr, (int(xx), RAIL_Y), 16, WHITE, -1, cv2.LINE_AA)
            cv2.circle(fr, (int(xx), RAIL_Y), 10, PINK, -1, cv2.LINE_AA)
            put(fr, lab, "mono", 30, xx, RAIL_Y + 14, (255, 255, 255), a, "ct")
        else:
            cv2.circle(fr, (int(xx), RAIL_Y), 6, (90, 70, 100), -1, cv2.LINE_AA)
            put(fr, lab, "mono", 20, xx, RAIL_Y + 16, (110, 90, 120), a, "ct")
    if not done:
        cv2.circle(fr, (int(xe), RAIL_Y), 5, WHITE, -1, cv2.LINE_AA)


def photo_card(name, bw, bh, zoom, cx, cy):
    """contain-fit image inside a white-bordered card → BGRA"""
    s = img(name)
    if s.shape[2] == 4:
        s = s[:, :, :3]
    h, w = s.shape[:2]
    sc = min(bw / w, bh / h)
    cw, ch = int(w * sc), int(h * sc)
    # ken burns inside the card
    scz = max(cw / w, ch / h) * zoom
    M = np.array([[scz, 0, cw / 2 - cx * w * scz], [0, scz, ch / 2 - cy * h * scz]], np.float32)
    inner = cv2.warpAffine(s, M, (cw, ch), flags=cv2.INTER_AREA if scz < 0.7 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    bd = 14
    card = np.full((ch + bd * 2, cw + bd * 2, 4), 255, np.uint8)
    card[:, :, :3] = (245, 240, 238)
    card[bd:bd + ch, bd:bd + cw, :3] = inner
    return card


def s_timeline(t):
    b = tb(t)
    idx = max(i for i, e in enumerate(EVENTS) if b >= e[0])
    b0, nb, year, zh, en, l1, l2, im, _ = EVENTS[idx]
    t0 = bt(b0)
    dur = nb * BAR
    x = t - t0
    k = x / dur
    p = pulse(t)
    fe = flash_env(t, 0.09)
    hot = clamp((b - 121) / 16)            # intensity ramps through the build
    is_ai = idx == len(EVENTS) - 1
    name = H_ + im

    # background: blurred + darkened version of the same single image
    fr = blurred(name, 0.42 if not is_ai else 0.5).copy()
    if is_ai:
        fr = dim(fr, 0.8 + 0.5 * beat_env(t))

    # photo card (left)
    bw, bh = 1010, 800
    z = lerp(1.0, 1.07, k) + (0.03 * p if hot > 0 else 0) + 0.05 * math.exp(-x / 0.12)
    card = photo_card(name, bw, bh, z, 0.5, lerp(0.47, 0.53, k))
    ang = (-2.2 if idx % 2 == 0 else 2.0) * (1 - 0.35 * k) + (1.5 * p * math.sin(t * 40) if is_ai else 0)
    ch, cw = card.shape[:2]
    Mr = cv2.getRotationMatrix2D((cw / 2, ch / 2), ang, 1.0)
    cs, sn = abs(Mr[0, 0]), abs(Mr[0, 1])
    nw, nh = int(ch * sn + cw * cs) + 4, int(ch * cs + cw * sn) + 4
    Mr[0, 2] += nw / 2 - cw / 2
    Mr[1, 2] += nh / 2 - ch / 2
    card = cv2.warpAffine(card, Mr, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    slide = (1 - ease(x / 0.22)) * -120
    cxp, cyp = 600 + slide, 500
    sh = card.copy()
    sh[:, :, :3] = 0
    blit(fr, sh, cxp + 16, cyp + 20, 0.45 * ease(x / 0.2), 1.0, "cm")
    blit(fr, card, cxp, cyp, ease(x / 0.12), 1.0 + 0.03 * math.exp(-x / 0.1), "cm")

    # right column
    rx = 1150
    put(fr, f"{idx + 1:02d} / {len(EVENTS):02d}", "mono", 30, rx, 96, (255, 170, 215))
    put(fr, "泡沫里程表　BUBBLE ODOMETER", "sansb", 28, rx + 150, 97, (200, 180, 210))
    prev = EVENTS[idx - 1][2] if idx else 1600
    if is_ai:
        yb = min(3, int(x / BAR))
        y_from = 2022 if yb == 0 else 2023 + yb - 1
        y_to = 2023 + yb
        kr = (x - yb * BAR) / 0.3
        prev = y_from
        year_now = y_to
    else:
        year_now = year
        kr = x / (0.34 if nb > 1 else 0.2)
    odometer(fr, rx, 150, prev, year_now, clamp(kr), 250, (255, 255, 255) if not is_ai else (170, 255, 200))
    a1 = ease((x - 0.10) / 0.2)
    put(fr, zh, "serif", 96 if len(zh) <= 7 else 80, rx - 4, 405 + (1 - a1) * 30, (255, 255, 255), a1, stroke=4, sfill=rgb(INK), shadow=4)
    put(fr, en, "bebas", 46, rx, 540, (255, 150, 215), ease((x - 0.16) / 0.2), spacing=3)
    a2 = ease((x - 0.26) / 0.25)
    fs = 36 if max(len(l1), len(l2)) > 17 else 40
    put(fr, l1, "sansb", fs, rx, 618, (255, 255, 255), a2, stroke=3, sfill=rgb(INK))
    if l2:
        a3 = ease((x - min(0.45 * dur, 1.5)) / 0.3)
        put(fr, l2, "sansb", fs, rx, 618 + fs + 22, (255, 225, 150), a3, stroke=3, sfill=rgb(INK))

    # the curve (always the same shape)
    gx, gy, gw, gh = rx, 760, 640, 185
    rect(fr, gx - 10, gy - 14, gx + gw + 10, gy + gh + 12, (14, 8, 18), 0.6)
    put(fr, "PRICE", "mono", 18, gx, gy - 10, (150, 130, 160))
    end = draw_curve(fr, gx, gy, gw, gh, clamp(k * 1.04), EV_COL[idx], 5, stop_at_peak=is_ai, wob=1.0, seed=idx * 3.1)
    if end:
        cv2.circle(fr, end, 9, WHITE, -1, cv2.LINE_AA)
        if is_ai and k * 1.04 >= 0.72:
            # the future: dotted, unknown
            for j in range(0, 9):
                px_ = end[0] + 22 + j * 20
                if (j + int(t * 6)) % 2 == 0:
                    cv2.circle(fr, (px_, end[1] + int(8 * math.sin(j + t * 5))), 4, (200, 200, 200), -1, cv2.LINE_AA)
            put(fr, "？", "serif", 120, end[0] + 230, end[1] + 70, (255, 255, 255), 1, "cm", stroke=5, sfill=rgb(INK),
                scale=1 + 0.15 * beat_env(t))
    rail(fr, idx, clamp(k))

    # era look
    if idx < 3:
        fr = tint(fr, (150, 200, 235), 0.16)       # warm paper for the oldest three
    sp = 3 * fe + (4 * p * hot if not is_ai else 5 * p)
    fr = rgb_split(fr, sp)
    if hot > 0.4 or is_ai:
        fr = glitch(fr, t, (0.2 * hot + (0.12 if is_ai else 0)) * p * (1 if x < 0.2 else 0.25))
    fr = vignette(fr)
    fl = 0.75 * math.exp(-x / 0.10) + 0.18 * fe
    if b < 110.3:
        fr = dim(fr, smooth((b - 110) / 0.3))
        fl = 0
    return flash(fr, fl)


def s_changing(t):
    """bars 141–145: 瞬息萬變之物 — the object changes every beat (text only)"""
    b = tb(t)
    x = t - bt(141)
    nbt = int(x / BEAT)
    words = [e[8] for e in EVENTS] + ["？？？"]
    fr = np.zeros((H, W, 3), np.uint8)
    hue = [(60, 20, 110), (110, 30, 90), (40, 30, 130), (90, 20, 60)][nbt % 4]
    fr[:] = hue
    # speed lines
    for i in range(26):
        yy = int(rnd(i, 5) * H)
        ln = 200 + rnd(i, 6) * 700
        xx = (rnd(i, 7) * (W + ln) + t * (2600 + 1800 * rnd(i, 8))) % (W + ln) - ln
        cv2.line(fr, (int(xx), yy), (int(xx + ln), yy), tuple(int(c * 1.5) for c in hue), 3)
    put(fr, "瞬息萬變之物", "serif", 86, W / 2, 170, (255, 255, 255), 1, "cm", stroke=5, sfill=rgb(INK), spacing=10)
    put(fr, "THINGS EVER-CHANGING", "bebas", 44, W / 2, 262, (255, 170, 215), 1, "cm", spacing=8)
    if nbt < len(words):
        wx = x - nbt * BEAT
        w_ = words[nbt]
        yr = str(EVENTS[nbt][2]) if nbt < len(EVENTS) - 1 else ("NOW" if nbt == len(EVENTS) - 1 else "NEXT")
        put(fr, yr, "bebas", 110, W / 2, 420, rgb(YELLOW), 1, "cm", spacing=12)
        put(fr, w_, "sans", 250 if len(w_) <= 4 else 190, W / 2, 640, (255, 255, 255), 1, "cm", stroke=14, sfill=(255, 60, 160), scale=1 + 0.4 * math.exp(-wx / 0.07))
    else:
        wx = x - len(words) * BEAT
        put(fr, "標的，一直在變。", "serif", 150, W / 2, 600, (255, 255, 255), 1, "cm", stroke=8, sfill=rgb(INK), scale=1 + 0.2 * math.exp(-wx / 0.1))
    rail(fr, len(EVENTS) - 1, 1, done=True)
    fr = rgb_split(fr, 3 + 7 * pulse(t))
    fr = vignette(fr)
    return flash(fr, 0.3 * beat_env(t, 0.06) * (1 if nbt < len(words) else 0.3) + 0.8 * math.exp(-x / 0.12))


def s_unchanging(t):
    """bars 145–153: 亙古不變之物 — thirteen bubbles, one curve"""
    b = tb(t)
    x = t - bt(145)
    fr = losscut_bg_only(t, 0.35)
    put(fr, "亙古不變之物", "serif", 86, W / 2, 130, (255, 255, 255), 1, "cm", stroke=5, sfill=rgb(INK), spacing=10)
    put(fr, "THINGS THAT NEVER CHANGE", "bebas", 44, W / 2, 222, (150, 230, 255), 1, "cm", spacing=8)
    gx, gy, gw, gh = 260, 300, 1400, 560
    rect(fr, gx - 30, gy - 30, gx + gw + 30, gy + gh + 30, (14, 8, 18), 0.55)
    n = len(EVENTS)
    # one new curve every half bar for the first 6.5 bars
    for i in range(n):
        ts = i * BAR / 2
        if x < ts:
            break
        pr = clamp((x - ts) / (BAR * 1.2))
        end = draw_curve(fr, gx, gy, gw, gh, pr, EV_COL[i], 3, stop_at_peak=(i == n - 1), wob=1.0, seed=i * 3.1)
        if end and pr < 1:
            cv2.circle(fr, end, 7, WHITE, -1, cv2.LINE_AA)
            lab = str(EVENTS[i][2]) if i < n - 1 else "AI ？"
            put(fr, lab, "mono", 34, end[0] + 14, end[1] - 44, tuple(reversed(EV_COL[i])), 1)
    # Kurumi's own account joins at bar 151.5
    if b >= 151.5:
        pr = clamp((t - bt(151.5)) / (BAR * 1.2))
        end = draw_curve(fr, gx, gy, gw, gh, pr, PINK, 9, wob=0.0)
        if end:
            cv2.circle(fr, end, 13, WHITE, -1, cv2.LINE_AA)
            put(fr, "くるみの口座", "jp", 50, min(end[0] + 20, gx + gw - 330), max(gy, end[1] - 80), (255, 150, 215), 1, stroke=5, sfill=rgb(INK))
    cap = None
    if b < 147:
        cap = "十三個泡沫。"
    elif b < 149:
        cap = "疊在一起——"
    elif b < 151.5:
        cap = "是同一條線。"
    else:
        cap = "她的帳戶，也是。"
    cb = [145, 147, 149, 151.5][[b < 147, b < 149, b < 151.5, True].index(True)]
    cx_ = t - bt(cb)
    put(fr, cap, "serif", 96, W / 2, 960, (255, 255, 255), ease(cx_ / 0.12), "cm", stroke=6, sfill=rgb(INK), scale=1 + 0.2 * math.exp(-cx_ / 0.1))
    fr = rgb_split(fr, 2 + 5 * pulse(t))
    fr = vignette(fr)
    return flash(fr, 0.8 * math.exp(-x / 0.12) + 0.25 * flash_env(t) + 0.6 * math.exp(-cx_ / 0.08) * (cb != 145))


def losscut_bg_only(t, k=0.5):
    bg = cover(OFF + "top_losscut_losscut_bg.jpg", 1.5, 0.5, 0.5, rot=-t * 14)
    return dim(bg, k)


GREED = ["02_3", "03_1", "02_4", "05_3", "04_2", "07_2", "02_2", "06_6", "04_4", "05_6", "07_5", "04_1", "03_4", "06_5", "07_3", "04_5"]
FEAR = ["01_1", "03_5", "02_5", "04_6", "01_6", "06_4", "03_6", "05_1", "07_1", "02_1", "03_2", "06_1", "07_4", "02_6", "05_2", "06_3"]


def big_word(fr, zh, en, col, x, y=H / 2):
    s = 1 + 0.5 * math.exp(-x / 0.09)
    put(fr, zh, "serif", 300, W / 2, y - 40, (255, 255, 255), 1, "cm", stroke=14, sfill=col, scale=s, shadow=10)
    put(fr, en, "bebas", 90, W / 2, y + 190, (255, 255, 255), 1, "cm", stroke=5, sfill=rgb(INK), spacing=26)


def s_human(t):
    """bars 153–169: the constant is the human — greed / fear / 'this time is different' / losscut"""
    b = tb(t)
    p = pulse(t)
    if b < 157:
        name, i, t0 = seq(GREED, t, bt(153), BEAT)
        x = t - t0
        fr = still(EP + name + ".jpg", t, t0, BEAT, 1.1, 1.2, (0.5, 0.42, 0.5, 0.42), punch=0.08 * math.exp(-x / 0.08), rot=(rnd(i) - 0.5) * 4)
        fr = cv2.convertScaleAbs(fr, alpha=1.08, beta=8)
        big_word(fr, "貪婪", "GREED", (30, 170, 255), t - bt(153))
        col = (120, 240, 255)
    elif b < 161:
        name, i, t0 = seq(FEAR, t, bt(157), BEAT)
        x = t - t0
        fr = still(EP + name + ".jpg", t, t0, BEAT, 1.1, 1.22, (0.5, 0.42, 0.5, 0.42), punch=0.08 * math.exp(-x / 0.08), shake=14,
                   rot=(rnd(i) - 0.5) * 5)
        fr = tint(fr, (90, 50, 230), 0.4)
        big_word(fr, "恐懼", "FEAR", (40, 20, 200), t - bt(157))
        col = (80, 60, 255)
    elif b < 165:
        mix = [v for pair in zip(GREED, FEAR) for v in pair]
        name, i, t0 = seq(mix, t, bt(161), BEAT / 2)
        x = t - t0
        fr = still(EP + name + ".jpg", t, t0, BEAT / 2, 1.12, 1.2, (0.5, 0.42, 0.5, 0.42), punch=0.07 * math.exp(-x / 0.05), shake=8,
                   rot=(rnd(i) - 0.5) * 6)
        if i % 2:
            fr = tint(fr, (90, 50, 230), 0.4)
        y = t - bt(161)
        s = 1 + 0.35 * math.exp(-y / 0.1)
        put(fr, "「這次不一樣。」", "serif", 190, W / 2, H / 2 - 60, (255, 255, 255), 1, "cm", stroke=12, sfill=(160, 30, 200), scale=s, shadow=8)
        if b >= 163:
            y2 = t - bt(163)
            put(fr, "——每一次，都一樣。", "serif", 120, W / 2, H / 2 + 170, rgb(YELLOW), 1, "cm", stroke=8, sfill=rgb(INK),
                scale=1 + 0.35 * math.exp(-y2 / 0.1))
        col = (255, 255, 255)
    else:
        # 165–169 losscut finale
        x = t - bt(165)
        fr = losscut_scene(t, bt(165), spin=1.6, fall=1.6, k=0.8, dy=-60)
        sp = sprite(OFF + "top_losscut_losscut_txt.png", 150)
        blit(fr, sp, W / 2, 760, 1.0, 1 + 0.8 * math.exp(-x / 0.12) + 0.05 * beat_env(t), "cm")
        put(fr, "人，亙古不變。", "serif", 150, W / 2, 940, (255, 255, 255), ease((x - BAR) / 0.15), "cm", stroke=8, sfill=(120, 0, 30),
            scale=1 + 0.3 * math.exp(-max(0, x - BAR) / 0.1))
        col = (255, 255, 255)
        if b >= 168:
            # quiet bar: drain to white
            k = (b - 168)
            fr = flash(fr, smooth(k) * 0.9)
    fr = glitch(fr, t, 0.22 * p)
    fr = rgb_split(fr, 3 + 9 * p)
    fr = vignette(fr)
    sec0 = bt(153 + 4 * int((b - 153) / 4))
    return flash(fr, 0.85 * math.exp(-(t - sec0) / 0.12) + 0.4 * flash_env(t), col)


def s_title(t):
    """bars 169–178: 致瞬息萬變之物 (images flicker faster and faster) ， 及亙古不變之物 (one image that never changes)"""
    b = tb(t)
    fe = flash_env(t, 0.06)
    i = int(np.searchsorted(FLASHES, t + 1e-4))
    allimgs = GREED + FEAR
    if b < 173:
        # ever-changing: a new still on every beatmap flash
        name = allimgs[(i * 7) % len(allimgs)]
        fr = cover(EP + name + ".jpg", 1.12 + 0.05 * fe, 0.5, 0.42)
        fr = dim(fr, 0.62)
        x = t - bt(169)
        s = 1 + 0.3 * math.exp(-x / 0.12)
        put(fr, "致", "serif", 120, W / 2, 300, (255, 190, 225), 1, "cm", stroke=6, sfill=rgb(INK))
        put(fr, "瞬息萬變之物，", "serif", 210, W / 2, 520, (255, 255, 255), 1, "cm", stroke=10, sfill=rgb(INK), scale=s, shadow=8, spacing=8)
        put(fr, "TO THINGS EVER-CHANGING,", "bebas", 60, W / 2, 720, (255, 190, 225), 1, "cm", spacing=10)
        fr = rgb_split(fr, 3 + 9 * fe)
        fr = vignette(fr)
        return flash(fr, 0.8 * math.exp(-x / 0.14) + 0.2 * fe)
    # never-changing: the same falling Kurumi; only the strobe accelerates
    x = t - bt(173)
    fr = losscut_scene(t, bt(173), spin=0.5, fall=0.25, k=0.72, dy=-110)
    fr = dim(fr, 0.8)
    s = 1 + 0.3 * math.exp(-x / 0.12)
    put(fr, "及", "serif", 120, W / 2, 690, (170, 230, 255), 1, "cm", stroke=6, sfill=rgb(INK))
    put(fr, "亙古不變之物。", "serif", 210, W / 2, 860, (255, 255, 255), 1, "cm", stroke=10, sfill=rgb(INK), scale=s, shadow=8, spacing=8)
    put(fr, "AND THINGS THAT NEVER CHANGE.", "bebas", 60, W / 2, 1010, (170, 230, 255), 1, "cm", spacing=10)
    fr = rgb_split(fr, 2 + 7 * fe)
    fr = vignette(fr)
    k = clamp((b - 175) / 3)
    out = flash(fr, 0.8 * math.exp(-x / 0.14) + (0.2 + 0.2 * k) * fe)
    if b > 177.5:
        out = flash(out, smooth((b - 177.5) / 0.5))
    return out


CREDITS = [
    "FX戦士くるみちゃん　©でむにゃん・炭酸だいすき／KADOKAWA／「FX戦士くるみちゃん」製作委員会",
    "Music：INTERNET YAMERO — Aiobahn feat. KOTOKO（NEEDY GIRL OVERDOSE）",
    "Sync：osu! beatmap by NeonMarijuana [INTERNET ANGEL]",
    "歷史圖片：Wikimedia Commons（詳見 SOURCES.md）",
    "Fan-made MAD · 非營利二次創作",
]


def s_end(t):
    """bars 178–end: silence. both lines, then tomorrow the market opens again."""
    b = tb(t)
    x = t - bt(178)
    if b < 182:
        fr = np.zeros((H, W, 3), np.uint8)
        fr[:] = (250, 244, 246)
        a = 1.0
        put(fr, "致瞬息萬變之物，", "serif", 130, W / 2, 400, rgb(INK), a, "cm", spacing=8)
        put(fr, "及亙古不變之物。", "serif", 130, W / 2, 590, rgb(INK), ease((x - BAR * 0.5) / 0.6), "cm", spacing=8)
        put(fr, "To things ever-changing, and things that never change.", "serifm", 38, W / 2, 760, (150, 110, 135), ease((x - BAR) / 0.8), "cm")
        fr = flash(fr, 1 - smooth(x / 0.5))
        if b > 181.6:
            fr = dim(fr, 1 - smooth((b - 181.6) / 0.4))
        return fr
    y = t - bt(182)
    fr = cover(EP + "07_5.jpg", 1.05 + 0.012 * y, 0.5, 0.4)
    fr = dim(fr, 0.7 * smooth(y / 0.6))
    put(fr, "明日も、相場は開く。", "jp", 84, W / 2, 330, (255, 255, 255), ease((y - 0.3) / 0.5), "cm", stroke=6, sfill=rgb(INK))
    put(fr, "明天，市場依然會開盤。", "serif", 70, W / 2, 450, (255, 220, 240), ease((y - 0.8) / 0.5), "cm", stroke=5, sfill=rgb(INK))
    rect(fr, 0, H - 300, W, H, (14, 8, 18), 0.72 * ease((y - 1.2) / 0.5))
    for i, c in enumerate(CREDITS):
        put(fr, c, "sansm", 27, W / 2, H - 270 + i * 46, (235, 225, 240), ease((y - 1.3 - i * 0.12) / 0.4), "cm")
    fr = vignette(fr)
    return dim(fr, 1 - smooth((t - (DUR - 2.2)) / 1.9))


SECTIONS = [
    (0, s_intro), (10, s_build), (18, s_drop1), (26, lambda t: s_verse(t, VERSE_A)), (42, lambda t: s_verse(t, VERSE_B)),
    (58, s_break1), (62, s_kicks), (70, s_hardcore), (85, s_prebreak), (86, s_pray), (94, s_drop2), (102, s_after),
    (110, s_timeline), (141, s_changing), (145, s_unchanging), (153, s_human), (169, s_title), (178, s_end),
]


def render(t):
    b = tb(t)
    fn = SECTIONS[0][1]
    for b0, f in SECTIONS:
        if b >= b0 - 1e-6:
            fn = f
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
