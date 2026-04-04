/* Rein Flow Board -- Canvas visualization engine
 * Version: 2.0.0
 * Reads theme colors from CSS variables so styling is fully controlled by CSS.
 * API endpoint is configurable via REIN_API global or auto-detected.
 */
'use strict';
const FLOW_BOARD_VERSION = '2.0.0';

// ---- Configuration ----
const API = window.REIN_API || '/api-flow.php';
const WS_URL = window.REIN_WS || `ws://${location.hostname}:8765`;
const SPEED = 1.8;

// ---- Theme colors (read from CSS variables) ----
const style = getComputedStyle(document.documentElement);
const C = {
  accent:    style.getPropertyValue('--accent').trim()    || '#00dca8',
  accentDim: style.getPropertyValue('--accent-dim').trim() || 'rgba(0,220,168,0.4)',
  blue:      style.getPropertyValue('--blue').trim()       || '#0088f0',
  red:       style.getPropertyValue('--red').trim()        || '#ff6464',
  text:      style.getPropertyValue('--text').trim()       || '#e0e0e0',
  textDim:   style.getPropertyValue('--text-dim').trim()   || '#999',
  textMuted: style.getPropertyValue('--text-muted').trim() || '#666',
  border:    style.getPropertyValue('--border').trim()     || '#333',
};

// ---- DOM ----
const cv = document.getElementById('cv');
const cx = cv.getContext('2d');
const tip = document.getElementById('tip');

// ---- State ----
let W, H, GW = 100, GH = 100, cs = 1;
let data = null, currentTask = '', currentFlow = '';
let nodes = [];
let paths = [];
let pathFill = {};
let pathState = {};
let dots = [];
let selected = null;
let canvasRect = { left: 0, top: 0 };
let needsOneDraw = false;

// ---- Status normalization ----
function norm(s) {
  if (!s || s === 'idle' || s === 'waiting' || s === 'pending' || s === 'queued') return 'idle';
  if (s === 'done' || s === 'completed' || s === 'success' || s === 'finished') return 'done';
  if (s === 'running' || s === 'active' || s === 'in_progress') return 'running';
  if (s === 'failed' || s === 'error' || s === 'crashed') return 'failed';
  return 'idle';
}

// ---- Resize ----
function resize() {
  const d = devicePixelRatio || 1;
  const a = document.querySelector('.canvas-wrap');
  W = a.clientWidth;
  cs = Math.min(W / GW, a.clientHeight / GH);
  H = a.clientHeight;
  cv.width = W * d; cv.height = H * d;
  cv.style.width = W + 'px'; cv.style.height = H + 'px';
  cx.setTransform(d, 0, 0, d, 0, 0);
  canvasRect = a.getBoundingClientRect();
  needsOneDraw = true;
}

function tx(c) { return c * cs; }
function ty(r) { return r * cs; }

