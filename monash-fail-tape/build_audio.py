#!/usr/bin/env python3
"""Builds the narration + soundtrack and the timeline the renderer syncs to.

Reads  script.json
Writes build/audio.wav  and  timeline.js  (window.TIMELINE = {...})
Needs: espeak-ng, numpy
"""
import json, os, subprocess, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
os.makedirs(BUILD, exist_ok=True)
SR = 44100
rng = np.random.default_rng(49)

FLASHES = {
    "intro": "WE MAKE SURE",
    "r2": "IT IS ALWAYS 49",
    "r6": "DO NOT LOOK UP",
    "r8": "THANK YOU FOR YOUR CONTRIBUTION",
    "outro": "AGAIN",
}


# ---------- helpers ----------
def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    if sr != SR:
        n = int(len(x) * SR / sr)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return x


def bandpass(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    gain = 1 / (1 + (lo / np.maximum(f, 1)) ** 6) / (1 + (f / hi) ** 6)
    return np.fft.irfft(X * gain, len(x))


def trim(x, thresh=0.01):
    idx = np.where(np.abs(x) > thresh)[0]
    if len(idx) == 0:
        return x
    return x[max(0, idx[0] - 400): idx[-1] + 2500]


def speak(text, low, idx):
    path = os.path.join(BUILD, f"s{idx:03d}.wav")
    pitch, speed = (4, 134) if low else (28, 150)
    subprocess.run(["espeak-ng", "-v", "en-gb", "-p", str(pitch), "-s", str(speed),
                    "-g", "3", "-w", path, text], check=True)
    x = trim(read_wav(path))
    x = bandpass(x, 260, 3300)                 # worn tape / PA speaker
    x = np.tanh(x * 2.2)
    x /= np.max(np.abs(x)) + 1e-9
    os.remove(path)
    return x * 0.5


def slowdown(x, end_rate=0.42):
    """Tape motor dying: playback rate glides from 1.0 down to end_rate."""
    out, pos, n = [], 0.0, len(x)
    while pos < n - 1:
        rate = 1.0 - (1.0 - end_rate) * (pos / n) ** 1.6
        i = int(pos)
        out.append(x[i] + (x[i + 1] - x[i]) * (pos - i))
        pos += rate
    return np.array(out)


def tone(freq, dur, amp=1.0):
    t = np.arange(int(dur * SR)) / SR
    return amp * np.sin(2 * np.pi * freq * t)


def fade(x, a=0.01, r=0.01):
    x = x.copy()
    na, nr = min(int(a * SR), len(x)), min(int(r * SR), len(x))
    if na: x[:na] *= np.linspace(0, 1, na)
    if nr: x[-nr:] *= np.linspace(1, 0, nr)
    return x


# ---------- timeline ----------
script = json.load(open(os.path.join(HERE, "script.json")))
segments, events, voice = [], [], []   # voice: (start, samples)
t, sidx = 0.0, 0
for seg in script["segments"]:
    out = {k: v for k, v in seg.items() if k not in ("sentences", "dur")}
    out["start"] = round(t, 3)
    if "sentences" not in seg:
        t += seg["dur"]
    else:
        cur = t + (1.25 if seg["type"] == "rule" else 0.8)
        twisted, sents = False, []
        for s in seg["sentences"]:
            twist = bool(s.get("twist"))
            twisted = twisted or twist
            x = speak(s.get("say", s["text"]), twisted, sidx); sidx += 1
            if s.get("slowdown"):
                x = slowdown(x)
            st = cur + (0.85 if twist else 0.38)
            en = st + len(x) / SR
            voice.append((st, x))
            sents.append({"text": s["text"], "start": round(st, 3), "end": round(en, 3), "twist": twist})
            if twist:
                out["twistAt"] = round(st, 3)
                events.append({"t": round(st - 0.12, 3), "kind": "glitch", "strength": 1.0, "dur": 0.55})
                if seg["id"] in FLASHES:
                    events.append({"t": round(st + 0.3, 3), "kind": "flash", "text": FLASHES[seg["id"]], "dur": 0.13})
            cur = en
        out["sentences"] = sents
        t = cur + 1.5
    out["end"] = round(t, 3)
    events.append({"t": out["start"], "kind": "glitch", "strength": 0.6, "dur": 0.32})
    segments.append(out)

DUR = t
N = int(DUR * SR) + SR
mix = np.zeros(N)
tt = np.arange(N) / SR
seg = {s["id"]: s for s in segments}


def add(x, start, gain=1.0):
    i = int(start * SR)
    if i >= N: return
    x = x[: N - i]
    mix[i:i + len(x)] += x * gain


# ---------- bed: hiss, mains hum (50 Hz, as is proper), drone ----------
body_end = seg["stop"]["start"]
body = (tt < body_end).astype(float)
hiss = rng.standard_normal(N)
hiss = np.diff(hiss, prepend=0) * 0.5 + hiss * 0.3
mix += hiss * 0.010
mix += 0.016 * np.sin(2 * np.pi * 50 * tt) + 0.007 * np.sin(2 * np.pi * 100 * tt) + 0.004 * np.sin(2 * np.pi * 150 * tt)
ramp = np.clip((tt - seg["intro"]["start"]) / (body_end - seg["intro"]["start"]), 0, 1)
drone = (np.sin(2 * np.pi * 55 * tt) + np.sin(2 * np.pi * 55.6 * tt) + 0.6 * np.sin(2 * np.pi * 82.9 * tt)
         + 0.35 * np.sin(2 * np.pi * 110.4 * tt + 2 * np.sin(2 * np.pi * 0.11 * tt)))
drone *= (0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * tt)) * (0.025 + 0.05 * ramp) * body
mix += drone

