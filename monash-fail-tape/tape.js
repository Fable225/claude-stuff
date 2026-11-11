/* Renders the tape one frame at a time. Everything is a pure function of the
   frame number, so the same frame always comes out the same (needed for the
   offline render in render.mjs). Scene is drawn at 640x480, blown up to
   960x720 and then run through a VHS-ish post pass. */
(() => {
const T = window.TIMELINE, W = 640, H = 480, OW = 960, OH = 720;
const out = document.getElementById('out');
const o = out.getContext('2d', { willReadFrequently: true });
const scene = document.createElement('canvas'); scene.width = W; scene.height = H;
const g = scene.getContext('2d');
g.textRendering = 'optimizeSpeed';   // no ligatures: this is meant to be a character generator
const C = { bg: '#070a2e', fg: '#dcdccf', amb: '#f0c93a', red: '#e8301f', pale: '#ff9a84',
            dim: '#7480c4', ink: '#b9c4e8', dark: '#02041a', paper: '#c9cbbd' };
const MYBG = '#062a24';
const F = px => `${px}px VT, monospace`;
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = x => { x = clamp(x); return x * x * (3 - 2 * x); };
const lerp = (a, b, k) => a + (b - a) * k;
function hash(a, b = 0) {
  let n = (Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263)) | 0;
  n = Math.imul(n ^ (n >>> 13), 1274126177); n ^= n >>> 16;
  return (n >>> 0) / 4294967296;
}
function txt(s, x, y, px, col, align = 'left') {
  g.font = F(px); g.fillStyle = col; g.textAlign = align; g.textBaseline = 'top'; g.fillText(s, x, y);
}
const R = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
const box = (x, y, w, h, col, lw = 1) => { g.strokeStyle = col; g.lineWidth = lw; g.strokeRect(x + .5, y + .5, w, h); };
const disc = (x, y, r, col) => { g.fillStyle = col; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); };
const wrapCache = new Map();
function wrap(s, px, maxW) {
  const key = px + '|' + maxW + '|' + s;
  if (wrapCache.has(key)) return wrapCache.get(key);
  g.font = F(px);
  const lines = []; let line = '';
  for (const w of s.split(' ')) {
    const tr = line ? line + ' ' + w : w;
    if (g.measureText(tr).width > maxW && line) { lines.push(line); line = w; } else line = tr;
  }
  if (line) lines.push(line);
  wrapCache.set(key, lines); return lines;
}
function person(x, base, h, col, stretch = 1) {
  const hr = h * 0.1;
  g.fillStyle = col;
  g.beginPath(); g.ellipse(x, base - h + hr * stretch, hr * 0.85, hr * stretch, 0, 0, 7); g.fill();
  const top = base - h + hr * 2 * stretch + 1;
  g.beginPath(); g.moveTo(x - h * 0.17, top + h * 0.07); g.quadraticCurveTo(x, top - h * 0.04, x + h * 0.17, top + h * 0.07);
  g.lineTo(x + h * 0.13, base); g.lineTo(x - h * 0.13, base); g.closePath(); g.fill();
  return base - h + hr * stretch;   // head centre y
}
const eyes = (x, y, d, col = '#fff') => { R(x - d - 1, y - 1, 2, 2, col); R(x + d - 1, y - 1, 2, 2, col); };

/* ------------------------------------------------------------ figures ---
   Each draws into a 264x330 panel. st = { t, s, sp, tw, f }:
   seconds into segment, current sentence index, seconds into that sentence,
   seconds since the rule "turned" (negative before), frame number. */
