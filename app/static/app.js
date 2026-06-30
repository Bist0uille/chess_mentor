/* Chess Mentor — frontend (multi-coups + flèches + cases légales) */
let board = null;
let game = null;          // chess.js : position LIVE
let puzzle = null;
let ply = 0;
let hintLevel = 0;
let solved = false;
let busy = false;

// Annotations (clic droit) et sélection (clic gauche)
let annotations = [];     // [{kind:'arrow'|'circle', from, to}]
let selected = null;      // case sélectionnée (clic gauche)
let annotStart = null;    // case de départ d'une flèche en cours
let centers = {};         // case -> {x,y} en px relatifs à #board
let sqSize = 50;

const NS = "http://www.w3.org/2000/svg";
const ARROW_COLOR = "rgba(21,120,27,0.78)";

const $status = document.getElementById("status");
const $meta = document.getElementById("meta");
const $hints = document.getElementById("hints");
const $progress = document.getElementById("progress");
const $lineWrap = document.getElementById("lineWrap");
const $line = document.getElementById("line");
const $boardEl = document.getElementById("board");

function setStatus(msg, cls) { $status.textContent = msg; $status.className = cls || ""; }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function uciToObj(uci) {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4),
           promotion: uci.length > 4 ? uci[4] : undefined };
}
function updateProgress() {
  if (!puzzle) return;
  $progress.textContent =
    `Coup ${Math.min(ply + 1, puzzle.n_solver_moves)} / ${puzzle.n_solver_moves}`;
}

/* ---------- chargement d'un puzzle ---------- */
async function loadPuzzle() {
  if (busy) return;
  setStatus("Chargement…", "");
  $hints.innerHTML = "";
  $lineWrap.style.display = "none";
  hintLevel = 0; ply = 0; solved = false;
  clearSelection(); annotations = []; redrawAll();
  const r = await fetch("/api/puzzle");
  if (!r.ok) { setStatus("Erreur : " + (await r.text()), "ko"); return; }
  puzzle = await r.json();
  game = new Chess(puzzle.fen);
  const orientation = puzzle.side_to_move === "w" ? "white" : "black";
  const trait = puzzle.side_to_move === "w" ? "Blancs" : "Noirs";
  $meta.innerHTML = `Trait aux <b>${trait}</b> · rating ${puzzle.rating} · ` +
    `${puzzle.n_solver_moves} coup(s) à trouver · ` +
    `thèmes : ${(puzzle.themes || []).join(", ") || "—"}`;
  if (board) board.destroy();
  board = Chessboard("board", {
    position: puzzle.fen, orientation, draggable: true,
    pieceTheme: "https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png",
    onDrop, onDragStart,
  });
  setupOverlay();
  updateProgress();
  setStatus("À toi de jouer.", "");
}

/* ---------- coups (drag + clic) ---------- */
function onDragStart(source) {
  if (solved || busy) return false;
  // n'autorise à saisir que les pièces du camp au trait
  const piece = game.get(source);
  return piece && piece.color === game.turn();
}

function onDrop(source, target) {
  // Clic simple (relâché sur la même case) : on GARDE la sélection et les points.
  if (source === target) return;
  clearSelection();
  if (!tryMove(source, target)) return "snapback";
}

function tryMove(source, target) {
  if (solved || busy) return false;
  const probe = new Chess(game.fen());
  const mv = probe.move({ from: source, to: target, promotion: "q" });
  if (mv === null) return false;
  validate(mv.from + mv.to + (mv.promotion || ""));
  return true;
}

async function validate(uci) {
  busy = true;
  try {
    const r = await fetch("/api/attempt", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: puzzle.id, uci, ply }),
    });
    const data = await r.json();
    if (!data.correct) {
      setStatus(data.legal
        ? "❌ Coup légal, mais ce n'est pas la solution. Réessaie."
        : "❌ Coup invalide.", "ko");
      board.position(game.fen());
      return;
    }
    game.move(uciToObj(uci));
    if (data.opponent_uci) game.move(uciToObj(data.opponent_uci));
    board.position(game.fen());
    ply = data.next_ply;
    updateProgress();
    if (data.done) {
      solved = true;
      setStatus("✅ Résolu ! Bien joué.", "ok");
      if (data.line_san) { $line.textContent = data.line_san.join("  ");
                           $lineWrap.style.display = "block"; }
    } else {
      const rep = data.opponent_san ? ` L'adversaire répond ${data.opponent_san}.` : "";
      setStatus(`✅ Bon coup !${rep} Continue.`, "ok");
    }
  } finally { busy = false; }
}

