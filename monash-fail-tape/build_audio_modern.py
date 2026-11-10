#!/usr/bin/env python3
"""Narration + soundtrack + timeline for the modern version.

Reads  script-modern.json
Writes build/audio-modern.wav  and  timeline-modern.js
Needs: piper-tts (pip), numpy. Downloads the voice model on first run.
"""
import json, os, urllib.request
import numpy as np
import wave
from piper import PiperVoice, SynthesisConfig

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
VOICE_DIR = os.environ.get("VOICE_DIR", os.path.join(BUILD, "voices"))
VOICE = "en_GB-cori-high"     # piper has no en-AU voice; the Australian part is the wording
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/"
os.makedirs(VOICE_DIR, exist_ok=True)
for ext in (".onnx", ".onnx.json"):
    p = os.path.join(VOICE_DIR, VOICE + ext)
    if not os.path.exists(p):
        print("downloading", VOICE + ext)
        urllib.request.urlretrieve(VOICE_URL + VOICE + ext, p)
voice_model = PiperVoice.load(os.path.join(VOICE_DIR, VOICE + ".onnx"))
VSR = voice_model.config.sample_rate
SR = 44100
rng = np.random.default_rng(49)


# ---------- helpers ----------
def resample(x, factor):
    """factor > 1 makes it longer (and lower)."""
    n = int(len(x) * factor)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def trim(x, thresh=0.012):
    idx = np.where(np.abs(x) > thresh)[0]
    return x if len(idx) == 0 else x[max(0, idx[0] - 300): idx[-1] + 3000]


def fade(x, a=0.01, r=0.01):
    x = x.copy()
    na, nr = min(int(a * SR), len(x)), min(int(r * SR), len(x))
    if na: x[:na] *= np.linspace(0, 1, na)
    if nr: x[-nr:] *= np.linspace(1, 0, nr)
    return x


def speak(text, dark):
    cfg = SynthesisConfig(length_scale=1.1 if dark else 1.0, noise_scale=0.5, noise_w_scale=0.7)
    x = np.concatenate([c.audio_int16_array for c in voice_model.synthesize(text, cfg)]).astype(np.float64) / 32768
    x = trim(resample(x, SR / VSR))
    if dark:                                     # same voice, a little lower, a little digital
        x = resample(x, 1.07)
        held = np.repeat(x[::7], 7)[: len(x)]
        x = 0.72 * x + 0.28 * np.pad(held, (0, len(x) - len(held)))
    x /= np.max(np.abs(x)) + 1e-9
    return x * 0.46


def stutter_in(x):
    """Skips like a bad stream on the way in."""
    n = int(0.085 * SR)
    head = fade(x[:n], 0.002, 0.004)
    return np.concatenate([head, head * 0.9, head * 0.8, x])


def stutter_out(x):
    """Catches on the last word and will not let go."""
    n = int(0.42 * SR)
    tail = x[-n - 3000: -3000]
    reps = [fade(resample(tail, 1 + 0.06 * i), 0.004, 0.01) * (0.9 ** i) for i in range(1, 6)]
    return np.concatenate([x[:-3000]] + reps)


def bell(freq, dur, bend=0.0):
    t = np.arange(int(dur * SR)) / SR
    f = freq * (1 - bend * (t / dur) ** 2)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) + 0.4 * np.sin(2.01 * ph) * np.exp(-t * 6) + 0.2 * np.sin(4.2 * ph) * np.exp(-t * 14)) * np.exp(-t * 3.2)


def pad(freqs, n):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        out += np.sin(2 * np.pi * f * t + i) * (0.7 + 0.3 * np.sin(2 * np.pi * (0.05 + 0.013 * i) * t + i))
        out += 0.3 * np.sin(2 * np.pi * f * 1.004 * t + 2 * i)
    return out / len(freqs)


# ---------- timeline ----------
script = json.load(open(os.path.join(HERE, "script-modern.json")))
segments, events, voice = [], [], []
t = 0.0
for seg in script["segments"]:
    out = {k: v for k, v in seg.items() if k not in ("sentences", "dur")}
    out["start"] = round(t, 3)
    if "sentences" not in seg:
        t += seg["dur"]
    else:
        cur = t + 1.0
        dark, sents = False, []
        for s in seg["sentences"]:
            twist = bool(s.get("twist"))
            dark = dark or twist
            x = speak(s.get("say", s["text"]), dark)
            if twist: x = stutter_in(x)
            if s.get("stutter"): x = stutter_out(x)
            st = cur + (0.9 if twist else 0.42)
            en = st + len(x) / SR
            voice.append((st, x))
            sents.append({"text": s["text"], "start": round(st, 3), "end": round(en, 3), "twist": twist})
            if twist:
                out["twistAt"] = round(st, 3)
                events.append({"t": round(st - 0.1, 3), "kind": "glitch", "strength": 1.0, "dur": 0.5})
            if s.get("notify"):
                events.append({"t": round(st + 0.45, 3), "kind": "notif", "text": s["notify"], "dur": 3.6})
            cur = en
        out["sentences"] = sents
        t = cur + 1.5
    out["end"] = round(t, 3)
    segments.append(out)

DUR = t
N = int(DUR * SR) + SR
mix = np.zeros(N)
tt = np.arange(N) / SR
seg = {s["id"]: s for s in segments}


def add(x, start, gain=1.0):
    i = int(start * SR)
    if i >= N or i < 0: return
    x = x[: N - i]
    mix[i:i + len(x)] += x * gain


