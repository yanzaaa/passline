"""Passline Mission Control — dashboard HTML/CSS/JS as a Python string constant."""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Passline — Mission Control</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* ── Reset & tokens ─────────────────────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:      #080b0f;
  --surface: #0e1116;
  --card:    #12161d;
  --border:  #1c2130;
  --border2: #252d3d;
  --text:    #c8d0e0;
  --muted:   #5a6478;
  --dim:     #3a4255;
  --red:     #ff3b3b;
  --amber:   #f5a623;
  --green:   #00d26a;
  --blue:    #4a9eff;
  --violet:  #9b72ff;
  --red-dim: rgba(255,59,59,.12);
  --amber-dim:rgba(245,166,35,.12);
  --green-dim:rgba(0,210,106,.12);
  --blue-dim: rgba(74,158,255,.12);
  --font:    'Inter', system-ui, sans-serif;
  --mono:    'JetBrains Mono', 'Fira Code', monospace;
  --r:       6px;
  --r2:      10px;
}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:var(--font);font-size:14px;overflow-x:hidden}

/* ── Scrollbars ──────────────────────────────────────────────────────── */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:var(--surface)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

/* ── Layout ──────────────────────────────────────────────────────────── */
.topbar{
  display:flex;align-items:center;gap:16px;
  padding:10px 20px;
  background:var(--surface);
  border-bottom:1px solid var(--border);
  position:sticky;top:0;z-index:100;
  flex-wrap:wrap;
}
.logo{
  font-size:17px;font-weight:700;letter-spacing:.04em;
  color:#fff;display:flex;align-items:center;gap:8px;
}
.logo-dot{width:8px;height:8px;border-radius:50%;background:var(--green);
  box-shadow:0 0 8px var(--green);animation:pulse 2s ease infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}
.topbar-spacer{flex:1}
.delivery-window{
  display:flex;align-items:center;gap:8px;
  font-family:var(--mono);font-size:13px;
  color:var(--muted);
}
.delivery-window span{color:var(--text)}
#countdown{
  font-family:var(--mono);font-size:15px;font-weight:500;
  color:var(--amber);letter-spacing:.08em;
  min-width:70px;text-align:right;
}
.holds-pill{
  display:flex;align-items:center;gap:6px;
  padding:4px 12px;border-radius:20px;
  background:var(--red-dim);border:1px solid rgba(255,59,59,.3);
  font-size:12px;font-weight:600;color:var(--red);
  transition:all .3s;
}
.holds-pill.zero{background:var(--green-dim);border-color:rgba(0,210,106,.3);color:var(--green)}
#holds-count{font-size:15px;font-family:var(--mono)}

.main{
  display:grid;
  grid-template-columns:300px 1fr 320px;
  gap:0;
  height:calc(100vh - 57px);
  overflow:hidden;
}
.col{
  border-right:1px solid var(--border);
  overflow-y:auto;
  padding:16px;
  display:flex;flex-direction:column;gap:12px;
}
.col:last-child{border-right:none}
.col-header{
  font-size:10px;font-weight:600;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);
  padding-bottom:10px;border-bottom:1px solid var(--border);
}

/* ── Cards ───────────────────────────────────────────────────────────── */
.card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r2);padding:14px;
}

/* ── Drop zone ───────────────────────────────────────────────────────── */
.dropzone{
  border:2px dashed var(--border2);
  border-radius:var(--r2);padding:20px;
  text-align:center;cursor:pointer;
  transition:all .2s;
  background:var(--card);
}
.dropzone:hover,.dropzone.drag-over{
  border-color:var(--blue);background:var(--blue-dim);
}
.dropzone-icon{font-size:26px;margin-bottom:8px;color:var(--dim)}
.dropzone-label{font-size:13px;color:var(--muted)}
.dropzone-sub{font-size:11px;color:var(--dim);margin-top:4px}
input[type=file]{display:none}

/* ── Demo chips ──────────────────────────────────────────────────────── */
.demo-chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{
  padding:5px 12px;border-radius:20px;font-size:12px;font-weight:500;
  border:1px solid var(--border2);background:var(--surface);
  color:var(--text);cursor:pointer;transition:all .2s;
  font-family:var(--mono);
}
.chip:hover{border-color:var(--blue);color:var(--blue);background:var(--blue-dim)}

