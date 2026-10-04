#!/usr/bin/env python3
"""Private localhost chess match: ChatGPT vs. Julia, with configurable colors.

Julia's move pipeline:
  optional opening book -> optional tablebase -> negamax search + quiescence + TT
  -> evaluation margin filter -> safety flags (SEE/threats)
  -> model selects among remaining moves -> fallback = search's best move.

Search sets a quality floor; the model decides the move's "style".
"""
from __future__ import annotations

import argparse
import socket
import json
import random
import threading
import time
import traceback
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import chess
import chess.polyglot
import chess.syzygy

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 335,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20_000,
}
MAX_CANDIDATES = 8
DEFAULT_MARGIN = 120        # Send moves within X centipawns of the best to the model.
DEFAULT_DEPTH = 6           # Maximum iterative deepening depth.
DEFAULT_THINK_TIME = 3.0    # Search budget per move, in seconds.

INF = 10**9
MATE = 100_000
MATE_BOUND = MATE - 1_000
MAX_PLY = 64
MAX_CHECK_EXT_PLY = 12
QUIESCE_MAX_DEPTH = 8
DELTA_MARGIN = 200
TT_LIMIT = 500_000
EXACT, LOWER, UPPER = 0, 1, 2

WEB_DIR = Path(__file__).resolve().parent
UNICODE_PIECES = {
    (chess.WHITE, chess.KING): "♔", (chess.WHITE, chess.QUEEN): "♕",
    (chess.WHITE, chess.ROOK): "♖", (chess.WHITE, chess.BISHOP): "♗",
    (chess.WHITE, chess.KNIGHT): "♘", (chess.WHITE, chess.PAWN): "♙",
    (chess.BLACK, chess.KING): "♚", (chess.BLACK, chess.QUEEN): "♛",
    (chess.BLACK, chess.ROOK): "♜", (chess.BLACK, chess.BISHOP): "♝",
    (chess.BLACK, chess.KNIGHT): "♞", (chess.BLACK, chess.PAWN): "♟",
}

# --------------------------------------------------------------------------- #
# Static evaluation (piece-square tables, simplified evaluation function).
# Tables use White's perspective, with a8 at index 0.
# --------------------------------------------------------------------------- #
_PAWN_PST = (
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 25, 25, 10, 5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, -5, -10, 0, 0, -10, -5, 5,
    5, 10, 10, -20, -20, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
)
_KNIGHT_PST = (
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
)
_BISHOP_PST = (
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
)
_ROOK_PST = (
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, 10, 10, 10, 10, 5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    0, 0, 0, 5, 5, 0, 0, 0,
)
_QUEEN_PST = (
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -5, 0, 5, 5, 5, 5, 0, -5,
    0, 0, 5, 5, 5, 5, 0, -5,
    -10, 5, 5, 5, 5, 5, 0, -10,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
)
_KING_MID_PST = (
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20,
)
_KING_END_PST = (
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
)
PST = {
    chess.PAWN: _PAWN_PST, chess.KNIGHT: _KNIGHT_PST, chess.BISHOP: _BISHOP_PST,
    chess.ROOK: _ROOK_PST, chess.QUEEN: _QUEEN_PST,
}
PASSED_BONUS = (0, 10, 20, 35, 60, 100, 160, 0)  # By relative rank.
BISHOP_PAIR = 30
TEMPO = 10


def _build_passed_masks() -> dict[bool, list[int]]:
    masks: dict[bool, list[int]] = {chess.WHITE: [0] * 64, chess.BLACK: [0] * 64}
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        for color, step in ((chess.WHITE, 1), (chess.BLACK, -1)):
            mask = 0
            for ff in (f - 1, f, f + 1):
                if not 0 <= ff < 8:
                    continue
                rr = r + step
                while 0 <= rr < 8:
                    mask |= chess.BB_SQUARES[chess.square(ff, rr)]
                    rr += step
            masks[color][sq] = mask
    return masks


PASSED_MASK = _build_passed_masks()
ORDER = {chess.PAWN: 1, chess.KNIGHT: 2, chess.BISHOP: 3, chess.ROOK: 4, chess.QUEEN: 5, chess.KING: 6}