# ---------- bed: a pleasant corporate pad that sours whenever a rule turns ----------
body = np.clip((tt - seg["title"]["start"]) / 2, 0, 1) * np.clip((seg["end"]["end"] - tt) / 0.05, 0, 1)
darkness = np.zeros(N)
for s in segments:
    if "twistAt" in s:
        a, b = s["twistAt"], s["end"]
        darkness = np.maximum(darkness, np.clip((tt - a) / 1.2, 0, 1) * np.clip((b - tt) / 0.7, 0, 1))
es = seg["end"]["start"]
darkness = np.maximum(darkness, np.clip((tt - es - 5.2) / 1.5, 0, 1) * (tt < seg["end"]["end"]))
nice = pad([130.81, 196.0, 329.63, 293.66, 493.88], N)          # Cmaj9, wide and harmless
nasty = pad([65.4, 92.5, 138.59, 277.18, 370.0], N)              # tritones and a flat ninth
sub = np.sin(2 * np.pi * 41 * tt) * (0.5 + 0.5 * np.sin(2 * np.pi * 1.1 * tt)) ** 2
mix += body * (nice * (1 - darkness) * 0.05 + nasty * darkness * 0.075 + sub * darkness * 0.06)

# ---------- title sting ----------
ts = seg["title"]["start"]
for i, (f, at) in enumerate([(523.25, 0.5), (659.25, 0.72), (783.99, 0.94), (987.77, 1.16), (1046.5, 1.7)]):
    add(bell(f, 2.6, bend=0.035 if i == 4 else 0.0) * 0.07, ts + at)
add(fade(bell(196, 0.5) * 0.12, 0.002, 0.05), ts + 7.2)                                   # "Start" pressed
add(fade(rng.standard_normal(int(0.12 * SR)) * 0.05, 0.002, 0.08), ts + 7.2)

# ---------- per segment ----------
for s in segments:
    if s["type"] in ("rule", "intro", "outro"):
        n = int(0.35 * SR)
        whoosh = rng.standard_normal(n) * np.sin(np.linspace(0, np.pi, n)) ** 2
        add(np.convolve(whoosh, np.ones(24) / 24, "same") * 0.09, s["start"])
        add(bell(659.25, 1.2) * 0.05, s["start"] + 0.25)
        add(bell(880.0, 1.4) * 0.05, s["start"] + 0.39)
    if "twistAt" in s:
        a = s["twistAt"] - 0.1
        tl = np.arange(int(1.0 * SR)) / SR
        add(np.sin(2 * np.pi * (70 * np.exp(-tl * 3.5) + 33) * tl) * np.exp(-tl * 3.8) * 0.34, a)   # sub drop
        n = int(0.22 * SR)
        crush = np.sign(np.sin(2 * np.pi * np.repeat(rng.choice([90, 180, 720, 1440, 2880], n // 441 + 1), 441)[:n] * np.arange(n) / SR))
        gate = np.repeat(rng.random(n // 882 + 1) > 0.4, 882)[:n]
        add(fade(crush * gate * 0.09, 0.001, 0.02), a)
for e in events:
    if e["kind"] == "notif":                                     # three-note ping, a touch too slow
        for i, f in enumerate([1174.66, 1396.91, 1108.73]):
            add(bell(f, 0.9) * 0.085, e["t"] + i * 0.11)

# ---------- ending: autoplay countdown ----------
for i in range(5):
    add(fade(np.sin(2 * np.pi * 660 * np.arange(int(0.09 * SR)) / SR) * 0.07, 0.003, 0.02), es + 1.2 + i * 0.8)
add(fade(np.sin(2 * np.pi * 330 * np.arange(int(0.5 * SR)) / SR) * 0.1, 0.003, 0.2), es + 5.2)
events.append({"t": round(es + 5.2, 3), "kind": "glitch", "strength": 1.0, "dur": 0.7})
n = int(0.3 * SR)
add(fade(np.sign(np.sin(2 * np.pi * 110 * np.arange(n) / SR)) * (rng.random(n) > 0.5) * 0.1, 0.001, 0.02), es + 5.2)
for i, (f, at) in enumerate([(523.25, 5.9), (659.25, 6.12), (783.99, 6.34), (987.77, 6.56)]):   # the sting again, flat
    add(bell(f * 0.94, 2.2, bend=0.08) * 0.06, es + at)

# ---------- voice (with a short slap so it sounds "produced") ----------
vmix = np.zeros(N)
for st, x in voice:
    i = int(st * SR)
    x = fade(x, 0.004, 0.03)[: N - i]
    vmix[i:i + len(x)] += x
d = int(0.11 * SR)
vmix[d:] += vmix[:-d] * 0.1
mix += vmix

mix = np.tanh(mix * 1.4) / 1.4
mix = mix[: int(DUR * SR)]
mix *= 0.89 / np.max(np.abs(mix))
with wave.open(os.path.join(BUILD, "audio-modern.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype(np.int16).tobytes())

events.sort(key=lambda e: e["t"])
timeline = {"fps": script["fps"], "duration": round(DUR, 3), "segments": segments, "events": events}
with open(os.path.join(HERE, "timeline-modern.js"), "w") as f:
    f.write("window.TIMELINE = " + json.dumps(timeline, indent=1) + ";\n")
print(f"duration {DUR:.1f}s, {len(voice)} sentences, {len(events)} events")
for s in segments:
    print(f"  {s['id']:<10} {s['start']:7.2f} -> {s['end']:7.2f}  twist {s.get('twistAt')}")
