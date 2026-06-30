/* Chess Mentor — frontend (multi-coups) */
let board = null;
let game = null;          // chess.js : position LIVE (avance à chaque bon coup)
let puzzle = null;        // {id, rating, themes, side_to_move, n_solver_moves}
let ply = 0;              // numéro du coup solveur en cours (0-based)
let hintLevel = 0;
let solved = false;
let busy = false;

const $status = document.getElementById("status");
const $meta = document.getElementById("meta");
const $hints = document.getElementById("hints");
const $progress = document.getElementById("progress");
const $lineWrap = document.getElementById("lineWrap");
const $line = document.getElementById("line");

function setStatus(msg, cls) { $status.textContent = msg; $status.className = cls || ""; }

function uciToObj(uci) {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4),
           promotion: uci.length > 4 ? uci[4] : undefined };
}

function updateProgress() {
  if (!puzzle) return;
  $progress.textContent = `Coup ${Math.min(ply + 1, puzzle.n_solver_moves)} / ` +
    `${puzzle.n_solver_moves}`;
}

async function loadPuzzle() {
  if (busy) return;
  setStatus("Chargement…", "");
  $hints.innerHTML = "";
  $lineWrap.style.display = "none";
  hintLevel = 0; ply = 0; solved = false;
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
    onDrop,
  });
  updateProgress();
  setStatus("À toi de jouer.", "");
}

function onDrop(source, target) {
  if (solved || busy) return "snapback";
  // Légalité testée sur une copie de la position LIVE (sans muter game)
  const probe = new Chess(game.fen());
  const move = probe.move({ from: source, to: target, promotion: "q" });
  if (move === null) return "snapback";
  validate(move.from + move.to + (move.promotion || ""));
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
      board.position(game.fen());  // on revient à la position courante
      return;
    }
    // Bon coup : on l'applique à la position live
    game.move(uciToObj(uci));
    if (data.opponent_uci) game.move(uciToObj(data.opponent_uci));
    board.position(game.fen());
    ply = data.next_ply;
    updateProgress();
    if (data.done) {
      solved = true;
      setStatus("✅ Résolu ! Bien joué.", "ok");
      if (data.line_san) {
        $line.textContent = data.line_san.join("  ");
        $lineWrap.style.display = "block";
      }
    } else {
      const rep = data.opponent_san ? ` L'adversaire répond ${data.opponent_san}.` : "";
      setStatus(`✅ Bon coup !${rep} Continue.`, "ok");
    }
  } finally {
    busy = false;
  }
}

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

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function showSolution() {
  if (!puzzle || busy) return;
  busy = true; solved = true;
  try {
    const r = await fetch(`/api/solution?id=${encodeURIComponent(puzzle.id)}`);
    const data = await r.json();
    $line.textContent = data.san.join("  ");
    $lineWrap.style.display = "block";
    setStatus("Rejeu de la solution…", "");
    // Rejoue toute la ligne depuis la position de départ, sur l'échiquier.
    const g = new Chess(puzzle.fen);
    board.position(puzzle.fen);
    await sleep(500);
    for (const uci of data.uci) {
      g.move(uciToObj(uci));
      board.position(g.fen());
      await sleep(650);
    }
    setStatus("Solution rejouée.", "ok");
  } finally {
    busy = false;
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

document.getElementById("new").onclick = loadPuzzle;
document.getElementById("hint").onclick = nextHint;
document.getElementById("solution").onclick = showSolution;

loadPuzzle();
