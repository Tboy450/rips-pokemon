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

4. `pack_slice`
   - The selected pack fills the screen.
   - Use a left-to-right or right-to-left horizontal swipe across the pack.

5. `reveal_animation`
   - Fireworks/card spin.
   - A delayed swipe can speed up reveal, but no decision is made here.

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
python -m rips_ai session-buy --pack two_fifty
python -m rips_ai session-result --image analysis_frames/time_020.jpg --rarity-hint "blue flashes"
python -m rips_ai session-buyback --image analysis_frames/time_022.jpg --commit
```

Short screenshot workflow:

```bash
python -m rips_ai session-screen analysis_frames/time_001.jpg --pack two_fifty --commit
python -m rips_ai session-screen analysis_frames/time_020.jpg --rarity-hint "blue flashes"
python -m rips_ai session-screen analysis_frames/time_022.jpg --commit
```

`session-buyback` only changes tracked bank when `--commit` is supplied. This keeps the tracker from moving forward before the app action is actually accepted. Committed outcomes are logged to `data/outcomes.jsonl` by default.

Live capture path:

```bash
python -m rips_ai device-capture
python -m rips_ai device-advise --state pack --pack-price 2.50 --min-bank 10
python -m rips_ai device-advise --state result --pack-price 1.00
python -m rips_ai device-advise --state buyback --expected-sell 0.30
```