/* ── Delivery cards ──────────────────────────────────────────────────── */
.delivery-card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:12px;
  transition:border-color .3s;
}
.delivery-card.hold{border-color:rgba(255,59,59,.5)}
.delivery-card.repairing{border-color:rgba(245,166,35,.4)}
.delivery-card.cleared{border-color:rgba(0,210,106,.4)}

.dc-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.dc-id{font-family:var(--mono);font-size:12px;font-weight:500;color:#fff}
.dc-lang{font-size:11px;color:var(--muted);font-family:var(--mono)}
.dc-meta{font-size:11px;color:var(--muted);margin-bottom:8px}

.status-badge{
  padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;
  letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;
}
.badge-hold{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,59,59,.3)}
.badge-repairing{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,166,35,.3)}
.badge-cleared{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,210,106,.3)}
.badge-pending{background:rgba(74,158,255,.08);color:var(--blue);border:1px solid rgba(74,158,255,.2)}

.progress-bar{
  height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin-top:6px;
}
.progress-fill{height:100%;background:var(--amber);border-radius:2px;width:0%;
  transition:width .4s ease;box-shadow:0 0 6px var(--amber)}

/* ── Break button ────────────────────────────────────────────────────── */
.break-btn{
  width:100%;padding:12px;border-radius:var(--r);
  background:rgba(255,59,59,.1);border:1px solid rgba(255,59,59,.3);
  color:var(--red);font-size:13px;font-weight:700;letter-spacing:.06em;
  cursor:pointer;transition:all .2s;text-transform:uppercase;
}
.break-btn:hover{background:rgba(255,59,59,.2);border-color:var(--red)}

/* ── Demo controls ───────────────────────────────────────────────────── */
.demo-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.ctrl-btn{
  padding:7px 16px;border-radius:var(--r);font-size:12px;font-weight:600;
  cursor:pointer;border:1px solid;transition:all .2s;letter-spacing:.03em;
}
.btn-play{
  background:var(--green-dim);border-color:rgba(0,210,106,.4);color:var(--green);
}
.btn-play:hover{background:rgba(0,210,106,.25)}
.btn-stop{
  background:var(--red-dim);border-color:rgba(255,59,59,.3);color:var(--red);
}
.btn-stop:hover{background:rgba(255,59,59,.2)}
.btn-loop{
  background:var(--surface);border-color:var(--border2);color:var(--muted);
}
.btn-loop.active{background:var(--blue-dim);border-color:rgba(74,158,255,.4);color:var(--blue)}
.sse-status{
  font-size:10px;font-weight:600;letter-spacing:.06em;display:flex;align-items:center;gap:5px;
}
.sse-dot{width:6px;height:6px;border-radius:50%;background:var(--muted)}
.sse-dot.live{background:var(--green);box-shadow:0 0 5px var(--green)}
.sse-dot.reconnecting{background:var(--amber);animation:pulse 1s infinite}

/* ── Station tiles ───────────────────────────────────────────────────── */
.stations-grid{
  display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;
}
.station-tile{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:10px 12px;
  transition:border-color .3s;
}
.station-tile.working{
  border-color:rgba(245,166,35,.5);
  background:rgba(245,166,35,.04);
  animation:station-pulse 1.5s ease infinite;
}
.station-tile.offline{opacity:.45}
@keyframes station-pulse{0%,100%{box-shadow:none}50%{box-shadow:0 0 10px rgba(245,166,35,.2)}}

