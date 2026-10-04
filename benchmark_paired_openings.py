#!/usr/bin/env python3
"""Play exact color-swapped opening pairs against the existing Julia HTTP API."""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn


OPENINGS = [
    ("Ruy Lopez", ("e2e4", "e7e5", "g1f3", "b8c6")),
    ("Queens Gambit", ("d2d4", "d7d5", "c2c4", "e7e6")),
    ("Sicilian Defense", ("e2e4", "c7c5", "g1f3", "d7d6")),
    ("Kings Indian", ("d2d4", "g8f6", "c2c4", "g7g6")),
    ("English Opening", ("c2c4", "e7e5", "g1f3", "b8c6")),
    ("Reti Opening", ("g1f3", "d7d5", "g2g3", "g8f6")),
    ("Queens Pawn", ("d2d4", "d7d5", "g1f3", "g8f6")),
    ("French Defense", ("e2e4", "e7e6", "d2d4", "d7d5")),
    ("Caro-Kann Defense", ("e2e4", "c7c6", "d2d4", "d7d5")),
    ("Pirc Defense", ("e2e4", "d7d6", "d2d4", "g8f6")),
    ("Scandinavian Defense", ("e2e4", "d7d5", "e4d5", "d8d5")),
    ("Modern Defense", ("e2e4", "g7g6", "d2d4", "f8g7")),
    ("Nimzo-Larsen Attack", ("b2b3", "d7d5", "c1b2", "g8f6")),
    ("Bird Opening", ("f2f4", "d7d5", "g1f3", "g8f6")),
    ("Dutch Defense", ("d2d4", "f7f5", "c2c4", "g8f6")),
    ("Benoni Defense", ("d2d4", "g8f6", "c2c4", "c7c5")),
    ("Vienna Game", ("e2e4", "e7e5", "b1c3", "g8f6")),
    ("Italian Game", ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5")),
    ("Four Knights Game", ("e2e4", "e7e5", "g1f3", "b8c6", "b1c3", "g8f6")),
    ("Queens Gambit Accepted", ("d2d4", "d7d5", "c2c4", "d5c4")),
    ("Slav Defense", ("d2d4", "d7d5", "c2c4", "c7c6")),
    ("Grunfeld Defense", ("d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "d7d5")),
    ("Catalan Opening", ("d2d4", "g8f6", "c2c4", "e7e6", "g2g3", "d7d5")),
    ("Trompowsky Attack", ("d2d4", "g8f6", "c1g5", "d7d5")),
    ("Scotch Game", ("e2e4", "e7e5", "g1f3", "b8c6", "d2d4", "e5d4")),
    ("Petrov Defense", ("e2e4", "e7e5", "g1f3", "g8f6")),
    ("Philidor Defense", ("e2e4", "e7e5", "g1f3", "d7d6")),
    ("Kings Gambit", ("e2e4", "e7e5", "f2f4", "e5f4")),
    ("Budapest Gambit", ("d2d4", "g8f6", "c2c4", "e7e5")),
    ("Bogo-Indian Defense", ("d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "f8b4")),
    ("London System", ("d2d4", "d7d5", "c1f4", "g8f6")),
    ("Queens Indian Defense", ("d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "b7b6")),
    ("Nimzo-Indian Defense", ("d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4")),
    ("Tarrasch Defense", ("d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "c7c5")),
    ("Semi-Slav Defense", ("d2d4", "d7d5", "c2c4", "c7c6", "b1c3", "e7e6")),
    ("Alekhine Defense", ("e2e4", "g8f6", "e4e5", "f6d5")),
    ("Scandinavian Defense, Nf6 Variation", ("e2e4", "d7d5", "e4d5", "g8f6")),
    ("Queens Gambit Declined", ("d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6")),
    ("Kings Indian Classical", ("d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "g1f3", "d7d6")),
    ("Old Indian Defense", ("d2d4", "g8f6", "c2c4", "d7d6", "b1c3", "e7e5")),
    ("Ruy Lopez Berlin Defense", ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6")),
    ("Ruy Lopez Morphy Defense", ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6")),
    ("Evans Gambit Accepted", ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "b2b4", "c5b4")),
    ("Scotch Gambit", ("e2e4", "e7e5", "g1f3", "b8c6", "d2d4", "e5d4")),
    ("Queens Gambit Exchange", ("d2d4", "d7d5", "c2c4", "e7e6", "c4d5", "e6d5")),
    ("Dutch Leningrad", ("d2d4", "f7f5", "c2c4", "g8f6", "g2g3", "g7g6")),
    ("Kings Indian Fianchetto", ("d2d4", "g8f6", "g1f3", "g7g6", "g2g3", "f8g7")),
    ("Kings Indian Attack", ("e2e4", "e7e6", "d2d3", "d7d5", "b1d2", "c7c5")),
    ("Blackmar-Diemer Gambit", ("d2d4", "d7d5", "e2e4", "d5e4")),
    ("Grunfeld Exchange Variation", ("d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "d7d5", "c4d5", "f6d5")),
]


def request_json(url: str, payload: dict | None = None, timeout: float = 900) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def build_opening(moves: tuple[str, ...]) -> chess.Board:
    board = chess.Board()
    for uci in moves:
        board.push_uci(uci)
    if board.turn != chess.WHITE or not board.is_valid():
        raise ValueError("Opening must leave a legal position with White to move.")
    return board


def play_one(engine, api: str, start_board: chess.Board, julia_color: str,
             elo: int, move_time: float, pair_no: int, opening_name: str,
             round_no: int, max_plies: int) -> dict:
    fen = start_board.fen()
    state = request_json(api + "/api/reset", {
        "fen": fen,
        "julia_color": julia_color,
    })
    if state.get("julia_color") != ("w" if julia_color == "white" else "b"):
        raise RuntimeError("Server did not apply the requested Julia color.")
    board = start_board.copy(stack=False)
    moves: list[str] = []
    for row in state.get("history", []):
        moves.append(row["uci"])
        board.push_uci(row["uci"])
    started = time.monotonic()
    human_color = state["human_color"]

    while not state.get("game_over") and len(moves) < max_plies:
        expected_human_turn = chess.WHITE if human_color == "w" else chess.BLACK
        if board.turn != expected_human_turn:
            raise RuntimeError("API returned before Julia finished her move.")
        result = engine.play(board, chess.engine.Limit(time=move_time))
        if result.move is None or result.move not in board.legal_moves:
            raise RuntimeError("Stockfish returned no legal move.")
        moves.append(result.move.uci())
        state = request_json(api + "/api/move", {"move": result.move.uci()})
        for row in state.get("history", [])[len(moves):]:
            moves.append(row["uci"])
        board = start_board.copy(stack=False)
        for uci in moves:
            board.push_uci(uci)

    adjudicated = not state.get("game_over")
    result_text = "1/2-1/2" if adjudicated else state.get("result", "*")
    termination = (f"Draw — benchmark adjudication at {max_plies} plies after opening setup."
                   if adjudicated else state.get("note", "").replace("ChatGPT", "Stockfish 19"))
    julia_white = julia_color == "white"
    if result_text == "1/2-1/2":
        score_julia = 0.5
    elif result_text == "1-0":
        score_julia = 1.0 if julia_white else 0.0
    elif result_text == "0-1":
        score_julia = 0.0 if julia_white else 1.0
    else:
        score_julia = 0.5

    game = chess.pgn.Game()
    if fen != chess.STARTING_FEN:
        game.setup(start_board)
    node = game
    replay_board = start_board.copy(stack=False)
    for uci in moves:
        move = chess.Move.from_uci(uci)
        node = node.add_variation(move)
        replay_board.push(move)
    game.headers.update({
        "Event": "Julia Chess Paired-Opening Benchmark",
        "Site": "Local API",
        "Date": datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        "Round": f"{pair_no}.{round_no}",
        "White": "Julia" if julia_white else f"Stockfish 19 (UCI_Elo {elo})",
        "Black": f"Stockfish 19 (UCI_Elo {elo})" if julia_white else "Julia",
        "TimeControl": f"~{move_time:g}s/move Stockfish; Julia search budget 3.0s",
        "Termination": termination,
        "Opening": opening_name,
        "Result": result_text,
    })
    return {
        "pair": pair_no,
        "round": round_no,
        "opening": opening_name,
        "julia_color": "White" if julia_white else "Black",
        "start_fen": fen,
        "result": result_text,
        "score_julia": score_julia,
        "termination": termination,
        "plies": len(moves),
        "seconds": round(time.monotonic() - started, 2),
        "pgn": str(game),
        "pgn_headers": dict(game.headers),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:27600")
    parser.add_argument("--stockfish", required=True)
    parser.add_argument("--elo", type=int, default=1480)
    parser.add_argument("--pairs", type=int, default=2)
    parser.add_argument("--start-pair", type=int, default=1,
                        help="One-based opening index, useful for continuing a benchmark batch.")
    parser.add_argument("--move-time", type=float, default=3.0)
    parser.add_argument("--max-plies", type=int, default=160,
                        help="Draw by benchmark adjudication after this many plies from the opening FEN.")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("rating_paired"))
    args = parser.parse_args()

    if not 1320 <= args.elo <= 3190:
        raise SystemExit("Stockfish 19 UCI_Elo must be between 1320 and 3190.")
    if args.start_pair < 1 or args.start_pair + args.pairs - 1 > len(OPENINGS):
        raise SystemExit(f"Choose a valid range within the {len(OPENINGS)} fixed openings.")
    args.output.mkdir(parents=True, exist_ok=True)
    last_pair = args.start_pair + args.pairs - 1
    stem = f"paired-stockfish19-elo{args.elo}-pairs{args.start_pair}-{last_pair}"
    pgn_path = args.output / f"{stem}.pgn"
    json_path = args.output / f"{stem}.json"
    engine = chess.engine.SimpleEngine.popen_uci(args.stockfish)
    if engine.id.get("name") != "Stockfish 19":
        engine.quit()
        raise SystemExit(f"Expected official Stockfish 19, got {engine.id!r}")
    engine.configure({"Threads": 1, "Hash": 128, "UCI_LimitStrength": True, "UCI_Elo": args.elo})
    rows: list[dict] = []

    try:
        with pgn_path.open("w", encoding="utf-8", newline="\n") as pgn_file:
            selected = OPENINGS[args.start_pair - 1:last_pair]
            for pair_index, (opening_name, prefix) in enumerate(selected, args.start_pair):
                white_to_move = build_opening(prefix)
                starts = ((white_to_move, "white"), (white_to_move.mirror(), "black"))
                pair_rows = []
                for round_no, (start_board, color) in enumerate(starts, 1):
                    row = play_one(engine, args.api, start_board, color, args.elo,
                                   args.move_time, pair_index, opening_name, round_no, args.max_plies)
                    pair_rows.append(row)
                    rows.append(row)
                    pgn_text = row.pop("pgn")
                    pgn_file.write(pgn_text + "\n\n")
                    pgn_file.flush()
                    print(json.dumps({k: v for k, v in row.items() if k != "pgn_headers"}), flush=True)
                pair_score = sum(row["score_julia"] for row in pair_rows)
                pair_record = {
                    "pair": pair_index,
                    "opening": opening_name,
                    "julia_score_over_two_games": pair_score,
                    "paired_games": [{k: v for k, v in row.items() if k != "pgn_headers"} for row in pair_rows],
                }
                json_path.write_text(json.dumps({
                    "stockfish": engine.id,
                    "stockfish_uci_elo": args.elo,
                    "stockfish_move_time_seconds": args.move_time,
                    "julia_configuration": "current server model/search; three seconds search budget",
                    "protocol": f"fixed opening positions, each played twice with colors swapped; adjudicated draw after {args.max_plies} plies from setup FEN",
                    "pairs": pair_index,
                    "games": [{k: v for k, v in game.items() if k != "pgn_headers"} for game in rows],
                    "score_fraction": sum(game["score_julia"] for game in rows) / len(rows),
                    "pgn_file": str(pgn_path),
                }, indent=2), encoding="utf-8")
                print(json.dumps(pair_record), flush=True)
    finally:
        engine.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