// ==== LAYOUT (dagre + orthogonal routing) ====
function buildScene() {
  if (!data || !data.blocks) return;
  nodes = []; paths = []; pathFill = {}; pathState = {}; dots = [];

  const blocks = data.blocks;
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'TB', nodesep: 5, edgesep: 3, ranksep: 4, marginx: 0, marginy: 0 });
  g.setDefaultEdgeLabel(() => ({}));
  blocks.forEach(b => g.setNode(b.name, { label: b.name, width: 4, height: 4 }));
  (data.edges || []).forEach(e => g.setEdge(e.from, e.to));
  dagre.layout(g);

  const gGraph = g.graph();
  const graphW = gGraph.width || 10, graphH = gGraph.height || 10;
  GW = 100;
  GH = Math.max(graphH + 10, 60);
  const offC = (GW - graphW) / 2, offR = 5;

  blocks.forEach(b => {
    const n = g.node(b.name);
    if (!n) return;
    nodes.push({
      id: b.name, c: n.x + offC, r: n.y + offR,
      label: shortLabel(b.name), status: norm(b.status), block: b
    });
  });
  resize();

  // Orthogonal path routing
  const nodeR = 2.5;
  let pid = 0;
  (data.edges || []).forEach(e => {
    const fn = nodes.find(n => n.id === e.from);
    const tn = nodes.find(n => n.id === e.to);
    if (!fn || !tn) return;

    if (tn.r <= fn.r) {
      // Loop: route around right side
      const loopX = Math.max(fn.c, tn.c) + 6;
      paths.push({
        id: pid++, from: e.from, to: e.to, loop: true, label: e.label || '',
        pts: [[fn.c + nodeR, fn.r], [loopX, fn.r], [loopX, tn.r], [tn.c + nodeR, tn.r]]
      });
    } else {
      const midR = (fn.r + tn.r) / 2;
      paths.push({
        id: pid++, from: e.from, to: e.to, label: e.label || '',
        pts: [[fn.c, fn.r + nodeR], [fn.c, midR], [tn.c, midR], [tn.c, tn.r - nodeR]]
      });
    }
  });

  // Init path states from block statuses
  paths.forEach(p => {
    const fb = nodes.find(n => n.id === p.from);
    const tb = nodes.find(n => n.id === p.to);
    if (!fb || !tb) { pathFill[p.id] = 0; pathState[p.id] = 'idle'; return; }

    if (fb.status === 'done' && tb.status === 'done') {
      pathFill[p.id] = 1; pathState[p.id] = 'filled';
    } else if (fb.status === 'done' && tb.status === 'running') {
      pathFill[p.id] = 0; pathState[p.id] = 'filling';
      dots.push({ pathId: p.id, t: 0 });
    } else if (fb.status === 'done') {
      pathFill[p.id] = 1; pathState[p.id] = 'filled';
    } else if (fb.status === 'running') {
      pathFill[p.id] = 0.3; pathState[p.id] = 'filling';
      dots.push({ pathId: p.id, t: 0.3 });
    } else {
      pathFill[p.id] = 0; pathState[p.id] = 'idle';
    }
  });
}

function shortLabel(name) {
  return name
    .replace('dept_', '').replace('customer_', 'c:').replace('review_', 'r:')
    .replace('final_', 'f:').replace('analyst_', 'a:').replace('competitive_', 'comp_')
    .replace('_initial', '').replace('_review', '/r').replace('_synthesis', '/s')
    .replace('recommendation', 'final');
}

// ==== PATH MATH ====
function pLen(pts) {
  let l = 0;
  for (let i = 1; i < pts.length; i++)
    l += Math.abs(pts[i][0] - pts[i - 1][0]) + Math.abs(pts[i][1] - pts[i - 1][1]);
  return l;
}

function ptOn(pts, t) {
  let segs = [], tot = 0;
  for (let i = 1; i < pts.length; i++) {
    const l = Math.abs(pts[i][0] - pts[i - 1][0]) + Math.abs(pts[i][1] - pts[i - 1][1]);
    segs.push(l); tot += l;
  }
  let d = t * tot, acc = 0;
  for (let i = 0; i < segs.length; i++) {
    if (acc + segs[i] >= d && segs[i] > 0) {
      const f = (d - acc) / segs[i];
      return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f];
    }
    acc += segs[i];
  }
  return pts[pts.length - 1];
}

function partialPath(pts, fill) {
  const tot = pLen(pts), fd = fill * tot;
  let acc = 0, fp = [[pts[0][0], pts[0][1]]];
  for (let i = 1; i < pts.length; i++) {
    const sl = Math.abs(pts[i][0] - pts[i - 1][0]) + Math.abs(pts[i][1] - pts[i - 1][1]);
    if (acc + sl >= fd) {
      const f = sl > 0 ? (fd - acc) / sl : 0;
      fp.push([pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f]);
      break;
    }
    fp.push([pts[i][0], pts[i][1]]);
    acc += sl;
  }
  return fp;
}

// ==== DRAWING ====

function drawGrid() {
  cx.strokeStyle = 'rgba(255,255,255,0.012)';
  cx.lineWidth = 0.5;
  for (let i = 0; i <= GW; i += 5) {
    cx.beginPath(); cx.moveTo(tx(i), 0); cx.lineTo(tx(i), ty(GH)); cx.stroke();
  }
  for (let i = 0; i <= GH; i += 5) {
    cx.beginPath(); cx.moveTo(0, ty(i)); cx.lineTo(tx(GW), ty(i)); cx.stroke();
  }
}