/* ---------- surcouche SVG : flèches + cases légales ---------- */
function setupOverlay() {
  let svg = document.getElementById("overlay");
  if (svg) svg.remove();
  svg = document.createElementNS(NS, "svg");
  svg.id = "overlay";
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", "100%");
  svg.style.cssText =
    "position:absolute;inset:0;pointer-events:none;z-index:15";
  // marqueur de pointe de flèche
  svg.innerHTML =
    `<defs><marker id="ah" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="4"
       markerHeight="4" orient="auto-start-reverse">
       <path d="M0,0 L10,5 L0,10 z" fill="${ARROW_COLOR}"/></marker></defs>
     <g id="g-hints"></g><g id="g-annot"></g>`;
  $boardEl.style.position = "relative";
  $boardEl.appendChild(svg);
  computeCenters();
  bindBoardEvents();
}

function computeCenters() {
  centers = {};
  const brect = $boardEl.getBoundingClientRect();
  const squares = $boardEl.querySelectorAll("[data-square]");
  squares.forEach(el => {
    const r = el.getBoundingClientRect();
    sqSize = r.width;
    centers[el.getAttribute("data-square")] =
      { x: r.left - brect.left + r.width / 2, y: r.top - brect.top + r.height / 2 };
  });
}

function squareFromEvent(e) {
  const el = e.target.closest("[data-square]");
  return el ? el.getAttribute("data-square") : null;
}

let eventsBound = false;
function bindBoardEvents() {
  computeCenters();
  if (eventsBound) return;
  eventsBound = true;

  // bloque le menu contextuel sur l'échiquier
  $boardEl.addEventListener("contextmenu", e => e.preventDefault());

  // capture : on intercepte le clic DROIT avant que chessboard.js ne démarre un drag
  $boardEl.addEventListener("mousedown", e => {
    if (e.button === 2) {
      e.preventDefault();
      e.stopPropagation();
      annotStart = squareFromEvent(e);
    }
  }, true);

  // clic GAUCHE : sélection / clic-pour-jouer (+ efface les annotations)
  $boardEl.addEventListener("mousedown", e => {
    if (e.button !== 0) return;
    if (annotations.length) { annotations = []; drawAnnot(); }
    const sq = squareFromEvent(e);
    if (!sq) { clearSelection(); return; }
    if (selected && sq === selected) { clearSelection(); return; }  // re-clic = désélection
    if (selected && isLegalDest(selected, sq)) {
      const from = selected; clearSelection(); tryMove(from, sq);
      return;
    }
    const piece = game && game.get(sq);
    if (piece && piece.color === game.turn() && !solved) {
      selectSquare(sq);
    } else {
      clearSelection();
    }
  });

  // relâchement clic DROIT : termine la flèche / pose un cercle
  window.addEventListener("mouseup", e => {
    if (e.button !== 2 || annotStart == null) return;
    const end = squareFromEvent(e);
    if (end) toggleAnnotation(annotStart, end);
    annotStart = null;
  });

  window.addEventListener("resize", () => { computeCenters(); redrawAll(); });
}

function isLegalDest(from, to) {
  if (!game) return false;
  return game.moves({ square: from, verbose: true }).some(m => m.to === to);
}

function selectSquare(sq) {
  selected = sq;
  drawHints();
}
function clearSelection() {
  selected = null;
  drawHints();
}

function toggleAnnotation(from, to) {
  const kind = from === to ? "circle" : "arrow";
  const i = annotations.findIndex(a => a.kind === kind && a.from === from && a.to === to);
  if (i >= 0) annotations.splice(i, 1);
  else annotations.push({ kind, from, to });
  drawAnnot();
}

function redrawAll() { drawHints(); drawAnnot(); }

