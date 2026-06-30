/* Wrapper minimal d'un moteur UCI (Lozza) tournant dans un Web Worker.
   Aucun en-tête spécial requis (JS pur, pas de WebAssembly / SharedArrayBuffer). */
class Engine {
  constructor(url) {
    this.ok = false;
    try {
      this.worker = new Worker(url);
      this.worker.onmessage = (e) => this._line(e.data);
      this.worker.postMessage("uci");
      this.worker.postMessage("setoption name Hash value 16");
      this.worker.postMessage("ucinewgame");  // requis par Lozza avant toute recherche
      this.worker.postMessage("isready");
      this.ok = true;
    } catch (err) {
      console.warn("Moteur indisponible :", err);
    }
    this._pending = null;
    this._q = Promise.resolve();
  }

  _line(line) {
    if (typeof line !== "string" || !this._pending) return;
    if (line.startsWith("info")) {
      const cp = / score cp (-?\d+)/.exec(line);
      const mate = / score mate (-?\d+)/.exec(line);
      const pv = / pv (.+)$/.exec(line);
      if (mate) { this._pending.mate = parseInt(mate[1], 10); this._pending.cp = null; }
      else if (cp) { this._pending.cp = parseInt(cp[1], 10); this._pending.mate = null; }
      if (pv) this._pending.pv = pv[1].trim().split(/\s+/);
    } else if (line.startsWith("bestmove")) {
      const bm = line.split(/\s+/)[1];
      const p = this._pending;
      this._pending = null;
      p.resolve({ bestmove: bm, cp: p.cp, mate: p.mate, pv: p.pv, stm: p.stm });
    }
  }

  /** Analyse une position FEN à la profondeur donnée. Score relatif au trait. */
  analyse(fen, depth = 12) {
    if (!this.ok) return Promise.resolve(null);
    const stm = fen.split(" ")[1] === "b" ? "b" : "w";
    const run = () => new Promise((resolve) => {
      this._pending = { resolve, cp: null, mate: null, pv: [], stm };
      this.worker.postMessage("position fen " + fen);
      this.worker.postMessage("go depth " + depth);
    });
    const p = this._q.then(run, run);
    this._q = p.catch(() => {});
    return p;
  }
}

/** Score (cp/mate, relatif au trait) → point de vue des Blancs.
 *  Convention Lozza : « mate N » = mat en N+1 ; N >= 0 ⇒ le trait gagne. */
function whiteEval(res) {
  if (!res) return null;
  if (res.mate != null) {
    const stmWins = res.mate >= 0;                       // le camp au trait mate
    const whiteWins = (res.stm === "w") === stmWins;
    const dist = Math.abs(res.mate) + 1;                 // mate 0 → mat en 1
    return { mate: whiteWins ? dist : -dist };
  }
  if (res.cp != null) {
    const sign = res.stm === "w" ? 1 : -1;
    return { cp: sign * res.cp };
  }
  return null;
}

/** Formate une évaluation (point de vue Blancs) en texte court : « +2,3 » / « #3 ». */
function formatEval(ev) {
  if (!ev) return "—";
  if (ev.mate != null) return (ev.mate > 0 ? "#" : "#-") + Math.abs(ev.mate);
  const v = ev.cp / 100;
  return (v >= 0 ? "+" : "") + v.toFixed(1).replace(".", ",");
}

// Export Node (pour les tests unitaires) — sans effet dans le navigateur.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { whiteEval, formatEval };
}
