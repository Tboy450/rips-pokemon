# Triumph Rips AI

This is a local simulator and tracker for testing Rips by Triumph pack-cycling strategies.

The current goal is not to automate purchases. It models the decision after a pack outcome:

1. Keep cash at or above the minimum bank, default `$10.00`.
2. Focus on the `$1.00` and `$2.50` packs.
3. Open one pack manually in the Android app.
4. Enter the final card sell value into this tool.
5. Track the vault total, card count, and, when appraised, individual card values.
6. If individual vault values are known, vault only when the new card beats the
   current highest vault card and would replace it.
7. If individual vault values are unknown, fall back to the pack-cost rule:
   vault values above pack cost and sell values at or below pack cost.

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
python -m rips_ai session-workflow
python -m rips_ai session-recommend
```

`session-workflow` is the operational entry point. It reads the current tracker
and prints the next commands for the current stage, including bank diagnosis,
vault gallery audit, pending result handling, sell buyback verification, or
vault commit. Use it after any interruption or Shizuku failure before touching
Rips again. The first workflow checkpoint is always screen anchoring:

```bash
python -m rips_ai device-capture --output data/latest_screen.png
python -m rips_ai classify-screen data/latest_screen.png
```

If capture is unavailable or stale, use the visible screen manually before any
gesture:

```bash
python -m rips_ai session-diagnose --screen-state STATE --bank VALUE --vault VALUE --vault-count COUNT
```

When the app was interrupted or screenshot readback is unreliable, use a
manual diagnosis from the visible app state:

```bash
python -m rips_ai session-diagnose --screen-state pack --bank 11.30 --vault 8.90 --vault-count 5
python -m rips_ai session-diagnose --screen-state whats_inside --bank 11.30 --vault 8.90 --vault-count 5
```

`session-diagnose` prints screen-specific next steps plus tracker deltas. It
does not change the session unless all trusted totals are supplied with
`--commit`.

Check the probability-adjusted `$1` pack plan before opening:

```bash
python -m rips_ai session-plan --pack one_dollar
```

The live recommender uses bankroll tiers. For now, it deliberately stays on
`$1` packs until bank reaches `$20.00` because the bank/vault update loop still
needs more live validation. At or above `$20.00` it can move to `$2.50`; if bank
drops below `$20.00`, it falls back to `$1` again:

```bash
python -m rips_ai session-recommend
python -m rips_ai session-plan --pack two_fifty
python -m rips_ai session-recommend --two-fifty-bank 20
```

`five_dollar` is present in the sample pack config so accidental or manual `$5`
buys can be tracked with the correct cost, but it is not selected by the default
bankroll-tier recommender.

Use one screenshot and let the tool classify the current Rips screen:

```bash
python -m rips_ai session-screen /path/to/screenshot.png
```

`session-screen` also recognizes navigation-only states such as
`whats_inside`, `pack_picker`, `vault_gallery`, and `vault_appraisal`. Those
states print safe next steps and do not change tracked bank, vault, or pending
pack state.

On a pack screen, the tool only advises by default:

```bash
python -m rips_ai session-screen /path/to/pack.png --pack one_dollar
```

After you actually buy/open a pack in the app and the app accepts the action,
mark it pending with the explicit confirmation flag:

```bash
python -m rips_ai session-buy --pack one_dollar --purchase-confirmed
python -m rips_ai session-screen /path/to/pack.png --pack one_dollar --commit --purchase-confirmed
```

On the result screen, read the screenshot or enter the card value:

```bash
python -m rips_ai session-result --image /path/to/result.png --rarity-hint "blue flashes"
python -m rips_ai session-result --card-value 0.30 --rarity-hint "blue flashes"
```

For live tracking, the best advice depends on how much vault detail is known. If
`session-vault-audit --card-values ... --commit` has recorded individual vault
card values, the revealed card is advised as `vault` only when it beats the
current highest vault card and would replace it. If individual values are not
known, the tool falls back to the older pack-cost rule: values above the pack
cost are advised as `vault`, while values at or below cost are advised as `sell`
to preserve bank liquidity.

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

Open one live pack through the calibrated Shizuku gesture flow only when the
main buy screen is visible:

```bash
python -m rips_ai device-open-pack --pack one_dollar --dry-run
python -m rips_ai device-open-pack --pack one_dollar --stage tap-buy --confirmed-buy-screen --stay-in-rips
python -m rips_ai device-open-pack --pack one_dollar --stage finish-open --purchase-observed
```

The dry run prints the exact Shizuku gesture sequence and planned session
mutation without touching Rips or the tracker. The live command is staged so a
missed tap on `What's inside` cannot silently deduct bank: first run
`--stage tap-buy` and visually confirm the app reaches the post-buy picker or
result flow. Only then run `--stage finish-open --purchase-observed`, or use
`session-buy --purchase-confirmed` manually. Without `--purchase-observed`,
`device-open-pack` sends gestures only and leaves bank/pending state unchanged.
Use `--buy-tap X,Y` with `--dry-run` first when recalibrating the orange button
coordinate.

