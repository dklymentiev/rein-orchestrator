/* Rein Flow Board v6 (v5 + grid layout for 5000+ blocks) -- state-diff animation engine
 *
 * Same rendering / layout / colors as v4. The only difference is how
 * edge animations are triggered. v4 drove them from WebSocket events
 * (block_start / block_done) and fired edges based on inbound deps,
 * which led to misleading visuals (a block appears to light up while
 * nothing animates into it).
 *
 * v5 polls /api-flow.php?action=state every POLL_MS and computes a
 * diff against the previous snapshot. An edge `X -> Y` is fired only
 * when X transitions `not-done -> done` in the diff, i.e. at the real
 * moment when data flows out of X. This matches the user mental model:
 * "the droplet runs along an edge only when its source has just
 * finished and data actually moved forward". Works for forward edges
 * and loop back-edges uniformly, resilient to missed frames/events,
 * and transparent to replay.
 */
'use strict';
const FLOW_BOARD_VERSION = '5.0.0';
const POLL_MS = 500;

const API = window.REIN_API || '/api-flow.php';
const WS_URL = window.REIN_WS || (location.protocol === 'https:'
  ? `wss://rein-ws.sf.vpn`
  : `ws://${location.hostname}:8765`);
const cv = document.getElementById('cv');
const cx = cv.getContext('2d');
const tip = document.getElementById('tip');

// ---- Theme ----
const style = getComputedStyle(document.documentElement);
const C = {
  accent:  style.getPropertyValue('--accent').trim()  || '#00dca8',
  blue:    style.getPropertyValue('--blue').trim()     || '#0088f0',
  red:     style.getPropertyValue('--red').trim()      || '#ff6464',
  bg:      style.getPropertyValue('--bg').trim()       || '#0d1117',
  border:  style.getPropertyValue('--border').trim()   || '#1e2a3a',
  textDim: style.getPropertyValue('--text-dim').trim() || '#4a6a8a',
};

// ---- State ----
let W, H, GW = 60, GH = 60, cs = 1;
let userZoom = null;
let data = null, currentFlow = '', currentTask = '';
let nodes = [], edges = [];
let selected = null;
let canvasRect = { left: 0, top: 0 };

// Per-node animation
let nodeAnim = {};  // id -> { status, iter, maxIter, doneAt }
// Fires
let fires = [];     // { edge, progress, speed }
// Edge state
let edgeFill = {};  // edgeKey -> 0..1
// v5: previous block-state snapshot for state-diff poller (hoisted so
// buildGraph() can reset it without TDZ issues). See applyStateDiff().
let prevBlockState = {};

// ---- Resize ----
function resize() {
  const d = devicePixelRatio || 1;
  const a = document.querySelector('.canvas-wrap');
  W = a.clientWidth; H = a.clientHeight;
  cv.width = W * d; cv.height = H * d;
  cv.style.width = W + 'px'; cv.style.height = H + 'px';
  cx.setTransform(d, 0, 0, d, 0, 0);
  canvasRect = a.getBoundingClientRect();
  if (!userZoom) {
    const sx = W / GW, sy = H / GH;
    cs = Math.min(sx, sy) * 0.85;
  } else {
    cs = userZoom;
  }
}
function zoomIn() { userZoom = (userZoom || cs) * 1.25; resize(); }
function zoomOut() { userZoom = (userZoom || cs) * 0.8; resize(); }
function zoomFit() { userZoom = null; resize(); }
function tx(c) { return c * cs + (W - GW * cs) / 2; }
function ty(r) { return r * cs + (H - GH * cs) / 2; }

