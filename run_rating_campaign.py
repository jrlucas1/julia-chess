#!/usr/bin/env python3
"""Run paired Julia-vs-Stockfish samples until a fixed UTC deadline.

Each sample is a two-game color-swapped opening pair. Results are written by
the existing benchmark runner and indexed in campaign_status.json so the run
can be audited or resumed without overwriting prior samples.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNNER = BASE / "benchmark_paired_openings.py"
DEFAULT_STOCKFISH = BASE / "stockfish-19" / "stockfish" / "stockfish-windows-x86-64-universal.exe"
DEFAULT_PYTHON = BASE.parent / "v04" / "jev-bot" / "bridge" / ".venv-julia" / "Scripts" / "python.exe"
DEFAULT_ROOT = BASE / "rating_campaign_20261003"
LEVELS = (1320, 1400, 1480, 1560)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline", required=True, help="UTC ISO-8601 timestamp")
    parser.add_argument("--api", default="http://127.0.0.1:27600")
    parser.add_argument("--stockfish", type=Path, default=DEFAULT_STOCKFISH)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--output", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--reserve-seconds", type=int, default=1200,
                        help="Do not begin a pair unless this much time remains")
    args = parser.parse_args()

    deadline = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        raise SystemExit("--deadline must include a timezone, preferably Z.")
    if not args.python.is_file() or not RUNNER.is_file() or not args.stockfish.is_file():
        raise SystemExit("Python, benchmark runner, or Stockfish executable was not found.")

    args.output.mkdir(parents=True, exist_ok=True)
    # Child runners execute with cwd=BASE, so always pass an absolute output
    # path; a relative path would otherwise be nested under xadrez/ a second time.
    args.output = args.output.resolve()
    status_path = args.output / "campaign_status.json"
    log_path = args.output / "campaign.log"
    status = {"started_at_utc": utc_now().isoformat(), "deadline_utc": deadline.isoformat(),
              "levels": list(LEVELS), "status": "running", "completed_pairs": [],
              "current": None}
    if status_path.exists():
        previous = json.loads(status_path.read_text(encoding="utf-8"))
        if previous.get("status") == "running":
            status = previous
            status["resumed_at_utc"] = utc_now().isoformat()
            status["deadline_utc"] = deadline.isoformat()
        else:
            raise SystemExit(f"Campaign already has terminal status: {previous.get('status')}")

    def save() -> None:
        temporary = status_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(status, indent=2), encoding="utf-8")
        temporary.replace(status_path)

    # Existing completed records determine the next sample and opening, making
    # an interrupted campaign resumable without repeating a completed pair.
    completed = status["completed_pairs"]
    with log_path.open("a", encoding="utf-8", buffering=1) as log:
        log.write(f"\n[{utc_now().isoformat()}] Campaign supervisor started; deadline {deadline.isoformat()}\n")
        while utc_now() + timedelta(seconds=args.reserve_seconds) < deadline:
            n = len(completed)
            level = LEVELS[n % len(LEVELS)]
            opening_index = (n // len(LEVELS)) % 50 + 1
            sample_index = 1 + sum(item["elo"] == level for item in completed)
            output_dir = args.output / f"elo{level}" / f"sample_{sample_index:03d}"
            output_dir.mkdir(parents=True, exist_ok=True)
            command = [str(args.python), str(RUNNER), "--api", args.api,
                       "--stockfish", str(args.stockfish), "--elo", str(level),
                       "--pairs", "1", "--start-pair", str(opening_index),
                       "--move-time", "3", "--max-plies", "120",
                       "--output", str(output_dir)]
            status["current"] = {"elo": level, "opening_index": opening_index,
                                 "sample_index": sample_index,
                                 "started_at_utc": utc_now().isoformat(),
                                 "output_dir": str(output_dir)}
            save()
            log.write(f"\n[{utc_now().isoformat()}] Starting {status['current']}\n")
            attempts = 0
            while attempts < 3:
                attempts += 1
                log.write(f"[{utc_now().isoformat()}] Attempt {attempts}: {command!r}\n")
                proc = subprocess.run(command, cwd=BASE, stdout=log, stderr=subprocess.STDOUT)
                if proc.returncode == 0:
                    break
                log.write(f"[{utc_now().isoformat()}] Runner exited {proc.returncode}.\n")
                if attempts < 3:
                    time.sleep(20)
            if proc.returncode != 0:
                status["status"] = "failed"
                status["failure"] = {"returncode": proc.returncode,
                                     "failed_at_utc": utc_now().isoformat(),
                                     "current": status["current"]}
                status["current"] = None
                save()
                log.write(f"[{utc_now().isoformat()}] Campaign stopped after 3 failed attempts.\n")
                return proc.returncode

            result_path = next(output_dir.glob("*.json"), None)
            if result_path is None:
                status["status"] = "failed"
                status["failure"] = {"reason": "runner returned successfully but produced no JSON",
                                     "failed_at_utc": utc_now().isoformat(),
                                     "current": status["current"]}
                status["current"] = None
                save()
                return 2
            result = json.loads(result_path.read_text(encoding="utf-8"))
            completed.append({"elo": level, "opening_index": opening_index,
                              "sample_index": sample_index,
                              "score_fraction": result["score_fraction"],
                              "games": len(result["games"]),
                              "json": str(result_path), "pgn": result["pgn_file"],
                              "completed_at_utc": utc_now().isoformat()})
            status["current"] = None
            status["updated_at_utc"] = utc_now().isoformat()
            save()
            log.write(f"[{utc_now().isoformat()}] Completed pair {len(completed)}: "
                      f"UCI_Elo={level}, opening={opening_index}, "
                      f"score={result['score_fraction']:.1%}, games={len(result['games'])}.\n")

        status["status"] = "deadline_reached"
        status["current"] = None
        status["finished_at_utc"] = utc_now().isoformat()
        save()
        log.write(f"[{utc_now().isoformat()}] Deadline reserve reached; campaign stopped cleanly.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