Check the visible bank after a draw or app action:

```bash
python -m rips_ai session-bank-check --bank 11
python -m rips_ai session-bank-check --image /path/to/screenshot.png
```

The command reports tracked bank, observed bank, and delta. It does not change
the session unless the visible value is trusted and `--commit` is supplied:

```bash
python -m rips_ai session-bank-check --bank 11 --source "visible app bank after draw" --commit
```

If the app was interrupted and the tracker needs to align to a trusted resolved
state, reconcile bank, vault, card count, and stale pending state together:

```bash
python -m rips_ai session-reconcile --bank 11.30 --vault 8.90 --vault-count 5 --clear-pending
python -m rips_ai session-reconcile --bank 11.30 --vault 8.90 --vault-count 5 --clear-pending --count-cleared-pending --commit
```

Audit the gallery-style vault by long-pressing each card for its appraisal
value, recording the values, and entering them together:

```bash
python -m rips_ai session-vault-audit --card-values 1.00 2.50 5.40
python -m rips_ai session-vault-audit --card-values 1.00 2.50 5.40 --commit
```

If only the app's total and card count are visible, use:

```bash
python -m rips_ai session-vault-audit --total 8.90 --count 5
```

Generate the later Shizuku long-press plan for the vault gallery without
executing it:

```bash
python -m rips_ai device-vault-gallery-plan
python -m rips_ai device-vault-gallery-plan --emit shell
```

The gallery parameters live in `config/rips_android_flow.json` under
`vault_gallery`. Calibrate `first_card_center`, `x_step`, `y_step`, `columns`,
`rows`, `pages`, `long_press_ms`, and the `vault_gallery_scroll_next` gesture
from a real vault screenshot before executing any future automated appraisal.

If `device-capture` times out, Android is still blocking Codex to Shizuku communication. Set both apps to unrestricted battery usage and confirm Shizuku service is running.

## Next Best Upgrade Steps

The next phase should move in focused updates. Do not try to finish the whole
automation stack in one pass; each update should leave the project tested,
documented, and safe to resume.

1. Add a Shizuku-side fast controller.
   Stop driving the open process through repeated screenshot/OCR calls. Send
   one compact Android shell controller through Shizuku to wake/check unlock
   state, focus Rips, read compact UI/window state, wait through
   `Loading Packs...`, run the calibrated open gestures, and return concise
   logs.

2. Make the project less monolithic.
   Before adding more live automation, split the large CLI/device flow into
   smaller modules with clear ownership, such as Android state probing,
   screenshot evidence, pack-opening gestures, session mutation, and CLI
   formatting. Keep public commands stable while moving code.

