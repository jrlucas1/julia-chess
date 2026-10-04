# Julia chess benchmark

## Result — October 3, 2026

We played 100 games across 50 fixed opening positions. Each opening was played twice, with Julia taking White once and Black once. Julia scored **33.5/100 points (33.5%)** against Stockfish 19 configured at `UCI_Elo=1480`.

| Result for Julia | Games |
|---|---:|
| Wins | 20 |
| Draws | 27 |
| Losses | 53 |
| Score | 33.5 / 100 (33.5%) |

By color, Julia scored 20/50 (40%) as White and 13.5/50 (27%) as Black. This is descriptive for this sample; it does not establish a stable color effect.

Using the standard single-opponent Elo score formula gives a point estimate of **about 1,361**. Resampling the 50 opening pairs (50,000 bootstrap replicates; fixed seed 20261003) gives an approximate 95% interval of **1,294–1,420**. Both figures are specific to this opponent setup and should be presented as an experimental performance estimate, not Julia's general chess rating or an official FIDE rating.

## Protocol and configuration

- Opponent: Stockfish 19, pinned local executable, `UCI_Elo=1480`, one thread, 128 MB hash, 3 seconds per move.
- Julia: current local server model/search configuration, 3-second search budget per move.
- Openings: 50 fixed opening positions; each was played twice with colors swapped.
- Draw handling: game adjudicated as a draw after 120 plies from the opening setup if no result occurred earlier.
- Score formula: `R_est = 1480 + 400 * log10(p / (1 - p))`, where `p` is Julia's score fraction.
- Uncertainty: percentile bootstrap over opening pairs, keeping each color-swapped pair together. The interval reflects opening-sample variation only; it does not account for calibration error in Stockfish's UCI strength setting or uncertainty across machines and time controls.

The opening set and result artifacts are in `rating_paired/`. The paired batches cover pairs 1–50; their PGNs contain all 100 games and parse without errors. The latest batch is `paired-stockfish19-elo1480-pairs41-50.pgn` with matching JSON. The original 32-game pilot was superseded by this larger paired sample and is not added to the score.

## Supplemental five-hour campaign — October 3, 2026

During a separate five-hour window, Julia played **58 additional games** in 29 color-swapped opening pairs against Stockfish 19 at four configured `UCI_Elo` strengths. Julia scored **29.5/58 points (50.9%)** overall: 16 wins, 27 draws, and 15 losses.

| Stockfish `UCI_Elo` setting | Games | Julia W-D-L | Points | Score |
|---:|---:|---:|---:|---:|
| 1320 | 16 | 5-10-1 | 10/16 | 62.5% |
| 1400 | 14 | 6-5-3 | 8.5/14 | 60.7% |
| 1480 | 14 | 2-5-7 | 4.5/14 | 32.1% |
| 1560 | 14 | 3-7-4 | 6.5/14 | 46.4% |
| **Total** | **58** | **16-27-15** | **29.5/58** | **50.9%** |

By color, Julia scored 15/29 points (51.7%) as White and 14.5/29 (50.0%) as Black. Each opening pair was played with colors swapped. Stockfish searched for 3 seconds per move; games without an earlier result were adjudicated as draws after 120 plies from the opening setup. Julia used the current local server search configuration with a 3-second search budget per move.

Treat this as a separate, descriptive sample; do not combine it with the 100-game `UCI_Elo=1480` benchmark above. The four `UCI_Elo` values are Stockfish strength settings, not independently calibrated human ratings, and these small samples do not establish Julia's general chess rating. The score also does not change monotonically across the four settings, so report the per-setting counts instead of implying a measured rating curve. All 29 PGNs were replayed and checked against their JSON records; all 58 games had legal move sequences and matching results and colors. The artifacts are under `rating_campaign_20261003/`, with the campaign index in `rating_campaign_20261003/campaign_status.json`.

## Supplemental resumed window — October 3, 2026

In a later session, Julia played **20 more games** across 10 color-swapped opening pairs. The run stopped cleanly at its reserve threshold ahead of the 14:05 UTC usage-window reset. Julia scored **8.5/20 points (42.5%)**: 6 wins, 5 draws, and 9 losses.

| Stockfish `UCI_Elo` setting | Games | Julia W-D-L | Points | Score |
|---:|---:|---:|---:|---:|
| 1320 | 6 | 2-3-1 | 3.5/6 | 58.3% |
| 1400 | 6 | 2-1-3 | 2.5/6 | 41.7% |
| 1480 | 4 | 0-1-3 | 0.5/4 | 12.5% |
| 1560 | 4 | 2-0-2 | 2/4 | 50.0% |
| **Total** | **20** | **6-5-9** | **8.5/20** | **42.5%** |

These are configured Stockfish `UCI_Elo` targets, not independently calibrated ratings. This small, short-run sample is descriptive only; it does not establish a rating for Julia, and its non-monotonic scores should not be read as a rating curve. Keep it separate from both the original 100-game benchmark and the earlier 58-game supplemental campaign. All 10 PGNs were replayed with legal move checks and cross-checked against their paired JSON records; all 20 games passed. The artifacts are under `rating_campaign_20261003_session2/`, indexed by `rating_campaign_20261003_session2/campaign_status.json`.

## Supplemental reserve-window campaign — October 3, 2026

Julia played **76 additional games** in 38 color-swapped opening pairs during the later five-hour usage window. The supervisor stopped starting new pairs at its 20-minute reserve threshold, finished the active pair, and exited cleanly at 15:46 BRT. Julia scored **26/76 points (34.2%)**: 12 wins, 28 draws, and 36 losses.

| Stockfish `UCI_Elo` setting | Games | Julia W-D-L | Points | Score |
|---:|---:|---:|---:|---:|
| 1320 | 20 | 7-9-4 | 11.5/20 | 57.5% |
| 1400 | 20 | 4-7-9 | 7.5/20 | 37.5% |
| 1480 | 18 | 1-6-11 | 4/18 | 22.2% |
| 1560 | 18 | 0-6-12 | 3/18 | 16.7% |
| **Total** | **76** | **12-28-36** | **26/76** | **34.2%** |

This is a separate descriptive sample; do not pool it with the original 100-game benchmark or either earlier supplemental campaign. The listed Stockfish `UCI_Elo` values are configured engine-strength targets, **not independently calibrated ratings**. Although this sample's score declined across the four settings, its small per-setting samples and uncalibrated targets do not establish Julia's rating or a rating curve. The same opening was played with colors swapped, Stockfish used a 3-second move limit, Julia used a 3-second search budget, and games still unresolved after 120 plies from the setup position were adjudicated as draws. All 38 PGNs were replayed: all 76 move sequences were legal, and results, starting FENs, colors, and ply counts matched their JSON records. The artifacts and campaign index are under `rating_campaign_20261003_session3/`.