def evaluate(board: chess.Board) -> int:
    """Static evaluation in centipawns from the side-to-move perspective."""
    pieces = board.piece_map()
    non_pawn = 0
    queens = 0
    for p in pieces.values():
        if p.piece_type not in (chess.PAWN, chess.KING):
            non_pawn += PIECE_VALUES[p.piece_type]
            if p.piece_type == chess.QUEEN:
                queens += 1
    endgame = non_pawn <= 2_600 or (queens == 0 and non_pawn <= 4_000)

    white_pawns = board.pieces_mask(chess.PAWN, chess.WHITE)
    black_pawns = board.pieces_mask(chess.PAWN, chess.BLACK)
    bishops = {chess.WHITE: 0, chess.BLACK: 0}
    score = 0
    for sq, p in pieces.items():
        white = p.color
        idx = sq ^ 56 if white else sq
        pt = p.piece_type
        if pt == chess.KING:
            v = (_KING_END_PST if endgame else _KING_MID_PST)[idx]
        else:
            v = PIECE_VALUES[pt] + PST[pt][idx]
            if pt == chess.PAWN:
                enemy = black_pawns if white else white_pawns
                if not enemy & PASSED_MASK[white][sq]:
                    rank = chess.square_rank(sq)
                    v += PASSED_BONUS[rank if white else 7 - rank]
            elif pt == chess.BISHOP:
                bishops[white] += 1
        score += v if white else -v
    if bishops[chess.WHITE] >= 2:
        score += BISHOP_PAIR
    if bishops[chess.BLACK] >= 2:
        score -= BISHOP_PAIR
    score += TEMPO if board.turn else -TEMPO
    return score if board.turn else -score


def fmt_eval(score: int) -> str:
    if score >= MATE_BOUND:
        return f"mate em {(MATE - score + 1) // 2}"
    if score <= -MATE_BOUND:
        return f"leva mate em {(MATE + score + 1) // 2}"
    return f"{score / 100:+.1f}"


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
class _SearchTimeout(Exception):
    pass


def _victim_type(board: chess.Board, move: chess.Move) -> int:
        return board.piece_type_at(move.to_square) or chess.PAWN  # En passant captures a pawn.


