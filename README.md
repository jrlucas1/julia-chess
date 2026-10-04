# Julia Chess Lab

Julia Chess Lab lets Julia play chess on a local computer. A browser page shows the board. A Python server checks every move. Julia selects a move from a list that the search has checked.

## Repository contents

- `chess_server.py` runs the chess server and search.
- `index.html` shows the game in a browser.
- `benchmark_paired_openings.py` runs color-swapped games against Stockfish.
- `run_rating_campaign.py` runs paired games until a deadline.
- `rating_paired/`, `rating_pilot/`, and `rating_campaign_*` contain PGN and JSON results.
- `RATING_BENCHMARK.md` describes the test setup and results.

## Requirements

Use Windows to run `start_xadrez.bat`.

The repository does not contain the Julia model files or its Python environment. Set these paths before you start the server:

```bat
set "JULIA_PYTHON=C:\path\to\.venv-julia\Scripts\python.exe"
set "JULIA_MODEL_PATH=C:\path\to\Julia-1"
set "JULIA_DEVICE=cuda"
```

`JULIA_PYTHON` must point to a Python environment that can import `torch` and `julia`. `JULIA_MODEL_PATH` must point to the folder that contains `julia\__init__.py`.

## Start the game

1. Install `python-chess` in the Julia Python environment. The launcher installs this package if it is missing.
2. Set `JULIA_PYTHON` and `JULIA_MODEL_PATH` as shown above.
3. Set `JULIA_DEVICE` to `cuda` or `cpu`.
4. Run `start_xadrez.bat`.
5. Open the URL that the server prints.

Set `CHESS_JULIA_COLOR` to `white` or `black` to select Julia's color. The default color is black.

The launcher binds to all network interfaces by default. Devices on the same Wi-Fi can connect to the game. To allow access from this computer only, set `CHESS_HOST` to `127.0.0.1` before you start the launcher. Do not set router port forwarding for this server.

## Search settings

Set these variables before you start the launcher:

```bat
set "CHESS_DEPTH=6"
set "CHESS_THINK_TIME=3.0"
set "CHESS_MARGIN=120"
```

`CHESS_THINK_TIME` sets the maximum search time in seconds for each Julia move. The search can stop before it reaches `CHESS_DEPTH` when another search step cannot finish within the time limit.

## Run a benchmark

Start the chess server before you run a benchmark. Install Stockfish 19 separately. This repository does not contain the Stockfish program.

Use `--help` to see the available options:

```bat
python benchmark_paired_openings.py --help
python run_rating_campaign.py --help
```

Pass the path to the Stockfish program with `--stockfish`. The benchmark sends moves to the local server API. The default API address is `http://127.0.0.1:27600`.

## Results

The main test has 100 games and 50 color-swapped opening pairs. Julia scored 33.5 points against Stockfish 19 configured at `UCI_Elo=1480`.

A single-opponent Elo conversion gives an estimate near 1361. The opening-pair bootstrap interval is about 1294 to 1420. This interval measures variation across the tested openings. It does not measure the calibration error of the Stockfish setting.

The `UCI_Elo` values in the supplemental tests are engine settings. They are not independently calibrated ratings. The separate samples do not establish a general chess rating for Julia. Read [RATING_BENCHMARK.md](RATING_BENCHMARK.md) before you cite these results.

The data includes 254 games across four separate batches. Do not combine the batch scores as one rating result.

## License

This repository does not have a license file. Contact the repository owner before you reuse its code or data.