// ---- Build graph from API data ----
function buildGraph(d) {
  data = d;
  const blocks = d.blocks || [];
  nodes = []; edges = [];
  nodeAnim = {}; fires = []; edgeFill = {};
  // Reset the state-diff snapshot so the first poll after a task
  // switch seeds from scratch without replaying historical edges.
  prevBlockState = {};
  lastEventIndex = 0;

  // Layout: grid for large generated walls (>200 blocks, bNN_NNN names), dagre otherwise
  if (blocks.length > 200 && blocks[0] && blocks[0].name && blocks[0].name.match(/^b\d+_\d+/)) {
    const SX = 8, SY = 9;
    let maxC = 0, maxR = 0;
    blocks.forEach(b => {
      const m = b.name.match(/^b(\d+)_(\d+)/);
      if (m) { maxR = Math.max(maxR, +m[1]); maxC = Math.max(maxC, +m[2]); }
    });
    GW = (maxC + 1) * SX + 10;
    GH = (maxR + 1) * SY + 10;
    blocks.forEach(b => {
      const m = b.name.match(/^b(\d+)_(\d+)/);
      if (!m) return;
      const iters = b.iterations || 1;
      nodes.push({
        id: b.name, c: +m[2] * SX + 5, r: +m[1] * SY + 5,
        label: shortLabel(b.name), block: b, iterations: iters
      });
      nodeAnim[b.name] = { status: 'idle', iter: 0, maxIter: iters };
    });
  } else {
    // Dagre layout
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'TB', nodesep: 6, ranksep: 6, marginx: 4, marginy: 4 });
    g.setDefaultEdgeLabel(() => ({}));
    blocks.forEach(b => g.setNode(b.name, { width: 4, height: 4 }));
    (d.edges || []).forEach(e => g.setEdge(e.from, e.to));
    dagre.layout(g);

    const gGraph = g.graph();
    GW = Math.max((gGraph.width || 10) + 10, 40);
    GH = Math.max((gGraph.height || 10) + 10, 40);
    const offC = (GW - (gGraph.width || 10)) / 2, offR = 5;

    blocks.forEach(b => {
      const n = g.node(b.name);
      if (!n) return;
      const iters = b.iterations || 1;
      nodes.push({
        id: b.name, c: n.x + offC, r: n.y + offR,
        label: shortLabel(b.name), block: b, iterations: iters
      });
      nodeAnim[b.name] = { status: 'idle', iter: 0, maxIter: iters };
    });
  }
  resize();

  // Build edge paths
  const nodeR = 2.5;
  let pid = 0;
  (d.edges || []).forEach(e => {
    const fn = nodes.find(n => n.id === e.from);
    const tn = nodes.find(n => n.id === e.to);
    if (!fn || !tn) return;

    const key = `${e.from}->${e.to}`;
    let pts;
    if (tn.r <= fn.r) {
      // Loop edge
      const loopX = Math.max(fn.c, tn.c) + 6;
      pts = [[fn.c, fn.r + nodeR], [fn.c, fn.r + nodeR + 1],
             [loopX, fn.r + nodeR + 1], [loopX, tn.r - nodeR - 1],
             [tn.c, tn.r - nodeR - 1], [tn.c, tn.r - nodeR]];
    } else {
      const midR = (fn.r + tn.r) / 2;
      if (Math.abs(fn.c - tn.c) < 0.5) {
        pts = [[fn.c, fn.r + nodeR], [tn.c, tn.r - nodeR]];
      } else {
        pts = [[fn.c, fn.r + nodeR], [fn.c, midR], [tn.c, midR], [tn.c, tn.r - nodeR]];
      }
    }

    edges.push({
      id: pid++, from: e.from, to: e.to, key,
      pts, loop: tn.r <= fn.r, label: e.label || ''
    });
    edgeFill[key] = 0;
  });
}

function shortLabel(name) {
  return name.replace(/_/g, ' ').replace('chk', '?');
}

// ---- Partial path ----
function partialPath(pts, frac) {
  if (frac >= 1) return pts;
  let totalLen = 0;
  for (let i = 1; i < pts.length; i++)
    totalLen += Math.abs(pts[i][0]-pts[i-1][0]) + Math.abs(pts[i][1]-pts[i-1][1]);
  const fd = totalLen * frac;
  let acc = 0, fp = [[pts[0][0], pts[0][1]]];
  for (let i = 1; i < pts.length; i++) {
    const sl = Math.abs(pts[i][0]-pts[i-1][0]) + Math.abs(pts[i][1]-pts[i-1][1]);
    if (acc + sl >= fd) {
      const f = sl > 0 ? (fd - acc) / sl : 0;
      fp.push([pts[i-1][0]+(pts[i][0]-pts[i-1][0])*f, pts[i-1][1]+(pts[i][1]-pts[i-1][1])*f]);
      break;
    }
    fp.push([pts[i][0], pts[i][1]]);
    acc += sl;
  }
  return fp;
}