let oc = null, ox = null;
function ensureOffscreen() {
  if (!oc) oc = document.createElement('canvas');
  if (oc.width !== cv.width || oc.height !== cv.height) {
    oc.width = cv.width; oc.height = cv.height;
  }
  ox = oc.getContext('2d');
  const d = devicePixelRatio || 1;
  ox.setTransform(d, 0, 0, d, 0, 0);
}

function drawPaths() {
  ensureOffscreen();

  // 1. Idle paths
  ox.clearRect(0, 0, oc.width, oc.height);
  ox.lineCap = 'round'; ox.lineJoin = 'round';
  ox.strokeStyle = 'rgb(0,100,200)';
  ox.lineWidth = cs * 0.12;
  paths.forEach(p => {
    const pts = p.pts;
    ox.beginPath(); ox.moveTo(tx(pts[0][0]), ty(pts[0][1]));
    for (let i = 1; i < pts.length; i++) ox.lineTo(tx(pts[i][0]), ty(pts[i][1]));
    ox.stroke();
  });
  cx.save(); cx.globalAlpha = 0.15;
  cx.drawImage(oc, 0, 0, oc.width, oc.height, 0, 0, W, H);
  cx.globalAlpha = 1; cx.restore();

  // 2. Filled paths
  ox.clearRect(0, 0, oc.width, oc.height);
  ox.lineCap = 'round'; ox.lineJoin = 'round';
  ox.strokeStyle = 'rgb(0,220,170)';
  ox.lineWidth = cs * 0.14;
  let hasFilled = false;
  paths.forEach(p => {
    if ((pathState[p.id] || 'idle') === 'filled' || (pathFill[p.id] || 0) >= 1) {
      const pts = p.pts;
      ox.beginPath(); ox.moveTo(tx(pts[0][0]), ty(pts[0][1]));
      for (let i = 1; i < pts.length; i++) ox.lineTo(tx(pts[i][0]), ty(pts[i][1]));
      ox.stroke();
      hasFilled = true;
    }
  });
  if (hasFilled) {
    cx.save(); cx.globalAlpha = 0.4;
    cx.drawImage(oc, 0, 0, oc.width, oc.height, 0, 0, W, H);
    cx.globalAlpha = 1; cx.restore();
  }

  // 3. Filling animation (water)
  cx.save(); cx.lineCap = 'round'; cx.lineJoin = 'round';
  paths.forEach(p => {
    const fl = pathFill[p.id] || 0, st = pathState[p.id] || 'idle';
    if (st === 'filling' && fl > 0.001 && fl < 1) {
      const fp = partialPath(p.pts, fl);
      cx.strokeStyle = 'rgba(0,220,170,0.12)'; cx.lineWidth = cs * 0.5;
      cx.beginPath(); cx.moveTo(tx(fp[0][0]), ty(fp[0][1]));
      for (let i = 1; i < fp.length; i++) cx.lineTo(tx(fp[i][0]), ty(fp[i][1]));
      cx.stroke();
      cx.strokeStyle = 'rgba(0,255,200,0.9)'; cx.lineWidth = cs * 0.14;
      cx.beginPath(); cx.moveTo(tx(fp[0][0]), ty(fp[0][1]));
      for (let i = 1; i < fp.length; i++) cx.lineTo(tx(fp[i][0]), ty(fp[i][1]));
      cx.stroke();
    }
  });
  cx.restore();

  // 4. Arrowheads
  cx.save();
  paths.forEach(p => {
    const pts = p.pts, st = pathState[p.id] || 'idle';
    const last = pts[pts.length - 1], prev = pts[pts.length - 2];
    const ax = tx(last[0]), ay = ty(last[1]);
    const dx = last[0] - prev[0], dy = last[1] - prev[1];
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / len, uy = dy / len;
    const sz = cs * 0.6;
    cx.fillStyle = st === 'filled' ? 'rgba(0,220,170,0.5)' : 'rgba(0,100,200,0.2)';
    cx.beginPath();
    cx.moveTo(ax, ay);
    cx.lineTo(ax - ux * sz + uy * sz * 0.5, ay - uy * sz - ux * sz * 0.5);
    cx.lineTo(ax - ux * sz - uy * sz * 0.5, ay - uy * sz + ux * sz * 0.5);
    cx.closePath(); cx.fill();
  });
  cx.restore();

  // 5. Edge labels
  cx.save();
  const fs = Math.max(cs * 0.55, 5);
  cx.font = `bold ${fs}px 'JetBrains Mono',Consolas,monospace`;
  cx.textAlign = 'center'; cx.textBaseline = 'middle';
  paths.forEach(p => {
    if (!p.label) return;
    const pts = p.pts;
    const mid = pts.length >= 3 ? pts[Math.floor(pts.length / 2)] : pts[0];
    const lx = tx(mid[0]), ly = ty(mid[1]);
    if (p.label === 'OK') cx.fillStyle = 'rgba(0,220,170,0.6)';
    else if (p.label === 'FAIL') cx.fillStyle = 'rgba(255,100,100,0.6)';
    else cx.fillStyle = 'rgba(200,200,100,0.5)';
    cx.fillText(p.label, lx + cs * 0.8, ly);
  });
  cx.restore();
}

