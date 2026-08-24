# Android Flow From Sample Recording

Source recording: `Screen_Recording_20260817_060907_Rips.mp4`

Screen size in the sample: `1080x2340` portrait.

## Observed States

1. `pack_carousel`
   - Shows category, cash bank, centered pack, min value, max pull, pack style, and the orange buy button.
   - Example: `Pokemon Starter Pack`, `Buy for $1`.
   - The bank chip can briefly show a transaction overlay underneath it, so OCR reads only the tight top chip region.

2. `pack_style_sheet`
   - Shows `Estimated Payout Odds`, `Normal`/`High`, and `Apply`.
   - Odds are shown as real-time estimates and should be logged as observations, not treated as fixed truth.

3. `pack_picker`
   - Shows `Tap to select a pack to open`.
   - Tap the centered pack after this state appears.
   - Do not use this center tap on the main pack carousel; it can open the
     `What's inside` carousel instead of buying/opening.

4. `pack_slice`
   - The selected pack fills the screen.
   - Use a full-width left-to-right or right-to-left horizontal swipe across
     the pack. A short swipe can leave the pack unopened.
   - Follow with a second faster full-width horizontal swipe about `0.35s`
     later to spin/reveal the card.

5. `reveal_animation`
   - Fireworks/card spin.
   - The quick follow-up swipe can speed up reveal, but no decision is made here.

6. `card_result`
   - Shows the revealed card, large value, card name, `Sell`, and `Vault`.
   - This is the main decision state.
   - Read `revealed_card_value`, compare it to the pack cost, then choose:
     - `vault` if card value is greater than the pack cost.
     - `sell` otherwise to preserve bank liquidity.

7. `buyback_sheet`
   - Appears after choosing Sell.
   - Shows `Accept Buyback Offer`, the buyback amount, and `Accept`.
   - Accept only if the offer matches the intended sell amount.

8. `collection`
   - Shows `My Collection` and visible card values.
   - Use this as a periodic cross-check. The live advisor should primarily maintain vault value from its own decisions.
   - The gallery-style vault needs a long-press appraisal loop: long-press one
     visible card, read/write down its appraised value, close the appraisal,
     then repeat for each visible card and scroll to the next gallery page.

## Calibrated Files

- `config/screen_regions.example.json`: OCR crop regions for the sample layout.
- `config/rips_android_flow.json`: screen states and gesture coordinates from the recording.

## Sample Commands

Read a result screen and decide against a known vault:

```bash
python -m rips_ai advise-screen analysis_frames/time_020.jpg --state result --pack-price 1.00
```

Read pack-screen bank and check the bank floor before a buy:

```bash
python -m rips_ai advise-screen analysis_frames/time_001.jpg --state pack --pack-price 1 --min-bank 10
```

Use the live recommender for tier choice: it stays on `$1` packs until the
configured `$2.50` unlock bank, default `$15.00`, then falls back to `$1` if
bank drops below that threshold.

Read a buyback sheet and accept only if the amount matches:

```bash
python -m rips_ai advise-screen analysis_frames/time_022.jpg --state buyback --expected-sell 2.50
```

Track a real live run from the current app values:

```bash
python -m rips_ai session-start --bank 14 --vault 0 --min-bank 10 --force
python -m rips_ai session-recommend
python -m rips_ai session-buy --pack two_fifty --purchase-confirmed
python -m rips_ai session-result --image analysis_frames/time_020.jpg --rarity-hint "blue flashes"
python -m rips_ai session-buyback --image analysis_frames/time_022.jpg --commit
```

Short screenshot workflow:

```bash
python -m rips_ai session-screen analysis_frames/time_001.jpg --pack two_fifty
python -m rips_ai session-screen analysis_frames/time_001.jpg --pack two_fifty --commit --purchase-confirmed
python -m rips_ai session-screen analysis_frames/time_020.jpg --rarity-hint "blue flashes"
python -m rips_ai session-screen analysis_frames/time_022.jpg --commit
```

Pack-screen `--commit` requires `--purchase-confirmed`; this keeps screenshot
tests and stale pack screens from deducting bank or creating a pending pack
before the app has accepted the buy/open step.

`session-buyback` only changes tracked bank when `--commit` is supplied. This keeps the tracker from moving forward before the app action is actually accepted. Committed outcomes are logged to `data/outcomes.jsonl` by default.

Live capture path:

```bash
python -m rips_ai device-capture
python -m rips_ai device-advise --state pack --pack-price 2.50 --min-bank 10
python -m rips_ai device-advise --state result --pack-price 1.00
python -m rips_ai device-advise --state buyback --expected-sell 0.30
```

Live open path:

```bash
python -m rips_ai device-open-pack --pack one_dollar --confirmed-buy-screen
```

Use this only when the main pack buy screen is visible. It taps the lower
orange buy button, spins the post-buy picker carousel once, taps the centered
pack, performs the calibrated long slice plus fast follow-up swipe, updates the
session to pending, and returns to Codex unless `--stay-in-rips` is supplied.

Bank verification after a draw:

```bash
python -m rips_ai session-bank-check --bank 11
python -m rips_ai session-bank-check --image data/latest_screen.png
python -m rips_ai session-bank-check --bank 11 --source "visible app bank after draw" --commit
```

Use this after pack result resolution, sell/buyback, vault, or returning to the
buy screen. It prints tracked bank, observed bank, delta, and pending state.
Only use `--commit` after the visible bank is trusted.

Vault gallery appraisal:

```bash
python -m rips_ai device-vault-gallery-plan
python -m rips_ai device-vault-gallery-plan --emit shell
python -m rips_ai session-vault-audit --card-values 1.00 2.50 5.40 --commit
```

The current `vault_gallery` config is a placeholder. Before executing a future
Shizuku appraisal loop, calibrate these parameters from a real gallery screen:

1. `first_card_center`: center of the top-left visible card.
2. `columns` and `rows`: visible card grid dimensions before scrolling.
3. `x_step` and `y_step`: distance between adjacent card centers.
4. `pages`: number of gallery screens needed to cover all cards.
5. `long_press_ms`: duration needed to open appraisal/details.
6. `between_cards_ms`: minimum close/wait time before the next card.
7. `vault_gallery_scroll_next`: swipe from one gallery page to the next.
8. Appraisal value OCR region: crop box around the value shown after long press.

Later implementation should be a state machine, not blind looping: verify the
vault gallery is visible, long-press one card, verify the appraisal/detail sheet
is open, read the value, close it, confirm the gallery returned, then continue.
