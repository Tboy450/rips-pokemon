# Project Context

This project is a local advisor for the Pokemon side of Rips by Triumph. Its purpose is to help test pack-cycling strategy without automating real-money purchases.

## Goal

Build toward a screen-aware assistant that can:

1. Keep the cash bank at or above a configurable floor, currently `$10.00`.
2. Focus first on the `$1.00` and `$2.50` Pokemon packs.
3. Track the current vault collection total and card count.
4. Read each revealed card value from screenshots or live Android capture.
5. Track vault as a total collection value and card count.
6. Advise `vault` when the revealed card is worth more than the pack cost.
7. Advise `sell` otherwise, then verify the buyback amount before updating bank.
8. Collect real observed outcomes over time so placeholder pack assumptions can be replaced.

The current implementation is advisor-first. It should not tap purchases automatically until the screen reading, state tracking, and safety checks are reliable.

## Current Strategy Rules

- Buying a pack immediately deducts its price from tracked bank.
- A buy is blocked if it would put bank below the cash floor.
- A result screen creates one pending decision:
  - `vault` if card value is greater than the pack cost.
  - `sell` if card value is less than or equal to the pack cost.
- A sell is only committed after the buyback sheet amount matches the expected card value.
- A vault is only committed after the user taps Vault in the app; it adds the card value to tracked vault total and increments vault card count.
- Bankroll tiering keeps live recommendations on `$1` packs until bank reaches the `$2.50` unlock threshold, default `$15.00`; if bank drops below that threshold, recommendations fall back to `$1`.
- The session tracker stores bank, vault, opened count, pending pack, and history in `data/live_session.json`.
- Committed live sell/vault events are appended to `data/outcomes.jsonl` by default.

`data/live_session.json` is intentionally ignored by Git because it is device/session-specific.
`data/outcomes.jsonl` is also ignored and should hold real observed pull data.

## Current Known Session

At the time this context was written, the local working session was:

```text
bank: $13.00
vault: $7.10
vault cards: 3
cash floor: $10.00
pending: none
```

Recreate that state on a new device with:

```bash
python -m rips_ai session-start --bank 13 --vault 7.10 --vault-count 3 --min-bank 10 --force
```

If the real app state has changed, start with the current real bank and vault instead.

## App Flow

The flow observed from `Screen_Recording_20260817_060907_Rips.mp4`:

1. Choose a Pokemon pack from the carousel by swiping left/right.
2. Tap the pack/buy button.
3. Tap the selected pack when the picker screen appears.
4. Swipe horizontally to slice the pack.
5. About one second later, swipe again to speed the card spin.
6. On the result screen, read the large card value.
7. Tap Sell or Vault according to the advisor.
8. If selling, verify and accept the buyback sheet.

The calibrated state and gesture profile is in `config/rips_android_flow.json`.
OCR crop regions for a Samsung `1080x2340` portrait layout are in `config/screen_regions.example.json`.
The extracted sample frames in `analysis_frames/` are included as calibration fixtures and examples for screenshot commands.

## Main Commands

Start or reset live tracking:

```bash
python -m rips_ai session-start --bank 14 --vault 0 --min-bank 10 --force
```

Show tracked state:

```bash
python -m rips_ai session-status
```

Recommend the next pack from placeholder pack data:

```bash
python -m rips_ai session-recommend
```

Check the `$1` pack with probability-weighted bank/vault projections:

```bash
python -m rips_ai session-plan --pack one_dollar
```

Compare the locked or unlocked `$2.50` tier with its own probability table:

```bash
python -m rips_ai session-plan --pack two_fifty
python -m rips_ai session-recommend --two-fifty-bank 15
```

Use a screenshot-first workflow:

```bash
python -m rips_ai session-screen /path/to/pack.png --pack two_fifty --commit
python -m rips_ai session-screen /path/to/result.png --rarity-hint "blue flashes"
python -m rips_ai session-screen /path/to/buyback.png --commit
```

Use manual values when OCR is not available or not trusted:

```bash
python -m rips_ai session-buy --pack two_fifty
python -m rips_ai session-result --card-value 0.30 --rarity-hint "blue flashes"
python -m rips_ai session-buyback --amount 0.30 --commit
```

Use `python -m rips_ai analyze-ledger` to summarize observed card values,
observed profit, and sell/vault counts by pack.
Use `python -m rips_ai export-ledger-config --output data/packs.observed.json`
to convert observed pulls into a simulation config.

Try live Android capture through Shizuku:

```bash
python -m rips_ai device-capture --output data/latest_screen.png
python -m rips_ai classify-screen data/latest_screen.png
```

## Dependencies

The core package has no Python runtime dependencies beyond the standard library.

Optional tools:

- `tesseract` for OCR commands.
- `ffmpeg` for extracting frames from screen recordings during calibration.
- `shizuku` for live Android screenshots and later UI automation.

## Current Shizuku Status

Shizuku shell access has worked intermittently from this environment. The command `shizuku id` returned Android shell access at one point, but later Shizuku reported `Server is not running`.

The `device-capture` path was updated to avoid corrupting binary PNG output through the Shizuku wrapper by reading remote screenshots as indexed base64 chunks. If live capture fails, first confirm:

```bash
shizuku id
```

If that fails, open the Shizuku app and restart the service. Also keep Codex and Shizuku unrestricted in Android battery settings.

## What To Improve Next

1. Collect enough real outcomes in `data/outcomes.jsonl`, then export `data/packs.observed.json`.
2. Recalibrate OCR regions if the target device resolution differs from `1080x2340`.
3. Add collection-screen cross-checks to verify the tracked vault value.
4. Make `device-capture` plus `session-screen` the standard live loop once Shizuku is stable.
5. Only after the advisor is reliable, consider guarded tap/swipe assistance for non-purchase gestures.

## Safety Direction

Keep purchase decisions manual. The program may advise and track, but it should not independently spend money. Any later automation should require explicit user confirmation before a buy, sell, vault, or buyback accept action.