function drawNodes() {
  nodes.forEach(n => {
    const x = tx(n.c), y = ty(n.r), st = n.status, r = cs * 1.6;
    cx.save();
    cx.beginPath(); cx.arc(x, y, r, 0, Math.PI * 2);

    if (st === 'idle') {
      cx.fillStyle = 'rgba(0,80,180,0.06)'; cx.fill();
      cx.strokeStyle = selected === n.id ? 'rgba(0,220,170,0.5)' : 'rgba(0,100,200,0.3)';
      cx.lineWidth = cs * 0.06; cx.stroke();
      cx.beginPath(); cx.arc(x, y, cs * 0.15, 0, Math.PI * 2);
      cx.fillStyle = 'rgba(0,100,200,0.3)'; cx.fill();
    } else if (st === 'running') {
      const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 180);
      cx.fillStyle = `rgba(0,220,170,${0.12 + 0.08 * pulse})`; cx.fill();
      cx.strokeStyle = `rgba(0,220,170,${0.5 + 0.3 * pulse})`;
      cx.lineWidth = cs * 0.1; cx.stroke();
      cx.beginPath(); cx.arc(x, y, r + cs * 0.4, 0, Math.PI * 2);
      cx.strokeStyle = 'rgba(0,220,170,0.1)'; cx.lineWidth = cs * 0.6; cx.stroke();
      cx.beginPath(); cx.arc(x, y, cs * 0.25, 0, Math.PI * 2);
      cx.fillStyle = `rgba(0,255,200,${0.6 + 0.4 * pulse})`; cx.fill();
    } else if (st === 'done') {
      cx.fillStyle = 'rgba(0,220,170,0.15)'; cx.fill();
      cx.strokeStyle = 'rgba(0,220,170,0.6)'; cx.lineWidth = cs * 0.1; cx.stroke();
      cx.beginPath(); cx.arc(x, y, cs * 0.25, 0, Math.PI * 2);
      cx.fillStyle = 'rgba(0,220,170,0.8)'; cx.fill();
    } else if (st === 'failed') {
      cx.beginPath(); cx.arc(x, y, r, 0, Math.PI * 2);
      cx.fillStyle = 'rgba(255,100,100,0.06)'; cx.fill();
      cx.strokeStyle = 'rgba(255,100,100,0.4)'; cx.lineWidth = cs * 0.08; cx.stroke();
      cx.font = `bold ${cs}px 'JetBrains Mono',Consolas,monospace`;
      cx.textAlign = 'center'; cx.textBaseline = 'middle';
      cx.fillStyle = C.red; cx.fillText('!', x, y);
    }

    // Label
    const lfs = Math.max(cs * 0.72, 6);
    cx.font = `${lfs}px 'JetBrains Mono',Consolas,monospace`;
    cx.textAlign = 'center'; cx.textBaseline = 'top';
    if (st === 'running') cx.fillStyle = 'rgba(0,220,170,0.7)';
    else if (st === 'done') cx.fillStyle = 'rgba(0,220,170,0.5)';
    else if (st === 'failed') cx.fillStyle = 'rgba(255,100,100,0.5)';
    else cx.fillStyle = 'rgba(0,100,200,0.3)';
    cx.fillText(n.label, x, y + r + cs * 0.3);
    cx.restore();
  });
}

