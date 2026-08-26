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
- Bankroll tiering keeps live recommendations on `$1` packs until bank reaches
  the `$2.50` unlock threshold, default `$20.00`; if bank drops below that
  threshold, recommendations fall back to `$1`. This temporary higher threshold
  is intentional until bank and vault value updates are consistently correct in
  live runs.
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
vault: $3.40
vault cards: 2
vault card values: $3.30, $0.10
cash floor: $10.00
opened: 2
pending: none
```

Recreate that state on a new device with:

```bash
python -m rips_ai session-start --bank 16.50 --vault 3.40 --vault-count 2 --min-bank 10 --force
python -m rips_ai session-vault-audit --card-values 3.30 0.10 --commit --source "manual vault card appraisals"
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
python -m rips_ai session-recommend --two-fifty-bank 20
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

1. Add a Shizuku-side fast controller. Send one compact Android shell
   controller through Shizuku to wake/check unlock state, focus Rips, read
   compact UI/window state, wait through `Loading Packs...`, run the calibrated
   open gestures, and return concise logs. Use screenshots only when the fast
   state is ambiguous or OCR is required.
2. Make the project less monolithic. Before adding more automation, split the
   large CLI/device flow into smaller modules for Android state probing,
   screenshot evidence, pack-opening gestures, session mutation, and CLI
   formatting. Keep public commands stable while moving code.
3. Keep screenshots as fallback evidence. Screenshot readback should remain
   reliable, but it should not drive every live step. Capture PNGs for failure
   diagnosis, risky transitions, and OCR-only values such as card, bank,
   buyback, and vault appraisal amounts.
4. Add verified state checks before gestures. The assistant must distinguish
   the main pack carousel, `What's inside`, post-buy picker, slice screen,
   reveal/result, buyback sheet, vault gallery, and appraisal/detail sheet
   before tapping.
5. Convert `device-open-pack` into a resumable state machine: focus app, verify
   buy screen, tap Buy, verify picker, spin/select, slice/reveal, wait for
   result, then leave the session pending until the in-app result is resolved.
6. Add the result and buyback decision loop. Read the card value, advise `sell`
   or `vault`, verify buyback offers before accepting, and commit only after
   the matching in-app action is confirmed.
7. Turn `device-vault-gallery-plan` into a state-aware appraisal loop using
   calibrated grid points, long-press appraisal reads, close/back behavior, and
   `session-vault-audit` reconciliation.
8. Build replayable fixtures and observed data. Save screenshots/UI dumps for
   each app state, test classification and next allowed actions, then grow
   `data/outcomes.jsonl` into an observed pack config.

## Step 2 Modularization Plan

Do this as a refactor-only pass before adding another large live automation
feature. Keep command names, flags, and current output stable while moving code.

1. Move Android probing into `rips_ai/android_state.py`: Shizuku foreground
   checks, wake/keyguard checks, UI dump parsing, and compact state labels.
2. Move screenshot/evidence handling into `rips_ai/evidence.py`: capture,
   PNG validation, blank-frame detection, OCR evidence files, and manifests.
3. Move open-flow mechanics into `rips_ai/open_flow.py`: gestures, coordinate
   overrides, staged sequences, fast-controller script generation, checkpoints,
   and controller output parsing.
4. Keep tracker mutation in the existing session/ledger/vault modules. Android
   flow code should report observations; session code should decide what can be
   committed.
5. Thin `rips_ai/cli.py` so it parses arguments, calls modules, formats output,
   and returns exit codes.
6. Migrate one command path at a time: `device-open-pack --dry-run`, staged
   `tap-buy`, staged `finish-open`, then the Shizuku fast controller.
7. Test the boundaries after each move. Mock Shizuku only at the Android
   boundary and keep CLI tests focused on user-visible output plus session
   mutation.

## Safety Direction

Keep purchase decisions manual. The program may advise and track, but it should not independently spend money. Any later automation should require explicit user confirmation before a buy, sell, vault, or buyback accept action.
