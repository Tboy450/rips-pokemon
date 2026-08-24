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

The next phase should make the advisor more screen-aware without letting it
silently spend money or rewrite tracked state. The main theme is to turn the
current manual checkpoints into small verified loops: identify the screen,
perform exactly one allowed action, read the result, compare it to the session
tracker, then require confirmation before committing anything risky.

1. Make Android screenshot readback reliable.
   `device-capture` needs a transfer path that consistently produces a locally
   readable, CRC-valid PNG. The Shizuku wrapper can corrupt raw PNG streams, and
   chunked base64 readback has hung mid-file, so try a bounded text transfer
   with retries, per-chunk timeouts, and a final PNG validation step. When this
   is stable, every live command can capture before and after its gesture and
   store evidence under `data/` for debugging.

2. Add screen-state verification before every gesture.
   The program should distinguish the main pack carousel, `What's inside`
   carousel, post-buy pack picker, pack slice screen, reveal animation, card
   result screen, buyback sheet, vault gallery, and appraisal/detail sheet.
   A command should refuse to tap when the observed state does not match the
   requested action. This directly prevents the previous mistake where a center
   tap opened the wrong carousel.

3. Convert `device-open-pack` into a state-machine flow.
   Instead of one timed Shizuku shell string, split the live open into steps:
   launch or focus Rips, verify the main buy screen, tap the lower orange buy
   button, wait for the post-buy picker, use two fast long carousel spins in
   the same direction, select the centered pack, verify the slice screen, perform the long slice and fast
   follow-up swipe, then wait for the result screen. Each step should have a
   timeout, a visible-state check, and a clear recovery message.

4. Diagnose bank after each draw and resolution.
   `session-bank-check` is the manual start. The next implementation should
   read the bank chip automatically after a buy, sell/buyback, vault action, and
   return to the buy screen. The command should report expected bank, observed
   bank, delta, pending pack state, and likely reason for the difference. It
   should not reconcile with `--commit` unless the visible bank was captured
   from a trusted screen.

5. Add a result-screen wait and decision loop.
   After opening a pack, the assistant should wait until the revealed card value
   is readable, run the sell/vault rule, and keep the session pending. When
   individual vault card values are known, compare the revealed card to the
   current highest vault card and only prepare Vault if it improves that best
   kept card. When slot values are unknown, fall back to the pack-cost rule. In
   both cases, the actual session commit should still happen only after the
   in-app action is confirmed.

6. Add a guarded buyback confirmation flow.
   The buyback sheet should be read before accepting. If the offer does not
   match the expected sell value, the assistant should stop and explain the
   mismatch. Once the value matches, a later guarded command can tap Accept and
   then run `session-bank-check` to confirm the bank increased by the expected
   amount before committing the sell.

7. Turn the vault gallery plan into a state-aware appraisal loop.
   `device-vault-gallery-plan` currently prints the long-press grid. The next
   version should verify the vault gallery, long-press one card, read the
   appraisal/detail value, close the detail sheet, confirm it returned to the
   gallery, and continue through every visible slot and page. Required
   calibration inputs are `first_card_center`, `x_step`, `y_step`, `columns`,
   `rows`, `pages`, `long_press_ms`, close/back behavior, scroll gesture, and
   the appraisal value OCR crop.

8. Reconcile tracked vault totals against gallery appraisals.
   After the gallery loop collects values, it should feed the total and card
   count into `session-vault-audit`. The audit should show tracked total,
   observed total, tracked count, observed count, value delta, and count delta.
   This becomes the correction mechanism when a previous Vault action was
   missed, double-counted, or appraised differently by the app later.

9. Improve OCR calibration and fallback parsing.
   Add per-region confidence checks, alternate crop boxes, and multiple OCR
   passes for the bank chip, card value, buyback value, and vault appraisal
   value. Keep manual override flags for every money value because screenshots
   and UI dumps will sometimes be wrong. Store raw OCR text with the audit event
   so incorrect reads can be diagnosed later.

10. Build a replayable screen fixture suite.
    Save representative screenshots for each app state and use them as tests:
    main pack carousel, `What's inside`, picker, slice, reveal, result, buyback,
    vault gallery, and appraisal detail. Tests should assert both
    classification and the next allowed action. This will make future gesture
    changes safer without needing Shizuku running.

11. Expand observed outcome logging.
    Every completed pull should append a ledger event with pack id, pack cost,
    card value, action, bank before/after, vault before/after, vault count,
    source method, and any OCR/manual notes. Once enough real pulls exist,
    export `data/packs.observed.json` and compare observed value distribution
    against the placeholder config.

12. Add bankroll policy experiments.
    The current tier rule is simple: stay on `$1` packs until the configured
    `$2.50` unlock bank. Later strategy code can compare policies such as
    stricter cash floors, different `$2.50` unlock thresholds, stop-loss
    limits, max packs per session, and vault-only profit targets. These should
    run in simulation first and only become live recommendations after enough
    observed data exists.

13. Add command dry-run and explain modes everywhere.
    Any command that can tap, commit, or reconcile should have a dry-run path
    that prints the exact action, expected screen, expected money change, and
    session mutation before doing it. This makes it easier to review the flow
    during Shizuku outages and prevents compacted sessions from guessing hidden
    state.

14. Improve handoff and recovery notes.
    Keep `docs/PROJECT_CONTEXT.md` updated with the last known real bank, vault
    total, vault card count, pending pack, foreground app assumption, and known
    Shizuku status. When automation stops mid-flow, the next session should be
    able to run `session-status`, `session-bank-check`, and
    `session-vault-audit` to recover before taking another app action.

## Important Assumption

`config/packs.example.json` is fake demo data. Replace it with observed outcomes before using the recommendation output as anything more than a test.