function drawDots() {
  dots.forEach(d => {
    const p = paths[d.pathId]; if (!p) return;
    const [px, py] = ptOn(p.pts, d.t);
    cx.save();
    cx.fillStyle = 'rgba(0,255,200,0.12)';
    cx.beginPath(); cx.arc(tx(px), ty(py), cs * 0.9, 0, Math.PI * 2); cx.fill();
    cx.fillStyle = '#00ffcc';
    cx.beginPath(); cx.arc(tx(px), ty(py), cs * 0.35, 0, Math.PI * 2); cx.fill();
    cx.fillStyle = '#fff';
    cx.beginPath(); cx.arc(tx(px), ty(py), cs * 0.12, 0, Math.PI * 2); cx.fill();
    cx.restore();
  });
}

function draw() {
  cx.clearRect(0, 0, W, H);
  drawGrid(); drawPaths(); drawDots(); drawNodes();
}

// ==== ANIMATION ====
let lastT = 0, lastDraw = 0;
function animate(t) {
  const dt = Math.min((t - lastT) / 1000, 0.05); lastT = t;
  paths.forEach(p => {
    if (pathState[p.id] === 'filling') {
      pathFill[p.id] = Math.min(1, pathFill[p.id] + SPEED * dt);
      if (pathFill[p.id] >= 1) pathState[p.id] = 'filled';
    }
  });
  dots = dots.filter(d => {
    if (pathState[d.pathId] === 'filling') { d.t = pathFill[d.pathId]; return true; }
    return false;
  });
  if (t - lastDraw > 33) { draw(); lastDraw = t; }
  requestAnimationFrame(animate);
}

// ==== DONE TRIGGER ====
function triggerDone(blockId) {
  paths.forEach(p => {
    if (p.from === blockId && pathState[p.id] !== 'filled' && pathState[p.id] !== 'filling') {
      pathFill[p.id] = 0; pathState[p.id] = 'filling';
      dots.push({ pathId: p.id, t: 0 });
    }
  });
}

// ==== TEST WATER ====
function testWater() {
  if (!paths.length) {
    const flow = document.getElementById('flowSel').value;
    if (!flow) { alert('Select a flow first'); return; }
    fetch(API + `?action=flow_schema&flow=${flow}`).then(r => r.json()).then(d => {
      if (d.error) return;
      data = d; buildScene(); startWaterTest();
    });
  } else {
    startWaterTest();
  }
}

function startWaterTest() {
  paths.forEach(p => { pathFill[p.id] = 0; pathState[p.id] = 'idle'; });
  nodes.forEach(n => n.status = 'idle');
  dots = [];
  const ranks = {};
  nodes.forEach(n => { const r = Math.round(n.r * 10); ranks[r] = ranks[r] || []; ranks[r].push(n); });
  const levels = Object.keys(ranks).map(Number).sort((a, b) => a - b).map(r => ranks[r]);
  let delay = 0;
  levels.forEach((phaseNodes) => {
    const waterTime = Math.ceil(1000 / SPEED);
    const phaseDelay = waterTime + 800;
    setTimeout(() => { phaseNodes.forEach(n => n.status = 'running'); }, delay);
    setTimeout(() => {
      phaseNodes.forEach(n => {
        n.status = 'done';
        paths.forEach(pp => { if (pp.to === n.id) { pathFill[pp.id] = 1; pathState[pp.id] = 'filled'; } });
      });
      phaseNodes.forEach(n => {
        paths.forEach(pp => {
          if (pp.from === n.id && pathState[pp.id] === 'idle') {
            const targetDeps = paths.filter(x => x.to === pp.to).map(x => x.from);
            const allDone = targetDeps.every(dep => { const dn = nodes.find(nn => nn.id === dep); return dn && dn.status === 'done'; });
            if (allDone) { pathFill[pp.id] = 0; pathState[pp.id] = 'filling'; dots.push({ pathId: pp.id, t: 0 }); }
          }
        });
      });
    }, delay + waterTime);
    delay += phaseDelay;
  });
}

