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
  --muted:   #8b9bb4;
  --dim:     #76839a;
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
/* OBJ-1: scale base font for 1080p screen-capture legibility */
html,body{height:100%;background:var(--bg);color:var(--text);font-family:var(--font);font-size:15px;overflow-x:hidden}

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
/* OBJ-1: boost col-header label size proportionally */
.col-header{
  font-size:11px;font-weight:600;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);
  padding-bottom:10px;border-bottom:1px solid var(--border);
}

/* ── Cards ───────────────────────────────────────────────────────────── */
.card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r2);padding:14px;
}

/* ── Drop zone ───────────────────────────────────────────────────────── */
.mic-btn { background: var(--bg); border: 1px solid var(--border); border-radius: 50%; width: 44px; height: 44px; cursor: pointer; color: var(--text); font-size: 18px; display: flex; align-items: center; justify-content: center; transition: all 0.2s; position: absolute; right: 16px; top: 16px; }
.mic-btn:hover { background: var(--surface); border-color: var(--dim); }
.mic-btn.recording { background: rgba(255, 60, 60, 0.15); border-color: rgba(255, 60, 60, 0.5); color: #ff5555; animation: pulse 1.5s infinite; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(255,60,60,0.4); } 70% { box-shadow: 0 0 0 10px rgba(255,60,60,0); } 100% { box-shadow: 0 0 0 0 rgba(255,60,60,0); } }

.origination-container { border: 1px solid var(--border); background: var(--surface); border-radius: 8px; margin-bottom: 20px; display: none; flex-direction: column; overflow: hidden; position: relative; }
.origination-container.active { display: flex; }
.origination-header { padding: 12px 16px; background: rgba(0,0,0,0.2); border-bottom: 1px solid var(--border); font-size: 13px; font-weight: 500; color: var(--dim); display: flex; justify-content: space-between; align-items: center; }
.origination-status { color: var(--primary); display: flex; align-items: center; gap: 8px; }
.origination-status.error { color: #ff5555; }
.origination-spinner { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.1); border-top-color: currentColor; border-radius: 50%; animation: spin 1s linear infinite; }

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
/* OBJ-6: single-row, no-wrap chips */
.demo-chips{display:flex;gap:8px;flex-wrap:wrap;overflow-x:visible}
/* OBJ-1: bump chip label size for legibility */
.chip{
  padding:5px 12px;border-radius:20px;font-size:13px;font-weight:500;
  border:1px solid var(--border2);background:var(--surface);
  color:var(--text);cursor:pointer;transition:all .2s;
  font-family:var(--mono);white-space:nowrap;flex-shrink:0;
}
.chip:hover{border-color:var(--blue);color:var(--blue);background:var(--blue-dim)}
/* OBJ-6: hopeless-case chip — hazard-stripe background, amber text */
.chip-hazard{
  border-color:rgba(245,166,35,.55);
  color:var(--amber);
  background:repeating-linear-gradient(
    -45deg,
    rgba(245,166,35,.10) 0px,
    rgba(245,166,35,.10) 4px,
    rgba(0,0,0,.0)  4px,
    rgba(0,0,0,.0)  10px
  );
}
.chip-hazard:hover{
  border-color:var(--amber);
  background:repeating-linear-gradient(
    -45deg,
    rgba(245,166,35,.20) 0px,
    rgba(245,166,35,.20) 4px,
    rgba(0,0,0,.0)  4px,
    rgba(0,0,0,.0)  10px
  );
  color:var(--amber);
}

/* ── Delivery cards ──────────────────────────────────────────────────── */
/* OBJ-8: shared internal spacing token — all card child elements use --dc-gap */
:root{--dc-gap:8px}
.delivery-card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:12px;
  transition:border-color .3s;
}
.delivery-card.hold{border-color:rgba(255,59,59,.5)}
.delivery-card.repairing{border-color:rgba(245,166,35,.4)}
.delivery-card.cleared{border-color:rgba(0,210,106,.4)}
/* OBJ-3: honest-fail card — deep crimson border, visually distinct from amber HOLD */
.delivery-card.failed{border-color:rgba(220,38,38,.7);background:rgba(220,38,38,.03)}