.station-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.station-name{font-size:12px;font-weight:600;color:#fff}
.lamp{width:10px;height:10px;border-radius:50%;transition:all .4s;flex-shrink:0}
.lamp-ready{background:var(--green);box-shadow:0 0 7px var(--green)}
.lamp-working{background:var(--amber);box-shadow:0 0 9px var(--amber);animation:pulse 1s infinite}
.lamp-offline{background:var(--dim)}
.station-role{font-size:10px;color:var(--muted);line-height:1.4;margin-bottom:6px}
.station-counter{font-family:var(--mono);font-size:11px;color:var(--dim)}
.station-counter span{color:var(--blue)}

/* ── Heat strip ──────────────────────────────────────────────────────── */
.heat-strip-wrap{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:12px;
}
.heat-strip-label{
  font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);margin-bottom:10px;display:flex;justify-content:space-between;
}
.heat-strip{
  display:flex;gap:2px;align-items:flex-end;min-height:40px;
  flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px;
}
.heat-cue{
  width:8px;min-width:8px;border-radius:2px 2px 0 0;
  transition:all .3s ease;cursor:pointer;position:relative;
}
.heat-cue:hover::after{
  content:attr(data-tip);
  position:absolute;bottom:calc(100% + 4px);left:50%;transform:translateX(-50%);
  background:var(--card);border:1px solid var(--border2);
  padding:3px 7px;border-radius:4px;font-size:10px;white-space:nowrap;
  color:var(--text);z-index:50;pointer-events:none;font-family:var(--mono);
}
.heat-legend{display:flex;gap:12px;margin-top:8px;font-size:10px;color:var(--muted)}
.hl-item{display:flex;align-items:center;gap:4px}
.hl-dot{width:8px;height:8px;border-radius:2px}

/* ── Diff panel ──────────────────────────────────────────────────────── */
.diff-panel{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:12px;
}
.diff-label{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);margin-bottom:10px}
.diff-cols{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.diff-side{background:var(--card);border-radius:var(--r);padding:10px}
.diff-side-label{font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  margin-bottom:6px}
.diff-before .diff-side-label{color:var(--red)}
.diff-after .diff-side-label{color:var(--green)}
.diff-text{font-family:var(--mono);font-size:11px;color:var(--text);line-height:1.5;
  min-height:40px}

/* ── Air-traffic log ─────────────────────────────────────────────────── */
.log-feed{
  flex:1;min-height:300px;
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);overflow-y:auto;
  font-family:var(--mono);font-size:11px;
  display:flex;flex-direction:column;
  padding:8px 0;
}
.log-entry{
  padding:4px 12px;line-height:1.5;border-bottom:1px solid rgba(255,255,255,.03);
  white-space:pre-wrap;word-break:break-all;transition:background .1s;
}
.log-entry:hover{background:rgba(255,255,255,.03)}
.log-entry.violation{color:var(--red)}
.log-entry.repaired {color:var(--green)}
.log-entry.lifecycle{color:var(--blue)}
.log-entry.station  {color:var(--muted)}
.log-entry.approval {color:var(--amber)}
.log-ts{color:var(--dim);margin-right:8px;font-size:10px}
.log-type{font-weight:600;margin-right:6px;min-width:85px;display:inline-block}

/* ── Approval card ───────────────────────────────────────────────────── */
.approval-card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r2);padding:16px;
  transition:all .4s;
}
.approval-card.active{
  border-color:rgba(245,166,35,.6);
  background:rgba(245,166,35,.05);
  box-shadow:0 0 20px rgba(245,166,35,.1);
}
.approval-title{font-size:13px;font-weight:700;color:var(--text);margin-bottom:6px}
.approval-sub{font-size:11px;color:var(--muted);margin-bottom:14px;line-height:1.5}
.approval-btns{display:flex;gap:8px}
.btn-approve{
  flex:1;padding:9px;border-radius:var(--r);
  background:var(--green-dim);border:1px solid rgba(0,210,106,.4);color:var(--green);
  font-size:12px;font-weight:700;cursor:pointer;letter-spacing:.04em;transition:all .2s;
}
.btn-approve:hover{background:rgba(0,210,106,.2)}
.btn-reject{
  flex:1;padding:9px;border-radius:var(--r);
  background:var(--red-dim);border:1px solid rgba(255,59,59,.3);color:var(--red);
  font-size:12px;font-weight:700;cursor:pointer;letter-spacing:.04em;transition:all .2s;
}
.btn-reject:hover{background:rgba(255,59,59,.2)}

/* ── Mobile ──────────────────────────────────────────────────────────── */
@media(max-width:900px){
  .main{grid-template-columns:1fr;height:auto;overflow-y:auto}
  .col{border-right:none;border-bottom:1px solid var(--border);max-height:none;overflow-y:visible}
  .stations-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:480px){
  .stations-grid{grid-template-columns:1fr}
  .diff-cols{grid-template-columns:1fr}
}
</style>
</head>
<body>