class Searcher:
    """Negamax alpha-beta with iterative deepening, a TT, killers, and quiescence."""

    def __init__(self, max_depth: int = DEFAULT_DEPTH, think_time: float = DEFAULT_THINK_TIME):
        self.max_depth = max_depth
        self.think_time = think_time
        self.tt: dict[int, tuple[int, int, int, Optional[chess.Move]]] = {}
        self.killers: list[list[Optional[chess.Move]]] = [[None, None] for _ in range(MAX_PLY + 1)]
        self.nodes = 0
        self.deadline = 0.0
        self._can_abort = False

    def reset(self) -> None:
        self.tt.clear()

    # -- API ---------------------------------------------------------------- #
    def search(self, board: chess.Board, margin: int) -> tuple[list[tuple[chess.Move, int]], int]:
        """Return sorted (move, centipawn score) pairs and the completed depth.

        Scores outside the best-minus-margin window are upper bounds; the caller
        filters using `score > best - margin`.
        """
        legal = list(board.legal_moves)
        start = time.monotonic()
        self.deadline = start + self.think_time
        self.nodes = 0
        self._can_abort = False
        self.killers = [[None, None] for _ in range(MAX_PLY + 1)]
        if len(self.tt) > TT_LIMIT:
            self.tt.clear()

        order = self._order(board, legal, None, 0)
        result: list[tuple[chess.Move, int]] = [(m, 0) for m in order]
        reached = 0
        for depth in range(1, self.max_depth + 1):
            try:
                scored = self._search_root(board.copy(), order, depth, margin)
            except _SearchTimeout:
                break
            result, reached = scored, depth
            order = [m for m, _ in scored]
            self._can_abort = True  # Depth 1 always completes.
            if len(legal) == 1 or abs(scored[0][1]) >= MATE_BOUND:
                break
            if time.monotonic() - start > self.think_time * 0.4:
                break  # The next iteration probably would not finish in time.
        return result, reached

    # -- root --------------------------------------------------------------- #
    def _search_root(self, board: chess.Board, moves: list[chess.Move], depth: int, margin: int):
        scored: list[tuple[chess.Move, int]] = []
        best = -INF
        for move in moves:
            alpha = best - margin if best > -INF else -INF
            board.push(move)
            score = -self._negamax(board, depth - 1, -INF, -alpha, 1)
            board.pop()
            scored.append((move, score))
            if score > best:
                best = score
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    # -- internal nodes ----------------------------------------------------- #
    def _tick(self) -> None:
        self.nodes += 1
        if self._can_abort and (self.nodes & 511) == 0 and time.monotonic() > self.deadline:
            raise _SearchTimeout

    def _order(self, board: chess.Board, moves, tt_move, ply: int) -> list[chess.Move]:
        killers = self.killers[ply] if ply <= MAX_PLY else (None, None)

        def key(m: chess.Move) -> int:
            if m == tt_move:
                return 1_000_000
            if board.is_capture(m):
                attacker = board.piece_type_at(m.from_square)
                return 10_000 + 10 * ORDER[_victim_type(board, m)] - ORDER[attacker]
            if m.promotion:
                return 9_000 + m.promotion
            if m in killers:
                return 5_000
            return 0

        return sorted(moves, key=key, reverse=True)

    def _negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self._tick()
        in_check = board.is_check()
        if in_check and board.is_checkmate():
            return -MATE + ply
        if board.halfmove_clock >= 100 or board.is_insufficient_material() or board.is_repetition(2):
            return 0

        if in_check and ply < MAX_CHECK_EXT_PLY:
            depth += 1
        if board.is_checkmate():
            return -MATE + ply
        if board.is_stalemate():
            return 0
        if depth <= 0:
            return self._quiesce(board, alpha, beta, 0)

        key = chess.polyglot.zobrist_hash(board)
        tt_move: Optional[chess.Move] = None
        entry = self.tt.get(key)
        if entry is not None:
            e_depth, e_flag, e_score, tt_move = entry
            if e_depth >= depth:
                if e_flag == EXACT:
                    return e_score
                if e_flag == LOWER:
                    alpha = max(alpha, e_score)
                else:
                    beta = min(beta, e_score)
                if alpha >= beta:
                    return e_score

        moves = list(board.legal_moves)
        if not moves:
            return -MATE + ply if in_check else 0
        moves = self._order(board, moves, tt_move, ply)

        orig_alpha = alpha
        best = -INF
        best_move: Optional[chess.Move] = None
        for move in moves:
            is_capture = board.is_capture(move)
            board.push(move)
            score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if score > best:
                best, best_move = score, move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if not is_capture and ply <= MAX_PLY and self.killers[ply][0] != move:
                    self.killers[ply][1] = self.killers[ply][0]
                    self.killers[ply][0] = move
                break

        if abs(best) < MATE_BOUND:  # Mate scores depend on ply, so do not cache them.
            flag = UPPER if best <= orig_alpha else LOWER if best >= beta else EXACT
            self.tt[key] = (depth, flag, best, best_move)
        return best

    def _quiesce(self, board: chess.Board, alpha: int, beta: int, qdepth: int) -> int:
        self._tick()
        in_check = board.is_check()
        if not in_check:
            if not any(board.legal_moves):
                return 0
            stand = evaluate(board)
            if stand >= beta:
                return stand
            best = stand
            alpha = max(alpha, stand)
            if qdepth >= QUIESCE_MAX_DEPTH:
                return best
        else:
            # A checked side cannot stand pat; it must consider every legal evasion.
            best = -INF
            evasions = list(board.legal_moves)
            if not evasions:
                return -MATE + qdepth
            if qdepth >= QUIESCE_MAX_DEPTH:
                best = -INF
                for move in evasions:
                    board.push(move)
                    score = -evaluate(board)
                    board.pop()
                    best = max(best, score)
                    alpha = max(alpha, score)
                    if alpha >= beta:
                        break
                return best

        def mvv_lva(m: chess.Move) -> int:
            s = 50 if m.promotion else 0
            if board.is_capture(m):
                s += 10 * ORDER[_victim_type(board, m)] - ORDER[board.piece_type_at(m.from_square)]
            return s

        moves = evasions if in_check else [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
        moves.sort(key=mvv_lva, reverse=True)
        for move in moves:
            if not in_check and not move.promotion and stand + PIECE_VALUES[_victim_type(board, move)] + DELTA_MARGIN < alpha:
                continue  # delta pruning
            board.push(move)
            score = -self._quiesce(board, -beta, -alpha, qdepth + 1)
            board.pop()
            if score >= beta:
                return score
            if score > best:
                best = score
                alpha = max(alpha, score)
        return best


# --------------------------------------------------------------------------- #
# SEE, threats, and move flags
# --------------------------------------------------------------------------- #
def _see_square(board: chess.Board, square: chess.Square) -> int:
    """Maximum exchange gain for the side to move when capturing on `square`."""
    victim = board.piece_type_at(square)
    if victim is None:
        return 0
    best_move: Optional[chess.Move] = None
    best_val = INF
    for m in board.legal_moves:
        if m.to_square == square and board.is_capture(m):
            val = PIECE_VALUES[board.piece_type_at(m.from_square)]
            if val < best_val:
                best_move, best_val = m, val
    if best_move is None:
        return 0
    board.push(best_move)
    gain = max(0, PIECE_VALUES[victim] - _see_square(board, square))
    board.pop()
    return gain


def see(board: chess.Board, move: chess.Move) -> int:
    """Static Exchange Evaluation for a capture, in centipawns from the mover's perspective."""
    value = PIECE_VALUES[_victim_type(board, move)]
    board.push(move)
    try:
        return value - _see_square(board, move.to_square)
    finally:
        board.pop()


def _threatened(board: chess.Board, color: bool) -> int:
    """Value of the most valuable piece of `color` under a profitable attack (0 = none)."""
    enemy = not color
    worst = 0
    for sq, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        attackers = board.attackers(enemy, sq)
        if not attackers:
            continue
        least = min(PIECE_VALUES[board.piece_type_at(a)] for a in attackers)
        value = PIECE_VALUES[piece.piece_type]
        if not board.is_attacked_by(color, sq) or least < value:
            worst = max(worst, value)
    return worst


def _flags(board: chess.Board, move: chess.Move, before_own: int, before_opp: int) -> list[str]:
    side = board.turn
    flags: list[str] = []
    if board.is_capture(move):
        gain = see(board, move)
        flags.append("profitable capture" if gain > 0 else "equal exchange" if gain == 0 else "risky capture")
    if move.promotion:
        flags.append("promotion")
    if board.is_castling(move):
        flags.append("castling")
    board.push(move)
    try:
        if board.is_checkmate():
            flags.append("checkmate")
        elif board.is_check():
            flags.append("check")
        after_own = _threatened(board, side)
        after_opp = _threatened(board, not side)
    finally:
        board.pop()
    if after_own > 0:
        flags.append("piece under threat")
    elif before_own > 0:
        flags.append("addresses a threat")
    if after_opp > 0 and after_opp > before_opp:
        flags.append("creates a threat")
    return flags


# --------------------------------------------------------------------------- #
# Legacy heuristic (last resort if search fails)
# --------------------------------------------------------------------------- #
def _move_score(board: chess.Board, move: chess.Move) -> tuple[float, str]:
    side = board.turn
    moving_piece = board.piece_at(move.from_square)
    if moving_piece is None:
        return -1_000_000, ""

    score = 0.0
    reasons: list[str] = []
    captured = board.piece_at(move.to_square)
    if board.is_en_passant(move):
        captured = chess.Piece(chess.PAWN, not side)
    if captured:
        score += PIECE_VALUES[captured.piece_type] * 0.65 - PIECE_VALUES[moving_piece.piece_type] * 0.08
        reasons.append("capture")
    if move.promotion:
        score += PIECE_VALUES[move.promotion] - PIECE_VALUES[chess.PAWN]
        reasons.append("promotion")
    if board.gives_check(move):
        score += 115
        reasons.append("check")
    if board.is_castling(move):
        score += 75
        reasons.append("castling")

    file_no = chess.square_file(move.to_square)
    rank_no = chess.square_rank(move.to_square)
    center_distance = abs(file_no * 2 - 7) + abs(rank_no * 2 - 7)
    if moving_piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.PAWN):
        score += max(0, 12 - center_distance) * 2.2
    if moving_piece.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(move.from_square) in (0, 7):
        score += 35
        reasons.append("development")

    after = board.copy()
    after.push(move)
    if after.is_checkmate():
        score += 100_000
        reasons.append("checkmate")

    moving_after = after.piece_at(move.to_square)
    if moving_after and after.is_attacked_by(not side, move.to_square):
        attackers = len(after.attackers(not side, move.to_square))
        defenders = len(after.attackers(side, move.to_square))
        if attackers > defenders:
            score -= PIECE_VALUES[moving_after.piece_type] * 0.34
            reasons.append("square under threat")

    if moving_piece.piece_type == chess.KING and not board.is_castling(move):
        score -= 40
    return score, ", ".join(reasons) or "development and position"