const FW = 264, FH = 330;
const FIG = {
  results(st) {
    txt('ACADEMIC RECORD', 14, 12, 20, C.ink); R(14, 36, FW - 28, 1, C.dim);
    txt('UNIT', 14, 46, 16, C.dim); txt('MARK', 150, 46, 16, C.dim); txt('GRADE', 204, 46, 16, C.dim);
    const marks = ['71', '64', '49', '58', '66', '75'], grades = ['D', 'C', 'N', 'P', 'C', 'D'];
    for (let i = 0; i < 6; i++) {
      const y = 74 + i * 38, turned = st.tw > 0 && st.tw * 3.2 > ((i * 5 + 3) % 6) + 0.5;
      const bad = i === 2 || turned, col = bad ? (turned ? C.red : C.amb) : C.ink;
      R(14, y + 4, 86 + hash(i, 9) * 20, 14, bad ? col : '#3a4270');
      txt(bad ? '49' : marks[i], 156, y, 22, col); txt(bad ? 'N' : grades[i], 218, y, 22, col);
      if (i === 2 && st.s >= 2 && st.tw < 0 && (st.f >> 3) % 2) box(8, y - 4, FW - 18, 30, C.amb);
    }
    txt(st.tw > 0 ? 'STATUS: AS INTENDED' : 'STATUS: RELEASED', 14, 304, 18, st.tw > 0 ? C.red : C.dim);
  },
  email(st) {
    const late = st.s >= 1;
    txt(late ? '03:49' : '09:00', FW / 2, 14, 64, late ? C.amb : C.ink, 'center');
    txt(late ? 'AM  -  TOO EARLY' : 'AM', FW / 2, 76, 18, C.dim, 'center');
    box(14, 108, FW - 28, 204, C.dim); txt('INBOX', 22, 114, 18, C.dim); R(14, 136, FW - 28, 1, C.dim);
    let y = 144;
    if (late) {
      const on = (st.f >> 2) % 2 || st.tw > 0, col = st.tw > 0 ? C.red : C.amb;
      R(16, y - 2, FW - 32, 50, on ? '#1b1f52' : C.dark);
      disc(28, y + 11, 4, col);
      txt('RE: YOUR RESULT', 40, y, 20, col); txt('03:49', FW - 22, y, 16, col, 'right');
      txt(st.tw > 0.6 ? 'FROM: YOU' : 'FROM: ', 40, y + 22, 18, st.tw > 0.6 ? C.red : C.dim);
      if (st.tw > 2) txt('SENT: TOMORROW', 132, y + 22, 18, C.red);
      y += 58;
    }
    const rows = [['Your results are available', '09:00'], ['Library: item overdue', 'MON'], ['Parking permit reminder', 'FRI']];
    rows.forEach(([a, b], i) => { if (i === 0 && late) return; txt(a, 40, y, 18, C.dim); txt(b, FW - 22, y, 16, C.dim, 'right'); y += 32; });
    if (late && st.tw < 0) txt('1 UNREAD', 22, 286, 18, C.amb);
    if (st.tw > 3.2) txt('IT HAS BEEN OPENED', 22, 286, 18, C.red);
  },
  mark(st) {
    txt('FINAL MARKS - ALL STUDENTS', 12, 10, 18, C.dim);
    const base = 262, x0 = 22, bw = 12;
    for (let m = 40; m < 59; m++) {
      const x = x0 + (m - 40) * bw;
      const h = m < 49 ? 8 + hash(m, 4) * 34 : m === 49 ? 196 * ease(st.t / 1.6) : 0;
      R(x, base - h, bw - 2, h, m === 49 ? (st.s >= 1 ? C.red : C.amb) : C.ink);
    }
    R(12, base, FW - 24, 1, C.dim);
    const px = x0 + 10 * bw - 1;
    for (let y = 34; y < base; y += 8) R(px, y, 1, 4, C.fg);
    txt('PASS', px + 6, 36, 18, C.fg); txt('50', px - 4, base + 6, 16, C.fg);
    txt('40', x0, base + 6, 16, C.dim); txt('49', x0 + 9 * bw - 14, base + 6, 16, C.red);
    if (st.tw > 0) {                    // the missing mark leaves
      const k = ease(st.tw / 3.2), bx = lerp(x0 + 10 * bw, 236, k), by = lerp(base - 204, 96 - Math.sin(k * 3.14) * 40, k);
      R(bx, by, bw - 2, 7, C.amb);
      if (st.s >= 3) { box(180, 100, 72, 44, C.amb); txt('CAPITAL', 216, 104, 16, C.amb, 'center'); txt('WORKS', 216, 120, 16, C.amb, 'center'); }
    }
    if (st.s >= 1) txt('n = EVERYONE', 22, 292, 18, C.red);
  },
  paper(st) {
    g.save(); g.translate(FW / 2, FH / 2); g.rotate(-0.045); g.translate(-FW / 2, -FH / 2);
    R(36, 22, 192, 288, C.paper); R(36, 22, 192, 30, '#aeb0a2');
    txt('EXAM SCRIPT', 44, 28, 18, '#1a1a2a'); txt('49/100', 222, 28, 18, '#a01810', 'right');
    for (let i = 0; i < 11; i++) {
      const y = 70 + i * 21, gone = st.tw > 0 && st.tw * 2.4 > ((i * 7) % 11);
      if (gone) {
        const n = 1 + Math.floor(hash(i, 2) * 4);
        txt('STAY '.repeat(n) + (i % 3 === 0 ? 'ENROLLED' : ''), 46 + (hash(i, st.f >> 2) - .5) * 2, y - 9, 20, '#b0140c');
      } else {
        g.strokeStyle = '#2a2f66'; g.lineWidth = 1.2; g.beginPath();
        const len = 90 + hash(i, 1) * 80;
        for (let x = 0; x < len; x += 3) g.lineTo(46 + x, y + Math.sin(x * 0.9 + i) * 2.4 + (hash(i * 97 + x, 3) - .5) * 4);
        g.stroke();
      }
    }
    g.restore();
    if (st.s >= 1 && st.tw < 0) txt('IS THIS YOUR HANDWRITING?', FW / 2, 308, 16, C.amb, 'center');
  },
  queue(st) {
    R(0, 0, FW, 132, '#0b0f3a'); R(0, 252, FW, 2, C.dim);
    txt('SERVICE COUNTER', 12, 6, 18, C.dim);
    R(24, 44, 92, 74, C.amb); box(24, 44, 92, 74, C.fg);
    person(70, 118, 54, '#3a3110'); R(24, 106, 92, 12, '#8a7420');
    txt('WINDOW 1', 70, 26, 16, C.fg, 'center');
    [38, 70, 102].forEach((x, i) => person(x, 252 + Math.sin(st.t * 0.9 + i * 2) * 1.2, 66 + (i % 2) * 5, C.ink));
    if (st.tw > 0) {
      const a = ease(st.tw / 1.4) * (hash(st.f, 11) < 0.06 ? 0.3 : 1);
      g.globalAlpha = a;
      R(148, 44, 92, 74, '#000'); box(148, 44, 92, 74, C.red);
      txt('WINDOW 2', 194, 26, 16, C.red, 'center');
      if (st.tw > 1.5) eyes(194, 76, 7, C.pale);
      [162, 194, 226].forEach((x, i) => {
        const h = 104 + (i % 2) * 10, hy = person(x, 252, h, '#000', 1.5);
        g.strokeStyle = '#7a120b'; g.lineWidth = 1.5; g.beginPath(); g.ellipse(x, hy, h * 0.085, h * 0.15, 0, 0, 7); g.stroke();
        g.beginPath(); g.moveTo(x - h * 0.17, 252 - h * 0.62); g.lineTo(x - h * 0.13, 252); g.moveTo(x + h * 0.17, 252 - h * 0.62); g.lineTo(x + h * 0.13, 252); g.stroke();
        if (st.s >= 3 && st.sp > 0.5 + i * 0.35) eyes(x, hy - 2, 4, '#fff');   // they turn around
      });
      g.globalAlpha = 1;
    }
    const serving = st.s >= 3 && st.sp > 1.8;
    txt(serving ? 'NOW SERVING: YOU' : 'PLEASE WAIT TO BE CALLED', FW / 2, 284, 20, serving ? C.red : C.dim, 'center');
  },
  lift(st) {
    R(56, 14, 152, 304, '#1a1e4a'); box(56, 14, 152, 304, C.dim);
    const turned = st.tw > 0.3, fl = Math.floor(st.t * 0.9) % 12;
    R(88, 26, 88, 46, '#000'); box(88, 26, 88, 46, C.dim);
    txt(turned ? '12' : (fl === 0 ? 'G' : String(fl)), 132, 26, 44, turned ? C.red : C.amb, 'center');
    const rows = [[9, 10, 11], [6, 7, 8], [3, 4, 5], [0, 1, 2]];
    rows.forEach((row, r) => row.forEach((n, c) => {
      const x = 92 + c * 40, y = 148 + r * 44, lit = !turned && n === fl;
      disc(x, y, 15, lit ? C.amb : '#0a0d30'); g.strokeStyle = C.ink; g.lineWidth = 1; g.beginPath(); g.arc(x, y, 15, 0, 7); g.stroke();
      txt(n === 0 ? 'G' : String(n), x, y - 10, 20, lit ? '#000' : C.ink, 'center');
    }));
    if (st.tw > 0) {
      const a = ease(st.tw / 1.2), pulse = 0.65 + 0.35 * Math.sin(st.t * 7);
      g.globalAlpha = a;
      disc(132, 102, 15 + pulse * 3, `rgba(232,48,31,${0.35 * pulse})`);
      disc(132, 102, 15, '#3a0805'); g.strokeStyle = C.red; g.lineWidth = 2; g.beginPath(); g.arc(132, 102, 15, 0, 7); g.stroke();
      txt('12', 132, 92, 20, C.red, 'center');
      g.globalAlpha = 1;
    }
  },
  invig(st) {
    R(0, 0, FW, 206, '#0b0f3a'); R(0, 206, FW, 2, C.dim);
    disc(222, 40, 16, '#0a0d30'); g.strokeStyle = C.dim; g.beginPath(); g.arc(222, 40, 16, 0, 7); g.stroke();
    R(221, 28, 2, 13, C.ink); R(222, 39, 10, 2, C.ink);
    [48, 124, 200].forEach((x, i) => person(x, 206, 70, C.ink));
    for (let r = 0; r < 3; r++) for (let c = 0; c < 4 + r; c++) {
      const w = 30 + r * 10, gap = FW / (4 + r);
      R(c * gap + (gap - w) / 2, 232 + r * 34, w, 8 + r * 2, '#3a4270');
    }
    const four = st.tw > 0.2;
    txt('COUNT: ' + (four ? 4 : 3), 12, 10, 24, four ? C.red : C.amb);
    if (st.tw > 0) {
      const near = ease((st.tw - 3) / 5.5), h = lerp(96, 250, near), b = lerp(206, 338, near), x = lerp(162, 132, near);
      g.globalAlpha = ease(st.tw / 0.9) * (hash(st.f, 3) < 0.05 ? 0.4 : 1);
      const hy = person(x, b, h, '#000', 1.35);
      g.strokeStyle = '#5a0d08'; g.lineWidth = 1.5; g.beginPath(); g.ellipse(x, hy, h * 0.085, h * 0.135, 0, 0, 7); g.stroke();
      eyes(x, hy - 1, h * 0.032 + 1, '#fff');
      g.globalAlpha = 1;
    }
  },
  repeat(st) {
    const n = st.tw > 0 ? 1 + (st.t - st.tw) * 0.75 + st.tw * 1.2 + Math.pow(st.tw, 3.2) * 4 : 1 + st.t * 0.75;
    const last = Math.floor(n), col = st.tw > 0 ? C.pale : C.ink;
    for (let i = Math.max(1, last - 12); i <= last; i++) {
      const y = 270 - (n - i) * 24;
      txt(String(i).padStart(4, '0'), 14, y, 22, col); txt('49', 96, y, 22, col); txt('N', 160, y, 22, col); txt('PAID', 204, y, 22, col);
    }
    R(0, 0, FW, 38, C.dark); R(0, 294, FW, 36, C.dark);
    txt('ATT.', 14, 10, 18, C.dim); txt('MARK', 88, 10, 18, C.dim); txt('GRADE', 142, 10, 18, C.dim); txt('FEE', 208, 10, 18, C.dim);
    R(10, 34, FW - 20, 1, C.dim); R(10, 296, FW - 20, 1, C.dim);
    txt('ATTEMPTS: ' + last.toLocaleString('en-AU'), 14, 302, 22, st.tw > 0 ? C.red : C.amb);
  },
  building(st) {
    if (st.tw <= 0.25) {
      const cols = 13, bw = 12, bh = 8, x0 = 34, ground = 286, total = cols * 26;
      const count = st.s >= 1 ? total : Math.min(total, Math.floor(st.t * 26));
      for (let i = 0; i < count; i++) {
        const r = Math.floor(i / cols), c = i % cols;
        R(x0 + c * bw + (r % 2 ? 0 : 0), ground - (r + 1) * bh, bw - 1, bh - 1, hash(i, 5) < 0.12 ? C.amb : '#8f6a4a');
      }
      R(10, ground, FW - 20, 2, C.dim);
      R(226, 30, 3, ground - 30, C.ink); R(110, 30, 136, 3, C.ink); R(122, 33, 1, 30 + ((st.f >> 1) % 6), C.ink); R(118, 62 + ((st.f >> 1) % 6), 9, 6, C.amb);
      txt(st.s >= 1 ? 'COMPLETED: OVERNIGHT' : 'UNDER CONSTRUCTION', 12, 300, 18, st.s >= 1 ? C.amb : C.dim);
      txt('EACH BRICK = ONE ATTEMPT', 12, 8, 16, C.dim);
    } else {
      R(0, 0, FW, FH, '#14100a');
      txt('DONOR WALL', FW / 2, 10, 28, C.amb, 'center'); R(30, 42, FW - 60, 1, C.amb);
      txt('with thanks to', FW / 2, 46, 16, '#8a7420', 'center');
      const count = Math.floor(st.tw * 7), cap = 24;
      for (let i = 0; i < Math.min(count, cap); i++) {
        const c = i % 2, r = (i - c) / 2, newest = i === Math.min(count, cap) - 1;
        txt('YOUR NAME', 22 + c * 122, 70 + r * 19, 20, newest ? '#fff' : (count > cap && hash(i, st.f >> 1) < 0.2 ? C.red : C.amb));
      }
      if (st.s >= 3) txt('x ' + Math.max(49, count), FW / 2, 300, 24, C.red, 'center');
    }
  },
  bus(st) {
    const on = st.tw > 0, k = on ? 1 + Math.min(st.tw * 0.045, 0.34) : 1;
    R(0, 262, FW, 2, C.dim); R(238, 120, 3, 142, C.ink); R(228, 108, 24, 20, on ? '#3a0805' : C.amb);
    txt('BUS LOOP', 12, 8, 18, C.dim);
    g.save(); g.translate(122 + (on ? (hash(st.f, 2) - .5) * 2 : 0), 262); g.scale(k, k); g.translate(-122, -262);
    R(46, 250, 26, 12, '#000'); R(172, 250, 26, 12, '#000');
    g.fillStyle = on ? '#141833' : '#6a76b0'; g.beginPath(); g.roundRect(40, 62, 164, 190, 10); g.fill();
    R(52, 74, 140, 26, '#000');
    if (on) txt('49', 122, 70, 34, C.red, 'center'); else txt('601 HUNTINGDALE', 122, 78, 20, C.amb, 'center');
    R(52, 108, 140, 78, on ? '#000' : '#10143c');
    if (!on) { person(92, 186, 54, '#2a3066'); R(120, 108, 2, 78, '#6a76b0'); }
    else if (st.tw > 1.6) for (let i = 0; i < 5; i++) eyes(66 + i * 28, 150 + (i % 2) * 8, 3, C.pale);
    R(40, 232, 164, 8, on ? '#000' : '#3a4270');
    disc(60, 214, 9, on ? C.red : '#f4f0c0'); disc(184, 214, 9, on ? C.red : '#f4f0c0');
    g.restore();
    if (st.s >= 2) txt('DO NOT TOUCH ON', FW / 2, 300, 22, C.red, 'center');
  },
  pay(st) {
    const on = st.tw > 0, appr = st.s >= 3 && st.sp > 1.2, lcd = on ? C.red : '#7ddc8a';
    txt('EFTPOS', 12, 6, 18, C.dim);
    R(52, 28, 160, 294, '#1a1e4a'); box(52, 28, 160, 294, C.dim);
    R(64, 40, 136, 98, '#04120a'); box(64, 40, 136, 98, C.dim);
    if (!appr) {
      txt('SUPP EXAM FEE', 70, 44, 18, lcd);
      txt(st.s >= 1 ? 'NO CASH' : '+ SURCHARGE', 70, 62, 18, lcd);
      txt('SELECT ACCOUNT', 70, 86, 18, lcd);
      txt('CHQ SAV CR', 70, 108, 22, lcd);
      if (on && (st.f >> 2) % 2) txt('YOU', 166, 108, 22, '#fff');
    } else {
      txt('APPROVED', 132, 44, 34, C.red, 'center');
      txt('PAID WITH:', 70, 86, 18, C.red); R(70, 108, 124, 18, C.red);
    }
    ['CHQ', 'SAV', 'CR', ''].forEach((k, i) => {
      const hot = i === 3 && on;
      R(64 + i * 35, 148, 31, 18, hot ? ((st.f >> 2) % 2 ? C.red : '#5a0d08') : '#0a0d30'); box(64 + i * 35, 148, 31, 18, hot ? C.red : C.ink);
      txt(k, 64 + i * 35 + 15, 149, 16, C.ink, 'center');
    });
    [[1, 2, 3], [4, 5, 6], [7, 8, 9], ['X', 0, 'OK']].forEach((row, r) => row.forEach((k, c) => {
      const x = 68 + c * 44, y = 180 + r * 32, dead = k === 'X' && st.tw > 1.2;
      R(x, y, 38, 24, k === 'X' ? (dead ? '#1a1a22' : '#7a120b') : k === 'OK' ? '#12502a' : '#0a0d30'); box(x, y, 38, 24, dead ? '#33364a' : C.ink);
      txt(String(k), x + 19, y + 2, 20, dead ? '#33364a' : C.fg, 'center');
    }));
    if (st.tw > 1.2) txt('CANCEL: NO RESPONSE', 132, 304, 16, C.red, 'center');
  },
  canopy(st) {
    const on = st.tw > 0, vx = 132, vy = 150;
    R(0, 0, FW, FH, '#04061c');
    g.strokeStyle = C.dim; g.lineWidth = 1;
    [[0, 20], [FW, 20], [0, FH], [FW, FH]].forEach(([x, y]) => { g.beginPath(); g.moveTo(x, y); g.lineTo(vx, vy); g.stroke(); });
    const ph = (st.t * 0.45) % 1;                           // you keep walking
    for (let k = 9; k >= 0; k--) {
      const z = k + 1 - ph, sc = 1 / (1 + z * 0.55), dark = on && k > 8 - st.tw * 1.3;
      box(vx - 132 * sc, vy - 130 * sc, 264 * sc, 310 * sc, dark ? '#2a2f66' : C.ink);
      if (!dark) R(vx - 3 * sc - 1, vy - 130 * sc + 2, 6 * sc + 2, 3 * sc + 1, C.amb);
    }
    const exit = on ? Math.max(0, 1 - st.tw / 2.5) : 1;      // the far end stops getting closer, then goes
    if (exit > 0) { R(vx - 9 * exit, vy - 12 * exit, 18 * exit, 26 * exit, C.amb); if (!on) txt('PYRAMID', vx, vy - 34, 16, C.amb, 'center'); }
    const secs = Math.floor(on ? 600 + st.tw * 6 + st.tw * st.tw * 55 : Math.min(599, 412 + st.t * 14));
    R(0, 0, FW, 26, '#04061c');
    txt('WALKED  ' + String(Math.floor(secs / 60)).padStart(2, '0') + ':' + String(secs % 60).padStart(2, '0'), 12, 4, 22, on ? C.red : C.amb);
    if (st.s >= 3) {                                        // something large comes up behind you
      const h = Math.min(96, st.sp * 34);
      R(0, FH - h, FW, h, '#000');
      for (let i = 0; i < 6; i++) { R(i * 44, FH - h - 10 - (i % 2) * 8, 40, 12 + (i % 2) * 8, '#000'); if (h > 30) R(i * 44 + 14, FH - h + 8, 8, 8, hash(i, st.f >> 3) < 0.7 ? C.red : '#3a0805'); }
      txt('BEHIND YOU: CAMPUS', FW / 2, FH - 24, 20, C.red, 'center');
    }
  },
  mamak(st) {
    const on = st.tw > 0;
    R(0, 0, FW, 30, '#0b0f3a'); txt('RESTORAN  -  BUKA 24 JAM', FW / 2, 5, 20, C.amb, 'center');
    txt(on ? '02:49 AM' : '02:4' + (Math.floor(st.t / 3) % 9) + ' AM', 12, 36, 18, on ? C.red : C.dim); txt('OPEN', FW - 12, 36, 18, C.dim, 'right');
    R(0, 232, FW, 3, C.dim);
    g.fillStyle = C.ink; g.beginPath(); g.ellipse(58, 224, 42, 9, 0, 0, 7); g.fill();
    g.fillStyle = '#c9a25a'; g.beginPath(); g.ellipse(58, 221, 28, 6, 0, 0, 7); g.fill();
    R(176, 206, 72, 26, '#3a4270'); R(180, 200, 64, 8, C.ink); txt('NOTES', 212, 208, 16, C.ink, 'center');
    if (on) {                                               // nobody ordered this
      const a = ease(st.tw / 1.2), left = st.s >= 3 ? Math.max(0.08, 1 - st.sp / 4.5) : 1, top = 150, bot = 230;
      g.globalAlpha = a;
      g.fillStyle = '#2a3066'; g.beginPath(); g.moveTo(108, top); g.lineTo(156, top); g.lineTo(150, bot); g.lineTo(114, bot); g.closePath(); g.fill();
      const ty = bot - (bot - top - 10) * left;
      g.fillStyle = '#b8743a'; g.beginPath(); g.moveTo(109 + (ty - top) * 0.07, ty); g.lineTo(155 - (ty - top) * 0.07, ty); g.lineTo(150, bot); g.lineTo(114, bot); g.closePath(); g.fill();
      R(110 + (ty - top) * 0.07, ty - 9, 44 - (ty - top) * 0.14, 9, '#f0e6d0');
      g.strokeStyle = C.red; g.lineWidth = 1; g.beginPath(); g.moveTo(108, top); g.lineTo(156, top); g.lineTo(150, bot); g.lineTo(114, bot); g.closePath(); g.stroke();
      g.strokeStyle = C.ink; g.lineWidth = 1.5;
      for (let i = 0; i < 3; i++) { g.beginPath(); for (let y = 0; y < 44; y += 4) g.lineTo(120 + i * 12 + Math.sin(y * 0.3 + st.t * 3 + i) * 3, top - 8 - y); g.stroke(); }
      g.globalAlpha = 1;
      if (st.s >= 3) txt('IT IS BEING DRUNK', FW / 2, 124 - 80, 18, C.red, 'center');
    }
    R(18, 244, 228, 80, C.paper);
    txt('TABLE 49', 26, 246, 18, '#1a1a2a'); txt('BIL', 238, 246, 18, '#1a1a2a', 'right');
    txt('ROTI CANAI      x1', 26, 264, 18, '#1a1a2a');
    if (st.s >= 1) txt('MILO AIS        x1', 26, 282, 18, '#1a1a2a');
    if (on) txt('TEH TARIK       x1', 26, st.s >= 1 ? 300 : 282, 18, '#b0140c');
    if (st.s >= 3 && st.sp > 0.8) { R(18, 306, 228, 18, '#b0140c'); txt('CHARGED TO: TUITION FEES', FW / 2, 305, 18, '#fff', 'center'); }
  },
  qr(st) {
    const on = st.tw > 0, x0 = 38, y0 = 40, m = 9, paid = st.s >= 3 && st.sp > 0.9;
    txt('SCAN TO PAY', 12, 8, 20, C.dim); txt('RM', FW - 12, 8, 20, C.amb, 'right');
    R(x0 - 9, y0 - 9, 21 * m + 18, 21 * m + 18, C.paper);
    const finder = (cx, cy, core) => { R(x0 + cx * m, y0 + cy * m, 7 * m, 7 * m, '#10122a'); R(x0 + (cx + 1) * m, y0 + (cy + 1) * m, 5 * m, 5 * m, C.paper); R(x0 + (cx + 2) * m, y0 + (cy + 2) * m, 3 * m, 3 * m, core || '#10122a'); };
    const eye = on && st.tw > 0.8;
    for (let j = 0; j < 21; j++) for (let i = 0; i < 21; i++) {
      if ((i < 8 && j < 8) || (i > 12 && j < 8) || (i < 8 && j > 12)) continue;
      if (eye && i > 5 && i < 15 && j > 5 && j < 15) continue;
      if (hash(i * 31 + j, on ? 100 + (st.f >> 2) : 7) < 0.48) R(x0 + i * m, y0 + j * m, m, m, '#10122a');
    }
    finder(0, 0); finder(14, 0); finder(0, 14);
    if (eye) {                                              // it looks back
      const blink = hash(st.f >> 3, 17) < 0.12, px = Math.round(Math.sin(st.t * 1.7) * 1.2), py = Math.round(Math.cos(st.t * 1.1) * 0.8);
      R(x0 + 6 * m, y0 + 6 * m, 9 * m, 9 * m, C.paper); R(x0 + 7 * m, y0 + 7 * m, 7 * m, 7 * m, '#10122a'); R(x0 + 8 * m, y0 + 8 * m, 5 * m, 5 * m, C.paper);
      if (blink) R(x0 + 8 * m, y0 + 10 * m, 5 * m, m, '#10122a'); else R(x0 + (9 + px) * m, y0 + (9 + py) * m, 3 * m, 3 * m, '#b0140c');
    }
    if (on && !paid) {
      const sy = (st.tw * 120) % FH;
      R(0, sy, FW, 3, C.red); g.globalAlpha = 0.22; R(0, sy - 18, FW, 18, C.red); g.globalAlpha = 1;
    }
    if (paid) { txt('BAYARAN DITERIMA', FW / 2, 250, 26, C.red, 'center'); txt('PAYMENT RECEIVED', FW / 2, 278, 18, C.pale, 'center'); txt('TERIMA KASIH', FW / 2, 302, 18, C.pale, 'center'); }
    else if (on) { if ((st.f >> 3) % 2) txt('SCANNING YOU', FW / 2, 256, 26, C.red, 'center'); txt('DO NOT MOVE', FW / 2, 290, 20, C.pale, 'center'); }
    else { txt('FPX / JOMPAY / DUITNOW QR', FW / 2, 256, 18, C.ink, 'center'); txt('AMOUNT: RM ----.--', FW / 2, 282, 20, C.amb, 'center'); }
  },
  time(st) {
    const on = st.tw > 0, mins = st.t * 2.2;
    const clock = (cx, name, hour, extra, col) => {
      disc(cx, 84, 46, '#0a0d30'); g.strokeStyle = col; g.lineWidth = 2; g.beginPath(); g.arc(cx, 84, 46, 0, 7); g.stroke();
      for (let i = 0; i < 12; i++) { const a = i * Math.PI / 6; R(cx + Math.sin(a) * 40 - 1, 84 - Math.cos(a) * 40 - 1, 2, 2, col); }
      const total = hour * 60 + mins + extra, ha = total / 720 * Math.PI * 2, ma = total / 60 * Math.PI * 2;
      g.strokeStyle = col; g.lineWidth = 3; g.beginPath(); g.moveTo(cx, 84); g.lineTo(cx + Math.sin(ha) * 22, 84 - Math.cos(ha) * 22); g.stroke();
      g.lineWidth = 1.5; g.beginPath(); g.moveTo(cx, 84); g.lineTo(cx + Math.sin(ma) * 36, 84 - Math.cos(ma) * 36); g.stroke();
      txt(name, cx, 136, 16, col, 'center');
    };
    txt('YOU', 68, 6, 18, C.dim, 'center'); txt('THEM', 196, 6, 18, on ? C.red : C.dim, 'center');
    clock(68, 'KUALA LUMPUR', 6, on ? -st.tw * 2.2 : 0, C.ink);                       // yours stops
    clock(196, 'MELBOURNE', 9, on ? st.tw * st.tw * 90 : 0, on ? C.red : C.amb);       // theirs does not
    txt(on ? 'AHEAD. ALWAYS.' : st.s >= 1 ? 'RESULT: DECIDED' : '3 HRS AHEAD', 196, 154, 16, on ? C.red : C.amb, 'center');
    txt(st.s >= 1 ? 'RESULT: PENDING' : 'WAITING', 68, 154, 16, C.ink, 'center');
    box(16, 184, 232, 132, on ? C.red : C.dim);
    if (!on) { txt('TELEPHONE', 132, 190, 18, C.dim, 'center'); txt('NO CALL IN PROGRESS', 132, 240, 18, C.dim, 'center'); }
    else {
      const live = st.tw > 2.2;
      txt(live ? 'CONNECTED: CLAYTON' : 'CALLING CLAYTON' + '.'.repeat(1 + (st.f >> 3) % 3), 132, 190, 18, C.pale, 'center');
      if (live) {
        txt('VOICE MATCH: YOU', 132, 212, 22, C.red, 'center');
        g.strokeStyle = C.red; g.lineWidth = 1.5; g.beginPath();
        for (let x = 0; x <= 208; x += 4) g.lineTo(28 + x, 264 + (hash(x, st.f >> 1) - 0.5) * 44 * Math.sin(x / 208 * Math.PI));
        g.stroke();
        txt('CALL TIME 49:49', 132, 292, 18, C.pale, 'center');
      }
    }
  },
  mate(st) {
    const k = st.tw > 0 ? ease(st.tw / 2.6) : 0;
    g.fillStyle = '#3a4270'; g.beginPath(); g.moveTo(22, 330); g.quadraticCurveTo(30, 206, 132, 196); g.quadraticCurveTo(234, 206, 242, 330); g.fill();
    R(114, 166, 36, 40, C.ink);
    g.fillStyle = k > 0.5 ? '#d6dcf4' : C.ink; g.beginPath(); g.ellipse(132, 110, 50, 64, 0, 0, 7); g.fill();
    g.globalAlpha = 1 - k;
    g.fillStyle = C.dark; g.beginPath(); g.ellipse(112, 100, 6, 4, 0, 0, 7); g.fill(); g.beginPath(); g.ellipse(152, 100, 6, 4, 0, 0, 7); g.fill();
    R(103, 86, 18, 2, C.dark); R(143, 86, 18, 2, C.dark); R(131, 104, 2, 20, C.dark);
    g.strokeStyle = C.dark; g.lineWidth = 2; g.beginPath(); g.arc(132, 130, 18, 0.25, 2.9); g.stroke();
    g.globalAlpha = 1;
    txt(st.tw > 0 ? 'MATE (FORMER)' : 'MATE', 12, 8, 18, st.tw > 0 ? C.red : C.dim);
    if (st.s >= 3) {
      g.strokeStyle = C.red; g.lineWidth = 2; g.beginPath(); g.moveTo(108, 190); g.lineTo(132, 252); g.lineTo(156, 190); g.stroke();
      R(108, 252, 48, 58, '#14060a'); box(108, 252, 48, 58, C.red, 2);
      R(122, 260, 20, 22, '#d6dcf4'); txt('STAFF', 132, 286, 18, C.red, 'center');
    }
  },
};

