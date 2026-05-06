# Next Steps

## 1. Real-world Product Name label testing

Use a real Click & Drop CSV with long Product Name values.

Check:

- how many characters show on the Royal Mail label
- how many lines show before text is visually cut
- whether the current 95-character warning limit is too high or too low
- whether default shortening rules need to be stronger

Possible future improvements:

- saved presets for lots
- more default shortening rules
- stronger abbreviation mode
- per-lot Product Name limits

## 2. Improve Product Name rules UX

Current rules are editable text.

Potential improvements:

- save rule presets per lot
- show before/after side by side
- highlight rows fixed by rules
- show original length vs optimized length
- add a reset-to-default-rules button

## 3. Metrics polish

Potential improvements:

- add daily summary cards
- add error/success rates
- add email sent counts by lot
- add tracking labels found vs rows
- add Product Name over-limit count to metrics

## 4. Email polish

Potential improvements:

- add a final review card before sending
- log selected subjects
- add CC/BCC configuration
- add warehouse email as sender once tested
- move recipient mapping into config instead of hard-coded app values

## 5. Etsy API integration

Blocked until Etsy approves/activates API key.

Once approved:

1. Generate OAuth URL.
2. Obtain access and refresh tokens.
3. Fetch paid/unshipped orders.
4. Generate Etsy review CSV.
5. Generate DPL input CSV.
6. Compare against manual Etsy export before trusting automation.

Later:

- send tracking back to Etsy after labels are generated
- mark orders dispatched
- let Etsy notify customers

## 6. Inbox automation

Future idea for stores without API access:

- warehouse email receives order CSV attachments
- app reads inbox
- detects new CSV
- imports attachment automatically
- formats Click & Drop CSV

This should be done after the current manual tabbed workflow is stable.