// ---- Drawing ----
function drawEdges() {
  cx.save(); cx.lineCap = 'round'; cx.lineJoin = 'round';
  edges.forEach(e => {
    const pts = e.pts;
    const fill = edgeFill[e.key] || 0;
    const active = fill > 0.01;

    // Base (forward = muted blue, loop = muted red, active = bright green)
    // Alpha bumped from 0.12 so the static topology is visible even when
    // no edge is animating -- previously forward edges were invisible on
    // dark background and users couldn't tell why a block lit up.
    cx.strokeStyle = active ? 'rgba(0,220,170,0.55)' : e.loop ? 'rgba(255,120,100,0.40)' : 'rgba(100,160,220,0.35)';
    cx.lineWidth = cs * (active ? 0.14 : 0.08);
    cx.beginPath();
    cx.moveTo(tx(pts[0][0]), ty(pts[0][1]));
    for (let i = 1; i < pts.length; i++) cx.lineTo(tx(pts[i][0]), ty(pts[i][1]));
    cx.stroke();

    // Filled portion (animation)
    if (fill > 0.01 && fill < 0.99) {
      const fp = partialPath(pts, fill);
      cx.strokeStyle = e.loop ? 'rgba(255,150,50,0.6)' : 'rgba(0,255,200,0.5)';
      cx.lineWidth = cs * 0.14;
      cx.beginPath();
      cx.moveTo(tx(fp[0][0]), ty(fp[0][1]));
      for (let i = 1; i < fp.length; i++) cx.lineTo(tx(fp[i][0]), ty(fp[i][1]));
      cx.stroke();
    }

    // Arrow
    if (pts.length >= 2 && cs >= 2) {
      const last = pts[pts.length-1], prev = pts[pts.length-2];
      const dx = last[0]-prev[0], dy = last[1]-prev[1];
      const len = Math.sqrt(dx*dx+dy*dy)||1;
      const ux = dx/len, uy = dy/len, sz = cs*0.5;
      const ax = tx(last[0]), ay = ty(last[1]);
      cx.fillStyle = active ? 'rgba(0,220,170,0.7)' : e.loop ? 'rgba(255,120,100,0.45)' : 'rgba(100,160,220,0.4)';
      cx.beginPath();
      cx.moveTo(ax, ay);
      cx.lineTo(ax-ux*sz+uy*sz*0.4, ay-uy*sz-ux*sz*0.4);
      cx.lineTo(ax-ux*sz-uy*sz*0.4, ay-uy*sz+ux*sz*0.4);
      cx.closePath(); cx.fill();
    }

    // Edge label
    if (e.label && cs >= 3) {
      const mid = pts[Math.floor(pts.length/2)];
      cx.font = `bold ${cs*0.45}px monospace`;
      cx.textAlign = 'center';
      cx.fillStyle = e.loop ? 'rgba(255,150,50,0.6)' : 'rgba(200,200,100,0.5)';
      cx.fillText(e.label, tx(mid[0]) + cs, ty(mid[1]));
    }
  });
  cx.restore();
}

function drawNodes() {
  nodes.forEach(n => {
    const x = tx(n.c), y = ty(n.r);
    const st = nodeAnim[n.id];
    const r = cs * 1.6;

    cx.save();

    // Glow
    if (st.status === 'running') {
      const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 180);
      cx.beginPath(); cx.arc(x, y, r * 2.2, 0, Math.PI * 2);
      cx.fillStyle = `rgba(0,220,170,${0.04 + 0.04*pulse})`; cx.fill();
    }

    cx.beginPath(); cx.arc(x, y, r, 0, Math.PI * 2);
    if (st.status === 'running') {
      cx.fillStyle = 'rgba(0,220,168,0.25)'; cx.strokeStyle = C.accent; cx.lineWidth = 2;
    } else if (st.status === 'done') {
      cx.fillStyle = 'rgba(0,220,168,0.15)'; cx.strokeStyle = C.accent; cx.lineWidth = 1;
    } else if (st.status === 'cycling') {
      const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 120);
      cx.fillStyle = `rgba(255,180,0,${0.15+0.1*pulse})`; cx.strokeStyle = '#ffb400'; cx.lineWidth = 1.5;
    } else {
      cx.fillStyle = 'rgba(30,42,58,0.4)'; cx.strokeStyle = C.border; cx.lineWidth = 0.6;
    }
    cx.fill(); cx.stroke();

    // Label
    if (cs >= 2) {
      const fs = Math.max(cs * 0.6, 6);
      cx.font = `${fs}px 'JetBrains Mono',monospace`;
      cx.textAlign = 'center'; cx.textBaseline = 'middle';
      cx.fillStyle = st.status === 'running' || st.status === 'cycling' ? '#fff' :
                     st.status === 'done' ? C.accent : C.textDim;
      cx.fillText(n.label, x, y + r + fs);
    }

    // Iteration counter
    if (n.iterations > 1 && st.iter > 0) {
      const fs = Math.max(cs * 0.45, 5);
      cx.font = `bold ${fs}px monospace`;
      cx.fillStyle = 'rgba(255,200,0,0.7)';
      cx.textAlign = 'center';
      cx.fillText(`${st.iter}/${st.maxIter}`, x, y - r - fs * 0.3);
    }

    cx.restore();
  });
}