// ==== API ====
async function loadFlows() {
  try {
    const r = await fetch(API + '?action=flows');
    const d = await r.json();
    const sel = document.getElementById('flowSel');
    sel.innerHTML = '<option value="">-- flow --</option>';
    (d.flows || []).filter(f => f.exists).forEach(f => {
      const o = document.createElement('option'); o.value = f.id; o.textContent = f.id; sel.appendChild(o);
    });
    sel.onchange = () => selectFlow(sel.value);
  } catch (e) { console.error('[FLOWS]', e); }
}

async function selectFlow(flowId) {
  if (!flowId) return;
  currentFlow = flowId;
  history.replaceState(null, '', `?flow=${flowId}`);
  try {
    const r = await fetch(API + '?action=list');
    const d = await r.json();
    const runs = (d.tasks || []).filter(t => t.flow === flowId).sort((a, b) => b.id.localeCompare(a.id));
    const rs = document.getElementById('runSel');
    rs.innerHTML = '<option value="">--</option>';
    runs.forEach(t => {
      const o = document.createElement('option'); o.value = t.id;
      const dt = t.id.match(/\d{8}-\d{6}/)?.[0] || t.id;
      o.textContent = `${dt} (${t.status})`; rs.appendChild(o);
    });
    const now = Date.now();
    const recent = t => { const m = t.id.match(/(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/); return m ? (now - new Date(m[1], m[2] - 1, m[3], m[4], m[5], m[6]).getTime()) < 600000 : false; };
    const best = runs.find(t => t.status === 'running' && recent(t)) || runs.find(t => t.status === 'completed') || runs[0];
    if (best) { rs.value = best.id; await loadState(best.id); }
    else {
      const tr = await fetch(API + `?action=flow_schema&flow=${flowId}`);
      const td = await tr.json();
      if (!td.error) { data = td; buildScene(); updateBadge('template'); needsOneDraw = true; }
    }
  } catch (e) { console.error('[SELECT]', e); }
}

async function loadState(taskId) {
  if (!taskId) return;
  currentTask = taskId;
  try {
    const r = await fetch(API + `?action=state&task=${taskId}`);
    const text = await r.text();
    let d;
    try { d = JSON.parse(text); } catch (e) { console.error('[STATE] Bad JSON:', text.substring(0, 200)); return; }
    if (d.error) { console.error('[STATE]', d.error); return; }
    data = d;
    buildScene();
    updateBadge(data.status);
    renderEvents(data.events || []);
    needsOneDraw = true;
  } catch (e) { console.error('[STATE]', e); }
}

function viewRun() {
  const id = document.getElementById('runSel').value;
  if (id) loadState(id);
}

// ==== RUN FLOW ====
async function runFlow() {
  const flow = document.getElementById('flowSel').value;
  if (!flow) { alert('Select a flow first'); return; }
  const topic = document.getElementById('topicIn').value.trim() || 'demo';
  try {
    const r = await fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `action=start&flow=${encodeURIComponent(flow)}&question=${encodeURIComponent(topic)}`
    });
    const text = await r.text();
    let d;
    try { d = JSON.parse(text); } catch (e) { console.error('[RUN] Bad JSON:', text.substring(0, 200)); return; }
    if (d.error) { alert(d.error); return; }
    if (d.task_id) {
      currentTask = d.task_id;
      addEvent('launched', d.task_id);
      if (nodes.length) {
        nodes.forEach(n => { n.status = 'idle'; n.block.status = 'idle'; });
        paths.forEach(p => { pathFill[p.id] = 0; pathState[p.id] = 'idle'; });
        dots = [];
      } else {
        const tr = await fetch(API + `?action=flow_schema&flow=${flow}`);
        const txt2 = await tr.text();
        try { data = JSON.parse(txt2); if (!data.error) buildScene(); } catch (e) {}
      }
      updateBadge('running');
      setTimeout(() => {
        const rs = document.getElementById('runSel');
        const o = document.createElement('option');
        o.value = d.task_id; o.textContent = d.task_id.match(/\d{8}-\d{6}/)?.[0] + ' (running)';
        o.selected = true; rs.prepend(o);
      }, 500);
    }
  } catch (e) { console.error('[RUN]', e); }
}