<!-- ── Top bar ────────────────────────────────────────────────────── -->
<header class="topbar">
  <div class="logo">
    <div class="logo-dot"></div>
    PASSLINE
    <span style="color:var(--muted);font-weight:400;font-size:13px">/ Mission Control</span>
  </div>
  <div class="topbar-spacer"></div>
  <div class="delivery-window">
    <span>DELIVERY WINDOW</span>
    <div id="countdown">4:00:00</div>
  </div>
  <div class="holds-pill zero" id="holds-pill">
    <span>HOLDS</span>
    <span id="holds-count">0</span>
  </div>
  <div class="sse-status" id="sse-status">
    <div class="sse-dot" id="sse-dot"></div>
    <span id="sse-label">CONNECTING</span>
  </div>
</header>

<!-- ── Three-column main ─────────────────────────────────────────── -->
<main class="main">

  <!-- ── LEFT: Deliveries ──────────────────────────────────────── -->
  <section class="col" id="col-left">
    <div class="col-header">Deliveries on the Board</div>

    <!-- Drop zone -->
    <div class="dropzone" id="dropzone" title="Drop an SRT file or click to browse">
      <div class="dropzone-icon">⬇</div>
      <div class="dropzone-label">Drop subtitle file here</div>
      <div class="dropzone-sub">or click to browse · triggers demo</div>
      <input type="file" id="file-input" accept=".srt,.vtt,.ass,.ssa">
    </div>

    <!-- Demo chips -->
    <div class="card" style="padding:10px 14px">
      <div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px">Demo Files</div>
      <div class="demo-chips">
        <div class="chip" onclick="triggerDemo('DEMO-EN-001','en-US')">EN-001</div>
        <div class="chip" onclick="triggerDemo('DEMO-FR-002','fr-FR')">FR-002</div>
        <div class="chip" onclick="triggerDemo('DEMO-JA-003','ja-JP')">JA-003</div>
      </div>
    </div>

    <!-- Demo controls -->
    <div class="card" style="padding:10px 14px">
      <div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px">Demo Replay</div>
      <div class="demo-controls">
        <button class="ctrl-btn btn-play" onclick="startReplay(false)">▶ PLAY</button>
        <button class="ctrl-btn btn-stop" onclick="stopReplay()">■ STOP</button>
        <button class="ctrl-btn btn-loop" id="btn-loop" onclick="toggleLoop()">↺ LOOP</button>
      </div>
    </div>

    <!-- Delivery cards container -->
    <div id="delivery-cards"></div>

    <div style="flex:1"></div>
    <button class="break-btn" onclick="alert('BREAK THIS FILE — placeholder')">⚡ BREAK THIS FILE</button>
  </section>

  <!-- ── CENTER: Agent Stations ────────────────────────────────── -->
  <section class="col" id="col-center">
    <div class="col-header">Agent Stations</div>

    <!-- Station grid -->
    <div class="stations-grid">
      <div class="station-tile" id="st-timing">
        <div class="station-top">
          <span class="station-name">Timing</span>
          <div class="lamp lamp-ready" id="lamp-timing"></div>
        </div>
        <div class="station-role">Validates cue timing, gaps, and overlaps</div>
        <div class="station-counter">Jobs: <span id="cnt-timing">0</span></div>
      </div>
      <div class="station-tile" id="st-format">
        <div class="station-top">
          <span class="station-name">Format</span>
          <div class="lamp lamp-ready" id="lamp-format"></div>
        </div>
        <div class="station-role">Checks line length and cue structure</div>
        <div class="station-counter">Jobs: <span id="cnt-format">0</span></div>
      </div>
      <div class="station-tile" id="st-language">
        <div class="station-top">
          <span class="station-name">Language</span>
          <div class="lamp lamp-ready" id="lamp-language"></div>
        </div>
        <div class="station-role">Readability and naturalness review</div>
        <div class="station-counter">Jobs: <span id="cnt-language">0</span></div>
      </div>
      <div class="station-tile" id="st-fixer">
        <div class="station-top">
          <span class="station-name">Fixer</span>
          <div class="lamp lamp-ready" id="lamp-fixer"></div>
        </div>
        <div class="station-role">Repairs flagged cues with LLM suggestions</div>
        <div class="station-counter">Jobs: <span id="cnt-fixer">0</span></div>
      </div>
      <div class="station-tile" id="st-verifier">
        <div class="station-top">
          <span class="station-name">Verifier</span>
          <div class="lamp lamp-ready" id="lamp-verifier"></div>
        </div>
        <div class="station-role">Confirms repairs meet spec before sign-off</div>
        <div class="station-counter">Jobs: <span id="cnt-verifier">0</span></div>
      </div>
      <div class="station-tile" id="st-vendor_health">
        <div class="station-top">
          <span class="station-name">Vendor Health</span>
          <div class="lamp lamp-ready" id="lamp-vendor_health"></div>
        </div>
        <div class="station-role">Checks delivery channel readiness</div>
        <div class="station-counter">Jobs: <span id="cnt-vendor_health">0</span></div>
      </div>
    </div>

    <!-- Reading-speed heat strip -->
    <div class="heat-strip-wrap">
      <div class="heat-strip-label">
        <span>Reading Speed — CPS per Cue</span>
        <span id="heat-cue-count" style="color:var(--dim)">—</span>
      </div>
      <div class="heat-strip" id="heat-strip">
        <span style="color:var(--dim);font-size:11px;align-self:center;padding:4px 0">
          Awaiting cue analysis…
        </span>
      </div>
      <div class="heat-legend">
        <div class="hl-item"><div class="hl-dot" style="background:#2dba6c"></div>Safe (&lt;12)</div>
        <div class="hl-item"><div class="hl-dot" style="background:#8ab820"></div>Moderate (12–15)</div>
        <div class="hl-item"><div class="hl-dot" style="background:#f5a623"></div>Fast (15–20)</div>
        <div class="hl-item"><div class="hl-dot" style="background:#ff3b3b"></div>Over limit (&gt;20)</div>
      </div>
    </div>

    <!-- Before/After diff panel -->
    <div class="diff-panel">
      <div class="diff-label">Before / After — Last Repair</div>
      <div class="diff-cols">
        <div class="diff-side diff-before">
          <div class="diff-side-label">Before</div>
          <div class="diff-text" id="diff-before">—</div>
        </div>
        <div class="diff-side diff-after">
          <div class="diff-side-label">After</div>
          <div class="diff-text" id="diff-after">—</div>
        </div>
      </div>
    </div>
  </section>

  <!-- ── RIGHT: Air-traffic log ────────────────────────────────── -->
  <section class="col" id="col-right">
    <div class="col-header">Air-Traffic Log</div>

    <!-- Live event feed -->
    <div class="log-feed" id="log-feed"></div>

    <!-- Human approval -->
    <div class="approval-card" id="approval-card">
      <div class="approval-title">🔔 Human Approval Required</div>
      <div class="approval-sub" id="approval-sub">
        Waiting for approval request…
      </div>
      <div class="approval-btns">
        <button class="btn-approve" onclick="handleApproval('approve')">✓ APPROVE</button>
        <button class="btn-reject" onclick="handleApproval('reject')">✗ REJECT</button>
      </div>
    </div>
  </section>
