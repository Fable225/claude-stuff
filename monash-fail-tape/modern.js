/* Modern version: a clean "compulsory online module" that slips into dark mode
   whenever a rule turns. Pure function of the frame number, like tape.js.
   Laid out on a 960x540 grid and drawn at 2x (1920x1080). */
(() => {
const T = window.TIMELINE, S = 2, W = 960, H = 540;
const out = document.getElementById('out'), g = out.getContext('2d');
const tmp = document.createElement('canvas'); tmp.width = W * S; tmp.height = H * S;
const tg = tmp.getContext('2d');
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = x => { x = clamp(x); return x * x * (3 - 2 * x); };
const lerp = (a, b, k) => a + (b - a) * k;
function hash(a, b = 0) {
  let n = (Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263)) | 0;
  n = Math.imul(n ^ (n >>> 13), 1274126177); n ^= n >>> 16;
  return (n >>> 0) / 4294967296;
}
const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const mix = (a, b, k) => { const A = hex(a), B = hex(b); return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * k)).join(',')})`; };
const palette = k => ({
  k, bg: mix('#f3f5f9', '#07080c', k), card: mix('#ffffff', '#12141c', k), text: mix('#0d1b2e', '#ececf1', k),
  muted: mix('#5d6b80', '#8b90a0', k), accent: mix('#1560d8', '#ff2f2f', k), line: mix('#dde3ec', '#272b38', k),
  soft: mix('#e9f0fc', '#2a1114', k), ok: mix('#12805c', '#ff2f2f', k), page: mix('#ffffff', '#e6e2d8', k),
});
let P = palette(0);

function t(s, x, y, size, weight, col, align = 'left', ls = 0, italic = false) {
  g.font = `${italic ? 'italic ' : ''}${weight} ${size}px Inter, sans-serif`;
  g.letterSpacing = ls + 'px'; g.fillStyle = col; g.textAlign = align; g.textBaseline = 'top';
  g.fillText(s, x, y);
}
function tw_(s, size, weight, ls = 0) { g.font = `${weight} ${size}px Inter, sans-serif`; g.letterSpacing = ls + 'px'; return g.measureText(s).width; }
function rr(x, y, w, h, r, fill, stroke, lw = 1) {
  g.beginPath(); g.roundRect(x, y, w, h, r);
  if (fill) { g.fillStyle = fill; g.fill(); }
  if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw; g.stroke(); }
}
const disc = (x, y, r, col) => { g.fillStyle = col; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); };
const label = (s, x, y, col) => t(s, x, y, 10, 700, col || P.muted, 'left', 1.2);
function pill(x, y, s, bg, fg, size = 11, align = 'left') {
  const w = tw_(s, size, 700) + 18, h = size + 11, x0 = align === 'right' ? x - w : x;
  rr(x0, y, w, h, h / 2, bg); t(s, x0 + 9, y + 5, size, 700, fg);
  return w;
}
const wrapCache = new Map();
function wrap(s, size, weight, maxW) {
  const key = size + '|' + weight + '|' + maxW + '|' + s;
  if (wrapCache.has(key)) return wrapCache.get(key);
  const lines = []; let line = '';
  for (const w of s.split(' ')) {
    const tr = line ? line + ' ' + w : w;
    if (tw_(tr, size, weight) > maxW && line) { lines.push(line); line = w; } else line = tr;
  }
  if (line) lines.push(line);
  wrapCache.set(key, lines); return lines;
}

/* An original parody crest: blank book, a 49, and a wall built of repeat fees. */
function crest(cx, top, s, pal, motto) {
  g.save(); g.translate(cx - 50 * s, top); g.scale(s, s);
  const sh = new Path2D('M0 0H100V56C100 86 76 103 50 113C24 103 0 86 0 56Z');
  g.fillStyle = pal.text; g.fill(sh);
  g.save(); g.clip(sh);
  g.fillStyle = pal.card; g.globalAlpha *= 0.92;
  for (let r = 0; r < 4; r++) for (let c = -1; c < 8; c++) g.fillRect(c * 15 + (r % 2 ? 7 : 0), 85 + r * 8, 13, 6);
  g.restore();
  g.save(); g.translate(6, 5.5); g.scale(0.88, 0.88); g.strokeStyle = pal.card; g.lineWidth = 1.4; g.stroke(sh); g.restore();
  g.fillStyle = pal.card;
  g.beginPath(); g.moveTo(25, 14); g.lineTo(48, 19); g.lineTo(48, 37); g.lineTo(25, 32); g.closePath(); g.fill();
  g.beginPath(); g.moveTo(75, 14); g.lineTo(52, 19); g.lineTo(52, 37); g.lineTo(75, 32); g.closePath(); g.fill();
  t('49', 50, 42, 37, 800, pal.k > 0.5 ? pal.accent : pal.card, 'center');
  if (motto) { rr(-14, 121, 128, 19, 4, pal.accent); t(motto, 50, 126, 9, 700, '#fff', 'center', 1.6); }
  g.restore();
}

/* ------------------------------------------------------------ figures ---
   Drawn into a 372x384 card. st = { t, s, sp, tw, f, since(i) }. */
const FW = 372, FH = 384;
const FIG = {
  results(st) {
    label('RESULTS · SEMESTER 2', 22, 22); t('Academic record', 22, 38, 20, 700, P.text);
    const marks = ['71', '64', '49', '58', '75'], grades = ['D', 'C', 'N', 'P', 'D'];
    for (let i = 0; i < 5; i++) {
      const y = 86 + i * 50, turned = st.tw > 0 && st.tw * 3 > ((i * 3 + 2) % 5) + 0.4, bad = i === 2 || turned;
      if (i === 2 && st.s >= 2 || turned) rr(12, y - 6, FW - 24, 44, 10, P.soft);
      rr(22, y + 3, 120 + hash(i, 9) * 50, 11, 5, P.line); rr(22, y + 21, 64, 7, 3, P.line);
      t(bad ? '49' : marks[i], 268, y + 4, 20, 700, bad ? P.accent : P.text, 'right');
      pill(300, y + 5, bad ? 'N' : grades[i], bad ? P.accent : P.line, bad ? '#fff' : P.text, 12);
    }
    t(st.tw > 0 ? 'Status: as intended' : 'Status: released', 22, 346, 13, 600, st.tw > 0 ? P.accent : P.muted);
  },
  notif(st) {
    const late = st.s >= 1, px = 96, py = 22, pw = 180, ph = 340;
    rr(px, py, pw, ph, 28, mix('#1c2c4c', '#000000', P.k), P.line, 2);
    rr(px + 62, py + 10, 56, 12, 6, '#000');
    t(late ? 'Results day · not yet' : 'Results day', px + pw / 2, py + 38, 10, 500, 'rgba(255,255,255,.7)', 'center');
    t(late ? '3:49' : '9:00', px + pw / 2, py + 52, 50, 300, '#fff', 'center');
    const a = late ? ease(st.since(1) / 0.4) : ease(st.t / 0.5), y = py + 136 - (1 - a) * 10, on = st.tw > 0.5;
    g.globalAlpha *= a;
    rr(px + 10, y, pw - 20, 74, 14, 'rgba(255,255,255,.95)', on ? '#ff2f2f' : null, 2);
    t('STUDENT PORTAL', px + 22, y + 11, 8, 700, '#6a7385', 'left', 0.8);
    t(late ? '3:49 am' : '9:00 am', px + pw - 22, y + 11, 8, 600, '#6a7385', 'right');
    t(on ? 'From: You' : late ? 'Your result is ready' : 'Results are available', px + 22, y + 28, 12, 700, on ? '#d01a1a' : '#111');
    t(on ? 'Sent: tomorrow' : 'Tap to view.', px + 22, y + 48, 10, 500, on ? '#d01a1a' : '#444');
    if (late && !on) disc(px + pw - 26, y + 52, 3 + Math.sin(st.t * 6), '#1560d8');
    if (st.tw > 3) {
      g.globalAlpha *= ease((st.tw - 3) / 0.4);
      rr(px + 10, y + 84, pw - 20, 50, 14, 'rgba(255,255,255,.95)');
      t('Opened', px + 22, y + 94, 12, 700, '#d01a1a'); t('It has been opened.', px + 22, y + 112, 10, 500, '#d01a1a');
    }
    g.globalAlpha = st.alpha;
    rr(px + 60, py + ph - 14, 60, 4, 2, 'rgba(255,255,255,.6)');
  },
  mark(st) {
    label(st.s >= 1 ? "EVERYONE'S FINAL MARK" : 'YOUR FINAL MARK', 22, 22);
    const cx = 130, cy = 132, r = 70, k = ease(st.t / 1.2);
    g.lineWidth = 14; g.lineCap = 'round';
    g.strokeStyle = P.line; g.beginPath(); g.arc(cx, cy, r, 0, 7); g.stroke();
    g.strokeStyle = P.accent; g.beginPath(); g.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * 0.49 * k); g.stroke();
    g.lineCap = 'butt';
    t(String(Math.round(49 * k)), cx, cy - 34, 54, 800, P.text, 'center'); t('out of 100', cx, cy + 26, 11, 500, P.muted, 'center');
    t('Pass mark', 236, 96, 11, 500, P.muted); t('50', 236, 110, 30, 800, P.text);
    t(st.s >= 1 ? 'It is always 49.' : 'So close.', 236, 150, 11, 600, st.s >= 1 ? P.accent : P.muted);
    label('ALL STUDENTS', 22, 236);
    const base = 344, x0 = 40, bw = 15;
    for (let m = 40; m < 59; m++) {
      const h = m < 49 ? 6 + hash(m, 4) * 26 : m === 49 ? 76 * k : 0;
      if (h) rr(x0 + (m - 40) * bw, base - h, bw - 4, h, 3, m === 49 ? P.accent : P.line);
    }
    g.fillStyle = P.line; g.fillRect(22, base, FW - 44, 1.5);
    const px = x0 + 10 * bw - 2;
    g.fillStyle = P.muted; for (let y = 262; y < base; y += 7) g.fillRect(px, y, 1.5, 4);
    t('40', x0, base + 6, 10, 600, P.muted); t('49', x0 + 9 * bw + 5, base + 6, 10, 700, P.accent, 'center'); t('50', px + 4, base + 6, 10, 600, P.muted);
    if (st.tw > 0) {                         // the other mark leaves
      const q = ease(st.tw / 3), x = lerp(px + 2, 268, q), y = lerp(base - 86, 246 - Math.sin(q * Math.PI) * 30, q);
      if (st.s >= 3) pill(246, 262, 'Capital works', P.accent, '#fff', 11);
      rr(x, y, 26, 18, 9, P.text); t('+1', x + 13, y + 3, 11, 800, P.card, 'center');
    }
  },
  paper(st) {
    rr(0, 0, FW, 40, 0, P.soft);
    t('exam_script.pdf', 22, 13, 12, 600, P.text); t('Page 1 of 49', FW - 22, 14, 11, 500, P.muted, 'right');
    g.save(); g.shadowColor = 'rgba(0,0,0,.18)'; g.shadowBlur = 16 * S; g.shadowOffsetY = 4 * S; rr(46, 56, 280, 350, 3, P.page); g.restore();
    t('Final examination', 64, 72, 11, 700, '#222'); t('49 / 100', 308, 72, 11, 700, '#c4161c', 'right');
    for (let i = 0; i < 12; i++) {
      const y = 112 + i * 22, gone = st.tw > 0 && st.tw * 2.4 > ((i * 7) % 12);
      g.fillStyle = '#e3e3e0'; g.fillRect(64, y + 6, 244, 1);
      if (gone) {
        const words = ['stay', 'stay enrolled', 'stay stay', 'enrol again', 'stay'];
        t(Array(words[i % 5].length > 6 ? 1 + (i % 2) : 1 + (i % 3)).fill(words[i % 5]).join('  '), 64 + (hash(i, st.f >> 2) - 0.5) * 1.6, y - 11, 15, 600, '#c4161c', 'left', 0, true);
      } else {
        g.strokeStyle = '#2740a8'; g.lineWidth = 1.3; g.beginPath();
        const len = 120 + hash(i, 1) * 120;
        for (let x = 0; x < len; x += 3) g.lineTo(64 + x, y + Math.sin(x * 0.8 + i) * 2.4 + (hash(i * 97 + x, 3) - 0.5) * 4);
        g.stroke();
      }
    }
    if (st.s >= 1 && st.tw < 0) { const w = tw_('Is this your handwriting?', 11, 700) + 18; pill((FW - w) / 2, 340, 'Is this your handwriting?', P.text, P.card); }
  },
  queue(st) {
    label('SERVICE COUNTER', 22, 22); t('Now serving', 22, 38, 20, 700, P.text);
    const on = st.tw > 0, blink = on && (st.f >> 3) % 2;
    rr(22, 78, FW - 44, 92, 14, on ? P.accent : P.soft, on && blink ? '#fff' : null, 2);
    const fg = on ? '#fff' : P.text;
    t(on ? 'A049' : st.s >= 1 ? 'A048' : 'A047', 40, 98, 46, 800, fg);
    t('→', 196, 108, 28, 500, fg, 'center'); t(on ? 'Window 2' : 'Window 1', FW - 40, 110, 24, 700, fg, 'right');
    rr(22, 184, FW - 44, 72, 14, P.card, P.line);
    label('YOUR TICKET', 38, 198); t('A049', 38, 214, 28, 800, P.text);
    t('Position', FW - 38, 198, 10, 600, P.muted, 'right');
    t(on ? 'Now' : st.s >= 1 ? '2nd' : '3rd', FW - 38, 214, 28, 800, on ? P.accent : P.text, 'right');
    label('WAITING', 22, 276);
    let x = 22; ['A050', 'A051', 'A052', 'A053'].forEach(s => { x += pill(x, 294, s, P.line, P.text, 12) + 8; });
    t('Windows open: 1', 22, 344, 13, 600, on ? P.accent : P.muted);
    if (st.s >= 3 && st.sp > 0.6) t('Please proceed.', FW - 22, 344, 13, 700, P.accent, 'right');
  },
  lift(st) {
    label('MENZIES BUILDING · LIFT 3', 22, 22); t('Select your floor', 22, 38, 20, 700, P.text);
    const fl = Math.floor(st.t * 0.9) % 12, on = st.tw > 0, pressed = st.s >= 3 && st.sp > 0.9;
    [[8, 9, 10, 11], [4, 5, 6, 7], [0, 1, 2, 3]].forEach((row, r) => row.forEach((n, c) => {
      const x = 27 + c * 82, y = 84 + r * 62, lit = !on && n === fl;
      rr(x, y, 72, 52, 12, lit ? P.accent : P.card, lit ? null : P.line, 1.5);
      t(n === 0 ? 'G' : String(n), x + 36, y + 13, 22, 700, lit ? '#fff' : P.text, 'center');
    }));
    if (on) {
      const a = ease(st.tw / 1.0), pulse = 0.5 + 0.5 * Math.sin(st.t * 7);
      g.globalAlpha *= a;
      rr(150 - pulse * 4, 270 - pulse * 4, 72 + pulse * 8, 52 + pulse * 8, 16, 'rgba(255,47,47,.25)');
      rr(150, 270, 72, 52, 12, pressed ? '#ff2f2f' : P.card, '#ff2f2f', 2);
      t('12', 186, 283, 22, 800, pressed ? '#fff' : '#ff2f2f', 'center');
      g.globalAlpha = st.alpha;
    }
    t(pressed ? 'Going up.' : on ? 'Floors: G to 11' : 'Floors: G to 11', 22, 346, 13, pressed ? 700 : 600, pressed ? P.accent : P.muted);
    if (on) t(pressed ? 'Selected for you' : 'New', FW - 22, 346, 13, 700, P.accent, 'right');
  },
  invig(st) {
    label('EXAM ROOM · LIVE', 22, 22); t('Invigilators', 22, 38, 20, 700, P.text);
    const four = st.tw > 0.2;
    pill(FW - 22, 38, four ? '4' : '3', four ? P.accent : P.text, four ? '#fff' : P.card, 14, 'right');
    rr(22, 80, FW - 44, 282, 12, P.soft, P.line);
    t('Door', 328, 86, 9, 600, P.muted, 'right');
    for (let r = 0; r < 6; r++) for (let c = 0; c < 7; c++) {
      const you = r === 3 && c === 3, x = 60 + c * 38, y = 120 + r * 38;
      rr(x, y, 16, 16, 4, you ? P.accent : P.card, you ? null : P.line);
      if (you) t('You', x + 8, y + 19, 9, 700, P.accent, 'center');
    }
    const pt = st.tw > 0 ? st.t - st.tw : st.t;          // the three stop walking when it arrives
    [125, 201, 277].forEach((x, i) => {
      const y = 222 + 96 * Math.sin(pt * 0.55 + i * 2.1), pr = (st.t * 0.8 + i * 0.3) % 1;
      if (st.tw <= 0) { g.strokeStyle = P.text; g.globalAlpha *= 0.35 * (1 - pr); g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 7 + pr * 9, 0, 7); g.stroke(); g.globalAlpha = st.alpha; }
      disc(x, y, 7, P.text);
    });
    if (st.tw > 0) {
      const q = ease((st.tw - 1) / 5.5), x = lerp(338, 204, q), y = lerp(96, 248, q);
      g.globalAlpha *= ease(st.tw / 0.6);
      for (let i = 0; i < 3; i++) { const pr = (st.t * 0.9 + i / 3) % 1; g.strokeStyle = '#ff2f2f'; g.globalAlpha = st.alpha * 0.6 * (1 - pr); g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 9 + pr * 22, 0, 7); g.stroke(); }
      g.globalAlpha = st.alpha;
      disc(x, y, 9, '#ff2f2f'); disc(x, y, 4.5, '#000');
    }
  },
  repeat(st) {
    label('WES · ENROLMENT', 22, 22); t('Attempt history', 22, 38, 20, 700, P.text);
    const n = st.tw > 0 ? 1 + (st.t - st.tw) * 0.75 + st.tw * 1.2 + Math.pow(st.tw, 3.4) * 4 : 1 + st.t * 0.75;
    const last = Math.floor(n);
    g.save(); g.beginPath(); g.rect(0, 98, FW, 218); g.clip();
    for (let i = Math.max(1, last - 9); i <= last; i++) {
      const y = 284 - (n - i) * 30;
      if (i % 2) rr(14, y - 6, FW - 28, 30, 6, P.soft);
      t('#' + i.toLocaleString('en-AU'), 28, y, 14, 600, P.text); t('49', 160, y, 14, 600, P.text);
      t('N', 222, y, 14, 700, P.accent); pill(FW - 28, y - 3, 'Paid', P.ok, '#fff', 11, 'right');
    }
    g.restore();
    ['ATTEMPT', 'MARK', 'GRADE'].forEach((s, i) => label(s, [28, 160, 222][i], 78)); t('FEE', FW - 28, 78, 10, 700, P.muted, 'right', 1.2);
    g.fillStyle = P.line; g.fillRect(22, 96, FW - 44, 1.5);
    rr(22, 324, FW - 44, 42, 10, P.soft);
    t('Attempts so far', 36, 337, 13, 600, P.text); t(last.toLocaleString('en-AU'), FW - 36, 333, 20, 800, P.accent, 'right');
  },
  pay(st) {
    label('CHECKOUT · SUPPLEMENTARY FEE', 22, 22); t('How would you like to pay?', 22, 38, 19, 700, P.text);
    const opts = [['Card', 'Surcharge applies'], ['EFTPOS', ''], ['BPAY', ''], ['PayID', '']];
    const chosen = st.tw > 2.2, approved = st.s >= 3 && st.sp > 1.3;
    const row = (i, name, note, a, o = {}) => {
      const y = 76 + i * 36;
      g.globalAlpha = st.alpha * a;
      rr(22, y, FW - 44, 30, 9, o.red ? P.soft : P.card, o.red ? '#ff2f2f' : P.line, o.red ? 1.5 : 1);
      g.strokeStyle = o.red ? '#ff2f2f' : P.muted; g.lineWidth = 1.5; g.beginPath(); g.arc(40, y + 15, 6, 0, 7); g.stroke();
      if (o.sel) disc(40, y + 15, 3.2, '#ff2f2f');
      const col = o.off ? P.muted : o.red ? '#ff2f2f' : P.text;
      t(name, 56, y + 8, 13, 600, col);
      if (o.off) { g.fillStyle = P.muted; g.fillRect(54, y + 15, tw_(name, 13, 600) + 4, 1.5); }
      t(note, FW - 34, y + 9, 11, 500, o.red ? '#ff2f2f' : P.muted, 'right');
      g.globalAlpha = st.alpha;
    };
    opts.forEach(([n, note], i) => row(i, n, note, ease((st.since(0) - i * 0.5) / 0.3)));
    if (st.s >= 1) row(4, 'Cash', 'Not accepted', ease(st.since(1) / 0.3), { off: true });
    if (st.tw > 0) row(5, 'Something of yours', 'Recommended', ease(st.tw / 0.9), { red: true, sel: chosen });
    if (!approved) {
      rr(22, 310, 226, 44, 12, P.accent); t(chosen ? 'Paying…' : 'Pay now', 135, 324, 14, 700, '#fff', 'center');
      g.globalAlpha = st.alpha * (st.tw > 1.2 ? 0.35 : 1);
      rr(258, 310, FW - 280, 44, 12, null, P.line, 1.5); t('Cancel', 258 + (FW - 280) / 2, 324, 14, 600, P.text, 'center');
      g.globalAlpha = st.alpha;
    } else {
      rr(22, 298, FW - 44, 70, 12, '#ff2f2f');
      t('Approved', 38, 308, 18, 800, '#fff'); t('Receipt no. 49', FW - 38, 312, 11, 600, 'rgba(255,255,255,.8)', 'right');
      t('Paid with:', 38, 340, 12, 600, '#fff'); rr(104, 338, 150, 16, 3, '#000');
    }
  },
  building(st) {
    if (st.tw <= 0.25) {
      label('CAMPUS DEVELOPMENT', 22, 22); t('New building', 22, 38, 20, 700, P.text);
      if (st.s >= 1) pill(FW - 22, 40, 'Opened overnight', P.accent, '#fff', 11, 'right');
      rr(22, 78, FW - 44, 164, 12, P.soft);
      const cols = 16, total = cols * 16, count = st.s >= 1 ? total : Math.min(total, Math.floor(st.t * 44));
      for (let i = 0; i < count; i++) {
        const r = Math.floor(i / cols), c = i % cols;
        g.globalAlpha = st.alpha * (0.45 + 0.5 * hash(i, 5));
        rr(66 + c * 15, 230 - (r + 1) * 9, 13.5, 7.5, 1.5, P.accent);
      }
      g.globalAlpha = st.alpha;
      g.fillStyle = P.muted; g.fillRect(40, 230, FW - 80, 1.5);
      t('Funded', 22, 258, 12, 600, P.muted); t(Math.round(count / total * 100) + '%', FW - 22, 256, 14, 800, P.text, 'right');
      rr(22, 280, FW - 44, 10, 5, P.line); rr(22, 280, Math.max(10, (FW - 44) * count / total), 10, 5, P.accent);
      t('Source: repeat enrolments', 22, 304, 12, 500, P.muted); t('One brick per attempt', 22, 324, 12, 500, P.muted);
    } else {
      label('DONOR WALL', 22, 22); t('With thanks to', 22, 38, 20, 700, P.text);
      const count = Math.floor(st.tw * 7), cap = 22;
      for (let i = 0; i < Math.min(count, cap); i++) {
        const c = i % 2, r = (i - c) / 2, x = 22 + c * 168, y = 80 + r * 23, newest = i === Math.min(count, cap) - 1;
        const hot = newest || (count > cap && hash(i, st.f >> 2) < 0.18);
        disc(x + 8, y + 8, 7, hot ? P.accent : P.line); t('Your name', x + 24, y, 13, 600, hot ? P.accent : P.text);
      }
      if (st.s >= 3) t('× ' + Math.max(49, count), FW - 22, 344, 20, 800, P.accent, 'right');
      t('Platinum tier', 22, 348, 12, 600, P.muted);
    }
  },
  bus(st) {
    label('CLAYTON · BUS LOOP', 22, 22); t('Departures', 22, 38, 20, 700, P.text);
    const on = st.tw > 0, shift = on ? ease(st.tw / 0.5) * 60 : 0;
    const rows = [['601', 'Huntingdale Station', '2 min'], ['900', 'Caulfield', '6 min'], ['601', 'Huntingdale Station', '9 min']];
    rows.forEach(([rt, dest, m], i) => {
      const y = 82 + i * 60 + shift;
      g.globalAlpha = st.alpha * (on ? 0.45 : 1);
      rr(22, y, FW - 44, 50, 12, P.card, P.line);
      rr(34, y + 11, 54, 28, 8, P.text); t(rt, 61, y + 17, 14, 800, P.card, 'center');
      t(dest, 100, y + 9, 14, 600, P.text); t('On time', 100, y + 28, 11, 500, P.muted);
      t(on ? '—' : m, FW - 36, y + 15, 16, 700, P.text, 'right');
      g.globalAlpha = st.alpha;
    });
    if (on) {
      g.globalAlpha = st.alpha * ease(st.tw / 0.5);
      rr(22, 82, FW - 44, 50, 12, P.soft, '#ff2f2f', 2);
      rr(34, 93, 54, 28, 8, '#ff2f2f'); t('49', 61, 99, 14, 800, '#fff', 'center');
      t(st.tw > 1.6 ? 'Not a bus' : '—', 100, 91, 14, 700, '#ff2f2f'); t(st.s >= 2 ? 'Waiting for you' : 'Arriving', 100, 110, 11, 600, '#ff2f2f');
      t('Now', FW - 36, 97, 16, 800, '#ff2f2f', 'right');
      g.globalAlpha = st.alpha;
    }
    if (st.s >= 2 && st.sp > 0.3) { rr(22, 326, FW - 44, 40, 10, '#ff2f2f'); t('Do not touch on.', FW / 2, 338, 14, 700, '#fff', 'center'); }
  },
  mate(st) {
    const staff = st.s >= 3 && st.sp > 0.2, k = st.tw > 0 ? ease(st.tw / 2.4) : 0;
    disc(42, 42, 19, staff ? '#ff2f2f' : P.line);
    g.globalAlpha = st.alpha * (1 - k);
    disc(35, 38, 2.2, P.text); disc(49, 38, 2.2, P.text);
    g.strokeStyle = P.text; g.lineWidth = 1.8; g.beginPath(); g.arc(42, 43, 8, 0.35, 2.8); g.stroke();
    g.globalAlpha = st.alpha;
    t(staff ? 'Staff' : 'Jono', 72, 26, 15, 700, staff ? P.accent : P.text);
    t(staff ? 'Always online' : 'Online', 72, 46, 11, 500, staff ? P.accent : P.muted);
    g.fillStyle = P.line; g.fillRect(0, 72, FW, 1.5);
    const bubble = (y, s, mine, since, red) => {
      if (since < 0) return;
      const a = ease(since / 0.25), w = tw_(s, 13, 500) + 26, x = mine ? FW - 22 - w : 22;
      g.globalAlpha = st.alpha * a;
      rr(x, y + (1 - a) * 8, w, 34, 16, mine ? P.accent : red ? '#ff2f2f' : P.soft);
      t(s, x + 13, y + 10 + (1 - a) * 8, 13, 500, mine || red ? '#fff' : P.text);
      g.globalAlpha = st.alpha;
    };
    bubble(90, 'passed that unit btw', false, st.since(0) - 0.6);
    bubble(134, 'no way. who was your lecturer?', true, st.since(1) - 1.4);
    if (st.since(1) > 2.6 && st.tw < 0.8) {            // typing…
      rr(22, 178, 54, 34, 16, P.soft);
      for (let i = 0; i < 3; i++) disc(38 + i * 11, 195 - Math.max(0, Math.sin(st.t * 6 - i * 0.9)) * 3, 3, P.muted);
    }
    bubble(178, "can't remember their face", false, st.tw - 0.8);
    bubble(222, 'does it matter', false, st.tw - 2.8);
    bubble(266, 'See you next semester.', false, staff ? st.sp - 1.0 : -1, true);
    rr(22, 334, FW - 44, 34, 17, null, P.line, 1.5); t(staff ? 'You can no longer reply' : 'Message', 38, 344, 12, 500, P.muted);
  },
  motto(st) {
    const pago = st.s >= 5;
    crest(FW / 2, 44, 1.75, P, pago ? 'ANCORA PAGO' : 'ANCORA IMPARO');
    const n = st.s >= 3 ? 3 + Math.floor(st.since(3) * 1.6) : st.s >= 2 ? 3 : st.s >= 1 ? 2 : 1;
    t('Attempt ' + n, FW / 2, 318, 22, 800, st.tw > 0 ? P.accent : P.text, 'center');
    t(pago ? '"I am still paying"' : '"I am still learning"', FW / 2, 348, 12, 500, P.muted, 'center', 0, true);
  },
};

/* --------------------------------------------------------------- scenes --- */
const RULES = T.segments.filter(s => s.type === 'rule').length;
function chrome(seg, t0) {
  crest(43, 9, 0.3, P);
  t('MONASH UNIVERSITY', 68, 12, 13, 800, P.text, 'left', 1.4);
  t('Office of Academic Continuity', 68, 30, 10, 500, P.muted);
  t('Compulsory module · Unsatisfactory progress', 912, 12, 10, 500, P.muted, 'right');
  for (let i = 0; i < RULES; i++) {
    const n = i + 1, cur = seg.type === 'rule' ? seg.num : seg.type === 'outro' ? RULES + 1 : 0;
    disc(912 - (RULES - 1 - i) * 13 - 3, 35, 3, n < cur ? P.muted : n === cur ? P.accent : P.line);
  }
  g.fillStyle = P.line; g.fillRect(0, 52, W, 1);
  rr(48, 498, 864, 3, 1.5, P.line); rr(48, 498, Math.max(3, 864 * t0 / T.duration), 3, 1.5, P.accent);
  t('Skipping is disabled for this module', 48, 510, 10, 500, P.muted);
}
const watermark = () => t('Parody · not affiliated with Monash University', 912, 510, 10, 500, P.muted, 'right');

function captions(seg, t0, x, y, maxW) {
  let turned = false;
  for (let i = 0; i < seg.sentences.length; i++) {
    const s = seg.sentences[i];
    if (t0 < s.start) break;
    turned = turned || s.twist;
    const current = i === seg.sentences.length - 1 || t0 < seg.sentences[i + 1].start;
    const lines = wrap(s.text, 19, 500, maxW), nWords = s.text.split(' ').length;
    let budget = Math.ceil(nWords * clamp((t0 - s.start) / Math.max(0.3, (s.end - s.start) * 0.9)));
    const a = ease((t0 - s.start) / 0.25);
    g.globalAlpha *= a;
    for (let j = 0; j < lines.length && budget > 0; j++) {
      const words = lines[j].split(' ');
      t(words.slice(0, budget).join(' '), x, y + j * 27 + (1 - a) * 6, 19, current ? 600 : 500, current ? (turned ? P.accent : P.text) : P.muted);
      budget -= words.length;
    }
    g.globalAlpha /= a || 1;
    y += lines.length * 27 + 10;
  }
}
function state(seg, t0, f, alpha) {
  let s = -1;
  seg.sentences.forEach((x, i) => { if (t0 >= x.start) s = i; });
  return { t: t0 - seg.start, s, sp: s >= 0 ? t0 - seg.sentences[s].start : 0, tw: seg.twistAt != null ? t0 - seg.twistAt : -1, f, alpha,
           since: i => t0 - seg.sentences[i].start };
}
function lesson(seg, t0, f) {
  const lt = t0 - seg.start, a = ease(lt / 0.45) * ease((seg.end - t0) / 0.3), dy = (1 - ease(lt / 0.45)) * 14;
  chrome(seg, t0); watermark();
  g.save(); g.globalAlpha = a; g.translate(0, dy);
  const chip = seg.type === 'rule' ? `RULE ${seg.num} OF ${RULES}` : seg.type === 'intro' ? 'INTRODUCTION' : 'CONCLUSION';
  rr(48, 88, tw_(chip, 11, 700, 1.2) + 22, 24, 12, P.soft); t(chip, 59, 94, 11, 700, P.accent, 'left', 1.2);
  t(seg.title, 46, 120, 42, 800, P.text, 'left', -0.8);
  captions(seg, t0, 48, 190, 440);
  const FX = 540, FY = 84;
  g.save(); g.shadowColor = `rgba(10,20,40,${0.12 + 0.3 * P.k})`; g.shadowBlur = 30 * S; g.shadowOffsetY = 8 * S;
  rr(FX, FY, FW, FH, 18, P.card); g.restore();
  rr(FX, FY, FW, FH, 18, null, P.k > 0.5 ? P.accent : P.line, 1);
  g.save(); g.translate(FX, FY); g.beginPath(); g.roundRect(0, 0, FW, FH, 18); g.clip();
  FIG[seg.fig || 'motto'](state(seg, t0, f, a));
  g.restore(); g.restore();
}
const SCENE = {
  card(seg, t0) {
    const dark = seg.id === 'credits', y0 = (H - seg.lines.length * 28) / 2;
    seg.lines.forEach((l, i) => {
      g.globalAlpha = ease((t0 - seg.start - 0.3 - i * 0.1) / 0.5) * ease((seg.end - t0) / 0.5);
      t(l, W / 2, y0 + i * 28, 19, i === 0 && dark ? 800 : 500, l.startsWith('(') ? P.accent : P.text, 'center');
    });
    g.globalAlpha = 1; watermark();
  },
  title(seg, t0, f, attempt) {
    const lt = t0 - seg.start, show = (at, d = 0.5) => ease((lt - at) / d);
    let a = show(0.3, 0.7);
    g.globalAlpha = a; crest(W / 2, 62 - (1 - a) * 10, 1.25, P, attempt ? 'ANCORA PAGO' : 'ANCORA IMPARO');
    g.globalAlpha = show(0.9); t('MONASH UNIVERSITY', W / 2, 260, 20, 800, P.text, 'center', 4);
    g.globalAlpha = show(1.1); t('Office of Academic Continuity', W / 2, 288, 13, 500, P.muted, 'center');
    a = show(1.5); g.globalAlpha = a; t("So you've failed a unit", W / 2, 318 + (1 - a) * 10, 52, 800, P.text, 'center', -1.2);
    if (attempt) { g.globalAlpha = 1; t('Attempt ' + attempt, W / 2, 392, 26, 800, P.accent, 'center'); watermark(); return; }
    const chips = ['Compulsory module', '4 min', 'Cannot be skipped'], ws = chips.map(c => tw_(c, 11, 700) + 18);
    let x = (W - ws.reduce((p, c) => p + c, 0) - 16) / 2;
    chips.forEach((c, i) => { g.globalAlpha = show(2.4 + i * 0.25, 0.35); pill(x, 392, c, i === 2 ? P.accent : P.soft, i === 2 ? '#fff' : P.accent); x += ws[i] + 8; });
    const pressed = lt > 7.2;
    g.globalAlpha = show(3.3) * (pressed ? 0.8 : 1);
    rr(W / 2 - 62 + (pressed ? 2 : 0), 436 + (pressed ? 1 : 0), 124 - (pressed ? 4 : 0), 38 - (pressed ? 2 : 0), 19, P.accent);
    t(pressed ? 'Starting…' : 'Start', W / 2, 447, 14, 700, '#fff', 'center');
    g.globalAlpha = show(4.6) * (1 - show(7.2, 0.2));
    t('This module will start by itself in ' + Math.max(1, Math.ceil(7.2 - lt)) + '.', W / 2, 484, 11, 500, P.muted, 'center');
    g.globalAlpha = 1; watermark();
  },
  intro: lesson, rule: lesson, outro: lesson,
  end(seg, t0, f) {
    const lt = t0 - seg.start;
    if (lt >= 5.2) {                                    // it starts again, in the dark
      const q = clamp((lt - 5.2) / 3.0);
      SCENE.title({ start: seg.start - 10 }, t0, f, 2 + Math.floor(q * q * 47));
      return;
    }
    const a = ease(lt / 0.4), n = clamp(5 - Math.floor((lt - 1.2) / 0.8), 1, 5), frac = clamp(((lt - 1.2) % 0.8) / 0.8);
    g.globalAlpha = a;
    g.save(); g.shadowColor = 'rgba(10,20,40,.14)'; g.shadowBlur = 30 * S; g.shadowOffsetY = 8 * S; rr(250, 150, 460, 240, 20, P.card); g.restore();
    label('UP NEXT', 282, 180, P.accent);
    t("So you've failed a unit", 282, 198, 28, 800, P.text, 'left', -0.5);
    t('Attempt 2 · Compulsory module · 4 min', 282, 236, 12, 500, P.muted);
    g.lineWidth = 5; g.strokeStyle = P.line; g.beginPath(); g.arc(310, 316, 26, 0, 7); g.stroke();
    g.strokeStyle = P.accent; g.lineCap = 'round'; g.beginPath(); g.arc(310, 316, 26, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (lt < 1.2 ? 0 : frac)); g.stroke(); g.lineCap = 'butt';
    t(String(n), 310, 302, 24, 800, P.text, 'center');
    t('Starts in ' + n, 352, 300, 14, 600, P.text); t('Autoplay is on', 352, 320, 11, 500, P.muted);
    rr(500, 296, 92, 40, 12, P.accent); t('Play now', 546, 309, 13, 700, '#fff', 'center');
    g.globalAlpha = a * 0.4; rr(602, 296, 78, 40, 12, null, P.line, 1.5); t('Cancel', 641, 309, 13, 600, P.text, 'center');
    g.fillStyle = P.text; g.fillRect(618, 316, 46, 1.5);
    g.globalAlpha = a; t('Cancel is unavailable for compulsory modules', 680, 346, 10, 500, P.muted, 'right');
    g.globalAlpha = 1; watermark();
  },
};

/* --------------------------------------------------------------- driver --- */
function darkness(seg, t0) {
  if (seg.id === 'credits') return 1;
  if (seg.type === 'end') return t0 - seg.start >= 5.2 ? 1 : 0;
  if (seg.twistAt == null || t0 < seg.twistAt) return 0;
  return ease((t0 - seg.twistAt) / 0.45) * ease((seg.end - t0) / 0.35);
}
function renderFrame(f) {
  const t0 = Math.min(f / T.fps, T.duration - 1e-3);
  const seg = T.segments.find(s => t0 >= s.start && t0 < s.end) || T.segments[T.segments.length - 1];
  let gI = 0, note = null;
  for (const e of T.events) {
    if (t0 < e.t || t0 >= e.t + e.dur) continue;
    if (e.kind === 'glitch') gI = Math.max(gI, e.strength * (1 - (t0 - e.t) / e.dur));
    if (e.kind === 'notif') note = e;
  }
  P = palette(darkness(seg, t0));
  g.setTransform(S, 0, 0, S, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
  g.fillStyle = P.bg; g.fillRect(0, 0, W, H);
  SCENE[seg.type](seg, t0, f);
  g.globalAlpha = 1;
  if (P.k > 0.02) {                                     // the room gets smaller
    const v = g.createRadialGradient(W / 2, H / 2, H * 0.62, W / 2, H / 2, W * 0.72);
    v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, `rgba(0,0,0,${0.6 * P.k})`);
    g.fillStyle = v; g.fillRect(0, 0, W, H);
  }
  if (note) {
    const a = ease((t0 - note.t) / 0.35) * ease((note.t + note.dur - t0) / 0.35), D = palette(1);
    const w = Math.max(300, tw_(note.text, 14, 600) + 96), x = (W - w) / 2, y = -64 + a * 76;
    g.save(); g.shadowColor = 'rgba(0,0,0,.35)'; g.shadowBlur = 24 * S; g.shadowOffsetY = 6 * S; rr(x, y, w, 58, 18, '#171920'); g.restore();
    rr(x, y, w, 58, 18, null, 'rgba(255,255,255,.14)');
    crest(x + 30, y + 11, 0.31, D);
    t('STUDENT PORTAL', x + 58, y + 12, 9, 700, '#9aa0b0', 'left', 1); t('now', x + w - 18, y + 12, 9, 600, '#9aa0b0', 'right');
    t(note.text, x + 58, y + 29, 14, 600, '#fff');
  }
  if (gI > 0) {                                         // stream corruption: torn slices and inverted blocks
    g.setTransform(1, 0, 0, 1, 0, 0);
    tg.drawImage(out, 0, 0);
    const n = 4 + Math.floor(gI * 12);
    for (let i = 0; i < n; i++) {
      const y = Math.floor(hash(f * 13 + i, 1) * H * S), h = Math.floor((6 + hash(f * 7 + i, 2) * 70) * S), dx = (hash(f * 5 + i, 3) - 0.5) * 260 * gI * S;
      g.drawImage(tmp, 0, y, W * S, h, dx, y, W * S, h);
    }
    g.globalCompositeOperation = 'difference'; g.fillStyle = '#fff';
    for (let i = 0; i < 3; i++) if (hash(f * 3 + i, 4) < gI) g.fillRect(hash(f + i, 5) * W * S * 0.7, hash(f + i, 6) * H * S, (80 + hash(f + i, 7) * 500) * S, (4 + hash(f + i, 8) * 40) * S);
    g.globalCompositeOperation = 'source-over';
  }
}
window.renderFrame = renderFrame;
window.frameJPEG = (f, q) => { renderFrame(f); return out.toDataURL('image/jpeg', q).slice(23); };
window.ready = Promise.all([300, 500, 600, 700, 800].map(w => document.fonts.load(`${w} 20px Inter`)).concat(document.fonts.load('italic 600 15px Inter'))).then(() => true);
if (!location.search.includes('render')) window.ready.then(() => {   // silent live preview
  const s0 = performance.now();
  const tick = () => { renderFrame(Math.floor(((performance.now() - s0) / 1000) % T.duration * T.fps)); requestAnimationFrame(tick); };
  tick();
});
})();