function drawFires() {
  if (!fires.length) return;
  cx.save();
  fires.forEach(f => {
    const pp = partialPath(f.edge.pts, f.progress);
    const t = pp[pp.length-1];
    const x = tx(t[0]), y = ty(t[1]);
    cx.beginPath(); cx.arc(x, y, cs*1, 0, Math.PI*2);
    cx.fillStyle = f.edge.loop ? 'rgba(255,180,50,0.08)' : 'rgba(0,255,200,0.06)'; cx.fill();
    cx.beginPath(); cx.arc(x, y, cs*0.35, 0, Math.PI*2);
    cx.fillStyle = f.edge.loop ? '#ffb430' : '#00ffc8'; cx.fill();
    cx.beginPath(); cx.arc(x, y, cs*0.12, 0, Math.PI*2);
    cx.fillStyle = '#fff'; cx.fill();
  });
  cx.restore();
}

function draw() {
  cx.clearRect(0, 0, W, H);
  drawEdges();
  drawNodes();
  drawFires();
}

// ---- Animation ----
let lastT = 0;
let actionQueue = [];

function scheduleAction(delay, fn) {
  actionQueue.push({ time: performance.now() + delay, fn });
}

function fireTo(fromId, toId, speed) {
  const edge = edges.find(e => e.from === fromId && e.to === toId);
  if (!edge) return;
  edgeFill[edge.key] = 0;
  fires.push({ edge, progress: 0, speed: speed || 1.5 });
}

function addEvent(type, block, detail) {
  const el = document.getElementById('events');
  const d = document.createElement('div');
  d.className = 'ev';
  const ts = new Date().toLocaleTimeString();
  // Extract cost from detail string if present (e.g. "cost=$0.0034")
  let costHtml = '';
  if (detail) {
    const costMatch = detail.match(/cost=\$?([\d.]+)/);
    if (costMatch) costHtml = ` <span style="color:#f5d742;font-weight:bold">$${costMatch[1]}</span>`;
    const tokMatch = detail.match(/tokens=(\d+)/);
    if (tokMatch) costHtml += ` <span style="color:#888">${tokMatch[1]}tok</span>`;
  }
  d.innerHTML = `<span class="t">${ts}</span> <span class="e">${type}</span> <span class="b">${block}</span>${costHtml}`;
  el.prepend(d);
  if (el.children.length > 150) el.removeChild(el.lastChild);
}

// Track which rein.log events we already showed (by index) to avoid dupes
let lastEventIndex = 0;

function processStateEvents(events) {
  if (!events || !events.length) return;
  // Show only new events since last poll
  const newEvents = events.slice(lastEventIndex);
  lastEventIndex = events.length;
  for (const ev of newEvents) {
    addEvent(ev.type || '', ev.block || ev.detail || '', ev.detail || '');
  }
}

function animate(t) {
  const dt = Math.min((t - lastT) / 1000, 0.05); lastT = t;

  // Advance fires
  fires = fires.filter(f => {
    f.progress += f.speed * dt;
    edgeFill[f.edge.key] = Math.min(f.progress, 1);
    if (f.progress >= 1) {
      edgeFill[f.edge.key] = 1;
      return false;
    }
    return true;
  });

  // Process scheduled actions (copy-then-run to avoid losing new actions added during callbacks)
  const now = performance.now();
  const ready = [];
  const pending = [];
  for (const a of actionQueue) {
    if (now >= a.time) ready.push(a);
    else pending.push(a);
  }
  actionQueue = pending;
  ready.forEach(a => a.fn());

  draw();
  requestAnimationFrame(animate);
}

// ---- Test: simulate process execution with cycles ----
// ---- REIN letter bitmap ----
const _REIN_BM = {
  R:[[1,1,1,1,0],[1,0,0,0,1],[1,0,0,0,1],[1,1,1,1,0],[1,0,1,0,0],[1,0,0,1,0],[1,0,0,0,1]],
  E:[[1,1,1,1,1],[1,0,0,0,0],[1,0,0,0,0],[1,1,1,1,0],[1,0,0,0,0],[1,0,0,0,0],[1,1,1,1,1]],
  I:[[1,1,1,1,1],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[1,1,1,1,1]],
  N:[[1,0,0,0,1],[1,1,0,0,1],[1,0,1,0,1],[1,0,1,0,1],[1,0,0,1,1],[1,0,0,1,1],[1,0,0,0,1]],
};

