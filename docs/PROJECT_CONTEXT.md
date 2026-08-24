# Project Context

This project is a local advisor for the Pokemon side of Rips by Triumph. Its purpose is to help test pack-cycling strategy without automating real-money purchases.

## Goal

Build toward a screen-aware assistant that can:

1. Keep the cash bank at or above a configurable floor, currently `$10.00`.
2. Focus first on the `$1.00` and `$2.50` Pokemon packs.
3. Track the current vault collection total, card count, and individual card
   appraisals when known.
4. Read each revealed card value from screenshots or live Android capture.
5. Track vault as total value/card count, with optional per-card values from
   gallery appraisal.
6. If per-card vault values are known, advise `vault` only when the revealed
   card beats the current highest vault card and would replace it.
7. If per-card vault values are unknown, fall back to the pack-cost rule:
   vault above cost, sell at or below cost.
8. Collect real observed outcomes over time so placeholder pack assumptions can be replaced.

The current implementation is advisor-first. It should not tap purchases automatically until the screen reading, state tracking, and safety checks are reliable.

## Current Strategy Rules

- A pack buy only deducts tracked bank after the command includes explicit
  `--purchase-confirmed`, meaning the in-app buy/open step was already
  accepted.
- A buy is blocked if it would put bank below the cash floor.
- A result screen creates one pending decision:
  - If individual vault card values are known, `vault` only if the card beats
    the current highest vault card and would replace it.
  - If individual vault card values are unknown, `vault` if card value is
    greater than the pack cost and `sell` otherwise.
- A sell is only committed after the buyback sheet amount matches the expected card value.
- A vault is only committed after the user taps Vault in the app. If the
  pending advice is a replacement, it replaces the tracked vault card and
  records the replaced value as the expected old-card return. If no per-card
  vault values are known, it adds the card value to the tracked vault total and
  increments vault card count.
- Bankroll tiering keeps live recommendations on `$1` packs until bank reaches the `$2.50` unlock threshold, default `$15.00`; if bank drops below that threshold, recommendations fall back to `$1`.
- The session tracker stores bank, vault, opened count, pending pack, and history in `data/live_session.json`.
- Committed live sell/vault events are appended to `data/outcomes.jsonl` by default.
- Visible bank checks are explicit audits. `session-bank-check` reports the
  tracked bank, observed bank, and delta, and only rewrites tracked bank with
  `--commit`.
- Vault gallery appraisal is also explicit. `session-vault-audit` compares
  tracked vault value/count against manually entered appraised values, and only
  rewrites tracked vault totals with `--commit`.
- Individual vault card values must come from real gallery appraisals, not from
  subtracting or inferring values from the vault total. Any total-only
  `session-vault-audit` or `session-reconcile` clears stale individual card
  values so the advisor falls back to the pack-cost rule until the gallery is
  appraised again.

`data/live_session.json` is intentionally ignored by Git because it is device/session-specific.
`data/outcomes.jsonl` is also ignored and should hold real observed pull data.

## Current Known Session

At the time this context was written, the local working session was:

```text
bank: $16.50
vault: $6.80
vault cards: 2
cash floor: $10.00
opened: 2
pending: none
```

Recreate that state on a new device with:

