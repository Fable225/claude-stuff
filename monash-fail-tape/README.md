# So You've Failed a Unit

A short analog-horror / "rules horror" parody: a worn-out VHS training tape from a
fictional university office, telling students who copped an N grade what to do next.
Narration and on-screen text are in Australian English.

**This is fiction and parody.** It is not affiliated with, produced by, or endorsed by
Monash University. The "Office of Academic Continuity", its rules, and everything the
tape claims about marks, fees and buildings are made up for the joke.

- `so-youve-failed-a-unit.mp4` — the finished video (960×720, 24 fps, about 4 min 20 s)

## How it is made

| File | What it does |
| --- | --- |
| `script.json` | The whole script: segments, on-screen sentences, how each is spoken, where each rule "turns" |
| `build_audio.py` | Speaks each sentence with `espeak-ng`, degrades it, adds hum, drone, jingle and stings, and writes `build/audio.wav` plus `timeline.js` |
| `timeline.js` | Generated. Start and end time of every segment and sentence, so picture follows sound |
| `tape.js`, `video.html` | Draws any frame of the tape on a canvas (scene at 640×480, then a VHS pass: scanlines, noise, chroma bleed, tracking errors) |
| `render.mjs` | Steps through every frame in headless Chromium and pipes them to `ffmpeg` with the audio |

## Rebuilding

Needs `espeak-ng`, `ffmpeg`, Python with `numpy`, and Node with Playwright (Chromium).

```bash
python3 build_audio.py
```

```bash
node render.mjs
```

Opening `video.html` in a browser plays a silent live preview.

To change the tape, edit `script.json` and run both steps again. `text` is what appears
on screen, `say` (optional) is what the voice reads, and `"twist": true` marks the
sentence where a rule goes wrong.

## Credits

Font: [VT323](https://fonts.google.com/specimen/VT323) by Peter Hull, SIL Open Font
License (see `fonts/OFL.txt`).