3. Keep screenshots as fallback evidence.
   Screenshot readback should remain reliable, but screenshots should not be
   the primary control loop. Capture PNG evidence only for ambiguous fast
   states, failures, risky transitions, and OCR-only values such as result
   cards, buyback offers, bank chips, and vault appraisals.

4. Add verified state checks before gestures.
   The program should distinguish the main pack carousel, `What's inside`,
   post-buy picker, slice screen, reveal/result, buyback sheet, vault gallery,
   and appraisal/detail sheet. A command should refuse to tap when the observed
   state does not match the requested action.

5. Convert `device-open-pack` into a resumable state machine.
   The full opener should be restartable at a known checkpoint: focus app,
   verify buy screen, tap Buy, verify picker, spin/select, slice/reveal, wait
   for result, then leave the session pending until the in-app result is
   resolved.

6. Add the result and buyback decision loop.
   Read the revealed card value, advise `sell` or `vault`, verify buyback
   offers before accepting, and commit session changes only after the matching
   in-app action is confirmed.

7. Turn vault gallery planning into an appraisal loop.
   Use the calibrated grid plan to long-press each card, read appraisal/detail
   values, close the detail sheet, and feed totals into `session-vault-audit`
   for correction.

8. Build replayable fixtures and observed data.
   Save representative screenshots/UI dumps for each app state, test
   classification and next allowed actions, then grow `data/outcomes.jsonl`
   into an observed pack config for simulation and strategy tuning.

## Step 2 Refactor Plan

Status: implemented for the current Android and `device-open-pack` surface.
`rips_ai/android_state.py` owns Shizuku/device-state command helpers,
`rips_ai/evidence.py` owns screenshot capture and PNG validation,
`rips_ai/open_flow.py` owns gesture and flow construction, and `rips_ai/device.py`
remains as a compatibility re-export for older imports. `rips_ai/cli.py` now
keeps command parsing, output formatting, and exit-code handling.

The refactor should happen before adding much more live automation. Keep the
CLI commands stable, move behavior behind smaller modules, and test each move
before changing behavior.

1. Create an Android state module.
   Move Shizuku foreground checks, wake/keyguard checks, UI dump parsing, and
   compact state labels into `rips_ai/android_state.py`. This module should not
   know about pack economics or session mutation.

2. Create an evidence module.
   Move screenshot capture, PNG validation, blank-frame detection, OCR evidence
   files, and run manifests into `rips_ai/evidence.py`. The fast controller can
   call this only when it needs proof or OCR input.

3. Create a pack-opening flow module.
   Move gesture loading, coordinate overrides, staged commands, fast-controller
   script generation, checkpoint names, and parser output into
   `rips_ai/open_flow.py`. This module should return planned actions and
   observed states, not print user-facing text.

4. Keep session decisions in the session layer.
   Leave bank, pending pack, vault, ledger, and reconciliation mutations in
   `rips_ai/session.py`, `rips_ai/ledger.py`, and `rips_ai/vault.py`. The opener
   should ask these modules what can be committed instead of editing tracker
   state directly.

5. Thin the CLI.
   `rips_ai/cli.py` should parse arguments, call the smaller modules, format
   output, and return exit codes. It should stop containing long Android shell
   builders or multi-stage business logic.

6. Migrate one command path at a time.
   Start with `device-open-pack --dry-run`, then staged `tap-buy`, then
   `finish-open`, then the fast controller. After each move, run the existing
   CLI tests before changing the next path.

7. Add boundaries to tests.
   Unit-test module functions without Shizuku, mock Shizuku only at the Android
   boundary, and keep CLI tests focused on command output plus session mutation.

8. Acceptance criteria.
   The refactor is done when existing command output stays compatible, the test
   suite passes, `cli.py` no longer owns Android control details, and adding a
   new app state does not require editing unrelated session or ledger code.

## Important Assumption

`config/packs.example.json` is fake demo data. Replace it with observed outcomes before using the recommendation output as anything more than a test.