</main>

<script>
/* ═══════════════════════════════════════════════════════════════════
   Passline Mission Control — client JS
   All UI state is driven purely by event_type dispatch.
   ═══════════════════════════════════════════════════════════════════ */

// ── State ────────────────────────────────────────────────────────────
const seen      = new Set();   // event_ids processed — prevents duplicates on reconnect
const deliveries = {};          // delivery_id → { card, violations, repairs, status }
let holdsCount  = 0;
let loopMode    = false;
let sseFailures = 0;
let pollingTimer= null;
let countdownS  = 14400;       // 4-hour delivery window
let progressTimers = {};

// ── Countdown ────────────────────────────────────────────────────────
setInterval(() => {
  if (countdownS > 0) countdownS--;
  const h = Math.floor(countdownS / 3600);
  const m = Math.floor((countdownS % 3600) / 60);
  const s = countdownS % 60;
  document.getElementById('countdown').textContent =
    `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  if (countdownS < 600) {
    document.getElementById('countdown').style.color = 'var(--red)';
  }
}, 1000);

// ── SSE status indicator ─────────────────────────────────────────────
function setSseStatus(state) { // 'live' | 'reconnecting' | 'polling' | 'offline'
  const dot   = document.getElementById('sse-dot');
  const label = document.getElementById('sse-label');
  dot.className = 'sse-dot';
  if (state === 'live')         { dot.classList.add('live');         label.textContent = 'LIVE'; }
  else if (state === 'reconnecting') { dot.classList.add('reconnecting'); label.textContent = 'RECONNECTING'; }
  else if (state === 'polling') { label.textContent = 'POLLING'; }
  else                          { label.textContent = 'OFFLINE'; }
}

// ── Event dispatch table ─────────────────────────────────────────────
const HANDLERS = {
  'subtitle.submitted': (ev) => { addDeliveryCard(ev);           addLog(ev, 'lifecycle'); },
  'station.working':    (ev) => { setLamp(ev.details.station_id, 'working');  addLog(ev, 'station'); },
  'station.ready':      (ev) => { setLamp(ev.details.station_id, 'ready');    addLog(ev, 'station'); },
  'qc.violation':       (ev) => { markViolation(ev);             addLog(ev, 'violation'); updateHolds(); },
  'qc.repaired':        (ev) => { markRepaired(ev);              addLog(ev, 'repaired'); updateDiff(ev); },
  'cue.analysis':       (ev) => { renderHeatStrip(ev.details.cues || []); addLog(ev, 'lifecycle'); },
  'approval.required':  (ev) => { showApproval(ev);              addLog(ev, 'approval'); },
  'delivery.passed':    (ev) => { markCleared(ev);               addLog(ev, 'lifecycle'); updateHolds(); },
};

function dispatch(ev) {
  if (seen.has(ev.event_id)) return;  // deduplicate (backfill replay on reconnect)
  seen.add(ev.event_id);
  const handler = HANDLERS[ev.event_type];
  if (handler) handler(ev);
}

// ── SSE connection ───────────────────────────────────────────────────
function connectSSE() {
  if (sseFailures >= 3) {
    setSseStatus('polling');
    startPolling();
    return;
  }
  setSseStatus('reconnecting');
  const src = new EventSource('/api/events');
  src.onopen = () => { setSseStatus('live'); sseFailures = 0; };
  src.onmessage = (e) => {
    try { dispatch(JSON.parse(e.data)); } catch(ex) { console.warn('bad event', ex); }
  };
  src.onerror = () => {
    src.close();
    sseFailures++;
    setSseStatus('reconnecting');
    setTimeout(connectSSE, 3000);
  };
}

// ── Polling fallback ─────────────────────────────────────────────────
function startPolling() {
  if (pollingTimer) return;
  pollingTimer = setInterval(async () => {
    try {
      const r = await fetch('/api/history');
      const events = await r.json();
      events.forEach(dispatch);
    } catch(e) {}
  }, 2000);
}

// ── Delivery cards ────────────────────────────────────────────────────
function addDeliveryCard(ev) {
  if (deliveries[ev.delivery_id]) return;
  const d = ev.details || {};
  const el = document.createElement('div');
  el.className = 'delivery-card pending';
  el.id = `dc-${CSS.escape(ev.delivery_id)}`;
  el.innerHTML = `
    <div class="dc-header">
      <span class="dc-id">${esc(ev.delivery_id)}</span>
      <span class="status-badge badge-pending" id="badge-${CSS.escape(ev.delivery_id)}">SUBMITTED</span>
    </div>
    <div class="dc-meta dc-lang">${esc(ev.language)} · ${d.cue_count || '?'} cues</div>
    <div class="progress-bar"><div class="progress-fill" id="prog-${CSS.escape(ev.delivery_id)}"></div></div>
  `;
  document.getElementById('delivery-cards').prepend(el);
  deliveries[ev.delivery_id] = { violations: 0, repairs: 0, status: 'submitted' };
}

function getCard(id)  { return document.getElementById(`dc-${CSS.escape(id)}`); }
function getBadge(id) { return document.getElementById(`badge-${CSS.escape(id)}`); }
function getProg(id)  { return document.getElementById(`prog-${CSS.escape(id)}`); }

function markViolation(ev) {
  const s = deliveries[ev.delivery_id];
  if (!s) return;
  s.violations++;
  s.status = 'hold';
  const card  = getCard(ev.delivery_id);
  const badge = getBadge(ev.delivery_id);
  if (card)  { card.className  = 'delivery-card hold'; }
  if (badge) { badge.className = 'status-badge badge-hold'; badge.textContent = `HOLD (${s.violations})`; }
}

function markRepaired(ev) {
  const s = deliveries[ev.delivery_id];
  if (!s) return;
  s.repairs++;
  s.status = 'repairing';
  const card  = getCard(ev.delivery_id);
  const badge = getBadge(ev.delivery_id);
  const prog  = getProg(ev.delivery_id);
  if (card)  { card.className  = 'delivery-card repairing'; }
  if (badge) { badge.className = 'status-badge badge-repairing'; badge.textContent = 'REPAIRING'; }
  // Animate progress: each repair advances toward 90%
  if (prog) {
    const pct = Math.min(90, s.repairs * 35);
    prog.style.width = pct + '%';
  }
}

function markCleared(ev) {
  const s = deliveries[ev.delivery_id];
  if (!s) return;
  s.status = 'cleared';
  const card  = getCard(ev.delivery_id);
  const badge = getBadge(ev.delivery_id);
  const prog  = getProg(ev.delivery_id);
  if (card)  { card.className  = 'delivery-card cleared'; }
  if (badge) { badge.className = 'status-badge badge-cleared'; badge.textContent = 'CLEARED FOR DELIVERY'; }
  if (prog)  { prog.style.width = '100%'; prog.style.background = 'var(--green)'; }
}

// ── Holds counter ────────────────────────────────────────────────────
function updateHolds() {
  holdsCount = Object.values(deliveries).filter(d => d.status === 'hold').length;
  const pill  = document.getElementById('holds-pill');
  const count = document.getElementById('holds-count');
  count.textContent = holdsCount;
  pill.className = holdsCount === 0 ? 'holds-pill zero' : 'holds-pill';
}

// ── Station lamps ────────────────────────────────────────────────────
const stationCounters = {};

function setLamp(stationId, state) {
  const lamp = document.getElementById(`lamp-${stationId}`);
  const tile = document.getElementById(`st-${stationId}`);
  if (!lamp || !tile) return;
  lamp.className = 'lamp';
  tile.className = 'station-tile';
  if (state === 'working') {
    lamp.classList.add('lamp-working');
    tile.classList.add('working');
    stationCounters[stationId] = (stationCounters[stationId] || 0) + 1;
    const cnt = document.getElementById(`cnt-${stationId}`);
    if (cnt) cnt.textContent = stationCounters[stationId];
  } else if (state === 'ready') {
    lamp.classList.add('lamp-ready');
  } else {
    lamp.classList.add('lamp-offline');
    tile.classList.add('offline');
  }
}

// ── Heat strip ───────────────────────────────────────────────────────
function cpsColor(cps) {
  if (cps < 12)  return '#2dba6c';  // green
  if (cps < 15)  return '#8ab820';  // yellow-green
  if (cps < 20)  return '#f5a623';  // amber
  return '#ff3b3b';                  // red — over limit
}

function cpsHeight(cps) {
  // Normalize 0–25 CPS to 8–48px height
  const h = Math.max(8, Math.min(48, (cps / 25) * 48));
  return Math.round(h);
}

function renderHeatStrip(cues) {
  const strip = document.getElementById('heat-strip');
  const countEl = document.getElementById('heat-cue-count');
  if (!cues || cues.length === 0) return;
  strip.innerHTML = '';
  cues.forEach(c => {
    const div = document.createElement('div');
    div.className = 'heat-cue';
    div.style.height = cpsHeight(c.cps) + 'px';
    div.style.background = cpsColor(c.cps);
    div.title = `Cue ${c.index}: ${c.cps} CPS`;
    div.setAttribute('data-tip', `#${c.index} · ${c.cps} CPS`);
    strip.appendChild(div);
  });
  countEl.textContent = `${cues.length} cues`;
}