```bash
python -m rips_ai session-start --bank 16.50 --vault 6.80 --vault-count 2 --min-bank 10 --force
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

Print the active workflow for the current tracked state:

```bash
python -m rips_ai session-workflow
python -m rips_ai session-diagnose --screen-state pack --bank 11.30 --vault 8.90 --vault-count 5
```

Use `session-diagnose` when the operator can see the screen but Shizuku capture
or context continuity is unreliable. It reports tracker drift and screen-specific
next steps without mutating unless complete trusted totals are supplied with
`--commit`.

Use this after compaction, Shizuku failure, app interruption, or any Rips action.
It prints the next stage-specific commands and includes the active bank
diagnosis and vault audit checkpoints. The first workflow step must be screen
anchoring before any gesture:

```bash
python -m rips_ai device-capture --output data/latest_screen.png
python -m rips_ai classify-screen data/latest_screen.png
```

If capture is unavailable, use what is visible on the device:

```bash
python -m rips_ai session-diagnose --screen-state STATE --bank VALUE --vault VALUE --vault-count COUNT
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
python -m rips_ai session-screen /path/to/pack.png --pack two_fifty
python -m rips_ai session-screen /path/to/pack.png --pack two_fifty --commit --purchase-confirmed
python -m rips_ai session-screen /path/to/result.png --rarity-hint "blue flashes"
python -m rips_ai session-screen /path/to/buyback.png --commit
```

`session-screen` also classifies `whats_inside`, `pack_picker`,
`vault_gallery`, and `vault_appraisal` as navigation-only states. Those states
print the next workflow action and do not mutate tracked session values.

Use manual values when OCR is not available or not trusted:

```bash
python -m rips_ai session-buy --pack two_fifty --purchase-confirmed
python -m rips_ai session-result --card-value 0.30 --rarity-hint "blue flashes"
python -m rips_ai session-buyback --amount 0.30 --commit
```

Use the calibrated live Shizuku flow only when the main buy screen is visible:

```bash
python -m rips_ai device-open-pack --pack one_dollar --dry-run
python -m rips_ai device-open-pack --pack one_dollar --stage tap-buy --confirmed-buy-screen --stay-in-rips
python -m rips_ai device-open-pack --pack one_dollar --stage finish-open --purchase-observed
```

The dry run prints the gesture sequence and planned session mutation without
touching Rips. The live flow is intentionally staged. First tap only the lower
orange buy button and leave Rips foreground for confirmation. Only after the
post-buy picker/result flow is visibly reached should the second command run
with `--purchase-observed`; that is the only `device-open-pack` path that marks
the session pending. If the tap lands on `What's inside`, reconcile the tracker
back to the visible app totals and do not use `--purchase-observed`.

Verify visible bank after a draw, sell/buyback, vault, or return to the buy
screen:

```bash
python -m rips_ai session-bank-check --bank 11
python -m rips_ai session-bank-check --bank 11 --source "visible app bank after draw" --commit
python -m rips_ai session-reconcile --bank 11.30 --vault 8.90 --vault-count 5 --clear-pending --count-cleared-pending --commit
```

Use `session-reconcile` after interruptions or manual app actions when the app
state is trusted but the tracker has stale pending state. Use
`--count-cleared-pending` only when the cleared pending pack really completed.

Audit the gallery-style vault by long-pressing each card in the app to reveal
its appraisal/detail value, then entering the values:

```bash
python -m rips_ai device-vault-gallery-plan
python -m rips_ai device-vault-gallery-plan --emit shell
python -m rips_ai session-vault-audit --card-values 1.00 2.50 5.40
python -m rips_ai session-vault-audit --card-values 1.00 2.50 5.40 --commit
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

1. Make Android screenshot readback reliable. The Shizuku wrapper can corrupt
   raw PNG streams, and chunked base64 readback can hang mid-file, so
   `device-capture` needs a faster validated transfer path.
2. Add screen-state verification before gestures. The assistant must
   distinguish the main pack carousel, the `What's inside` carousel, the
   post-buy picker carousel, the slice screen, the result screen, and buyback
   sheets before tapping.
3. Convert `device-open-pack` into a state-machine flow: tap the lower buy
   button, wait for the post-buy picker, use two fast long carousel spins in
   the same direction, select the centered pack, slice with the long swipe plus
   fast follow-up, then wait for result.
4. Add a result/buyback loop that reads the card value, advises `sell` or
   `vault`, and only commits after the in-app action is confirmed.
   When individual vault card values are known, compare against the current
   highest vault card. When they are unknown, use the pack-cost fallback and
   schedule a gallery audit.
5. Turn `device-vault-gallery-plan` into a state-aware appraisal loop. Required
   calibration parameters: top-left card center, grid columns/rows, center
   spacing, page count, scroll gesture, long-press duration, close/back action,
   and appraisal value OCR crop.
6. Add collection-screen cross-checks to verify tracked vault value and card
   count after vault actions.
7. Collect enough real outcomes in `data/outcomes.jsonl`, then export
   `data/packs.observed.json` to replace placeholder pack odds.

## Safety Direction

Keep purchase decisions manual. The program may advise and track, but it should not independently spend money. Any later automation should require explicit user confirmation before a buy, sell, vault, or buyback accept action.