// ==== WEBSOCKET ====
let ws = null, wsOk = false;
function connectWS() {
  try {
    ws = new WebSocket(WS_URL);
    ws.onopen = () => {
      wsOk = true;
      const el = document.getElementById('wsBar');
      el.textContent = 'WS: live'; el.style.color = C.accent;
    };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'connected') return;
        const bn = msg.block || '', et = msg.type || '';
        if (!bn) return;

        const node = nodes.find(n => n.id === bn);
        if (!node) return;

        const prev = node.status;
        if (et.includes('start')) { node.status = 'running'; node.block.status = 'running'; }
        if (et.includes('done') || et.includes('completed')) { node.status = 'done'; node.block.status = 'done'; }
        if (et.includes('fail')) { node.status = 'failed'; node.block.status = 'failed'; }

        if (node.status !== prev) {
          const isRetry = (prev === 'done' || prev === 'failed');
          if (node.status === 'running') {
            paths.forEach(p => {
              if (p.to !== bn) return;
              if (isRetry) {
                if (!p.loop) return;
              } else {
                if (pathState[p.id] === 'filling') return;
                const src = nodes.find(n => n.id === p.from);
                if (!src || src.status !== 'done') return;
              }
              pathFill[p.id] = 0; pathState[p.id] = 'filling';
              dots.push({ pathId: p.id, t: 0 });
            });
          }
          if (node.status === 'done') {
            paths.forEach(p => { if (p.to === bn) { pathFill[p.id] = 1; pathState[p.id] = 'filled'; } });
            paths.forEach(p => {
              if (p.from !== bn || p.loop) return;
              const targetDeps = paths.filter(pp => pp.to === p.to && !pp.loop).map(pp => pp.from);
              const allDepsDone = targetDeps.every(dep => { const dn = nodes.find(n => n.id === dep); return dn && dn.status === 'done'; });
              if (allDepsDone) { pathFill[p.id] = 0; pathState[p.id] = 'filling'; dots.push({ pathId: p.id, t: 0 }); }
            });
          }
        }
        addEvent(et, bn);

        const allDone = nodes.every(n => n.status === 'done');
        const anyFailed = nodes.some(n => n.status === 'failed');
        const anyRunning = nodes.some(n => n.status === 'running');
        if (anyFailed) updateBadge('failed');
        else if (allDone) updateBadge('completed');
        else if (anyRunning) updateBadge('running');
      } catch (err) {}
    };
    ws.onclose = () => {
      wsOk = false;
      const el = document.getElementById('wsBar');
      el.textContent = 'WS: off'; el.style.color = C.red;
      setTimeout(connectWS, 5000);
    };
  } catch (e) {}
}

// Polling fallback
setInterval(() => { if (!wsOk && currentTask) loadState(currentTask); }, 5000);

// ==== UI HELPERS ====
function updateBadge(st) {
  const el = document.getElementById('badge');
  el.textContent = (st || 'idle').toUpperCase();
  const colors = {
    completed: ['rgba(0,136,240,0.12)', C.blue],
    running:   ['rgba(0,220,170,0.12)', C.accent],
    failed:    ['rgba(255,100,100,0.12)', C.red],
    template:  ['rgba(255,255,255,0.05)', C.textMuted]
  };
  const c = colors[st] || [C.border, C.textMuted];
  el.style.background = c[0]; el.style.color = c[1];
}