function drawHints() {
  const g = document.getElementById("g-hints");
  if (!g) return;
  g.innerHTML = "";
  if (!selected || !game) return;
  // case sélectionnée surlignée
  rectHighlight(g, selected, "rgba(255,221,0,0.45)");
  for (const m of game.moves({ square: selected, verbose: true })) {
    const c = centers[m.to];
    if (!c) continue;
    const capture = m.flags.includes("c") || m.flags.includes("e");
    const circ = document.createElementNS(NS, "circle");
    circ.setAttribute("cx", c.x); circ.setAttribute("cy", c.y);
    if (capture) {
      circ.setAttribute("r", sqSize * 0.46);
      circ.setAttribute("fill", "none");
      circ.setAttribute("stroke", "rgba(20,85,20,0.45)");
      circ.setAttribute("stroke-width", sqSize * 0.09);
    } else {
      circ.setAttribute("r", sqSize * 0.16);
      circ.setAttribute("fill", "rgba(20,85,20,0.40)");
    }
    g.appendChild(circ);
  }
}

function rectHighlight(g, sq, color) {
  const c = centers[sq];
  if (!c) return;
  const r = document.createElementNS(NS, "rect");
  r.setAttribute("x", c.x - sqSize / 2); r.setAttribute("y", c.y - sqSize / 2);
  r.setAttribute("width", sqSize); r.setAttribute("height", sqSize);
  r.setAttribute("fill", color);
  g.appendChild(r);
}

function drawAnnot() {
  const g = document.getElementById("g-annot");
  if (!g) return;
  g.innerHTML = "";
  for (const a of annotations) {
    if (a.kind === "circle") {
      const c = centers[a.from]; if (!c) continue;
      const circ = document.createElementNS(NS, "circle");
      circ.setAttribute("cx", c.x); circ.setAttribute("cy", c.y);
      circ.setAttribute("r", sqSize * 0.45);
      circ.setAttribute("fill", "none");
      circ.setAttribute("stroke", ARROW_COLOR);
      circ.setAttribute("stroke-width", sqSize * 0.07);
      g.appendChild(circ);
    } else {
      const a0 = centers[a.from], b0 = centers[a.to];
      if (!a0 || !b0) continue;
      // raccourcit la flèche pour ne pas masquer la case cible
      const dx = b0.x - a0.x, dy = b0.y - a0.y;
      const len = Math.hypot(dx, dy) || 1;
      const shrink = sqSize * 0.34;
      const ex = b0.x - (dx / len) * shrink, ey = b0.y - (dy / len) * shrink;
      const line = document.createElementNS(NS, "line");
      line.setAttribute("x1", a0.x); line.setAttribute("y1", a0.y);
      line.setAttribute("x2", ex); line.setAttribute("y2", ey);
      line.setAttribute("stroke", ARROW_COLOR);
      line.setAttribute("stroke-width", sqSize * 0.16);
      line.setAttribute("stroke-linecap", "round");
      line.setAttribute("marker-end", "url(#ah)");
      g.appendChild(line);
    }
  }
}

/* ---------- indices & solution ---------- */
async function nextHint() {
  if (!puzzle || solved) return;
  if (hintLevel >= 4) { setStatus("Plus d'indices : à toi de conclure.", ""); return; }
  hintLevel += 1;
  const r = await fetch("/api/hint", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: puzzle.id, level: hintLevel }),
  });
  const data = await r.json();
  const li = document.createElement("li");
  li.innerHTML = `<b>Indice ${data.level}/${data.total_levels} :</b> ${escapeHtml(data.hint)}`;
  $hints.appendChild(li);
}

async function showSolution() {
  if (!puzzle || busy) return;
  busy = true; solved = true; clearSelection();
  try {
    const r = await fetch(`/api/solution?id=${encodeURIComponent(puzzle.id)}`);
    const data = await r.json();
    $line.textContent = data.san.join("  ");
    $lineWrap.style.display = "block";
    setStatus("Rejeu de la solution…", "");
    const g = new Chess(puzzle.fen);
    board.position(puzzle.fen); await sleep(500);
    for (const uci of data.uci) {
      g.move(uciToObj(uci)); board.position(g.fen()); await sleep(650);
    }
    setStatus("Solution rejouée.", "ok");
  } finally { busy = false; }
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

document.getElementById("new").onclick = loadPuzzle;
document.getElementById("hint").onclick = nextHint;
document.getElementById("solution").onclick = showSolution;

loadPuzzle();