function _buildReinLetters() {
  if (!nodes.length) return new Set();
  let minC=Infinity,maxC=-Infinity,minR=Infinity,maxR=-Infinity;
  nodes.forEach(n=>{if(n.c<minC)minC=n.c;if(n.c>maxC)maxC=n.c;if(n.r<minR)minR=n.r;if(n.r>maxR)maxR=n.r});
  const gCols=120,gRows=50,cW=(maxC-minC)/gCols,cH=(maxR-minR)/gRows;
  const sc=3,word='REIN',lw=5*sc,lh=7*sc,gap=2*sc;
  const tw=word.length*lw+(word.length-1)*gap;
  const sC=Math.floor((gCols-tw)/2),sR=Math.floor((gRows-lh)/2);
  const cells=new Set();
  for(let li=0;li<word.length;li++){const bm=_REIN_BM[word[li]],oC=sC+li*(lw+gap);
    for(let br=0;br<7;br++)for(let bc=0;bc<5;bc++)if(bm[br][bc])
      for(let r=0;r<sc;r++)for(let c=0;c<sc;c++)cells.add(`${sR+br*sc+r},${oC+bc*sc+c}`);}
  const set=new Set();
  nodes.forEach(n=>{const gc=Math.round((n.c-minC)/cW),gr=Math.round((n.r-minR)/cH);if(cells.has(`${gr},${gc}`))set.add(n.id)});
  return set;
}

function testWater() {
  // Reset all
  Object.keys(nodeAnim).forEach(id => {
    const n = nodes.find(nn => nn.id === id);
    nodeAnim[id] = { status: 'idle', iter: 0, maxIter: n ? n.iterations : 1 };
  });
  edges.forEach(e => edgeFill[e.key] = 0);
  fires = [];
  actionQueue = [];

  // Build forward dependency map
  const deps = {};      // node -> [source nodes] (forward only)
  const children = {};   // node -> [target edges] (forward only)
  const loopEdges = {};  // node -> [loop edges from this node]
  nodes.forEach(n => { deps[n.id] = []; children[n.id] = []; loopEdges[n.id] = []; });
  edges.forEach(e => {
    if (e.loop) {
      loopEdges[e.from].push(e);
    } else {
      if (!deps[e.to]) deps[e.to] = [];
      deps[e.to].push(e.from);
      children[e.from].push(e);
    }
  });

  const doneSet = new Set();
  const activatedSet = new Set();

  function checkAndRun(id) {
    if (activatedSet.has(id)) return;
    const na = nodeAnim[id];
    if (na.status !== 'idle') return;

    // All forward deps must be done
    if (!deps[id].every(d => doneSet.has(d))) return;

    activatedSet.add(id);
    const iters = na.maxIter;
    const ITER_TIME = 800;  // ms per iteration

    // Start running
    na.status = 'running';
    na.iter = 0;
    addEvent('start', id);

    let t = 0;

    for (let i = 0; i < iters; i++) {
      const iterNum = i;
      t += ITER_TIME;

      scheduleAction(t, () => {
        na.iter = iterNum + 1;

        if (iterNum < iters - 1) {
          // Mid-cycle: show cycling status, fire loop edges
          na.status = 'cycling';
          addEvent(`cycle ${iterNum+1}/${iters}`, id);

          loopEdges[id].forEach(le => {
            fireTo(id, le.to, 2);
            const target = nodeAnim[le.to];
            if (target) {
              target.status = 'cycling';
              scheduleAction(ITER_TIME * 0.6, () => {
                if (target.status === 'cycling') target.status = 'idle';
              });
            }
          });

          // Back to running for next iteration
          scheduleAction(ITER_TIME * 0.5, () => { na.status = 'running'; });
        } else {
          // Final iteration -- done
          na.status = 'done';
          doneSet.add(id);
          addEvent('done', id);

          // Fire to children and try activating them
          children[id].forEach(e => {
            fireTo(id, e.to, 1.5);
          });
          // After fire arrives, try children
          scheduleAction(800, () => {
            children[id].forEach(e => {
              checkAndRun(e.to);
            });
          });
        }
      });
    }
  }

  // For large grids (wall): wave down → tide out → REIN remains
  if (nodes.length > 200) {
    const letterNodes = _buildReinLetters();
    nodes.forEach(n => { n._isLetter = letterNodes.has(n.id); });

    const ranks = {};
    nodes.forEach(n => {
      const rank = Math.round(n.r);
      if (!ranks[rank]) ranks[rank] = [];
      ranks[rank].push(n);
    });
    const sorted = Object.keys(ranks).sort((a, b) => a - b);
    const totalRows = sorted.length;

    // Phase 1: white wave cascades top to bottom
    let ri = 0;
    const wave = setInterval(() => {
      if (ri >= totalRows) { clearInterval(wave); return; }
      const batch = Math.min(2, totalRows - ri);
      for (let b = 0; b < batch; b++) {
        ranks[sorted[ri + b]].forEach(n => {
          nodeAnim[n.id].status = 'running';
          // Fire incoming edge sparks (same as normal flow)
          edges.filter(e => e.to === n.id).forEach(e => {
            const src = nodes.find(nd => nd.id === e.from);
            if (src && (nodeAnim[src.id].status === 'done' || nodeAnim[src.id].status === 'running')) {
              edgeFill[e.key] = 0;
              fireTo(e.from, e.to, 2);
            }
          });
          if (!n._isLetter) {
            setTimeout(() => {
              nodeAnim[n.id].status = 'done';
              doneSet.add(n.id);
              // Fire outgoing edges
              edges.filter(e => e.from === n.id).forEach(e => {
                fireTo(e.from, e.to, e.loop ? 2.5 : 2);
              });
              // Random long loops back (10-50 rows up)
              if (Math.random() < 0.08) {
                const jumpBack = 10 + Math.floor(Math.random() * 40);
                const targetRow = Math.round(n.r) - jumpBack * 9;
                const target = nodes.find(t => Math.round(t.r) === Math.round(targetRow) && Math.abs(t.c - n.c) < 20);
                if (target) {
                  // Create temporary loop path and fire
                  const loopX = Math.max(n.c, target.c) + 6 + Math.random() * 8;
                  const nr = 2.5;
                  const tmpEdge = {
                    from: n.id, to: target.id, key: `_loop_${n.id}_${target.id}_${Date.now()}`,
                    loop: true, label: '',
                    pts: [
                      [n.c, n.r + nr], [n.c, n.r + nr + 1],
                      [loopX, n.r + nr + 1], [loopX, target.r - nr - 1],
                      [target.c, target.r - nr - 1], [target.c, target.r - nr]
                    ]
                  };
                  edges.push(tmpEdge);
                  edgeFill[tmpEdge.key] = 0;
                  fireTo(n.id, target.id, 1.2);
                }
              }
            }, 400 + Math.random() * 500);
          }
        });
      }
      ri += batch;
    }, 80);

    return;
  }

  // Start root nodes (no forward deps)
  const roots = nodes.filter(n => deps[n.id].length === 0);
  roots.forEach((n, i) => {
    scheduleAction(i * 300, () => checkAndRun(n.id));
  });
}