// ── Log feed ─────────────────────────────────────────────────────────
const LOG_TYPES = {
  'subtitle.submitted': ['lifecycle', 'SUBMITTED '],
  'station.working':    ['station',   'STATION   '],
  'station.ready':      ['station',   'STATION   '],
  'qc.violation':       ['violation', 'VIOLATION '],
  'qc.repaired':        ['repaired',  'REPAIRED  '],
  'cue.analysis':       ['lifecycle', 'ANALYSIS  '],
  'approval.required':  ['approval',  'APPROVAL  '],
  'delivery.passed':    ['lifecycle', 'CLEARED   '],
};

function addLog(ev, cls) {
  const feed = document.getElementById('log-feed');
  const ts   = new Date(ev.timestamp).toISOString().substr(11, 12);
  const [, typeLabel] = LOG_TYPES[ev.event_type] || ['station', ev.event_type.padEnd(9)];
  const detail = buildLogDetail(ev);

  const el = document.createElement('div');
  el.className = `log-entry ${cls}`;
  el.innerHTML = `<span class="log-ts">${esc(ts)}</span><span class="log-type">${esc(typeLabel)}</span>${esc(detail)}`;
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;

  // Keep log at ≤500 lines
  while (feed.children.length > 500) feed.removeChild(feed.firstChild);
}