def _legacy_best(board: chess.Board) -> chess.Move:
    ranked = [(_move_score(board, m)[0], m) for m in board.legal_moves]
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


# --------------------------------------------------------------------------- #
# Julia model
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    move: chess.Move
    score: int
    san: str
    flags: list[str] = field(default_factory=list)


class JuliaChess:
    def __init__(self, model_path: str, device: str, *, depth: int = DEFAULT_DEPTH,
                 think_time: float = DEFAULT_THINK_TIME, margin: int = DEFAULT_MARGIN,
                 book_path: Optional[str] = None, syzygy_path: Optional[str] = None):
        from julia import load_model

        print(f"[chess] Loading Julia from {model_path} on {device}...", flush=True)
        options = dict(strict_encoding=True, max_length=8192, head_length=512)
        try:
            self.engine = load_model(model_path, device=device, **options)
            self.device = device
        except Exception as exc:
            if device == "cpu":
                raise
            print(f"[chess] CUDA initialization failed ({type(exc).__name__}); falling back to CPU.", flush=True)
            self.engine = load_model(model_path, device="cpu", **options)
            self.device = "cpu"
        print("[chess] Julia loaded.", flush=True)

        self.searcher = Searcher(depth, think_time)
        self.margin = margin
        self.book = self._open_book(book_path)
        self.tb = self._open_tablebase(syzygy_path)
        self._think_lock = threading.Lock()  # TT and killer tables are shared; allow one decision at a time.

    # -- recursos opcionais ------------------------------------------------- #
    @staticmethod
    def _open_book(path: Optional[str]):
        if not path:
            return None
        try:
            reader = chess.polyglot.open_reader(path)
            print(f"[chess] Opening book: {path}", flush=True)
            return reader
        except Exception as exc:
            print(f"[chess] Opening book unavailable ({type(exc).__name__}: {exc}).", flush=True)
            return None

    @staticmethod
    def _open_tablebase(path: Optional[str]):
        if not path:
            return None
        try:
            tb = chess.syzygy.open_tablebase(path)
            print(f"[chess] Syzygy tablebase: {path}", flush=True)
            return tb
        except Exception as exc:
            print(f"[chess] Syzygy unavailable ({type(exc).__name__}: {exc}).", flush=True)
            return None

    def new_game(self) -> None:
        with self._think_lock:
            self.searcher.reset()

    def _book_move(self, board: chess.Board) -> Optional[chess.Move]:
        if self.book is None:
            return None
        try:
            move = self.book.weighted_choice(board).move
        except (IndexError, KeyError):
            return None
        return move if move in board.legal_moves else None

    def _tablebase(self, board: chess.Board) -> Optional[tuple[bool, list[chess.Move]]]:
        """Return (decisive?, best moves). For draws, restrict search to moves preserving WDL."""
        if self.tb is None or chess.popcount(board.occupied) > 7 or board.castling_rights:
            return None
        rows: list[tuple[int, int, chess.Move]] = []
        try:
            for move in list(board.legal_moves):
                board.push(move)
                try:
                    wdl = -self.tb.probe_wdl(board)
                    dtz = abs(self.tb.probe_dtz(board))
                finally:
                    board.pop()
                rows.append((wdl, dtz, move))
        except (KeyError, ValueError):  # No table exists for this position.
            return None
        if not rows:
            return None
        best_wdl = max(r[0] for r in rows)
        best = [r for r in rows if r[0] == best_wdl]
        if best_wdl > 0:
            best.sort(key=lambda r: r[1])
        elif best_wdl < 0:
            best.sort(key=lambda r: -r[1])
        return abs(best_wdl) == 2, [r[2] for r in best]

    # -- analysis ----------------------------------------------------------- #
    def _analyze(self, board: chess.Board, allowed: Optional[set[chess.Move]]):
        scored, depth = self.searcher.search(board, self.margin)
        if allowed:
            scored = [(m, s) for m, s in scored if m in allowed] or scored
        best = scored[0][1]
        kept = [(m, s) for m, s in scored if s > best - self.margin][:MAX_CANDIDATES] or scored[:1]
        before_own = _threatened(board, board.turn)
        before_opp = _threatened(board, not board.turn)
        candidates = [
            Candidate(m, s, board.san(m), _flags(board, m, before_own, before_opp))
            for m, s in kept
        ]
        print(f"[chess] Search: depth {depth}, {self.searcher.nodes} nodes, best {fmt_eval(best)}, "
              f"{len(candidates)} candidates", flush=True)
        return candidates, depth, best

    def _ask_model(self, board: chess.Board, candidates: list[Candidate], depth: int, best: int) -> Optional[chess.Move]:
        history_board = board.root()
        history_sans = []
        for past_move in board.move_stack:
            history_sans.append(history_board.san(past_move))
            history_board.push(past_move)
        history = " ".join(history_sans) or "start"
        state = (
            f"Private chess match. Julia plays {'White' if board.turn else 'Black'}.\n"
            f"FEN: {board.fen()}\nSAN history: {history}\n"
            f"It is {'White' if board.turn else 'Black'} to move.\n"
            f"Search evaluation (depth {depth}): {fmt_eval(best)} from the side-to-move perspective.\n"
            "Choose only from the supplied moves."
        )
        for attempt in range(2):
            shuffled = candidates[:]
            random.shuffle(shuffled)  # Reduce anchoring on the first option.
            criteria = {}
            for c in shuffled:
                extra = f"; {', '.join(c.flags)}" if c.flags else ""
                criteria[c.move.uci()] = f"{c.san} — eval {fmt_eval(c.score)}{extra} (UCI {c.move.uci()})"
            questions = {"action": {
                "type": "choice",
                "instructions": (
                    "Choose the best chess move for this position. Every listed move has been searched; "
                    "evaluations are in pawns from the side-to-move perspective. Prefer higher evaluations "
                    "unless there is a clear positional reason (king safety, piece activity, or pawn structure). "
                    "Avoid moves flagged as 'piece under threat' or 'risky capture'. Return one listed option only."
                ),
                "criteria": criteria,
            }}
            try:
                result = self.engine.predict(state=state, questions=questions)
                selected = result.get("answers", {}).get("action", {}).get("choice")
                if selected in criteria:
                    move = chess.Move.from_uci(selected)
                    if move in board.legal_moves:
                        return move
                print(f"[chess] Invalid model response ({selected!r}); attempt {attempt + 1}/2.", flush=True)
            except Exception as exc:  # A malformed model response must not crash the game.
                print(f"[chess] Move selection failed ({type(exc).__name__}); attempt {attempt + 1}/2.", flush=True)
        return None

    def choose(self, board: chess.Board) -> tuple[chess.Move, str]:
        if not any(True for _ in board.legal_moves):
            raise RuntimeError("Julia has no legal moves.")
        board = board.copy()
        with self._think_lock:
            book = self._book_move(board)
            if book is not None:
                return book, "Julia · opening book"

            allowed: Optional[set[chess.Move]] = None
            tb = self._tablebase(board)
            if tb is not None:
                decisive, moves = tb
                if decisive:
                    return moves[0], "Julia · tablebase"
                allowed = set(moves)

            try:
                candidates, depth, best = self._analyze(board, allowed)
            except Exception as exc:
                print(f"[chess] Search failed ({type(exc).__name__}: {exc}); using the legacy heuristic.", flush=True)
                return _legacy_best(board), "Julia · fallback"

            if len(candidates) == 1:
                return candidates[0].move, "Julia · search"
            move = self._ask_model(board, candidates, depth, best)
            if move is not None:
                return move, "Julia"
            return candidates[0].move, "Julia · search"