// ---- Tooltip ----
cv.addEventListener('mousemove', (e) => {
  const mx = e.clientX - canvasRect.left, my = e.clientY - canvasRect.top;
  let hit = null;
  const hitR = cs * 3;
  for (const n of nodes) {
    const dx = tx(n.c) - mx, dy = ty(n.r) - my;
    if (dx*dx + dy*dy < hitR*hitR) { hit = n; break; }
  }
  if (hit) {
    tip.style.display = 'block';
    tip.style.left = (e.clientX + 12) + 'px';
    tip.style.top = (e.clientY + 12) + 'px';
    document.getElementById('tip-name').textContent = hit.id;
    const st = nodeAnim[hit.id];
    document.getElementById('tip-info').innerHTML =
      `Status: ${st.status}<br>Iteration: ${st.iter}/${st.maxIter}` +
      (hit.block.prompt ? `<br>Prompt: ${hit.block.prompt}` : '');
    selected = hit.id;
  } else { tip.style.display = 'none'; selected = null; }
});
cv.addEventListener('mouseleave', () => { tip.style.display = 'none'; });

// ---- API ----
async function loadFlows() {
  try {
    const r = await fetch(API + '?action=flows');
    const d = await r.json();
    const sel = document.getElementById('flowSel');
    sel.innerHTML = '';
    (d.flows || []).forEach(f => {
      const o = document.createElement('option');
      o.value = f.id; o.textContent = f.id; sel.appendChild(o);
    });
    const params = new URLSearchParams(location.search);
    if (params.get('flow')) sel.value = params.get('flow');
    await loadFlow();
    await loadRuns();
  } catch(e) {}
}

async function loadFlow() {
  const flowId = document.getElementById('flowSel').value;
  if (!flowId) return;
  currentFlow = flowId;
  try {
    const r = await fetch(API + `?action=flow_schema&flow=${flowId}`);
    const d = await r.json();
    if (d.blocks) { buildGraph(d); draw(); }
  } catch(e) {}
}

async function loadRuns() {
  const sel = document.getElementById('runSel');
  sel.innerHTML = '<option value="">-- template --</option>';
  try {
    const r = await fetch(API + '?action=list');
    const d = await r.json();
    (d.tasks || []).filter(t => t.flow === currentFlow).slice(0, 20).forEach(t => {
      const o = document.createElement('option');
      o.value = t.id; o.textContent = t.id.replace('task-', '') + ' ' + (t.status || '');
      sel.appendChild(o);
    });
  } catch(e) {}
}