/* --------------------------------------------------------------- scenes --- */
function header(right) {
  txt('MONASH UNIVERSITY', 24, 12, 24, C.fg);
  txt('OFFICE OF ACADEMIC CONTINUITY', 24, 35, 16, C.dim);
  txt(right, W - 24, 12, 16, C.dim, 'right'); txt('TAPE 04-N', W - 24, 28, 16, C.dim, 'right');
  R(24, 55, W - 48, 1, C.dim);
}
function sentences(seg, t, x, y, maxW, px, f) {
  const lh = px + 2; let turned = false;
  for (let i = 0; i < seg.sentences.length; i++) {
    const s = seg.sentences[i];
    if (t < s.start) break;
    turned = turned || s.twist;
    const current = i === seg.sentences.length - 1 || t < seg.sentences[i + 1].start;
    let budget = Math.floor((t - s.start) * 46);
    g.globalAlpha = current ? 1 : 0.72;
    const lines = wrap(s.text, px, maxW);
    for (let j = 0; j < lines.length; j++) {
      if (budget <= 0) break;
      const shown = lines[j].slice(0, budget); budget -= lines[j].length + 1;
      txt(shown, x, y + j * lh, px, turned ? C.pale : C.fg);
      if (current && budget <= 0 && (f >> 2) % 2) R(x + g.measureText(shown).width + 2, y + j * lh + 3, px * 0.4, px * 0.72, turned ? C.pale : C.fg);
    }
    g.globalAlpha = 1;
    y += lines.length * lh + 9;
  }
  return y;
}
function state(seg, t, f) {
  let s = -1;
  seg.sentences.forEach((x, i) => { if (t >= x.start) s = i; });
  return { t: t - seg.start, s, sp: s >= 0 ? t - seg.sentences[s].start : 0, tw: seg.twistAt != null ? t - seg.twistAt : -1, f };
}
function figure(seg, st, n) {
  const FX = 352, FY = 66;
  g.save(); g.translate(FX, FY);
  R(0, 0, FW, FH, C.dark);
  g.beginPath(); g.rect(0, 0, FW, FH); g.clip();
  FIG[seg.fig](st);
  g.restore();
  box(FX, FY, FW, FH, st.tw > 0 ? C.red : C.dim);
  txt('FIG. ' + n, FX, FY + FH + 6, 16, C.dim);
}
const SCENE = {
  boot(seg, t) {
    if (t - seg.start < 1.2) { R(0, 0, W, H, '#000'); return; }
    ['#c0c0c0', '#c0c000', '#00c0c0', '#00c000', '#c000c0', '#c00000', '#0000c0'].forEach((c, i) => R(Math.round(i * W / 7), 0, Math.ceil(W / 7), 330, c));
    ['#0000c0', '#111', '#c000c0', '#111', '#00c0c0', '#111', '#c0c0c0'].forEach((c, i) => R(Math.round(i * W / 7), 330, Math.ceil(W / 7), 36, c));
    R(0, 366, W, 114, '#0a0a0a');
    txt('TAPE 04-N   PROPERTY OF THE OFFICE OF ACADEMIC CONTINUITY', W / 2, 388, 18, '#ddd', 'center');
    txt('DO NOT REMOVE FROM VIEWING ROOM', W / 2, 412, 18, '#ddd', 'center');
  },
  card(seg, t) {
    R(0, 0, W, H, '#000');
    const y0 = (H - seg.lines.length * 26) / 2;
    seg.lines.forEach((l, i) => {
      g.globalAlpha = ease((t - seg.start - 0.3 - i * 0.12) / 0.5) * ease((seg.end - t) / 0.5);
      txt(l, W / 2, y0 + i * 26, 24, i === seg.lines.length - 1 && l.startsWith('(') ? C.red : C.fg, 'center');
    });
    g.globalAlpha = 1;
  },
  title(seg, t, f) {
    const lt = t - seg.start; R(0, 0, W, H, C.bg);
    const melt = clamp((lt - 4.3) / 3), j = melt > 0 ? (hash(f, 1) - .5) * 5 * melt : 0;
    if (lt > 0.6) { g.save(); g.font = F(36); try { g.letterSpacing = '6px'; } catch (e) {} txt('MONASH UNIVERSITY', W / 2 + 3, 58, 36, C.fg, 'center'); g.restore(); R(140, 100, W - 280, 1, C.dim); }
    if (lt > 1.0) txt('OFFICE OF ACADEMIC CONTINUITY', W / 2, 108, 22, C.dim, 'center');
    if (lt > 1.4) txt('STUDENT TRAINING TAPE 04-N', W / 2, 136, 18, C.dim, 'center');
    const col = melt > 0.7 && hash(f >> 1, 8) < 0.25 ? C.red : C.amb;
    if (lt > 1.8) txt("SO YOU'VE", W / 2 + j, 184, 80, col, 'center');
    if (lt > 2.2) txt('FAILED A UNIT', W / 2 - j, 250, 80, col, 'center');
    if (lt > 3.1) txt('A guide for students who have received an N grade', W / 2, 348, 20, C.fg, 'center');
    if (lt > 5.6 && hash(f >> 1, 4) > 0.2) txt('DO NOT REWIND THIS TAPE.', W / 2, 400, 24, C.red, 'center');
  },
  intro(seg, t, f) {
    R(0, 0, W, H, C.bg); header('INTRODUCTION');
    const st = state(seg, t, f);
    txt('WELCOME', 24, 62, 44, C.amb);
    sentences(seg, t, 24, 116, 306, 22, f);
    figure(seg, st, 'A');
  },
  rule(seg, t, f) {
    const lt = t - seg.start, my = seg.group === 'M';
    const of = T.segments.filter(x => x.type === 'rule' && x.group === seg.group).length;
    const num = my ? 'M' + seg.num : String(seg.num).padStart(2, '0');
    if (lt < 1.0) {
      R(0, 0, W, H, '#000');
      txt('RULE ' + num, W / 2, 150, 120, C.amb, 'center');
      txt(seg.title, W / 2, 280, 34, C.fg, 'center');
      if (my) txt('MALAYSIA CAMPUS ONLY', W / 2, 330, 22, C.dim, 'center');
      return;
    }
    R(0, 0, W, H, my ? MYBG : C.bg); header(my ? 'MALAYSIA CAMPUS  ' + num + ' OF M' + of : 'RULE ' + num + ' OF ' + of);
    const st = state(seg, t, f);
    txt('RULE ' + num, 24, 60, 44, st.tw > 0 ? C.red : C.amb);
    txt(seg.title, 160, 76, 22, C.dim);
    sentences(seg, t, 24, 116, 306, 22, f);
    figure(seg, st, num);
  },
  section(seg, t, f) {          // a different tape, spliced in
    R(0, 0, W, H, MYBG);
    const st = state(seg, t, f);
    header('SUPPLEMENT');
    txt(seg.title, 24, 62, 44, st.tw > 0 ? C.red : C.amb);
    txt(seg.sub, 24, 108, 18, C.dim);
    sentences(seg, t, 60, 156, 520, 26, f);
  },
  outro(seg, t, f) {
    R(0, 0, W, H, C.bg);
    const st = state(seg, t, f);
    if (st.tw > 0) {
      g.globalAlpha = 0.16 * ease(st.tw / 4);
      const off = (st.tw * 14) % 22;
      for (let r = -1; r < 24; r++) txt('AND AGAIN.  '.repeat(7), -((r * 37) % 90), r * 22 - off, 22, C.red);
      g.globalAlpha = 1;
    }
    header('CONCLUSION');
    txt('IN CLOSING', 24, 62, 44, st.tw > 0 ? C.red : C.amb);
    sentences(seg, t, 60, 128, 520, 26, f);
  },
  end(seg, t, f) {
    const lt = t - seg.start;
    R(0, 0, W, H, lt > 4.4 ? '#000' : C.bg);
    if (lt > 4.4) {
      g.globalAlpha = 0.25 + 0.5 * clamp((lt - 4.4) / 2);
      for (let r = 0; r < 16; r++) for (let c = 0; c < 16; c++)
        if (hash(r * 16 + c, f >> 1) < clamp((lt - 4.4) / 1.6)) txt('49', 10 + c * 40, 4 + r * 30, 30, C.red);
      g.globalAlpha = 1;
    }
    const msg = lt < 2.6 ? ['SEE YOU', 'NEXT SEMESTER.'] : lt < 4.4 ? ['SEE YOU', 'EVERY SEMESTER.'] : ['YOU ARE', 'STILL LEARNING.'];
    const col = lt < 2.6 ? C.amb : lt < 4.4 ? C.red : '#fff';
    if (lt > 4.4) R(60, 150, W - 120, 180, '#000');
    txt(msg[0], W / 2, 164, 72, col, 'center'); txt(msg[1], W / 2, 236, 72, col, 'center');
  },
  stop(seg, t) { R(0, 0, W, H, t - seg.start < 1.1 ? '#000' : '#1418b8'); },
};