function buildLogDetail(ev) {
  const d = ev.details || {};
  switch (ev.event_type) {
    case 'subtitle.submitted': return `${ev.delivery_id}  ${ev.language}  ${d.cue_count || '?'} cues`;
    case 'station.working':    return `${d.station_name || d.station_id}  →  working`;
    case 'station.ready':      return `${d.station_name || d.station_id}  →  ready`;
    case 'qc.violation':       return `cue#${d.cue}  ${d.rule}  val=${d.value}  limit=${d.threshold}`;
    case 'qc.repaired':        return `cue#${d.cue}  ${d.rule}  repaired`;
    case 'cue.analysis':       return `${(d.cues||[]).length} cues analysed`;
    case 'approval.required':  return `${d.reason || 'review required'}`;
    case 'delivery.passed':    return `${ev.delivery_id}  CLEARED  ${d.note || ''}`;
    default:                   return `${ev.delivery_id}`;
  }
}

// ── Diff panel ───────────────────────────────────────────────────────
function updateDiff(ev) {
  const d = ev.details || {};
  if (d.original !== undefined) {
    document.getElementById('diff-before').textContent = d.original || '—';
    document.getElementById('diff-after').textContent  = d.repaired || '—';
  }
}

// ── Approval card ────────────────────────────────────────────────────
function showApproval(ev) {
  const card = document.getElementById('approval-card');
  const sub  = document.getElementById('approval-sub');
  card.classList.add('active');
  const d = ev.details || {};
  sub.textContent = d.reason || 'Human review required before delivery.';
  window._currentApprovalId = d.item_id || null;
}