# ---------- boot: static, then bars and tone ----------
add(fade(rng.standard_normal(int(1.2 * SR)) * 0.16, 0.01, 0.05), 0)
add(fade(tone(1000, 1.9, 0.07), 0.005, 0.01), 1.2)

# ---------- title jingle: cheerful, slightly wrong, sags at the end ----------
ts = seg["title"]["start"] + 0.7
notes = [(261.63, 0.0), (329.63, 0.34), (392.0, 0.68), (523.25, 1.02),
         (261.63, 1.7), (329.63, 1.7), (392.0, 1.7), (493.88, 1.7)]   # last chord: maj7, uneasy
jl = int(6.2 * SR)
jt = np.arange(jl) / SR
wob = 1 + 0.007 * np.sin(2 * np.pi * 0.8 * jt) + 0.002 * np.sin(2 * np.pi * 7 * jt)
sag = np.where(jt > 3.4, 2 ** (-((jt - 3.4) / 2.8) ** 2 * 3 / 12), 1.0)   # melts ~3 semitones flat
jingle = np.zeros(jl)
for f, at in notes:
    ph = 2 * np.pi * np.cumsum(f * wob * sag) / SR
    env = np.where(jt >= at, np.exp(-(jt - at) * (0.75 if at >= 1.7 else 2.2)), 0.0)
    env *= np.clip((jt - at) * 200, 0, 1)
    jingle += env * (np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph))
add(fade(jingle * 0.085, 0.0, 0.3), ts)

# ---------- per segment stings ----------
for s in segments:
    if s["type"] == "rule":
        add(fade(rng.standard_normal(int(0.22 * SR)) * 0.12, 0.002, 0.05), s["start"])
        beep = tone(853, 0.34, 0.035) + tone(960, 0.34, 0.035)
        add(fade(beep, 0.004, 0.01), s["start"] + 0.42)
    if "twistAt" in s:
        a, b = s["twistAt"], s["end"]
        n = int((b - a) * SR)
        lt = np.arange(n) / SR
        cluster = sum(np.sin(2 * np.pi * f * lt + p) for f, p in
                      [(196, 0), (207.65, 1), (293.66, 2), (311.13, 3), (98.5, 4)])
        env = np.clip(lt / 2.2, 0, 1) * np.clip((b - a - lt) / 0.9, 0, 1)
        trem = 0.75 + 0.25 * np.sin(2 * np.pi * 5.3 * lt)
        add(cluster * env * trem * 0.022, a)
        tl = np.arange(int(0.9 * SR)) / SR
        thump = np.sin(2 * np.pi * (62 * np.exp(-tl * 3) + 34) * tl) * np.exp(-tl * 4.5)
        add(thump * 0.32, a - 0.12)
        add(fade(rng.standard_normal(int(0.16 * SR)) * 0.14, 0.002, 0.08), a - 0.12)
for e in events:
    if e["kind"] == "flash":
        add(fade(rng.standard_normal(int(e["dur"] * SR)) * 0.2 + tone(31, e["dur"], 0.3), 0.001, 0.005), e["t"])

# ---------- ending: swell, then the tape runs out ----------
es, ee = seg["end"]["start"], seg["end"]["end"]
n = int((ee - es) * SR)
lt = np.arange(n) / SR
swell = sum(np.sin(2 * np.pi * f * (1 + 0.004 * lt) * lt) for f in (73.4, 77.8, 110, 116.5, 233.1, 246.9))
add(swell * (lt / (ee - es)) ** 2 * 0.045, es)
events.append({"t": round(es + 2.6, 3), "kind": "glitch", "strength": 1.0, "dur": 0.6})
events.append({"t": round(es + 4.4, 3), "kind": "glitch", "strength": 1.0, "dur": 0.9})
add(fade(rng.standard_normal(int(1.1 * SR)) * 0.22, 0.002, 0.1), seg["stop"]["start"])
tl = np.arange(int(0.25 * SR)) / SR
add(np.sin(2 * np.pi * 70 * tl) * np.exp(-tl * 18) * 0.4, seg["stop"]["start"] + 1.1)   # clunk

# ---------- voice ----------
for st, x in voice:
    add(fade(x, 0.004, 0.02), st)

# ---------- wow & flutter over the whole tape, soft clip, write ----------
warp = tt + 0.0016 * np.sin(2 * np.pi * 0.43 * tt) + 0.00022 * np.sin(2 * np.pi * 6.1 * tt)
mix = np.interp(warp, tt, mix)
mix = np.tanh(mix * 1.5) / 1.5
mix = mix[: int(DUR * SR)]
mix *= 0.89 / np.max(np.abs(mix))
with wave.open(os.path.join(BUILD, "audio.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype(np.int16).tobytes())

events.sort(key=lambda e: e["t"])
timeline = {"fps": script["fps"], "duration": round(DUR, 3), "segments": segments, "events": events}
with open(os.path.join(HERE, "timeline.js"), "w") as f:
    f.write("window.TIMELINE = " + json.dumps(timeline, indent=1) + ";\n")
print(f"duration {DUR:.1f}s, {len(voice)} sentences, {len(events)} events")
for s in segments:
    print(f"  {s['id']:<10} {s['start']:7.2f} -> {s['end']:7.2f}")