# --------------------------------------------------------------------------- #
# Game
# --------------------------------------------------------------------------- #
class ChessGame:
    def __init__(self, player: JuliaChess, julia_color: bool = chess.BLACK):
        self.player = player
        self.julia_color = julia_color
        self.human_color = not julia_color
        self.board = chess.Board()
        self.starting_fen = self.board.fen()
        self.history_moves: list[str] = []
        self.lock = threading.RLock()
        self.generation = 0      # Discard Julia decisions if a reset happens while she is thinking.
        self.thinking = False
        self.last_note = f"Your move — you play {'White' if self.human_color else 'Black'}."
        self.last_actor = ""

    def reset(self, fen: Optional[str] = None, julia_color: Optional[bool] = None) -> dict[str, Any]:
        board = chess.Board(fen) if fen else chess.Board()
        if not board.is_valid():
            raise ValueError("Invalid chess position.")
        with self.lock:
            self.generation += 1
            self.thinking = False
            self.board = board
            self.starting_fen = board.fen()
            self.history_moves = []
            if julia_color is not None:
                self.julia_color = julia_color
                self.human_color = not julia_color
            self.last_note = f"New game. Your move — you play {'White' if self.human_color else 'Black'}."
            self.last_actor = ""
        # Wait for an in-flight decision before clearing shared search tables.
        self.player.new_game()
        if self.board.turn == self.julia_color:
            with self.lock:
                generation = self.generation
                snapshot = self.board.copy()
                self.thinking = True
            self._make_julia_move(snapshot, generation)
        return self.state()

    def human_move(self, uci: str) -> dict[str, Any]:
        with self.lock:
            if self.board.is_game_over(claim_draw=True):
                raise ValueError("The game is over. Start a new game to continue.")
            if self.board.turn != self.human_color:
                raise ValueError("It is Julia's turn.")
            try:
                move = chess.Move.from_uci(uci)
            except ValueError as exc:
                raise ValueError("Invalid move format.") from exc
            if move not in self.board.legal_moves:
                raise ValueError("That move is not legal in this position.")
            san = self.board.san(move)
            self.board.push(move)
            self.history_moves.append(move.uci())
            self.last_actor = "ChatGPT"
            if self.board.is_game_over(claim_draw=True):
                self.last_note = self._end_message()
                return self.state()
            if self.board.turn != self.julia_color:
                self.last_note = f"ChatGPT played {san}. Your turn."
                return self.state()
            self.last_note = f"ChatGPT played {san}. Julia is thinking…"
            self.thinking = True
            generation = self.generation
            snapshot = self.board.copy()

        return self._make_julia_move(snapshot, generation)

    def _make_julia_move(self, snapshot: chess.Board, generation: int) -> dict[str, Any]:
        # Run inference outside the lock so GET /api/state remains responsive.
        try:
            julia_move, actor = self.player.choose(snapshot)
        except Exception:
            with self.lock:
                if generation == self.generation:
                    self.thinking = False
            raise

        with self.lock:
            if generation != self.generation:  # A reset happened while Julia was thinking.
                return self.state()
            julia_san = self.board.san(julia_move)
            self.board.push(julia_move)
            self.history_moves.append(julia_move.uci())
            self.thinking = False
            self.last_note = f"Julia played {julia_san}. Your turn."
            self.last_actor = actor
            return self.state()

    def _end_message(self) -> str:
        outcome = self.board.outcome(claim_draw=True)
        if outcome is None:
            return "Game over."
        if outcome.winner is None:
            return f"Draw — {outcome.termination.name.replace('_', ' ').lower()}."
        winner = "ChatGPT wins" if outcome.winner == self.human_color else "Julia wins"
        return f"{winner} — {outcome.termination.name.replace('_', ' ').lower()}."

    def state(self) -> dict[str, Any]:
        with self.lock:
            board = self.board
            pieces = []
            for rank in range(7, -1, -1):
                row = []
                for file_no in range(8):
                    square = chess.square(file_no, rank)
                    piece = board.piece_at(square)
                    row.append({
                        "square": chess.square_name(square),
                        "piece": piece.symbol() if piece else None,
                        "glyph": UNICODE_PIECES[(piece.color, piece.piece_type)] if piece else None,
                    })
                pieces.append(row)
            history = []
            replay = chess.Board(self.starting_fen)
            replay_moves = [chess.Move.from_uci(uci) for uci in self.history_moves]
            for move in replay_moves:
                color = "w" if replay.turn else "b"
                history.append({
                    "number": replay.fullmove_number,
                    "color": color,
                    "san": replay.san(move),
                    "uci": move.uci(),
                })
                replay.push(move)
            outcome = board.outcome(claim_draw=True)
            king_square = board.king(board.turn) if board.is_check() else None
            last_move = replay_moves[-1] if replay_moves else None
            return {
                "board": pieces,
                "turn": "w" if board.turn else "b",
                "legal_moves": [move.uci() for move in board.legal_moves],
                "history": history,
                "fen": board.fen(),
                "starting_fen": self.starting_fen,
                "check_square": chess.square_name(king_square) if king_square is not None else None,
                "last_move": ({"from": chess.square_name(last_move.from_square),
                               "to": chess.square_name(last_move.to_square)} if last_move else None),
                "game_over": outcome is not None,
                "result": board.result(claim_draw=True) if outcome else None,
                "note": self._end_message() if outcome else self.last_note,
                "last_actor": self.last_actor,
                "thinking": self.thinking,
                "julia_color": "w" if self.julia_color == chess.WHITE else "b",
                "human_color": "w" if self.human_color == chess.WHITE else "b",
            }