function viewRun() {
  const taskId = document.getElementById('runSel').value;
  if (!taskId) { loadFlow(); return; }
  currentTask = taskId;
  // Subscribe WS to this task
  if (ws && wsOk) ws.send(JSON.stringify({ type: 'subscribe', task_id: taskId }));
  fetch(API + `?action=state&task=${taskId}`)
    .then(r => r.json()).then(d => {
      if (d.blocks) {
        buildGraph(d);
        // Restore state from API
        d.blocks.forEach(b => {
          const na = nodeAnim[b.name];
          if (!na) return;
          if (b.status === 'completed' || b.status === 'done') {
            na.status = 'done';
            edges.filter(e => e.to === b.name).forEach(e => edgeFill[e.key] = 1);
          } else if (b.status === 'running') na.status = 'running';
          else if (b.status === 'failed') na.status = 'failed';
          if (b.run_count) na.iter = b.run_count;
        });
        draw();
      }
    });
  updateBadge('loading');
}

async function runFlow() {
  const flow = document.getElementById('flowSel').value;
  const topic = document.getElementById('topicIn').value || 'default';
  if (!flow) return;
  try {
    const r = await fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `action=start&flow=${encodeURIComponent(flow)}&question=${encodeURIComponent(topic)}`
    });
    const d = await r.json();
    if (d.task_id) { currentTask = d.task_id; loadFlow(); }
  } catch(e) {}
}

function updateBadge(s) {
  const b = document.getElementById('badge');
  b.textContent = (s || 'idle').toUpperCase();
}

// ---- WebSocket (live events from Rein daemon) ----
let ws = null, wsOk = false;

function connectWS() {
  try {
    ws = new WebSocket(WS_URL);
    ws.onopen = () => {
      wsOk = true;
      const el = document.getElementById('wsBar');
      el.textContent = 'WS: live'; el.style.color = C.accent;
      // Subscribe to current task
      if (currentTask) ws.send(JSON.stringify({ type: 'subscribe', task_id: currentTask }));
    };
    ws.onmessage = (e) => {
      // v5: WebSocket is used only as a connectivity heartbeat + event
      // log feed. Node statuses and edge fires are NEVER computed from
      // WS events -- that logic moved to applyStateDiff() driven by
      // the HTTP state poller (see below). This guarantees a single
      // source of truth and avoids the v4 class of bugs where a block
      // would "light up from nowhere" because WS event order did not
      // match actual data flow.
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'connected') return;
        const bn = msg.block || '', et = msg.type || '';
        if (bn) addEvent(et, bn);
      } catch (err) {}
    };
    ws.onclose = () => {
      wsOk = false;
      const el = document.getElementById('wsBar');
      el.textContent = 'WS: off'; el.style.color = C.red;
      setTimeout(connectWS, 5000);
    };
    ws.onerror = () => {};
  } catch (e) {}
}

// ---- State-diff poller (v5 core animation driver) ----
//
// The single source of truth for both block statuses and edge fires.
// Runs unconditionally every POLL_MS. For each polled state we compare
// the previous snapshot and fire animations only on real transitions.

// prevBlockState is hoisted at the top of the file (line 57) so
// buildGraph() can reset it without TDZ issues when the task switches.

function normalizeStatus(raw) {
  if (raw === 'completed') return 'done';
  if (raw === 'paused') return 'running';
  return raw || 'idle';
}

// v5: diff is driven by a TWO-PART state key per block:
//    { status, run_count }
//
// The issue with a naive status-only diff: when a routing gate
// completes and fires a loop back-edge, Rein cascades invalidation
// within a few milliseconds. By the time our poller (500ms interval)
// fetches state, the gate block has already been reset from
// `running -> done -> waiting` and we never observe `done`. Forward
// edges still work because their downstream is not reset.
//
// Using run_count instead: every time a block finishes, run_count
// gets incremented in Rein. If we observe run_count growing, the
// block completed at least once, regardless of its current status.
// We treat run_count growth as a "completion event" and fire the
// block's outgoing edges.

