// Renders video.html frame by frame and muxes it with build/audio.wav.
//   node render.mjs                        -> so-youve-failed-a-unit.mp4 (VHS version)
//   node render.mjs modern                 -> so-youve-failed-a-unit-modern.mp4
//   node render.mjs [modern] shots 30 41   -> build/shot-<t>.png at those seconds
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const { chromium } = createRequire(import.meta.url)('playwright');
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const V = args[0] === 'modern'
  ? { html: 'modern.html', audio: 'audio-modern.wav', out: 'so-youve-failed-a-unit-modern.mp4', size: [1920, 1080], vf: 'null', crf: '21' }
  // VHS: light denoise first, raw tape grain costs ~8 Mbit/s otherwise
  : { html: 'video.html', audio: 'audio.wav', out: 'so-youve-failed-a-unit.mp4', size: [960, 720], vf: 'hqdn3d=3:3:8:8', crf: '30' };
if (args[0] === 'modern') args.shift();
const url = pathToFileURL(path.join(here, V.html)).href + '?render';
const WORKERS = 4;

const browser = await chromium.launch();
const pages = [];
for (let i = 0; i < WORKERS; i++) {
  const p = await browser.newPage({ viewport: { width: V.size[0], height: V.size[1] } });
  p.on('pageerror', e => { console.error('page error:', e.message); process.exitCode = 1; });
  await p.goto(url);
  await p.evaluate(() => window.ready);
  pages.push(p);
}
const { fps, duration } = await pages[0].evaluate(() => window.TIMELINE);
const total = Math.ceil(duration * fps);

if (args[0] === 'shots') {
  for (const t of args.slice(1).map(Number)) {
    const b64 = await pages[0].evaluate(f => { window.renderFrame(f); return document.getElementById('out').toDataURL('image/png').slice(22); }, Math.round(t * fps));
    fs.writeFileSync(path.join(here, 'build', `shot-${t}.png`), Buffer.from(b64, 'base64'));
  }
  await browser.close();
  process.exit();
}

const outFile = path.join(here, V.out);
const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
  '-i', path.join(here, 'build', V.audio),
  '-vf', V.vf, '-c:v', 'libx264', '-preset', 'slow', '-crf', process.env.CRF || V.crf, '-pix_fmt', 'yuv420p',
  '-c:a', 'aac', '-b:a', '112k', '-shortest', '-movflags', '+faststart', outFile], { stdio: ['pipe', 'inherit', 'inherit'] });

const started = Date.now();
for (let f = 0; f < total; f += WORKERS) {
  const batch = await Promise.all(pages.map((p, i) => f + i < total ? p.evaluate(n => window.frameJPEG(n, 0.92), f + i) : null));
  for (const b64 of batch) if (b64 && !ff.stdin.write(Buffer.from(b64, 'base64'))) await once(ff.stdin, 'drain');
  if (f % (fps * 20) < WORKERS) console.log(`${Math.round(f / fps)}s / ${Math.round(duration)}s  (${((Date.now() - started) / 1000).toFixed(0)}s elapsed)`);
}
ff.stdin.end();
await once(ff, 'close');
await browser.close();
console.log('wrote', outFile, (fs.statSync(outFile).size / 1e6).toFixed(1) + ' MB');
