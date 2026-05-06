# DPL Formatter Runbook

## Daily fulfilment run

### Step 1 - Orders

1. Open the app.
2. Go to 1. Orders.
3. Upload the order CSV/Excel file.
4. Check summary counts:
   - Orders
   - Products
   - LBT
   - Parcel
   - Track24
   - TrackParcel
5. Review Product Name safety check.
6. If rows are over the limit:
   - open Product shortening rules
   - adjust rules if needed
   - tick Use these shortening rules for downloads
7. Download Click & Drop CSV.
8. Download Excel for checking if needed.

### Step 2 - Royal Mail Click & Drop

1. Upload the Click & Drop CSV into Royal Mail.
2. Generate labels manually.
3. Download labels PDF.

### Step 3 - Labels & Tracking

1. Return to the app.
2. Go to 2. Labels & Tracking.
3. Confirm remembered order file is correct.
4. Upload Royal Mail labels PDF.
5. Use Skip PDF pages with no tracking number only if labels contain extra pages without tracking numbers.
6. Confirm Quick Check:
   - order rows remembered
   - label pages / tracking labels found
7. Click Add Tracking to remembered orders.
8. Download Tracking CSV.
9. Download Tracking Excel if needed.

### Step 4 - Email / Finish

1. Go to 3. Email / Finish.
2. Select tracking lot:
   - Lot X
   - DPL lot
3. Confirm recipients:
   - tracking CSV recipient
   - labels PDF recipient
4. Review email subjects and bodies.
5. Tick confirmation checkbox.
6. Click Send separate emails.

## Troubleshooting

### Product Name is too long

Use Product shortening rules.

Default examples:

- TSHIRT => TS
- T-SHIRT => TS
- T SHIRT => TS
- LIGHT-BLUE => LTBLUE
- LIGHT BLUE => LTBLUE
- ROYAL BLUE => ROYBLU
- FRONT => F
- BACK => B
- FR+BK => FB
- BLACK => BLK
- WHITE => WHT

### Labels PDF has more pages than order rows

If some pages have no tracking number, tick:

    Skip PDF pages with no tracking number

The app will count only pages with tracking numbers.

### Tracking verification fails

Check:

- order file row order matches label order
- name appears on label
- postcode appears on label
- labels PDF is the correct one
- skip-pages checkbox is set correctly

### Email section does not appear

Tracking must be generated first.

### Email setup required appears

SMTP settings are missing from Streamlit secrets.

See:

    docs/SECRETS_AND_DEPLOYMENT.md

### Admin Metrics says no data

Check local .streamlit/secrets.toml has:

- METRICS_SHEET_ID
- METRICS_WORKSHEET
- [google_service_account]

Also confirm the Google Sheet is shared with the service account email.
