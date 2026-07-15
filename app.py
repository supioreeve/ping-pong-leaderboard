import sqlite3
from pathlib import Path
from flask import Flask, g, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "bdr_pingpong.db"
STATIC_DIR = BASE_DIR / "static"

PLAYERS = ["Kate", "David", "Megan", "Reeve", "Jack", "Chris", "Audrey", "Gina"]
STARTING_ELO = 1200
K_FACTOR = 32

app = Flask(__name__, static_folder=None)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            name TEXT PRIMARY KEY,
            elo REAL NOT NULL DEFAULT 1200,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            winner TEXT NOT NULL,
            loser TEXT NOT NULL,
            comment TEXT,
            winner_elo_before REAL NOT NULL,
            loser_elo_before REAL NOT NULL,
            winner_elo_after REAL NOT NULL,
            loser_elo_after REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    for name in PLAYERS:
        conn.execute(
            "INSERT OR IGNORE INTO players (name, elo) VALUES (?, ?)",
            (name, STARTING_ELO),
        )
    conn.commit()
    conn.close()


def compute_elo(winner_elo, loser_elo):
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 - expected_winner
    new_winner_elo = winner_elo + K_FACTOR * (1 - expected_winner)
    new_loser_elo = loser_elo + K_FACTOR * (0 - expected_loser)
    return new_winner_elo, new_loser_elo


def player_badges(row, rank):
    badges = []
    if rank == 1 and (row["wins"] + row["losses"]) > 0:
        badges.append({"emoji": "👑", "label": "Current Champ"})
    if row["streak"] >= 3:
        badges.append({"emoji": "🔥", "label": f"{row['streak']}-win streak"})
    if row["streak"] <= -3:
        badges.append({"emoji": "🥶", "label": f"{-row['streak']}-loss skid"})
    if row["wins"] + row["losses"] == 0:
        badges.append({"emoji": "🆕", "label": "No matches yet"})
    return badges


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(STATIC_DIR, path)


@app.route("/api/leaderboard")
def leaderboard():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM players ORDER BY wins DESC, elo DESC, name ASC"
    ).fetchall()
    result = []
    for i, row in enumerate(rows):
        games = row["wins"] + row["losses"]
        win_pct = round((row["wins"] / games) * 100, 1) if games else 0.0
        result.append(
            {
                "rank": i + 1,
                "name": row["name"],
                "wins": row["wins"],
                "losses": row["losses"],
                "games": games,
                "win_pct": win_pct,
                "elo": round(row["elo"]),
                "streak": row["streak"],
                "badges": player_badges(row, i + 1),
            }
        )
    return jsonify(result)


@app.route("/api/matches")
def matches():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM matches ORDER BY id DESC LIMIT 100"
    ).fetchall()
    return jsonify(
        [
            {
                "id": r["id"],
                "winner": r["winner"],
                "loser": r["loser"],
                "comment": r["comment"],
                "winner_elo_delta": round(r["winner_elo_after"] - r["winner_elo_before"], 1),
                "loser_elo_delta": round(r["loser_elo_after"] - r["loser_elo_before"], 1),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    )


@app.route("/api/matches", methods=["POST"])
def log_match():
    data = request.get_json(force=True) or {}
    winner = data.get("winner")
    loser = data.get("loser")
    comment = (data.get("comment") or "").strip()[:280]

    if winner not in PLAYERS or loser not in PLAYERS:
        return jsonify({"error": "Unknown player"}), 400
    if winner == loser:
        return jsonify({"error": "Winner and loser must be different people"}), 400

    db = get_db()
    winner_row = db.execute("SELECT * FROM players WHERE name = ?", (winner,)).fetchone()
    loser_row = db.execute("SELECT * FROM players WHERE name = ?", (loser,)).fetchone()

    new_winner_elo, new_loser_elo = compute_elo(winner_row["elo"], loser_row["elo"])

    new_winner_streak = winner_row["streak"] + 1 if winner_row["streak"] >= 0 else 1
    new_loser_streak = loser_row["streak"] - 1 if loser_row["streak"] <= 0 else -1

    db.execute(
        "UPDATE players SET elo = ?, wins = wins + 1, streak = ? WHERE name = ?",
        (new_winner_elo, new_winner_streak, winner),
    )
    db.execute(
        "UPDATE players SET elo = ?, losses = losses + 1, streak = ? WHERE name = ?",
        (new_loser_elo, new_loser_streak, loser),
    )
    db.execute(
        """
        INSERT INTO matches (winner, loser, comment, winner_elo_before, loser_elo_before, winner_elo_after, loser_elo_after)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (winner, loser, comment, winner_row["elo"], loser_row["elo"], new_winner_elo, new_loser_elo),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/head-to-head")
def head_to_head():
    a = request.args.get("a")
    b = request.args.get("b")
    if a not in PLAYERS or b not in PLAYERS or a == b:
        return jsonify({"error": "Pick two different players"}), 400

    db = get_db()
    a_wins = db.execute(
        "SELECT COUNT(*) c FROM matches WHERE winner = ? AND loser = ?", (a, b)
    ).fetchone()["c"]
    b_wins = db.execute(
        "SELECT COUNT(*) c FROM matches WHERE winner = ? AND loser = ?", (b, a)
    ).fetchone()["c"]
    recent = db.execute(
        """
        SELECT * FROM matches
        WHERE (winner = ? AND loser = ?) OR (winner = ? AND loser = ?)
        ORDER BY id DESC LIMIT 10
        """,
        (a, b, b, a),
    ).fetchall()

    return jsonify(
        {
            "a": a,
            "b": b,
            "a_wins": a_wins,
            "b_wins": b_wins,
            "recent": [
                {"winner": r["winner"], "loser": r["loser"], "comment": r["comment"], "created_at": r["created_at"]}
                for r in recent
            ],
        }
    )


@app.route("/api/players")
def players_list():
    return jsonify(PLAYERS)


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5050)
