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
let lastMove = [];        // cases du dernier coup joué (surbrillance)
let loadedHints = null;   // les 4 indices, chargés en un seul appel
let refuteMove = null;    // flèche de réfutation (coup du moteur)
let history = [];         // positions [{fen, lastMove, explain}] pour le navigateur
let histIdx = 0;          // index courant dans l'historique
let explore = false;      // mode exploration libre (après résolution)

const engine = new Engine("/static/lozza.js");  // moteur d'échecs (navigateur)
const REFUTE_COLOR = "rgba(179,38,30,0.85)";

// Notation française des pièces côté client (K→R, Q→D, R→T, B→F, N→C).
function frSan(s) {
  return s.replace(/[KQRBN]/g, c => ({ K: "R", Q: "D", R: "T", B: "F", N: "C" }[c]));
}

function band() {
  const [lo, hi] = document.getElementById("level").value.split("-").map(Number);
  return { min: lo, max: hi, elo: Math.round((lo + hi) / 2) };
}

const NS = "http://www.w3.org/2000/svg";
const ARROW_COLOR = "rgba(21,120,27,0.78)";

const $status = document.getElementById("status");
const $meta = document.getElementById("meta");
const $hints = document.getElementById("hints");
const $progress = document.getElementById("progress");
const $lineWrap = document.getElementById("lineWrap");
const $line = document.getElementById("line");
const $boardEl = document.getElementById("board");
const $themes = document.getElementById("themes");

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
  hintLevel = 0; ply = 0; solved = false; explore = false; lastMove = []; loadedHints = null;
  clearSelection(); annotations = []; clearRefute(); redrawAll();
  document.getElementById("movelog").style.display = "none";
  const b = band();
  const r = await fetch(`/api/puzzle?min_rating=${b.min}&max_rating=${b.max}`);
  if (!r.ok) { setStatus("Erreur : " + (await r.text()), "ko"); return; }
  puzzle = await r.json();
  game = new Chess(puzzle.fen);
  const orientation = puzzle.side_to_move === "w" ? "white" : "black";
  const trait = puzzle.side_to_move === "w" ? "Blancs" : "Noirs";
  $meta.innerHTML = `Trait aux <b>${trait}</b> · rating ${puzzle.rating} · ` +
    `${puzzle.n_solver_moves} coup(s) à trouver`;
  $themes.innerHTML = `<b>Thèmes :</b> ${(puzzle.themes || []).join(", ") || "—"}`;
  history = [{ fen: puzzle.fen, lastMove: [], explain: "" }];
  histIdx = 0;
  if (board) board.destroy();
  board = Chessboard("board", {
    position: puzzle.fen, orientation, draggable: true,
    pieceTheme: "https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png",
    onDrop, onDragStart, onSnapEnd,
  });
  setupOverlay();
  updateProgress();
  setStatus("À toi de jouer.", "");
  updateEval(puzzle.fen);
  updateNav();
  renderMoveLog();
}

/* ---------- coups (drag + clic) ---------- */
function reviewing() { return histIdx !== history.length - 1; }

// Position chess.js actuellement AFFICHÉE (live en résolution, ou case d'historique).
function curChess() {
  return explore ? new Chess(history[histIdx].fen) : game;
}

function onDragStart(source) {
  if (busy) return false;
  if (!explore && (solved || reviewing())) return false;  // résolution : pas de jeu hors trait
  const g = curChess();
  const piece = g.get(source);
  return piece && piece.color === g.turn();
}

// Coup joué en mode exploration (analyse libre, sans validation contre la solution).
// render=false quand le coup vient d'un glisser (chessboard a déjà bougé la pièce ;
// la resync se fait dans onSnapEnd) ; render=true pour un clic-pour-jouer.
function exploreMove(source, target, render) {
  const g = new Chess(history[histIdx].fen);
  const mv = g.move({ from: source, to: target, promotion: "q" });
  if (!mv) return false;
  history = history.slice(0, histIdx + 1);          // on branche depuis la position courante
  history.push({ fen: g.fen(), lastMove: [mv.from, mv.to], explain: "" });
  histIdx = history.length - 1;
  lastMove = [mv.from, mv.to];
  clearSelection(); clearRefute();
  if (render) board.position(g.fen());
  drawLastMove(); updateEval(g.fen()); updateNav(); renderMoveLog();
  return true;
}