function applyStateDiff(newBlocks) {
  // Build new state map with both status and run_count per block
  const newState = {};
  for (const b of newBlocks) {
    newState[b.name] = {
      status: normalizeStatus(b.status),
      run_count: (b.run_count || 0),
    };
  }

  // First diff seeds without firing -- opening a task mid-run must not
  // replay historical edges.
  const isSeed = Object.keys(prevBlockState).length === 0;

  for (const name in newState) {
    const curr = newState[name];
    const prev = prevBlockState[name];

    // Update node status for the renderer
    const na = nodeAnim[name];
    if (na) {
      na.status = curr.status;
      na.iter = curr.run_count;
    }

    if (isSeed) continue;
    if (!prev) continue;

    // COMPLETION DETECTED: run_count grew. Fire all outgoing edges.
    // This catches both the happy-path completion (status: running ->
    // done) and the loop-gate completion (status: running -> done ->
    // waiting in a single Rein tick).
    const completed = (curr.run_count > prev.run_count)
      || (curr.status === 'done' && prev.status !== 'done');

    if (completed) {
      edges.filter(edge => edge.from === name).forEach(edge => {
        // Skip edges into permanently-skipped branches -- data never
        // actually flowed there.
        if (newState[edge.to] && newState[edge.to].status === 'skipped') return;
        // Reset then set edgeFill so loop iterations re-animate the
        // same edge (if fill was already 1 the renderer would skip
        // the animation gradient, we want it to flow again).
        edgeFill[edge.key] = 0.001;
        fireTo(name, edge.to, edge.loop ? 2.5 : 2);
      });
    }
  }

  prevBlockState = newState;

  // Header badge from aggregate status
  const statuses = Object.values(newState).map(x => x.status);
  const allDone = statuses.every(s => s === 'done' || s === 'skipped');
  const anyFailed = statuses.some(s => s === 'failed');
  const anyRunning = statuses.some(s => s === 'running');
  if (anyFailed) updateBadge('failed');
  else if (allDone) updateBadge('completed');
  else if (anyRunning) updateBadge('running');
}

setInterval(() => {
  if (!currentTask) return;
  fetch(API + `?action=state&task=${currentTask}`)
    .then(r => r.json())
    .then(d => {
      if (d && d.blocks) applyStateDiff(d.blocks);
      if (d && d.events) processStateEvents(d.events);
    })
    .catch(() => {});
}, POLL_MS);

// ---- Flow selector ----
document.getElementById('flowSel').addEventListener('change', () => { loadFlow(); loadRuns(); });

// ---- Minimal embed mode (?minimal=1) ----
// Strips topbar/side panel via body class, auto-loads the ?flow=X flow,
// and if ?task=Y is set, subscribes to that specific task. Used by
// flow-factory.html to tile many boards into a grid via iframes.
//
// ?autorun=1 makes the iframe POST /api-flow.php?action=start to
// create a fresh task for the flow on load. Useful for factory-style
// demos where every iframe should show live animation from zero --
// otherwise, if the task finished before the page loaded, the state
// poller would see everything already 'done' and skip animation.
(async function initMinimal() {
  const params = new URLSearchParams(location.search);
  if (params.get('minimal') !== '1') return;
  document.body.classList.add('minimal');
  const title = params.get('title');
  const color = params.get('color');
  if (title) {
    const badge = document.createElement('div');
    badge.className = 'factory-title';
    badge.textContent = title;
    if (color) badge.style.setProperty('--category-color', color);
    document.body.appendChild(badge);
  }

  async function adoptTask(taskId) {
    currentTask = taskId;
    if (typeof ws !== 'undefined' && ws && wsOk) {
      try { ws.send(JSON.stringify({ type: 'subscribe', task_id: taskId })); } catch {}
    }
    try {
      const r = await fetch(API + `?action=state&task=${taskId}`);
      const d = await r.json();
      if (d && d.blocks) { buildGraph(d); draw(); }
    } catch {}
  }

  async function autorun(flow) {
    // Fire a fresh task via the existing start endpoint, then adopt it.
    try {
      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          action: 'start',
          flow: flow,
          question: 'factory demo',
        }),
      });
      const data = await res.json();
      if (data && data.task_id) {
        await adoptTask(data.task_id);
        return true;
      }
    } catch {}
    return false;
  }

  const autoTask = params.get('task');
  const autoRun = params.get('autorun') === '1';
  const flowParam = params.get('flow');

  const autoTest = params.get('test') === '1';

  // In minimal mode, load schema directly (loadFlows is skipped)
  if (flowParam) {
    currentFlow = flowParam;
    document.getElementById('flowSel').value = flowParam;
    try {
      const r = await fetch(API + '?action=flow_schema&flow=' + flowParam);
      const d = await r.json();
      if (d && d.blocks) { buildGraph(d); draw(); }
    } catch {}
  }

  // Run immediately (schema already loaded above)
  console.log('[FB6] autoTest=', autoTest, 'nodes=', nodes.length, 'autoRun=', autoRun);
  if (autoTest) {
    // Wait for nodes if schema is still loading
    if (nodes.length === 0) {
      await new Promise(r => { const c = setInterval(() => { if (nodes.length > 0) { clearInterval(c); r(); } }, 100); });
    }
    console.log('[FB6] testWater, nodes=', nodes.length);
    testWater();
  } else if (autoRun && flowParam) {
    await autorun(flowParam);
  } else if (autoTask) {
    await adoptTask(autoTask);
  }
})();

// ---- Init ----
addEventListener('resize', resize);
resize();
const _isMinimal = new URLSearchParams(location.search).get('minimal') === '1';
if (!_isMinimal) {
  loadFlows();
  connectWS();
}
requestAnimationFrame(animate);
