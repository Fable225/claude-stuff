# So You've Failed a Unit

A short analog-horror / "rules horror" parody: training material from a fictional
university office, telling students who copped an N grade what to do next.
Narration and on-screen text are in Australian English.

**This is fiction and parody.** It is not affiliated with, produced by, or endorsed by
Monash University. The "Office of Academic Continuity", its rules, and everything the
tape claims about marks, fees and buildings are made up for the joke.

There are two cuts:

- `so-youve-failed-a-unit.mp4` — the VHS cut. A worn training tape with 11 general
  rules, then "Supplement M": four more that apply only at the Malaysia campus
  (960×720, 24 fps, about 6 min 20 s).
- `so-youve-failed-a-unit-modern.mp4` — the modern cut. A clean "compulsory online
  module" that drops into dark mode whenever a rule turns, with 11 rules, including
  one on accepted payment methods (1920×1080, 30 fps, about 4 min 10 s).

The crest in the modern cut is an original parody design (a blank book, a 49 and a
brick wall). It is deliberately not the university's real crest.

## How it is made

| File | What it does |
| --- | --- |
| `script.json`, `script-modern.json` | The scripts: segments, on-screen sentences, how each is spoken, where each rule "turns" |
| `build_audio.py` | VHS cut. Speaks each sentence with `espeak-ng`, degrades it, adds hum, drone, jingle and stings; writes `build/audio.wav` and `timeline.js` |
| `build_audio_modern.py` | Modern cut. Speaks with a Piper neural voice, adds a pad, chimes and notification pings; writes `build/audio-modern.wav` and `timeline-modern.js` |
| `timeline.js`, `timeline-modern.js` | Generated. Start and end time of every segment and sentence, so picture follows sound |
| `tape.js`, `video.html` | VHS cut renderer (scene at 640×480, then scanlines, noise, chroma bleed, tracking errors) |
| `modern.js`, `modern.html` | Modern cut renderer (crest, portal layout, one interface mock-up per rule) |
| `render.mjs` | Steps through every frame in headless Chromium and pipes them to `ffmpeg` with the audio |

## Rebuilding

Needs `ffmpeg`, Python with `numpy`, and Node with Playwright (Chromium). The VHS cut
also needs `espeak-ng`; the modern cut needs `pip install piper-tts` and downloads its
voice model (about 110 MB) into `build/voices` on first run.

VHS cut:

```bash
python3 build_audio.py
```

```bash
node render.mjs
```

Modern cut:

```bash
python3 build_audio_modern.py
```

```bash
node render.mjs modern
```

Opening `video.html` or `modern.html` in a browser plays a silent live preview.

To change a cut, edit its script and run both steps again. `text` is what appears on
screen, `say` (optional) is what the voice reads, `"twist": true` marks the sentence
where a rule goes wrong, and `notify` (modern cut) pops a notification banner. In the
VHS script, `"group": "M"` puts a rule in the Malaysia supplement (numbered M1, M2, …).

## Credits

Font: [VT323](https://fonts.google.com/specimen/VT323) by Peter Hull, SIL Open Font
License (see `fonts/OFL.txt`).
Font: [Inter](https://rsms.me/inter/) by Rasmus Andersson, SIL Open Font License (see
`fonts/Inter-OFL.txt`).
Voice (modern cut): Piper `en_GB-cori-high`.