function handleApproval(action) {
  const card = document.getElementById('approval-card');
  const sub  = document.getElementById('approval-sub');
  card.classList.remove('active');
  sub.textContent = action === 'approve'
    ? '✓ Approved — delivery authorized.'
    : '✗ Rejected — delivery blocked.';
  const itemId = window._currentApprovalId;
  if (itemId) {
    fetch('/api/queue/' + itemId + '/' + action, {method:'POST'})
      .catch(err => console.warn('approval API call failed', err));
    window._currentApprovalId = null;
  }
}

// ── Demo controls ────────────────────────────────────────────────────
async function startReplay(loop) {
  const r = await fetch(`/api/replay?loop=${loop}`, {method:'POST'});
  if (!r.ok) console.warn('replay start failed', r.status);
}

async function stopReplay() {
  await fetch('/api/stop', {method:'POST'});
}

function toggleLoop() {
  loopMode = !loopMode;
  const btn = document.getElementById('btn-loop');
  btn.classList.toggle('active', loopMode);
}

function triggerDemo(id, lang) {
  // Visual: synthesise a card if not present (demo chips don't change delivery id)
  startReplay(false);
}

// ── File drop zone ────────────────────────────────────────────────────
const dz = document.getElementById('dropzone');
const fi = document.getElementById('file-input');

dz.addEventListener('click', () => fi.click());
fi.addEventListener('change', (e) => { if (e.target.files[0]) handleFile(e.target.files[0]); });
dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag-over'); });
dz.addEventListener('dragleave', ()  => dz.classList.remove('drag-over'));
dz.addEventListener('drop', (e) => {
  e.preventDefault();
  dz.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
});

function handleFile(file) {
  const label = dz.querySelector('.dropzone-label');
  label.textContent = `▶ ${file.name}`;
  const fd = new FormData();
  fd.append('file', file);
  fetch('/api/upload', {method:'POST', body: fd})
    .then(r => r.json())
    .then(() => startReplay(false))
    .catch(e => console.warn('upload failed', e));
}

// ── Helpers ──────────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ── Boot ─────────────────────────────────────────────────────────────
connectSSE();
</script>
</body>
</html>"""
