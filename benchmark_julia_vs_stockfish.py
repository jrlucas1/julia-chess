#!/usr/bin/env python3
"""Run a Stockfish UCI_Elo batch against Julia through the local chess API."""
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


OPENING_MOVES = ("e2e4", "d2d4", "g1f3", "c2c4", "g2g3", "b2b3", "e2e3", "f2f4")


def request_json(url: str, *, payload: dict | None = None, timeout: float = 900) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def game_from_uci_moves(moves: list[str], result: str) -> chess.pgn.Game:
    game = chess.pgn.Game()
    board = game.board()
    node = game
    for uci in moves:
        move = chess.Move.from_uci(uci)
        node = node.add_variation(move)
        board.push(move)
    game.headers["Result"] = result
    return game


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:27600")
    parser.add_argument("--stockfish", required=True)
    parser.add_argument("--elo", type=int, default=1320)
    parser.add_argument("--games", type=int, default=4)
    parser.add_argument("--move-time", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("rating_pilot"))
    args = parser.parse_args()

    engine = chess.engine.SimpleEngine.popen_uci(args.stockfish)
    if engine.id.get("name") != "Stockfish 19":
        raise SystemExit(f"Expected official Stockfish 19, got {engine.id!r}")
    if not 1320 <= args.elo <= 3190:
        raise SystemExit("Stockfish 19 UCI_Elo must be between 1320 and 3190.")
    engine.configure({"Threads": 1, "Hash": 128, "UCI_LimitStrength": True, "UCI_Elo": args.elo})
    args.output.mkdir(parents=True, exist_ok=True)
    pgn_path = args.output / f"julia-vs-stockfish19-elo{args.elo}-pilot.pgn"
    json_path = args.output / f"julia-vs-stockfish19-elo{args.elo}-pilot.json"
    rows: list[dict] = []

    try:
        with pgn_path.open("w", encoding="utf-8", newline="\n") as pgn_file:
            for game_no in range(args.games):
                state = request_json(args.api + "/api/reset", payload={})
                board = chess.Board()
                julia_color = state.get("julia_color", "b")
                human_color = state.get("human_color", "w" if julia_color == "b" else "b")
                moves: list[str] = [move["uci"] for move in state.get("history", [])]
                for uci in moves:
                    board.push_uci(uci)
                first = chess.Move.from_uci(OPENING_MOVES[game_no % len(OPENING_MOVES)])
                started = time.monotonic()

                while not state.get("game_over"):
                    if board.turn != (chess.WHITE if human_color == "w" else chess.BLACK):
                        raise RuntimeError("API returned before Julia completed her move.")
                    # Use varied White first moves when the opponent has White.
                    if human_color == "w" and len(moves) == 0:
                        if first not in board.legal_moves:
                            raise RuntimeError(f"Opening move {first.uci()} is not legal.")
                        move = first
                    else:
                        result = engine.play(board, chess.engine.Limit(time=args.move_time))
                        if result.move is None or result.move not in board.legal_moves:
                            raise RuntimeError("Stockfish returned no legal move.")
                        move = result.move
                    moves.append(move.uci())
                    state = request_json(args.api + "/api/move", payload={"move": move.uci()})
                    for row in state.get("history", [])[len(moves):]:
                        moves.append(row["uci"])
                    board = chess.Board()
                    for uci in moves:
                        board.push_uci(uci)

                result_text = state.get("result") or "*"
                game = game_from_uci_moves(moves, result_text)
                julia_white = julia_color == "w"
                julia_score = (1.0 if result_text == "1-0" else 0.0 if result_text == "0-1" else 0.5) if julia_white else (1.0 if result_text == "0-1" else 0.0 if result_text == "1-0" else 0.5)
                game.headers.update({
                    "Event": "Julia Chess Rating Pilot",
                    "Site": "Local API",
                    "Date": datetime.now(timezone.utc).strftime("%Y.%m.%d"),
                    "Round": str(game_no + 1),
                    "White": "Julia (current model + search configuration)" if julia_white else f"Stockfish 19 (UCI_Elo {args.elo})",
                    "Black": f"Stockfish 19 (UCI_Elo {args.elo})" if julia_white else "Julia (current model + search configuration)",
                    "TimeControl": f"~{args.move_time:g}s/move Stockfish; Julia server default",
                    "Termination": state.get("note", ""),
                })
                pgn_file.write(str(game) + "\n\n")
                pgn_file.flush()
                row = {
                    "round": game_no + 1,
                    "result": result_text,
                    "julia_color": "White" if julia_white else "Black",
                    "score_julia": julia_score,
                    "termination": state.get("note", ""),
                    "plies": len(moves),
                    "seconds": round(time.monotonic() - started, 2),
                    "first_move": moves[0] if moves else None,
                    "pgn_file": str(pgn_path),
                }
                rows.append(row)
                print(json.dumps(row), flush=True)
                json_path.write_text(json.dumps({
                    "stockfish": engine.id,
                    "stockfish_uci_elo": args.elo,
                    "stockfish_move_time_seconds": args.move_time,
                    "julia_server_budget": "existing server defaults: depth 6, 3.0s search, margin 120",
                    "julia_color": "Varies by server startup configuration",
                    "games": rows,
                    "julia_score_fraction": sum(r["score_julia"] for r in rows) / len(rows),
                }, indent=2), encoding="utf-8")
    finally:
        engine.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