class Handler(BaseHTTPRequestHandler):
    game: ChessGame
    web_root = WEB_DIR

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[chess-http] {self.address_string()} {fmt % args}", flush=True)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/state":
            self._json(200, self.game.state())
        elif path == "/":
            page = (self.web_root / "index.html").read_bytes()
            self._send(200, page, "text/html; charset=utf-8")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 2_048:
                raise ValueError("Request body is too large.")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/move":
                state = self.game.human_move(str(payload.get("move", "")))
                self._json(200, state)
            elif path == "/api/reset":
                color = payload.get("julia_color")
                if color not in (None, "white", "black"):
                    raise ValueError("julia_color must be 'white' or 'black'.")
                fen = payload.get("fen")
                if fen is not None and not isinstance(fen, str):
                    raise ValueError("fen must be a string.")
                julia_color = chess.WHITE if color == "white" else chess.BLACK if color == "black" else None
                self._json(200, self.game.reset(fen, julia_color=julia_color))
            else:
                self._json(404, {"error": "not found"})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # Fail safely and keep the server alive.
            print(f"[chess] Request failed: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            self._json(500, {"error": "Julia could not choose a move."})


class PrivateHTTPServer(ThreadingHTTPServer):
    # On Windows, HTTPServer normally enables SO_REUSEADDR; prevent two games
    # from accidentally sharing the same local port and splitting browser requests.
    allow_reuse_address = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Private local chess match: ChatGPT vs. Julia.")
    parser.add_argument("--julia-path", default=None, help="Path to the Julia-1 model directory.")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind to 127.0.0.1 for this PC only, or 0.0.0.0 to allow devices on your local network.")
    parser.add_argument("--port", type=int, default=27600)
    parser.add_argument("--julia-color", choices=("white", "black"), default="black",
                        help="Which color Julia plays; the API caller takes the other color.")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="Maximum search depth.")
    parser.add_argument("--think-time", type=float, default=DEFAULT_THINK_TIME,
                        help="Maximum search time per move, in seconds.")
    parser.add_argument("--margin", type=int, default=DEFAULT_MARGIN,
                        help="Centipawn margin for moves sent to the model.")
    parser.add_argument("--book", default=None, help="Polyglot opening book (.bin).")
    parser.add_argument("--syzygy", default=None, help="Directory containing Syzygy tables.")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        parser.error("Use 127.0.0.1 for this PC only, or 0.0.0.0 for local-network access.")

    if args.depth < 1:
        parser.error("--depth must be at least 1.")
    if args.think_time <= 0:
        parser.error("--think-time must be greater than 0.")
    if args.margin < 0:
        parser.error("--margin cannot be negative.")
    if args.julia_path:
        model_path = Path(args.julia_path).expanduser().resolve()
    else:
        candidates = [
            WEB_DIR.parent / "v04" / "jev-bot" / "bridge" / "Julia-1",
            WEB_DIR.parent / "bridge" / "Julia-1",
        ]
        model_path = next((path.resolve() for path in candidates if (path / "julia" / "__init__.py").is_file()), candidates[0].resolve())
    if not (model_path / "julia" / "__init__.py").is_file():
        parser.error(f"Julia model package not found in {model_path}. Pass --julia-path to the Julia-1 directory.")
    player = JuliaChess(
        str(model_path), args.device,
        depth=args.depth, think_time=args.think_time, margin=args.margin,
        book_path=args.book, syzygy_path=args.syzygy,
    )
    julia_color = chess.WHITE if args.julia_color == "white" else chess.BLACK
    Handler.game = ChessGame(player, julia_color=julia_color)
    if julia_color == chess.WHITE:
        Handler.game.reset()
    try:
        server = PrivateHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        raise SystemExit(f"Could not open port {args.port}; another chess server may already be running.") from exc
    local_url = f"http://127.0.0.1:{args.port}/"
    print(f"[chess] Private match ready on this PC ({args.julia_color}): {local_url}", flush=True)
    if args.host == "0.0.0.0":
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("192.0.2.1", 80))
                lan_ip = probe.getsockname()[0]
            finally:
                probe.close()
            if not lan_ip.startswith("127."):
                print(f"[chess] On your phone, open http://{lan_ip}:{args.port}/ on the same Wi-Fi.", flush=True)
        except OSError:
            print("[chess] LAN address unavailable; find this PC's IPv4 address with ipconfig.", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(local_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[chess] Shutting down the local match.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