function renderEvents(evts) {
  const el = document.getElementById('events'); el.innerHTML = '';
  evts.slice(-30).reverse().forEach(ev => {
    const d = document.createElement('div'); d.className = 'ev';
    const ts = (ev.ts || '').split('T')[1]?.substring(0, 8) || '';
    d.innerHTML = `<span class="t">${ts}</span> <span class="e">${ev.type || ''}</span> <span class="b">${ev.block || ''}</span>`;
    el.appendChild(d);
  });
}

function addEvent(type, block) {
  const el = document.getElementById('events');
  const d = document.createElement('div'); d.className = 'ev';
  d.innerHTML = `<span class="t">${new Date().toTimeString().substring(0, 8)}</span> <span class="e">${type}</span> <span class="b">${block}</span>`;
  el.prepend(d);
}

// ==== MOUSE ====
function mouseToGrid(e) {
  const cont = document.querySelector('.canvas-wrap');
  return [(e.clientX - canvasRect.left) / cs, (e.clientY - canvasRect.top + cont.scrollTop) / cs];
}

function findNode(mx, my) {
  let found = null, minD = 3;
  nodes.forEach(n => {
    const d = Math.sqrt((n.c - mx) ** 2 + (n.r - my) ** 2);
    if (d < minD) { minD = d; found = n; }
  });
  return found;
}

cv.addEventListener('mousemove', e => {
  if (!nodes.length) return;
  const [mx, my] = mouseToGrid(e);
  const found = findNode(mx, my);
  if (found) {
    tip.style.display = 'block';
    tip.style.left = (e.clientX + 15) + 'px'; tip.style.top = (e.clientY + 10) + 'px';
    const dur = found.block.duration_sec ? found.block.duration_sec.toFixed(1) + 's' : '-';
    document.getElementById('tip-name').textContent = found.block.name;
    document.getElementById('tip-info').textContent = `${found.block.specialist || found.block.agent || '-'} | ${found.status} | ${dur}`;
  } else {
    tip.style.display = 'none';
  }
});

cv.addEventListener('click', e => {
  if (!nodes.length) return;
  const [mx, my] = mouseToGrid(e);
  const found = findNode(mx, my);
  if (found) { selected = found.id; loadBlockDetail(found.id); }
});

async function loadBlockDetail(name) {
  if (!currentTask) return;
  try {
    const r = await fetch(API + `?action=block_detail&task=${currentTask}&block=${name}`);
    const text = await r.text();
    let d;
    try { d = JSON.parse(text); } catch (e) { return; }
    const b = (data.blocks || []).find(bb => bb.name === name) || {};
    let html = `<h3>${name}</h3>`;
    html += `<div class="ev">${b.specialist || ''} | ${b.status} | phase ${b.phase}${b.duration_sec ? ' | ' + b.duration_sec.toFixed(1) + 's' : ''}</div>`;
    if (d.result_md) html += `<div class="side-detail">${d.result_md.substring(0, 3000)}</div>`;
    if (d.runs && d.runs.length) {
      html += `<h3>Runs</h3>`;
      d.runs.forEach(r => {
        html += `<div class="run-item" onclick="loadLog('${name}',${r.run})">#${r.run} ${r.time} ${r.lines}ln</div>`;
      });
    }
    html += `<div id="lb"></div>`;
    document.getElementById('panel').innerHTML = html;
  } catch (e) {}
}

async function loadLog(block, run) {
  try {
    const r = await fetch(API + `?action=run_log&task=${currentTask}&block=${block}&run=${run}`);
    const text = await r.text();
    let d;
    try { d = JSON.parse(text); } catch (e) { return; }
    if (d.log) {
      document.getElementById('lb').innerHTML = `<h3>Log</h3><div class="side-detail" style="font-size:9px;max-height:200px">${d.log}</div>`;
    }
  } catch (e) {}
}

// ==== INIT ====
addEventListener('resize', () => resize());
resize();
loadFlows().then(() => {
  const params = new URLSearchParams(location.search);
  const flowParam = params.get('flow');
  if (flowParam) {
    document.getElementById('flowSel').value = flowParam;
    selectFlow(flowParam);
  }
});
connectWS();
requestAnimationFrame(animate);
