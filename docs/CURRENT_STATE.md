# Current State

Last updated after the tabbed fulfilment UI and Product Name safety work.

## Main branch contains

- Foundation refactor into core/
- Tests for classification, transform, tracking, and email sending
- CI validation with pytest and compile checks
- One tabbed fulfilment workflow
- Product Name length warning and shortening rules
- Tracking PDF verification
- Optional skip-pages-without-tracking mode
- Email sending with fixed recipients by lot
- Email confirmation checkbox
- Google Sheets metrics logging
- Local Admin Metrics panel with fixed sheet read range
- Advanced fallback tools for formatting-only and tracking-only workflows

## Daily user flow

1. Open the app.
2. Use the Orders tab.
3. Upload order CSV/Excel.
4. Review Product Name safety check.
5. Apply shortening rules only if needed.
6. Download Click & Drop CSV.
7. Create labels manually in Royal Mail Click & Drop.
8. Return to Labels & Tracking tab.
9. Upload Royal Mail labels PDF.
10. Add Tracking.
11. Download tracking CSV/Excel.
12. Use Email / Finish tab to send tracking CSV and labels PDF.

## Product Name behavior

Current strategy:

- Keep only the Product Name column.
- Do not use Extended customs description for now.
- Product Name length warning limit defaults to 95.
- Spaces and line breaks count.
- Product Name is packed into label-friendly lines.
- Commas are preserved.
- Line breaks prefer safe separators.
- Shortening rules can be applied before download.
- Rules are editable from the UI.

Known limitation:

Royal Mail / Click & Drop label rendering may still visually cut long product text depending on label layout. The app warns and helps shorten, but physical label behavior still needs real-world checking.

## Tracking behavior

Current strategy:

- Extract tracking numbers from PDF pages.
- Verify row order by matching name and postcode.
- Default strict behavior requires every page to have tracking.
- Optional checkbox skips PDF pages without tracking.
- When skip mode is enabled, order row count must equal number of tracking labels found.

Known limitation:

The app still assumes tracking labels are in the same order as rows after skipped pages are removed.

## Email behavior

Current strategy:

- SMTP configured from Streamlit secrets.
- Sender configured by [email] secrets.
- Tracking CSV recipient is chosen by lot.
- Labels PDF recipient is fixed.
- Send button is disabled until confirmation checkbox is checked.
- Email success/failure is logged to metrics.

Current recipients:

- Labels PDF -> operationsinkstitch@gmail.com
- Lot X tracking CSV -> info@inkstitch.co.uk
- DPL lot tracking CSV -> teefusion786@gmail.com

## Metrics behavior

Current strategy:

- Events are logged to Google Sheets.
- Logger is fail-safe and should not break the app.
- Admin Metrics are visible locally.
- Admin Metrics read only the configured metric columns to avoid broken extra sheet columns.

Tracked fields include:

- workflow
- event name
- file name/type
- input rows
- order/product totals
- category counts
- tracking labels found
- skip-pages-without-tracking flag
- selected lot
- email recipients
- sent email item types
- success/error message

## Etsy API state

Etsy API work is paused.

Current status:

- Etsy developer app was created.
- Key was pending Etsy personal approval.
- Live API fetching is blocked until Etsy activates the key.
- Do not assume Etsy API fetch is production-ready.

Next Etsy step once approved:

1. Generate OAuth authorization URL.
2. Exchange code for access/refresh tokens.
3. Add Etsy secrets locally and to Streamlit if needed.
4. Fetch paid/unshipped orders.
5. Generate review CSV and DPL input CSV.