function osd(seg, t, f) {
  if (seg.type === 'card' && seg.id === 'credits') return;
  if (seg.type === 'stop') {
    if (t - seg.start > 1.1) { txt('STOP', 30, 22, 28, '#fff'); R(92, 28, 16, 16, '#fff'); }
    return;
  }
  if (t < 4.2) { txt('PLAY', 30, 22, 28, '#fff'); g.fillStyle = '#fff'; g.beginPath(); g.moveTo(92, 26); g.lineTo(110, 36); g.lineTo(92, 46); g.fill(); }
  const sec = Math.floor(t), tc = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
  const cursed = seg.twistAt != null && t > seg.twistAt && hash(f >> 2, 6) < 0.3;
  g.globalAlpha = 0.75; txt('SP  0:' + (cursed ? '49:49' : String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0')), 24, 446, 22, cursed ? C.red : '#fff'); g.globalAlpha = 1;
}

/* ----------------------------------------------------------------- post --- */
const SCAN = [1.0, 0.93, 0.8];
const VW = OW >> 2, VIG = new Float32Array(VW * (OH >> 2));
for (let y = 0; y < OH >> 2; y++) for (let x = 0; x < VW; x++) {
  const dx = (x / VW - .5) * 2, dy = (y / (OH >> 2) - .5) * 2;
  VIG[y * VW + x] = 1 - 0.34 * Math.pow(dx * dx * 0.8 + dy * dy * 0.9, 1.4);
}
function post(t, f, P) {
  o.imageSmoothingEnabled = true; o.imageSmoothingQuality = 'low';
  o.drawImage(scene, 0, 0, OW, OH);
  const src = o.getImageData(0, 0, OW, OH), s = src.data, dst = o.createImageData(OW, OH), d = dst.data;
  let seed = ((f + 1) * 2654435761) >>> 0, n = 0;
  const noise = 13 + P.gI * 42 + P.tint * 7, flick = 0.97 + 0.03 * hash(f, 21);
  const bandY = OH - ((t * 41) % (OH + 420)), bandH = 18 + 30 * hash(f >> 3, 7);
  const tr = 1 + 0.07 * P.tint, tg = 1 - 0.07 * P.tint, cs = 2 + ((P.gI * 9) | 0);
  for (let y = 0; y < OH; y++) {
    let off = Math.sin(y * 0.013 + t * 2.1) * 0.9, extra = 0;
    if (P.gI > 0) {
      const band = (y / bandH) | 0;
      if (hash(f * 31 + band, 3) < P.gI * 0.6) off += (hash(f * 17 + band, 5) - 0.5) * 150 * P.gI;
    }
    const db = y - bandY;
    if (db >= 0 && db < 24) { off += Math.sin(db * 0.5 + f) * 7; extra = 46; }
    if (y > OH - 15) { off += (hash(f, y) - 0.3) * 46 + (y - OH + 15) * 2.5; extra = 60; }
    off |= 0;
    const m0 = SCAN[y % 3] * flick, row = y * OW * 4, vrow = (y >> 2) * VW, na = noise + extra;
    for (let x = 0; x < OW; x++) {
      let sx = x + off; if (sx < 0) sx = 0; else if (sx >= OW) sx = OW - 1;
      const xr = sx + cs >= OW ? OW - 1 : sx + cs, xb = sx - cs < 0 ? 0 : sx - cs;
      if (!(x & 1)) { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; n = ((seed >>> 24) - 128) / 128; }
      let r = s[row + xr * 4], gg = s[row + sx * 4 + 1], b = s[row + xb * 4 + 2];
      if (P.stat > 0) { const sv = (n * 0.5 + 0.5) * 215; r = gg = b = sv; }
      const m = m0 * VIG[vrow + (x >> 2)], nn = n * na + 9, i = row + x * 4;
      d[i] = (r * 0.95 + nn) * m * tr; d[i + 1] = (gg * 0.95 + nn) * m * tg; d[i + 2] = (b * 0.95 + nn) * m * tg; d[i + 3] = 255;
    }
  }
  o.putImageData(dst, 0, 0);
}

/* --------------------------------------------------------------- driver --- */
function renderFrame(f) {
  const t = Math.min(f / T.fps, T.duration - 1e-3);
  const seg = T.segments.find(s => t >= s.start && t < s.end) || T.segments[T.segments.length - 1];
  let gI = 0, flash = null;
  for (const e of T.events) {
    if (t < e.t || t >= e.t + e.dur) continue;
    if (e.kind === 'glitch') gI = Math.max(gI, e.strength * (1 - (t - e.t) / e.dur));
    if (e.kind === 'flash') flash = e;
  }
  g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1;
  if (flash) {
    R(0, 0, W, H, '#000');
    const lines = wrap(flash.text, 96, W - 60), y0 = (H - lines.length * 88) / 2;
    lines.forEach((l, i) => txt(l, W / 2, y0 + i * 88, 96, C.red, 'center'));
    gI = Math.max(gI, 0.7);
  } else {
    SCENE[seg.type](seg, t, f);
    osd(seg, t, f);
  }
  const lt = t - seg.start;
  const stat = (seg.type === 'boot' && lt < 1.2) || (seg.type === 'stop' && lt < 1.1) ? 1 : 0;
  const tint = seg.twistAt != null && t > seg.twistAt ? ease((t - seg.twistAt) / 3) : seg.type === 'end' ? 1 : 0;
  post(t, f, { gI, stat, tint });
}
window.renderFrame = renderFrame;
window.frameJPEG = (f, q) => { renderFrame(f); return out.toDataURL('image/jpeg', q).slice(23); };
window.ready = document.fonts.load('20px VT').then(() => true);
if (!location.search.includes('render')) window.ready.then(() => {   // silent live preview
  const t0 = performance.now();
  const tick = () => { renderFrame(Math.floor(((performance.now() - t0) / 1000) % T.duration * T.fps)); requestAnimationFrame(tick); };
  tick();
});
})();
