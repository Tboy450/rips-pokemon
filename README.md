# Triumph Rips AI

This is a local simulator and tracker for testing Rips by Triumph pack-cycling strategies.

The current goal is not to automate purchases. It models the decision after a pack outcome:

1. Keep cash at or above the minimum bank, default `$10.00`.
2. Focus on the `$1.00` and `$2.50` packs.
3. Open one pack manually in the Android app.
4. Enter the final card sell value into this tool.
5. Treat the vault as a total collection value, not one replaceable card.
6. Vault profitable cards when the card value is greater than the pack cost.
7. Otherwise, sell the new card back into the bank.

## App Flow Notes

From the current app behavior:

1. Spin the wheel left or right to choose a pack.
2. Tap the chosen pack.
3. Slide left or right to slice the pack open.
4. About one second later, swipe again to speed up the card spin.
5. Record the final card value.

The flashing card colors may hint at rarity, but this first version treats them as notes only. The strategy uses final sell value.

## Commands

Run a simulation with the placeholder pack config:

```bash
python -m rips_ai simulate --bank 25 --min-bank 10 --runs 1000 --max-opens 100 --allow-negative-ev
```

Get the next recommended pack:

```bash
python -m rips_ai recommend --bank 14.50 --vault 3.00 --allow-negative-ev
```

Log one real manual outcome:

```bash
python -m rips_ai record --pack one_dollar --bank 14.50 --vault 3.00 --card-value 0.72 --rarity-hint "blue flashes"
```

Summarize logged outcomes:

```bash
python -m rips_ai analyze-ledger
```

The default ledger is `data/outcomes.jsonl`. It is ignored by Git because it
contains device/session-specific observed pulls.

Build a simulation config from observed outcomes:

```bash
python -m rips_ai export-ledger-config --output data/packs.observed.json
python -m rips_ai simulate --config data/packs.observed.json --bank 25 --min-bank 10 --allow-negative-ev
```

Parse measured screen text and decide whether to sell or vault:

```bash
python -m rips_ai advise-text --text "Balance $14.50 Vault $3.00 Sell Value $0.72"
```

OCR a screenshot, if `tesseract` is installed:

```bash
python -m rips_ai read-screen /path/to/screenshot.png
```

Read calibrated OCR regions from the current 1080x2340 Rips layout:

```bash
python -m rips_ai read-regions /path/to/screenshot.png
```

Ask for state-specific advice from a screenshot:

```bash
python -m rips_ai advise-screen /path/to/result.png --state result --pack-price 1.00
python -m rips_ai advise-screen /path/to/pack.png --state pack --pack-price 2.50 --min-bank 10
python -m rips_ai advise-screen /path/to/buyback.png --state buyback --expected-sell 0.30
```

The Android flow profile from the sample screen recording is in `config/rips_android_flow.json`.
Detailed notes are in `docs/ANDROID_FLOW.md`.
Project purpose, current direction, known session state, and next steps are in `docs/PROJECT_CONTEXT.md`.

## Live Session Tracking

Start tracking from the current app values:

```bash
python -m rips_ai session-start --bank 14 --vault 0 --min-bank 10 --force
```

Ask what to open next:

```bash
python -m rips_ai session-recommend
```

Check the probability-adjusted `$1` pack plan before opening:

```bash
python -m rips_ai session-plan --pack one_dollar
```

The live recommender uses bankroll tiers. By default, it stays on `$1` packs
until bank reaches `$15.00`; at or above that point it can move to `$2.50`.
If bank drops below `$15.00`, it falls back to `$1` again:

```bash
python -m rips_ai session-recommend
python -m rips_ai session-plan --pack two_fifty
python -m rips_ai session-recommend --two-fifty-bank 16
```

Use one screenshot and let the tool classify the current Rips screen:

```bash
python -m rips_ai session-screen /path/to/screenshot.png
```

On a pack screen, mark the buy as pending only after you actually buy the pack in the app:

```bash
python -m rips_ai session-screen /path/to/pack.png --pack two_fifty --commit
```

After you actually buy/open a pack in the app, mark it pending:

```bash
python -m rips_ai session-buy --pack two_fifty
```

On the result screen, read the screenshot or enter the card value:

```bash
python -m rips_ai session-result --image /path/to/result.png --rarity-hint "blue flashes"
python -m rips_ai session-result --card-value 0.30 --rarity-hint "blue flashes"
```

For live tracking, values above the pack cost are advised as `vault`; values at
or below the pack cost are advised as `sell` to preserve bank liquidity.

If the advice is `sell`, tap Sell in the app, then verify the buyback sheet:

```bash
python -m rips_ai session-buyback --image /path/to/buyback.png
python -m rips_ai session-buyback --amount 0.30 --commit
```

Committed sell/vault outcomes are appended to `data/outcomes.jsonl` by default.
Use `--ledger /path/to/outcomes.jsonl` to write a different file.

If the advice is `vault`, tap Vault in the app, then commit it:

```bash
python -m rips_ai session-vault
```

The older manual commands remain useful, but `session-screen` is the shortest workflow once you have screenshots.

Capture the live Android screen through Shizuku when available:

```bash
python -m rips_ai device-capture
python -m rips_ai device-advise --state result --pack-price 1.00
```

If `device-capture` times out, Android is still blocking Codex to Shizuku communication. Set both apps to unrestricted battery usage and confirm Shizuku service is running.

## Important Assumption

`config/packs.example.json` is fake demo data. Replace it with observed outcomes before using the recommendation output as anything more than a test.
