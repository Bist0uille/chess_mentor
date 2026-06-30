"""Détecteurs de « signaux faibles » d'une position d'échecs.

Tout est calculé de façon déterministe avec python-chess : ces signaux sont la
VÉRITÉ-TERRAIN qui ancre les explications du coach (aucune invention possible).

Convention : on reçoit un `chess.Board` dont `board.turn` est le camp qui doit
trouver le coup (le « solveur »). Les cibles sont les pièces adverses.
"""
from dataclasses import dataclass, asdict
from typing import List

import chess

PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}
PIECE_FR = {
    chess.PAWN: "pion",
    chess.KNIGHT: "cavalier",
    chess.BISHOP: "fou",
    chess.ROOK: "tour",
    chess.QUEEN: "dame",
    chess.KING: "roi",
}


@dataclass
class Signal:
    type: str            # identifiant machine : "hanging", "king_box", ...
    severity: int        # 1 (indice léger) .. 3 (signal fort)
    squares: List[str]   # cases concernées (noms : "f7", "e1"...)
    short: str           # phrase courte, factuelle, en français

    def to_dict(self):
        return asdict(self)


def _name(sq: int) -> str:
    return chess.square_name(sq)


def _piece_at_fr(board: chess.Board, sq: int) -> str:
    p = board.piece_at(sq)
    return PIECE_FR[p.piece_type] if p else "?"


def detect_hanging(board: chess.Board) -> List[Signal]:
    """Pièces adverses attaquées par nous et insuffisamment défendues."""
    me, them = board.turn, not board.turn
    out = []
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != them or piece.piece_type == chess.KING:
            continue
        attackers = board.attackers(me, sq)
        if not attackers:
            continue
        defenders = board.attackers(them, sq)
        val = PIECE_VALUE[piece.piece_type]
        if not defenders:
            sev = 3 if val >= 3 else 2
            out.append(Signal(
                "hanging", sev, [_name(sq)],
                f"Le {_piece_at_fr(board, sq)} en {_name(sq)} n'est pas défendu.",
            ))
        else:
            # capture potentiellement gagnante : mon attaquant le moins cher < valeur cible
            cheapest = min(
                PIECE_VALUE[board.piece_at(a).piece_type] for a in attackers
            )
            if cheapest < val and len(attackers) > len(defenders):
                out.append(Signal(
                    "underdefended", 2, [_name(sq)],
                    f"Le {_piece_at_fr(board, sq)} en {_name(sq)} est sous-défendu "
                    f"(plus d'attaquants que de défenseurs).",
                ))
    return out


def detect_king_safety(board: chess.Board) -> List[Signal]:
    """Cases de fuite du roi adverse + faiblesse du dernier rang."""
    me, them = board.turn, not board.turn
    ksq = board.king(them)
    out = []
    if ksq is None:
        return out

    flight = []
    for sq in board.attacks(ksq):  # cases adjacentes (déplacements du roi)
        occ = board.piece_at(sq)
        if occ and occ.color == them:
            continue  # case occupée par une pièce amie du roi
        if board.is_attacked_by(me, sq):
            continue  # case contrôlée par nous
        flight.append(sq)

    n = len(flight)
    if n == 0:
        out.append(Signal(
            "king_box", 3, [_name(ksq)],
            f"Le roi adverse en {_name(ksq)} n'a aucune case de fuite.",
        ))
    elif n == 1:
        out.append(Signal(
            "king_box", 2, [_name(ksq), _name(flight[0])],
            f"Le roi adverse en {_name(ksq)} n'a qu'une seule case de fuite "
            f"({_name(flight[0])}).",
        ))

    # Dernier rang : roi sur sa rangée de départ, mur de pions devant
    back_rank = 0 if them == chess.WHITE else 7
    if chess.square_rank(ksq) == back_rank:
        front = ksq + (8 if them == chess.WHITE else -8)
        blocked = all(
            (board.piece_at(s) is not None and board.piece_at(s).color == them)
            for s in board.attacks(ksq) if chess.square_rank(s) != back_rank
        )
        if blocked and 0 <= front < 64:
            out.append(Signal(
                "back_rank", 2, [_name(ksq)],
                f"Le roi adverse est sur son dernier rang, bloqué par ses pions "
                f"(faiblesse du dernier rang).",
            ))
    return out


def detect_alignments(board: chess.Board) -> List[Signal]:
    """Pièces adverses alignées avec leur roi (potentiel clouage / enfilade)."""
    me, them = board.turn, not board.turn
    ksq = board.king(them)
    out = []
    if ksq is None:
        return out
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != them or piece.piece_type == chess.KING:
            continue
        line = chess.ray(ksq, sq)  # bitboard de la ligne, 0 si non alignés
        if not line:
            continue
        between = chess.SquareSet(chess.between(ksq, sq))
        # ligne dégagée entre le roi et la pièce
        if any(board.piece_at(b) is not None for b in between):
            continue
        # est-ce une ligne exploitable (rangée/colonne = tour/dame, diag = fou/dame) ?
        same_rank = chess.square_rank(ksq) == chess.square_rank(sq)
        same_file = chess.square_file(ksq) == chess.square_file(sq)
        kind = "colonne/rangée" if (same_rank or same_file) else "diagonale"
        out.append(Signal(
            "alignment", 1, [_name(ksq), _name(sq)],
            f"Le roi adverse et son {_piece_at_fr(board, sq)} sont alignés "
            f"sur la même {kind} ({_name(ksq)}–{_name(sq)}).",
        ))
    return out[:2]  # on garde les plus parlants


def detect_forcing_moves(board: chess.Board) -> List[Signal]:
    """Échecs disponibles et doubles attaques (fourchettes) après un coup."""
    out = []
    checks = []
    forks = []
    for move in board.legal_moves:
        gives_check = board.gives_check(move)
        if gives_check:
            checks.append(move)
        # double attaque : après le coup, la pièce déplacée attaque >=2 cibles de valeur
        board.push(move)
        try:
            dest = move.to_square
            moved = board.piece_at(dest)
            if moved:
                targets = []
                for tsq in board.attacks(dest):
                    p = board.piece_at(tsq)
                    if p and p.color != moved.color and (
                        p.piece_type == chess.KING or PIECE_VALUE[p.piece_type] >= 3
                    ):
                        targets.append(tsq)
                if len(targets) >= 2:
                    forks.append((move, dest, targets))
        finally:
            board.pop()

    if checks:
        sqs = sorted({_name(m.to_square) for m in checks})
        out.append(Signal(
            "checks", 2, sqs,
            f"Coup(s) d'échec disponible(s) vers : {', '.join(sqs)}.",
        ))
    for move, dest, targets in forks[:2]:
        names = [_name(t) for t in targets]
        out.append(Signal(
            "double_attack", 3, [_name(dest)] + names,
            f"Un coup en {_name(dest)} attaque simultanément {', '.join(names)} "
            f"(double attaque).",
        ))
    return out


def detect_all(board: chess.Board) -> List[Signal]:
    """Tous les signaux, triés du plus fort au plus faible."""
    signals = (
        detect_hanging(board)
        + detect_king_safety(board)
        + detect_forcing_moves(board)
        + detect_alignments(board)
    )
    signals.sort(key=lambda s: s.severity, reverse=True)
    return signals