// Resync après un glisser en exploration (gère roque / prise en passant / promotion).
function onSnapEnd() {
  if (explore && board && history[histIdx]) board.position(history[histIdx].fen);
}

function onDrop(source, target) {
  // Clic simple (relâché sur la même case) : on GARDE la sélection et les points.
  if (source === target) return;
  clearSelection();
  if (explore) { if (!exploreMove(source, target, false)) return "snapback"; return; }
  if (!tryMove(source, target)) return "snapback";
}

function tryMove(source, target) {
  if (solved || busy) return false;
  const probe = new Chess(game.fen());
  const mv = probe.move({ from: source, to: target, promotion: "q" });
  if (mv === null) return false;
  if (mv.flags.includes("p")) {        // promotion : on demande la pièce
    choosePromotion(target).then(letter => {
      if (!letter) { board.position(game.fen()); return; }  // annulé
      validate(source + target + letter);
    });
    return true;
  }
  validate(mv.from + mv.to + (mv.promotion || ""));
  return true;
}

function choosePromotion(target) {
  const promo = document.getElementById("promo");
  const c = centers[target];
  const brect = $boardEl.getBoundingClientRect();
  promo.style.position = "fixed";
  if (c) {
    promo.style.left = (brect.left + Math.min(c.x, brect.width - 110)) + "px";
    promo.style.top = (brect.top + Math.max(0, c.y - 30)) + "px";
  }
  promo.style.display = "block";
  return new Promise(resolve => {
    function cleanup(letter) {
      promo.style.display = "none";
      promo.querySelectorAll("button").forEach(b => (b.onclick = null));
      document.removeEventListener("mousedown", outside, true);
      resolve(letter);
    }
    function outside(e) { if (!promo.contains(e.target)) cleanup(null); }
    promo.querySelectorAll("button").forEach(b => {
      b.onclick = () => cleanup(b.getAttribute("data-p"));
    });
    setTimeout(() => document.addEventListener("mousedown", outside, true), 0);
  });
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
      if (data.legal) refute(uci);  // le moteur explique pourquoi ça échoue
      return;
    }
    clearRefute();
    game.move(uciToObj(uci));
    lastMove = [uci.slice(0, 2), uci.slice(2, 4)];
    if (data.opponent_uci) {
      game.move(uciToObj(data.opponent_uci));
      lastMove.push(data.opponent_uci.slice(0, 2), data.opponent_uci.slice(2, 4));
    }
    board.position(game.fen());
    drawLastMove();
    updateEval(game.fen());
    history.push({ fen: game.fen(), lastMove: lastMove.slice(), explain: data.explain || "" });
    histIdx = history.length - 1;
    updateNav();
    renderMoveLog();
    ply = data.next_ply;
    updateProgress();
    if (data.done) {
      solved = true; explore = true;  // exploration libre de la suite
      setStatus("✅ Résolu ! Tu peux continuer à bouger les pièces pour explorer.", "ok");
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
    `<defs>
       <marker id="ah" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="4"
         markerHeight="4" orient="auto-start-reverse">
         <path d="M0,0 L10,5 L0,10 z" fill="${ARROW_COLOR}"/></marker>
       <marker id="ahr" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="4"
         markerHeight="4" orient="auto-start-reverse">
         <path d="M0,0 L10,5 L0,10 z" fill="${REFUTE_COLOR}"/></marker>
     </defs>
     <g id="g-lastmove"></g><g id="g-hints"></g><g id="g-annot"></g>`;
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
    if (annotations.length || refuteMove) { annotations = []; refuteMove = null; drawAnnot(); }
    if (!explore && reviewing()) { clearSelection(); return; }  // revue (résolution) : pas de jeu
    const sq = squareFromEvent(e);
    if (!sq) { clearSelection(); return; }
    if (selected && sq === selected) { clearSelection(); return; }  // re-clic = désélection
    if (selected && isLegalDest(selected, sq)) {
      const from = selected; clearSelection();
      if (explore) exploreMove(from, sq, true); else tryMove(from, sq);
      return;
    }
    const cg = curChess();
    const piece = cg && cg.get(sq);
    if (piece && piece.color === cg.turn() && (explore || !solved)) {
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

  window.addEventListener("resize", () => {
    if (board) board.resize();   // l'échiquier s'adapte à la largeur
    setupOverlay();              // recrée la surcouche SVG à la bonne taille
    redrawAll();                 // redessine flèches / cases / dernier coup
  });
}

function isLegalDest(from, to) {
  const g = curChess();
  if (!g) return false;
  return g.moves({ square: from, verbose: true }).some(m => m.to === to);
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

function redrawAll() { drawLastMove(); drawHints(); drawAnnot(); }

function drawLastMove() {
  const g = document.getElementById("g-lastmove");
  if (!g) return;
  g.innerHTML = "";
  for (const sq of lastMove) rectHighlight(g, sq, "rgba(255,221,0,0.32)");
}

/* ---------- navigateur de position (⏮ ◀ ▶ ⏭) ---------- */
function updateNav() {
  const atStart = histIdx <= 0, atEnd = histIdx >= history.length - 1;
  const set = (id, dis) => { const b = document.getElementById(id); if (b) b.disabled = dis; };
  set("navStart", atStart); set("navPrev", atStart);
  set("navNext", atEnd); set("navEnd", atEnd);
}

function showHist(idx) {
  if (!board || !history.length) return;
  histIdx = Math.max(0, Math.min(idx, history.length - 1));
  const h = history[histIdx];
  clearSelection();
  board.position(h.fen);
  lastMove = h.lastMove.slice();
  drawLastMove();
  updateEval(h.fen);
  updateNav();
  renderMoveLog();
}

/* ---------- moteur : barre d'éval + réfutation ---------- */
async function updateEval(fen) {
  const fill = document.getElementById("evalfill");
  const num = document.getElementById("evalnum");
  // Positions terminales : le moteur renverrait « mate 0 » (→ barre à 0). On
  // affiche directement le résultat à la place.
  try {
    const g = new Chess(fen);
    if (g.game_over()) {
      if (g.in_checkmate()) {
        const whiteWon = g.turn() === "b";  // trait au camp maté
        fill.style.height = whiteWon ? "100%" : "0%";
        num.textContent = whiteWon ? "1–0" : "0–1";
      } else {
        fill.style.height = "50%"; num.textContent = "½–½";
      }
      return;
    }
  } catch (e) { /* fen invalide : on ignore */ }
  if (!engine.ok) return;
  const res = await engine.analyse(fen, 11);
  const ev = whiteEval(res);
  if (!ev) return;
  let share;  // part des Blancs (0..100), 50 = égalité ; barre verticale (bas = Blancs)
  if (ev.mate != null) share = ev.mate > 0 ? 100 : 0;
  else share = Math.max(2, Math.min(98, 50 + ev.cp / 16));
  fill.style.height = share + "%";
  num.textContent = formatEval(ev);
}

async function refute(uci) {
  if (!engine.ok) return;
  const g = new Chess(game.fen());
  const mine = g.move(uciToObj(uci));
  if (!mine) return;
  const res = await engine.analyse(g.fen(), 14);
  if (!res || !res.bestmove) return;
  const reply = g.move(uciToObj(res.bestmove));
  // éval du point de vue du SOLVEUR (= - score relatif à l'adversaire au trait)
  let verdict;
  if (res.mate != null) {
    const m = -res.mate;
    verdict = m < 0 ? `tu te fais mater en ${Math.abs(m)}` : "la position reste tenable";
  } else {
    const cp = -res.cp / 100;
    verdict = cp <= -2 ? `tu es perdant (éval ${cp.toFixed(1).replace(".", ",")})`
            : cp <= -0.5 ? `tu es moins bien (éval ${cp.toFixed(1).replace(".", ",")})`
            : "ce n'est pas la solution";
  }
  const $r = document.getElementById("refute");
  $r.innerHTML = `<b>Pourquoi ça ne marche pas :</b> après ton coup, l'adversaire ` +
    `joue <b>${reply ? escapeHtml(frSan(reply.san)) : res.bestmove}</b> et ${verdict}.`;
  $r.style.display = "block";
  // flèche rouge de réfutation sur l'échiquier
  refuteMove = { from: res.bestmove.slice(0, 2), to: res.bestmove.slice(2, 4) };
  drawAnnot();
}

function clearRefute() {
  refuteMove = null;
  const $r = document.getElementById("refute");
  if ($r) $r.style.display = "none";
}

function renderMoveLog() {
  const el = document.getElementById("movelog");
  if (!el) return;
  const items = [];
  for (let i = 1; i < history.length; i++) {
    if (!history[i].explain) continue;
    const cur = i === histIdx ? " cur" : "";
    items.push(`<div class="mv${cur}">${escapeHtml(history[i].explain)}</div>`);
  }
  if (items.length) {
    el.innerHTML = `<div class="mvlabel">Pourquoi ces coups</div>` + items.join("");
    el.style.display = "flex";
  } else {
    el.style.display = "none";
  }
}

function drawHints() {
  const g = document.getElementById("g-hints");
  if (!g) return;
  g.innerHTML = "";
  const cg = curChess();
  if (!selected || !cg) return;
  // case sélectionnée surlignée
  rectHighlight(g, selected, "rgba(255,221,0,0.45)");
  for (const m of cg.moves({ square: selected, verbose: true })) {
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

function drawArrow(g, from, to, color, marker) {
  const a0 = centers[from], b0 = centers[to];
  if (!a0 || !b0) return;
  const dx = b0.x - a0.x, dy = b0.y - a0.y;
  const len = Math.hypot(dx, dy) || 1;
  const shrink = sqSize * 0.34;
  const ex = b0.x - (dx / len) * shrink, ey = b0.y - (dy / len) * shrink;
  const line = document.createElementNS(NS, "line");
  line.setAttribute("x1", a0.x); line.setAttribute("y1", a0.y);
  line.setAttribute("x2", ex); line.setAttribute("y2", ey);
  line.setAttribute("stroke", color);
  line.setAttribute("stroke-width", sqSize * 0.16);
  line.setAttribute("stroke-linecap", "round");
  line.setAttribute("marker-end", `url(#${marker})`);
  g.appendChild(line);
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
      drawArrow(g, a.from, a.to, ARROW_COLOR, "ah");
    }
  }
  if (refuteMove) drawArrow(g, refuteMove.from, refuteMove.to, REFUTE_COLOR, "ahr");
}

/* ---------- indices & solution ---------- */
async function nextHint() {
  if (!puzzle || solved) return;
  if (!loadedHints) {
    setStatus("Réflexion du coach…", "");
    const r = await fetch(
      `/api/hints?id=${encodeURIComponent(puzzle.id)}&target_elo=${band().elo}`);
    loadedHints = (await r.json()).hints;
    setStatus("", "");
  }
  if (hintLevel >= loadedHints.length) {
    setStatus("Plus d'indices : à toi de conclure.", ""); return;
  }
  hintLevel += 1;
  const li = document.createElement("li");
  li.innerHTML = `<b>Indice ${hintLevel}/${loadedHints.length} :</b> ` +
    escapeHtml(loadedHints[hintLevel - 1]);
  $hints.appendChild(li);
}

async function showSolution() {
  if (!puzzle || busy) return;
  busy = true; solved = true; clearSelection(); clearRefute();
  try {
    const r = await fetch(`/api/solution?id=${encodeURIComponent(puzzle.id)}`);
    const data = await r.json();
    $line.textContent = data.san.join("  ");
    $lineWrap.style.display = "block";
    // reconstruit l'historique complet depuis la position de départ
    const g = new Chess(puzzle.fen);
    history = [{ fen: puzzle.fen, lastMove: [], explain: "" }];
    data.uci.forEach((uci, i) => {
      g.move(uciToObj(uci));
      history.push({
        fen: g.fen(), lastMove: [uci.slice(0, 2), uci.slice(2, 4)],
        explain: (data.notes && data.notes[i]) || "",
      });
    });
    // anime du début à la fin (puis navigable avec ⏮ ◀ ▶ ⏭)
    setStatus("Rejeu de la solution…", "");
    for (let i = 0; i < history.length; i++) { showHist(i); await sleep(i === 0 ? 400 : 650); }
    explore = true;  // exploration libre après le rejeu
    setStatus("Solution rejouée. Tu peux continuer à bouger les pièces.", "ok");
  } finally { busy = false; }
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

document.getElementById("new").onclick = loadPuzzle;
document.getElementById("hint").onclick = nextHint;
document.getElementById("solution").onclick = showSolution;
document.getElementById("navStart").onclick = () => showHist(0);
document.getElementById("navPrev").onclick = () => showHist(histIdx - 1);
document.getElementById("navNext").onclick = () => showHist(histIdx + 1);
document.getElementById("navEnd").onclick = () => showHist(history.length - 1);
window.addEventListener("keydown", e => {
  if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;
  if (e.key === "ArrowLeft") { e.preventDefault(); showHist(histIdx - 1); }
  else if (e.key === "ArrowRight") { e.preventDefault(); showHist(histIdx + 1); }
});

loadPuzzle();