/* OBJ-8: header, meta, progress, and action rows share --dc-gap */
.dc-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--dc-gap)}
/* OBJ-1: boost card IDs and metadata for legibility */
.dc-id{font-family:var(--mono);font-size:13px;font-weight:500;color:#fff}
.dc-lang{font-size:12px;color:var(--muted);font-family:var(--mono)}
.dc-meta{font-size:12px;color:var(--muted);margin-bottom:var(--dc-gap)}

/* OBJ-1: badge text larger; OBJ-3: distinct honest-fail colour */
.status-badge{
  padding:3px 9px;border-radius:12px;font-size:11px;font-weight:700;
  letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;
}
/* OBJ-3: HOLD uses amber, not red, so badge-failed (red) is unambiguously different */
.badge-hold{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,166,35,.4)}
.badge-repairing{background:rgba(155,114,255,.12);color:var(--violet);border:1px solid rgba(155,114,255,.3)}
.badge-cleared{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,210,106,.3)}
.badge-pending{background:rgba(74,158,255,.08);color:var(--blue);border:1px solid rgba(74,158,255,.2)}
/* OBJ-3: honest-fail badge — saturated crimson (#dc2626), visually distinct from amber HOLD */
.badge-failed{background:rgba(220,38,38,.12);color:#f87171;border:1px solid rgba(220,38,38,.45)}

/* OBJ-8: progress bar, download link, briefing button share --dc-gap top margin */
.progress-bar{
  height:3px;background:var(--border);border-radius:2px;overflow:hidden;
  margin-top:var(--dc-gap);
}
.progress-fill{height:100%;background:var(--amber);border-radius:2px;width:0%;
  transition:width .4s ease;box-shadow:0 0 6px var(--amber)}

/* ── Break button ────────────────────────────────────────────────────── */
/* OBJ-1: larger label; OBJ-2: explicit disabled state */
.break-btn{
  width:100%;padding:12px;border-radius:var(--r);
  background:rgba(255,59,59,.1);border:1px solid rgba(255,59,59,.3);
  color:var(--red);font-size:14px;font-weight:700;letter-spacing:.06em;
  cursor:pointer;transition:all .2s;text-transform:uppercase;
}
.break-btn:hover{background:rgba(255,59,59,.2);border-color:var(--red)}
/* OBJ-2: disabled — muted colour, no-allowed cursor, suppressed border */
.break-btn:disabled,.break-btn[disabled]{
  background:rgba(255,59,59,.04);
  border-color:rgba(255,59,59,.12);
  color:rgba(255,59,59,.35);
  cursor:not-allowed;
  opacity:.55;
}
.break-btn:disabled:hover,.break-btn[disabled]:hover{
  background:rgba(255,59,59,.04);
  border-color:rgba(255,59,59,.12);
}

/* ── Demo controls ───────────────────────────────────────────────────── */
/* OBJ-6: force single row, no wrapping */
.demo-controls{display:flex;gap:8px;align-items:center;flex-wrap:nowrap;overflow-x:auto}
/* OBJ-1: slightly larger control button text */
.ctrl-btn{
  padding:7px 16px;border-radius:var(--r);font-size:13px;font-weight:600;
  cursor:pointer;border:1px solid;transition:all .2s;letter-spacing:.03em;
  white-space:nowrap;flex-shrink:0;
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
/* OBJ-1: boost SSE status label legibility */
.sse-status{
  font-size:11px;font-weight:600;letter-spacing:.06em;display:flex;align-items:center;gap:5px;
}
.sse-dot{width:6px;height:6px;border-radius:50%;background:var(--muted)}
.sse-dot.live{background:var(--green);box-shadow:0 0 5px var(--green)}
.sse-dot.reconnecting{background:var(--amber);animation:pulse 1s infinite}

/* ── Mode indicator (LIVE / REPLAY) ─────────────────────────────────── */
/* OBJ-5: LIVE = saturated green; REPLAY = amber; never simultaneous */
.mode-indicator{
  font-size:11px;font-weight:700;letter-spacing:.08em;
  padding:3px 10px;border-radius:20px;
  text-transform:uppercase;
}
.mode-indicator.live{
  background:rgba(0,210,106,.12);
  border:1px solid rgba(0,210,106,.4);
  color:#00d26a;
}
.mode-indicator.replay{
  background:rgba(245,166,35,.12);
  border:1px solid rgba(245,166,35,.45);
  color:#f5a623;
}

/* ── Confidence chip & citation popover ─────────────────────────────── */
/* OBJ-4: compact, tabular numerals, small font */
.conf-chip{
  display:inline-block;
  padding:1px 6px;border-radius:4px;
  font-size:10px;font-weight:600;
  font-family:var(--mono);
  font-variant-numeric:tabular-nums;
  background:rgba(74,158,255,.12);
  border:1px solid rgba(74,158,255,.3);
  color:var(--blue);
  cursor:pointer;
  vertical-align:middle;
  margin-left:4px;
  letter-spacing:.02em;
}
.flag-popover{
  margin-top:4px;margin-left:8px;
  padding:6px 10px;border-radius:var(--r);
  background:var(--card);border:1px solid var(--border2);
  font-size:11px;font-family:var(--mono);
  font-variant-numeric:tabular-nums;
  color:var(--text);line-height:1.6;
  max-width:280px;
}
.flag-popover strong{color:var(--blue);font-size:10px;letter-spacing:.04em}

/* ── Waiting-on-human delivery card state ───────────────────────────── */
/* OBJ-7: smooth pulse, ≥ 2s cycle, camera-safe opacity/scale animation */
@keyframes waiting-pulse{
  0%,100%{box-shadow:none;border-color:rgba(245,166,35,.35)}
  50%     {box-shadow:0 0 14px rgba(245,166,35,.22);border-color:rgba(245,166,35,.75)}
}
.delivery-card.waiting{
  border-color:rgba(245,166,35,.5);
  animation:waiting-pulse 2.4s ease-in-out infinite;
}

/* ── Briefing button (inside delivery card) ─────────────────────────── */
/* OBJ-8: shares --dc-gap top margin with progress bar and download link */
.briefing-btn{
  display:inline-block;margin-top:var(--dc-gap);
  padding:3px 10px;border-radius:var(--r);
  font-size:11px;font-weight:600;cursor:pointer;
  background:rgba(155,114,255,.1);
  border:1px solid rgba(155,114,255,.3);
  color:var(--violet);transition:all .2s;
}
.briefing-btn:hover{background:rgba(155,114,255,.2);border-color:var(--violet)}
.briefing-btn:disabled,.briefing-btn[disabled]{
  opacity:.45;cursor:not-allowed;color:var(--muted);
  border-color:var(--border2);background:transparent;
}

/* ── Station tiles ───────────────────────────────────────────────────── */
.stations-grid{
  display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;
}
.station-tile{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:10px 12px;
  transition:border-color .3s;
}
/* OBJ-7: station working pulse also slowed to camera-safe 2s+ */
.station-tile.working{
  border-color:rgba(245,166,35,.5);
  background:rgba(245,166,35,.04);
  animation:station-pulse 2s ease-in-out infinite;
}
.station-tile.offline{opacity:.45}
@keyframes station-pulse{0%,100%{box-shadow:none}50%{box-shadow:0 0 10px rgba(245,166,35,.2)}}

/* OBJ-1: station labels and counters boosted for 1080p legibility */
.station-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.station-name{font-size:13px;font-weight:600;color:#fff}
.lamp{width:10px;height:10px;border-radius:50%;transition:all .4s;flex-shrink:0}
.lamp-ready{background:var(--green);box-shadow:0 0 7px var(--green)}
/* OBJ-7: lamp working pulse slowed to 2s — camera-safe */
.lamp-working{background:var(--amber);box-shadow:0 0 9px var(--amber);animation:pulse 2s ease-in-out infinite}
.lamp-offline{background:var(--dim)}
.station-role{font-size:11px;color:var(--muted);line-height:1.4;margin-bottom:6px}
.station-counter{font-family:var(--mono);font-size:12px;color:var(--dim)}
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
.diff-text{font-family:var(--mono);font-size:14px;color:var(--text);line-height:1.5;
  min-height:48px}

button:focus, .chip:focus { outline: 2px solid var(--blue); outline-offset: 2px; }
/* ── Video Preview ─────────────────────────────────────────────────────── */
video { outline: none; }
::cue { font-family: var(--font); font-size: 16px; background: rgba(0,0,0,0.8); color: white; }
::cue(:lang(fa)) { direction: rtl; unicode-bidi: plaintext; }
::cue(:lang(fa-IR)) { direction: rtl; unicode-bidi: plaintext; }
::cue(:lang(fa-ir)) { direction: rtl; unicode-bidi: plaintext; }

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
/* OBJ-1: log timestamps and type labels readable at capture resolution */
.log-ts{color:var(--dim);margin-right:8px;font-size:11px}
.log-type{font-weight:600;margin-right:6px;min-width:90px;display:inline-block;font-size:11px}

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
/* OBJ-1: approval panel text larger for legibility */
.approval-title{font-size:14px;font-weight:700;color:var(--text);margin-bottom:6px}
.approval-sub{font-size:12px;color:var(--muted);margin-bottom:14px;line-height:1.5}
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
    <div class="col-header" style="display:flex;justify-content:space-between;align-items:center;">
      <span>Deliveries on the Board</span>
      <span class="mode-indicator live" id="mode-indicator">LIVE</span>
    </div>

    <!-- Drop zone -->
    <div class="dropzone" id="dropzone" style="position: relative;" title="Drop an SRT file or click to browse">
      <div class="dropzone-icon">⬇</div>
      <div class="dropzone-label">Drop subtitle file here</div>
      <div class="dropzone-sub">or click to browse · runs QC pipeline</div>
      <button class="mic-btn" id="micBtn" title="Hold to record speech">🎤</button>
      <input type="file" id="file-input" accept=".srt,.vtt,.ass,.ssa">
    </div>

    <div class="origination-container" id="originationCont">
      <div class="origination-header">
        <div>Origination Station</div>
        <div class="origination-status" id="originationStatus">
          <div class="origination-spinner"></div>
          <span id="originationStatusText">Transcribing...</span>
        </div>
      </div>
    </div>

    <!-- Demo chips -->
    <div class="card" style="padding:10px 14px">
      <div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px">Test Corpora & Demos</div>
      <div class="demo-chips">
        <div class="chip" role="button" tabindex="0" onclick="triggerDemo('demo-en','en-US')" onkeydown="if(event.key==='Enter') triggerDemo('demo-en','en-US')">English</div>
        <div class="chip" role="button" tabindex="0" onclick="triggerDemo('demo-fr','fr-FR')" onkeydown="if(event.key==='Enter') triggerDemo('demo-fr','fr-FR')">French</div>
        <div class="chip" role="button" tabindex="0" onclick="triggerDemo('demo-de','de-DE')" onkeydown="if(event.key==='Enter') triggerDemo('demo-de','de-DE')">German</div>
        <div class="chip" role="button" tabindex="0" onclick="triggerDemo('demo-es','es-ES')" onkeydown="if(event.key==='Enter') triggerDemo('demo-es','es-ES')">Spanish</div>
        <div class="chip" role="button" tabindex="0" onclick="triggerDemo('demo-ru','ru-RU')" onkeydown="if(event.key==='Enter') triggerDemo('demo-ru','ru-RU')">Russian</div>
        <div class="chip" role="button" tabindex="0" onclick="triggerDemo('demo-pt','pt-BR')" onkeydown="if(event.key==='Enter') triggerDemo('demo-pt','pt-BR')">Portuguese</div>
        <div class="chip" role="button" tabindex="0" onclick="triggerDemo('demo-zh','zh-CN')" onkeydown="if(event.key==='Enter') triggerDemo('demo-zh','zh-CN')">Chinese</div>
        <div class="chip" role="button" tabindex="0" onclick="triggerDemo('demo-fa','fa-IR')" onkeydown="if(event.key==='Enter') triggerDemo('demo-fa','fa-IR')">Persian</div>
        <div class="chip chip-hazard" role="button" tabindex="0" onclick="triggerDemo('hopeless','fr-FR')" onkeydown="if(event.key==='Enter') triggerDemo('hopeless','fr-FR')">Hopeless Case</div>
      </div>
    </div>

    <!-- Demo controls -->
    <div class="card" style="padding:10px 14px">
      <div style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px">Demo Replay</div>
      <div class="demo-controls">
        <button class="ctrl-btn btn-play" onclick="startReplay(loopMode)">▶ PLAY</button>
        <button class="ctrl-btn btn-stop" onclick="stopReplay()">■ STOP</button>
        <button class="ctrl-btn btn-loop" id="btn-loop" onclick="toggleLoop()">↺ LOOP</button>
        <button class="ctrl-btn btn-stop" onclick="startReset()" title="Clear board for a fresh take">⟳ RESET</button>
      </div>
    </div>

    <!-- Delivery cards container -->
    <div id="delivery-cards"></div>

    <div style="flex:1"></div>
    <button id="break-btn" class="break-btn" onclick="triggerBreak()" disabled title="No cleared delivery available to break">⚡ BREAK THIS FILE</button>
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
  'station.ready':      (ev) => { setLamp(ev.details.station_id, 'ready', ev.details);    addLog(ev, 'station'); },
  'qc.violation':       (ev) => { markViolation(ev);             addLog(ev, 'violation'); updateHolds(); },
  'qc.repaired':        (ev) => { markRepaired(ev);              addLog(ev, 'repaired'); updateDiff(ev); },
  'qc.unfixable':       (ev) => { addLog(ev, 'violation'); updateHolds(); },
  'cue.analysis':       (ev) => { renderHeatStrip(ev.details.cues || []); addLog(ev, 'lifecycle'); },
  'approval.required':  (ev) => { addLog(ev, 'approval'); },
  'delivery.passed':    (ev) => { markCleared(ev);               addLog(ev, 'lifecycle'); updateHolds(); },
  'delivery.failed':    (ev) => { markFailed(ev);               addLog(ev, 'lifecycle'); updateHolds(); },
};

function updateModeIndicator(isReplay) {
  const mode = document.getElementById('mode-indicator');
  if (!mode) return;
  if (isReplay) {
    mode.className = 'mode-indicator replay';
    mode.textContent = 'REPLAY';
  } else {
    mode.className = 'mode-indicator live';
    mode.textContent = 'LIVE';
  }
}

function dispatch(ev) {
  if (seen.has(ev.event_id)) return;  // deduplicate (backfill replay on reconnect)
  seen.add(ev.event_id);

  if (ev.delivery_id) {
    const isReplay = ev.delivery_id.startsWith('DEMO-');
    updateModeIndicator(isReplay);
  }

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

// ── Queue Polling ───────────────────────────────────────────────────
async function checkQueue() {
  try {
    const r = await fetch('/api/queue');
    if (!r.ok) return;
    const items = await r.json();
    if (items && items.length > 0) {
      const pending = items.find(i => i.status === 'pending');
      if (pending && window._currentApprovalId !== pending.item_id) {
        showApproval(pending);
      }
    } else {
      const acard = document.getElementById('approval-card');
      if (acard) acard.classList.remove('active');
      window._currentApprovalId = null;
    }
  } catch(e) {}
}
setInterval(checkQueue, 2000);

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
  const isReplay = ev.delivery_id.startsWith('DEMO-');
  el.className = 'delivery-card pending' + (isReplay ? ' is-replay' : '');
  el.id = `dc-${CSS.escape(ev.delivery_id)}`;
  el.setAttribute('data-delivery-id', ev.delivery_id);
  
  let parentLabelHtml = '';
  if (d.parent_id) {
    parentLabelHtml = `<div class="dc-parent" style="font-size:10px;color:var(--amber);margin-bottom:4px;font-family:var(--mono);">parent: ${esc(d.parent_id)}</div>`;
  }

  let replayTagHtml = '';
  if (isReplay) {
    replayTagHtml = `<span class="mode-indicator replay" style="font-size:9px;padding:1px 5px;margin-left:6px;border-radius:10px;vertical-align:middle;">REPLAY</span>`;
  }

  el.innerHTML = `
    <div class="dc-header">
      <span class="dc-id">${esc(ev.delivery_id)}${replayTagHtml}</span>
      <span class="status-badge badge-pending" id="badge-${CSS.escape(ev.delivery_id)}">SUBMITTED</span>
    </div>
    ${parentLabelHtml}
    <div class="dc-meta dc-lang">${esc(ev.language)} · ${d.cue_count || '?'} cues</div>
    <div class="progress-bar"><div class="progress-fill" id="prog-${CSS.escape(ev.delivery_id)}"></div></div>
    <div class="video-preview" id="vid-container-${CSS.escape(ev.delivery_id)}" style="display:none; margin-top:12px; border:1px solid var(--border); border-radius:var(--r); overflow:hidden; background:#000;">
      <video id="vid-${CSS.escape(ev.delivery_id)}" src="/static/tos-excerpt.mp4" controls crossorigin playsinline preload="none" style="width:100%; display:block;"></video>
    </div>
  `;
  document.getElementById('delivery-cards').prepend(el);
  deliveries[ev.delivery_id] = { violations: 0, repairs: 0, status: 'submitted', language: ev.language };
  updateInFlightState();
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

async function markCleared(ev) {
  const s = deliveries[ev.delivery_id];
  if (!s) return;
  s.status = 'cleared';
  const card  = getCard(ev.delivery_id);
  const badge = getBadge(ev.delivery_id);
  const prog  = getProg(ev.delivery_id);
  if (card)  { card.className  = card.className.replace('pending', '').replace('repairing', '').replace('hold', '') + ' cleared'; }
  if (badge) { badge.className = 'status-badge badge-cleared'; badge.textContent = 'CLEARED FOR DELIVERY'; }
  if (prog)  { prog.style.width = '100%'; prog.style.background = 'var(--green)'; }
  // Load preview subtitles
  const vidContainer = document.getElementById(`vid-container-${CSS.escape(ev.delivery_id)}`);
  if (vidContainer) {
    try {
      const resp = await fetch(`/api/download/${encodeURIComponent(ev.delivery_id)}`);
      if (resp.ok) {
        const srtText = await resp.text();
        const vttText = "WEBVTT\n\n" + srtText.replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, '$1.$2');
        const blob = new Blob([vttText], {type: 'text/vtt'});
        const url = URL.createObjectURL(blob);
        const video = document.getElementById(`vid-${CSS.escape(ev.delivery_id)}`);
        const track = document.createElement('track');
        track.kind = 'subtitles';
        track.label = ev.language || 'Subtitles';
        track.srclang = ev.language ? ev.language.toLowerCase() : 'en';
        track.src = url;
        track.default = true;
        video.appendChild(track);
        vidContainer.style.display = 'block';
      }
    } catch(e) { console.warn("Could not load preview subtitles", e); }
  }

  // Append a download link for the repaired SRT file if repaired_file_exists is true
  if (card && ev.details && ev.details.repaired_file_exists === true && !card.classList.contains('is-replay')) {
    const existing = card.querySelector('.download-link');
    if (!existing) {
      const link = document.createElement('a');
      link.className = 'download-link';
      link.href = `/api/download/${encodeURIComponent(ev.delivery_id)}`;
      link.textContent = '⬇ Download repaired SRT';
      link.style.cssText = 'display:block;margin-top:6px;font-size:11px;color:var(--green);text-decoration:underline;';
      card.appendChild(link);
    }
  }
  // Append Briefing button if enabled
  if (card && !card.classList.contains('is-replay')) {
    const existingBriefing = card.querySelector('.briefing-btn');
    if (!existingBriefing) {
      const bbtn = document.createElement('button');
      bbtn.className = 'briefing-btn';
      bbtn.onclick = () => playBriefing(ev.delivery_id);
      bbtn.textContent = '▶ Briefing';
      card.appendChild(bbtn);
    }
  }
  updateBreakButtonState();
  updateInFlightState();
}

function markFailed(ev) {
  const s = deliveries[ev.delivery_id];
  if (!s) return;
  s.status = 'failed';
  const card  = getCard(ev.delivery_id);
  const badge = getBadge(ev.delivery_id);
  const prog  = getProg(ev.delivery_id);
  if (card)  { card.className  = card.className.replace('pending', '').replace('repairing', '').replace('hold', '') + ' failed'; }
  if (badge) {
    badge.className = 'status-badge badge-failed';
    const remains = ev.details.remaining_violations || s.violations || 0;
    badge.textContent = `HELD — ${remains} violations remain`;
  }
  if (prog)  { prog.style.width = '100%'; prog.style.background = 'var(--amber)'; }

  if (card && !card.querySelector('.violations-breakdown')) {
    // Render per-rule breakdown
    const breakdown = ev.details.per_rule_breakdown || {};
    let bdHtml = '<div class="violations-breakdown" style="margin-top:6px;font-size:12px;color:var(--text);">';
    bdHtml += '<strong>Violations Breakdown:</strong><ul style="margin:2px 0 0 14px;padding:0;list-style:disc;">';
    
    const ruleNames = {
      'cps_exceeded': 'Reading speed exceeded',
      'cps_warning': 'Reading speed warning',
      'line_too_long': 'Line length limit exceeded',
      'three_line_cue': 'Cue has too many lines',
      'sub_one_second': 'Duration too short',
      'overlap': 'Cue overlap',
    };
    
    Object.entries(breakdown).forEach(([rule, count]) => {
      const plainRule = ruleNames[rule] || (rule.startsWith('MT') ? 'Language or meaning error' : rule);
      bdHtml += `<li>${esc(plainRule)}: ${count}</li>`;
    });
    bdHtml += '</ul></div>';
    
    const bdDiv = document.createElement('div');
    bdDiv.innerHTML = bdHtml;
    card.appendChild(bdDiv);

    // Conditionally show best-effort download link
    if (ev.details && ev.details.repaired_file_exists === true && !card.classList.contains('is-replay')) {
      const existing = card.querySelector('.download-link');
      if (!existing) {
        const link = document.createElement('a');
        link.className = 'download-link failed-download';
        link.href = `/api/download/${encodeURIComponent(ev.delivery_id)}`;
        link.textContent = '⬇ Download best-effort (not cleared)';
        link.style.cssText = 'display:block;margin-top:6px;font-size:11px;color:var(--amber);text-decoration:underline;';
        card.appendChild(link);
      }
    }

    // Append Briefing button if enabled
    if (!card.classList.contains('is-replay')) {
      const existingBriefing = card.querySelector('.briefing-btn');
      if (!existingBriefing) {
        const bbtn = document.createElement('button');
        bbtn.className = 'briefing-btn';
        bbtn.onclick = () => playBriefing(ev.delivery_id);
        bbtn.textContent = '▶ Briefing';
        card.appendChild(bbtn);
      }
    }
  }
  updateBreakButtonState();
  updateInFlightState();
}

function updateInFlightState() {
  const inFlight = Object.values(deliveries).filter(d => ['submitted', 'repairing', 'hold'].includes(d.status)).length > 0;
  const demoBtns = document.querySelectorAll('.demo-btn');
  const dz = document.getElementById('dropzone');
  
  if (inFlight) {
    demoBtns.forEach(btn => {
      btn.disabled = true;
      btn.title = "A delivery is currently in flight";
    });
    if (dz) {
      dz.style.pointerEvents = 'none';
      dz.style.opacity = '0.5';
      const dzLabel = dz.querySelector('.dropzone-label');
      if (dzLabel && !dzLabel.dataset.orig) dzLabel.dataset.orig = dzLabel.textContent;
      if (dzLabel) dzLabel.textContent = "Pipeline busy...";
    }
  } else {
    demoBtns.forEach(btn => {
      btn.disabled = false;
      btn.title = "";
    });
    if (dz) {
      dz.style.pointerEvents = 'auto';
      dz.style.opacity = '1';
      const dzLabel = dz.querySelector('.dropzone-label');
      if (dzLabel && dzLabel.dataset.orig) {
        dzLabel.textContent = dzLabel.dataset.orig;
        delete dzLabel.dataset.orig;
      }
    }
  }
}

function updateBreakButtonState() {
  const btn = document.getElementById('break-btn');
  if (!btn) return;
  const clearedCards = document.querySelectorAll('.delivery-card.cleared:not(.is-replay)');
  if (clearedCards.length > 0) {
    btn.disabled = false;
    btn.title = 'Break the most recently cleared delivery';
  } else {
    btn.disabled = true;
    btn.title = 'No cleared delivery available to break';
  }
}

async function playBriefing(deliveryId) {
  const card = getCard(deliveryId);
  if (!card) return;
  const bbtn = card.querySelector('.briefing-btn');
  if (bbtn) {
    bbtn.disabled = true;
    bbtn.textContent = '⏳ Loading...';
  }
  try {
    const resp = await fetch(`/api/briefing/${encodeURIComponent(deliveryId)}`);
    if (!resp.ok) {
      if (bbtn) {
        bbtn.textContent = 'Briefing failed - Try again';
        bbtn.disabled = false;
      }
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    if (bbtn) {
      bbtn.disabled = false;
      bbtn.textContent = '⏸ Playing';
    }
    audio.onended = () => {
      if (bbtn) bbtn.textContent = '▶ Briefing';
    };
    await audio.play();
  } catch (e) {
    if (bbtn) {
      bbtn.textContent = 'Briefing failed - Try again';
      bbtn.disabled = false;
    }
  }
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
  'qc.unfixable':       ['violation', 'UNFIXABLE '],
  'cue.analysis':       ['lifecycle', 'ANALYSIS  '],
  'approval.required':  ['approval',  'APPROVAL  '],
  'approval.timeout':   ['approval',  'TIMEOUT   '],
  'delivery.passed':    ['lifecycle', 'CLEARED   '],
  'delivery.failed':    ['violation', 'HELD      '],
};

function addLog(ev, cls) {
  const feed = document.getElementById('log-feed');
  const d = new Date(ev.timestamp);
  const ts = d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit' }) + '.' + String(d.getMilliseconds()).padStart(3, '0');
  const [, typeLabel] = LOG_TYPES[ev.event_type] || ['station', ev.event_type.padEnd(9)];
  const detail = buildLogDetail(ev);

  const el = document.createElement('div');
  el.className = `log-entry ${cls}`;

  let chipHtml = '';
  let popoverHtml = '';
  if (ev.event_type === 'qc.violation' && ev.details && ev.details.rule_ref && ev.details.rule_ref.startsWith('MT')) {
    const confidence_pct = Math.round((ev.details.confidence || 0) * 100);
    const id = `pop-${ev.event_id || Math.random().toString(36).substr(2, 9)}`;
    chipHtml = ` <span class="conf-chip" onclick="togglePopover('${id}', '${ev.details.rule_ref}', '${ev.language}')">${ev.details.rule_ref} · ${confidence_pct}%</span>`;
    popoverHtml = `<div id="${id}" class="flag-popover" style="display:none;" data-explanation="${esc(ev.details.explanation || ev.details.detail || '')}"></div>`;
  }

  el.innerHTML = `<span class="log-ts">${esc(ts)}</span><span class="log-type">${esc(typeLabel)}</span>${esc(detail)}${chipHtml}${popoverHtml}`;
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;

  // Keep log at ≤500 lines
  while (feed.children.length > 500) feed.removeChild(feed.firstChild);
}

async function togglePopover(popoverId, ruleRef, lang) {
  const el = document.getElementById(popoverId);
  if (!el) return;
  if (el.style.display === 'block') {
    el.style.display = 'none';
    return;
  }
  const explanation = el.getAttribute('data-explanation') || '';
  try {
    const r = await fetch(`/api/style-guide/${encodeURIComponent(ruleRef)}/${encodeURIComponent(lang)}`);
    if (r.ok) {
      const data = await r.json();
      el.innerHTML = `<strong>${esc(data.rule_ref)}: ${esc(data.rule_name)}</strong><br>Style Guide: ${esc(data.citation)}<br>Reason: ${esc(explanation)}`;
      el.style.display = 'block';
    }
  } catch (e) {
    console.warn('Failed to fetch style-guide citation', e);
  }
}

function buildLogDetail(ev) {
  const d = ev.details || {};
  switch (ev.event_type) {
    case 'subtitle.submitted': return `${ev.delivery_id}  ${ev.language}  ${d.cue_count || '?'} cues`;
    case 'station.working':    return `${d.station_name || d.station_id}  →  working`;
    case 'station.ready':      return `${d.station_name || d.station_id}  →  ready`;
    case 'qc.violation': {
      if (d.rule && d.rule.startsWith('MT')) return `cue#${d.cue}  ${d.rule}`;
      let val = d.value;
      let limit = d.threshold;
      if (typeof val === 'number') val = val.toFixed(2);
      if (typeof limit === 'number') limit = limit.toFixed(2);
      let unit = '';
      if (d.rule && d.rule.includes('cps')) unit = ' cps';
      else if (d.rule === 'line_too_long') unit = ' chars';
      else if (d.rule === 'sub_one_second') unit = ' ms';
      return `cue#${d.cue}  ${d.rule}  val=${val}${unit}  limit=${limit}${unit}`;
    }
    case 'qc.repaired':        return `cue#${d.cue}  ${d.rule}  repaired`;
    case 'qc.unfixable':       return `cue#${d.cue}  ${d.rule}  ${d.reason || 'unfixable'}`;
    case 'cue.analysis':       return `${(d.cues||[]).length} cues analysed`;
    case 'approval.required':  return `${d.reason || 'review required'}`;
    case 'approval.timeout':   return `No human decision was made`;
    case 'delivery.passed':    return `${ev.delivery_id}  CLEARED  ${d.note || ''}`;
    case 'delivery.failed':    return `${ev.delivery_id}  HELD — ${d.remaining_violations || '?'} violation(s) remain`;
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
async function showApproval(item) {
  const card = document.getElementById('approval-card');
  const sub  = document.getElementById('approval-sub');
  card.classList.add('active');
  window._currentApprovalId = item.item_id;
  window._currentApprovalDeliveryId = item.delivery_id;

  let styleGuideHtml = '';
  if (item.rule_ref) {
    try {
      // Find the language of the delivery from metadata if we can
      const dc = deliveries[item.delivery_id];
      const lang = dc ? dc.language : 'en';
      const sg = await fetch(`/api/style-guide/${encodeURIComponent(item.rule_ref)}/${encodeURIComponent(lang)}`);
      if (sg.ok) {
        const sgData = await sg.json();
        if (sgData.citation) {
          styleGuideHtml = `<div style="color:var(--text);margin-top:6px;font-style:italic;">"${esc(sgData.citation)}"</div>`;
        }
      }
    } catch(e) {}
  }

  const confPct = Math.round((item.confidence || 0) * 100);

  sub.innerHTML = `
    <div style="font-family:var(--mono);color:var(--dim);margin-bottom:8px;">
      Delivery ${esc(item.delivery_id)} · Cue ${item.cue_index}
    </div>
    <div style="display:flex;flex-direction:column;gap:4px;margin-bottom:8px;font-family:var(--mono);" dir="${lang === 'fa' || lang === 'fa-IR' || lang === 'fa-ir' ? 'rtl' : 'ltr'}">
      <div style="color:var(--amber);">BEFORE:<br/>${esc(item.original_text || '')}</div>
      <div style="color:var(--green);">AFTER:<br/>${esc(item.proposed_text || '')}</div>
    </div>
    <div style="margin-bottom:6px;">
      <span style="color:var(--amber);">${esc(item.rule_ref || 'Unknown')}</span> · ${confPct}% Confidence
    </div>
    ${styleGuideHtml}
    <div style="color:var(--text);margin-top:8px;">
      Reason: ${esc(item.explanation || item.reason || '')}
    </div>
  `;

  if (item.delivery_id) {
    const dc = getCard(item.delivery_id);
    if (dc) dc.classList.add('waiting');
  }
}

async function handleApproval(action) {
  const card = document.getElementById('approval-card');
  const sub  = document.getElementById('approval-sub');
  const itemId = window._currentApprovalId;
  const deliveryId = window._currentApprovalDeliveryId;

  if (itemId) {
    sub.textContent = '⏳ Sending decision...';
    try {
      const resp = await fetch('/api/queue/' + itemId + '/' + action, {method:'POST'});
      if (!resp.ok) {
        sub.textContent = '❌ Server rejected the decision. Try again.';
        return;
      }
    } catch(err) {
      sub.textContent = '❌ Network error submitting decision. Try again.';
      return;
    }
    window._currentApprovalId = null;
  }

  card.classList.remove('active');
  sub.textContent = action === 'approve'
    ? '✓ Approved — delivery authorized.'
    : '✗ Rejected — delivery blocked.';

  if (deliveryId) {
    const dc = getCard(deliveryId);
    if (dc) {
      dc.classList.remove('waiting');
    }
    window._currentApprovalDeliveryId = null;
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

async function startReset() {
  await fetch('/api/reset', {method:'POST'});
  
  // 1. Clear in-memory deduplication set and deliveries tracking dict
  seen.clear();
  for (const k in deliveries) {
    delete deliveries[k];
  }
  
  // 2. Cards and logs
  document.getElementById('delivery-cards').innerHTML = '';
  const logFeed = document.getElementById('log-feed');
  if (logFeed) logFeed.innerHTML = '';
  
  // 3. Holds count and pill
  holdsCount = 0;
  updateHolds();
  
  // 4. Station job counters and lamps
  for (const k in stationCounters) {
    stationCounters[k] = 0;
    const cnt = document.getElementById(`cnt-${k}`);
    if (cnt) cnt.textContent = '0';
  }
  document.querySelectorAll('.lamp').forEach(l => {
    l.className = 'lamp lamp-ready';
  });
  document.querySelectorAll('.station-tile').forEach(t => {
    t.className = 'station-tile';
  });
  
  // 5. Reading speed chart
  const strip = document.getElementById('heat-strip');
  if (strip) {
    strip.innerHTML = '<span style="color:var(--dim);font-size:11px;align-self:center;padding:4px 0">Awaiting cue analysis…</span>';
  }
  const countEl = document.getElementById('heat-cue-count');
  if (countEl) countEl.textContent = '—';
  
  // 6. Before/after diff panel
  const db = document.getElementById('diff-before');
  const da = document.getElementById('diff-after');
  if (db) db.textContent = '—';
  if (da) da.textContent = '—';
  
  // 7. Approval card
  const acard = document.getElementById('approval-card');
  if (acard) acard.classList.remove('active');
  const asub = document.getElementById('approval-sub');
  if (asub) asub.textContent = 'Waiting for approval request…';
  window._currentApprovalId = null;
  window._currentApprovalDeliveryId = null;
  
  // 8. Drop zone caption
  const dzLabel = document.querySelector('.dropzone-label');
  if (dzLabel) dzLabel.textContent = 'Drop subtitle file here';
  
  // 9. Delivery window countdown
  countdownS = 14400;
  const cdEl = document.getElementById('countdown');
  if (cdEl) cdEl.style.color = '';
  
  // 10. Mode indicator and break button state
  updateModeIndicator(false);
  updateBreakButtonState();
  updateInFlightState();
}

function toggleLoop() {
  loopMode = !loopMode;
  const btn = document.getElementById('btn-loop');
  btn.classList.toggle('active', loopMode);
}

async function triggerDemo(id, lang) {
  // Fetch the bundled demo corpus file and POST it to /api/upload so the
  // real pipeline runs — no demo replay, no startReplay() call.
  try {
    const srtResp = await fetch(`/api/demo/${encodeURIComponent(id)}`);
    if (!srtResp.ok) { console.warn('demo fetch failed', srtResp.status); return; }
    const blob = await srtResp.blob();
    const filename = id === 'hopeless' ? `demo-hopeless-${lang.split('-')[0].toLowerCase()}.srt` : `demo-${lang.split('-')[0].toLowerCase()}-broken.srt`;
    const file = new File([blob], filename, {type: 'text/plain'});
    const label = document.querySelector('.dropzone-label');
    if (label) label.textContent = `▶ ${filename}`;
    const fd = new FormData();
    fd.append('file', file);
    const uploadResp = await fetch('/api/upload', {method: 'POST', body: fd});
    if (!uploadResp.ok) {
        console.warn('demo upload failed', uploadResp.status);
        if (uploadResp.status === 422) {
            const label = document.querySelector('.dropzone-label');
            if (label) {
                label.textContent = '❌ Not a readable subtitle file';
                label.style.color = 'var(--amber)';
            }
        }
    } else {
      const data = await uploadResp.json();
      console.log('demo pipeline started', data);
    }
  } catch (e) { console.warn('triggerDemo error', e); }
}

async function triggerBreak() {
  const clearedCards = document.querySelectorAll('.delivery-card.cleared:not(.is-replay)');
  if (clearedCards.length === 0) return;
  const card = clearedCards[0];
  const deliveryId = card.getAttribute('data-delivery-id');

  const btn = document.getElementById('break-btn');
  if (btn) btn.disabled = true;

  try {
    const resp = await fetch(`/api/break/${encodeURIComponent(deliveryId)}`, {method: 'POST'});
    if (!resp.ok) {
      if (btn) btn.textContent = 'Break Failed';
      setTimeout(() => { if (btn) btn.textContent = '⚡ BREAK THIS FILE'; }, 3000);
    } else {
      const data = await resp.json();
      console.log('break pipeline started', data);
    }
  } catch (e) {
    if (btn) btn.textContent = 'Break Failed';
    setTimeout(() => { if (btn) btn.textContent = '⚡ BREAK THIS FILE'; }, 3000);
  } finally {
    setTimeout(updateBreakButtonState, 3000);
  }
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
  if (!file.name.toLowerCase().endsWith('.srt')) {
    label.textContent = `❌ Unsupported format: ${file.name}`;
    label.style.color = "var(--amber)";
    return;
  }
  label.style.color = "";
  label.textContent = `▶ ${file.name}`;
  const fd = new FormData();
  fd.append('file', file);
  fetch('/api/upload', {method:'POST', body: fd})
    .then(async r => {
      if (!r.ok) {
        if (r.status === 422) {
          label.textContent = '❌ Not a readable subtitle file';
          label.style.color = 'var(--amber)';
        } else {
          label.textContent = `❌ Upload failed: ${r.status}`;
          label.style.color = 'var(--amber)';
        }
        return null;
      }
      return r.json();
    })
    .then(data => { if (data) console.log('pipeline started', data); })
    .catch(e => console.warn('upload failed', e));
}

// ── Helpers ──────────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ── Boot ─────────────────────────────────────────────────────────────
let mediaRecorder;
let audioChunks = [];
let originationJobId = null;
let originationTimer = null;

const micBtn = document.getElementById('micBtn');
const originationCont = document.getElementById('originationCont');
const originationStatusText = document.getElementById('originationStatusText');
const originationStatus = document.getElementById('originationStatus');

if (micBtn) {
  micBtn.addEventListener('mousedown', startRecording);
  micBtn.addEventListener('mouseup', stopRecording);
  micBtn.addEventListener('mouseleave', () => { if (mediaRecorder && mediaRecorder.state === 'recording') stopRecording(); });
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
    audioChunks = [];
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = uploadRecording;
    mediaRecorder.start();
    micBtn.classList.add('recording');
  } catch (err) {
    console.error('Mic access denied or error:', err);
    alert('Microphone access is required to use this feature.');
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
  }
  micBtn.classList.remove('recording');
}

async function uploadRecording() {
  const blob = new Blob(audioChunks, { type: 'audio/webm;codecs=opus' });
  if (blob.size > 20 * 1024 * 1024) {
    alert("Audio recording exceeds the 20MB limit. Please record a shorter clip.");
    return;
  }
  
  const fd = new FormData();
  fd.append('file', blob, 'recording.webm');
  fd.append('source_language', 'en'); 
  
  originationCont.classList.add('active');
  originationStatusText.textContent = 'Uploading...';
  originationStatus.classList.remove('error');
  const spinner = document.querySelector('.origination-spinner');
  if (spinner) spinner.style.display = 'block';
  
  try {
    const resp = await fetch('/api/originate', { method: 'POST', body: fd });
    if (!resp.ok) {
        let msg = "Upload failed";
        try { const err = await resp.json(); msg = err.detail || msg; } catch(e){}
        throw new Error(msg);
    }
    const data = await resp.json();
    originationJobId = data.job_id;
    originationStatusText.textContent = 'Transcribing...';
    originationTimer = setInterval(pollOrigination, 1000);
  } catch (e) {
    console.error('Origination failed:', e);
    originationStatusText.textContent = e.message;
    originationStatus.classList.add('error');
    if (spinner) spinner.style.display = 'none';
  }
}

async function pollOrigination() {
  if (!originationJobId) return;
  try {
    const resp = await fetch(`/api/originate/status/${originationJobId}`);
    if (resp.ok) {
      const data = await resp.json();
      const st = data.status;
      if (st === 'completed') {
        clearInterval(originationTimer);
        originationStatusText.textContent = 'Spawning pipelines...';
        setTimeout(() => originationCont.classList.remove('active'), 3000);
      } else if (st === 'failed') {
        clearInterval(originationTimer);
        originationStatusText.textContent = data.error || 'Processing failed.';
        originationStatus.classList.add('error');
        const spinner = document.querySelector('.origination-spinner');
        if (spinner) spinner.style.display = 'none';
      } else {
        const displayStatus = st.replace('_', ' ');
        originationStatusText.textContent = displayStatus.charAt(0).toUpperCase() + displayStatus.slice(1) + '...';
      }
    }
  } catch (e) {
    console.error('Poll failed:', e);
  }
}

const originalResetBtn = document.getElementById('resetBtn');
if (originalResetBtn) {
    originalResetBtn.addEventListener('click', () => {
        originationCont.classList.remove('active');
        if (originationTimer) clearInterval(originationTimer);
    });
}

connectSSE();
</script>
</body>
</html>"""
