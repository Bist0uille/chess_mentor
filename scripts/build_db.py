"""Construit puzzles.sqlite à partir de la base ouverte de puzzles Lichess.

La base complète (~4 M puzzles) est volumineuse ; on la lit en streaming et on
filtre un sous-ensemble exploitable pour le proto.

Usage :
    python scripts/build_db.py --limit 3000 --min-rating 600 --max-rating 2200

Si le téléchargement n'est pas possible, on peut pointer un CSV/zst local :
    python scripts/build_db.py --source /chemin/lichess_db_puzzle.csv.zst
"""
import argparse
import csv
import io
import os
import sqlite3
import sys
import urllib.request

import zstandard as zstd

LICHESS_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(HERE, "puzzles.sqlite")

# Colonnes du CSV Lichess (ordre officiel)
# PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags


def open_stream(source: str):
    """Renvoie un itérateur de lignes texte depuis une source .zst (URL ou fichier)."""
    if source.startswith("http://") or source.startswith("https://"):
        print(f"Téléchargement en streaming depuis {source} ...", file=sys.stderr)
        resp = urllib.request.urlopen(source)  # noqa: S310 (URL connue, CC0)
        raw = resp
    else:
        print(f"Lecture du fichier local {source} ...", file=sys.stderr)
        raw = open(source, "rb")
    dctx = zstd.ZstdDecompressor()
    reader = dctx.stream_reader(raw)
    return io.TextIOWrapper(reader, encoding="utf-8", newline="")


def build(source, limit, min_rating, max_rating, min_popularity):
    con = sqlite3.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS puzzles")
    con.execute(
        """
        CREATE TABLE puzzles (
            id TEXT PRIMARY KEY,
            fen TEXT NOT NULL,
            moves TEXT NOT NULL,
            rating INTEGER NOT NULL,
            popularity INTEGER,
            nb_plays INTEGER,
            themes TEXT,
            game_url TEXT
        )
        """
    )
    con.execute("CREATE INDEX idx_rating ON puzzles(rating)")

    stream = open_stream(source)
    reader = csv.reader(stream)
    header = next(reader)  # ignore l'en-tête
    assert header[0] == "PuzzleId", f"En-tête inattendu : {header[:3]}"

    inserted = 0
    scanned = 0
    rows = []
    for row in reader:
        scanned += 1
        try:
            rating = int(row[3])
            popularity = int(row[5])
        except (ValueError, IndexError):
            continue
        if not (min_rating <= rating <= max_rating):
            continue
        if popularity < min_popularity:
            continue
        rows.append(
            (row[0], row[1], row[2], rating, popularity, int(row[6] or 0), row[7], row[8])
        )
        inserted += 1
        if len(rows) >= 1000:
            con.executemany("INSERT OR IGNORE INTO puzzles VALUES (?,?,?,?,?,?,?,?)", rows)
            con.commit()
            rows.clear()
            print(f"  ... {inserted} insérés / {scanned} scannés", file=sys.stderr)
        if inserted >= limit:
            break

    if rows:
        con.executemany("INSERT OR IGNORE INTO puzzles VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()

    total = con.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0]
    con.close()
    print(f"Terminé : {total} puzzles dans {DB_PATH}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default=LICHESS_URL, help="URL ou fichier .zst")
    p.add_argument("--limit", type=int, default=3000)
    p.add_argument("--min-rating", type=int, default=600)
    p.add_argument("--max-rating", type=int, default=2200)
    p.add_argument("--min-popularity", type=int, default=80)
    args = p.parse_args()
    build(args.source, args.limit, args.min_rating, args.max_rating, args.min_popularity)


if __name__ == "__main__":
    main()
