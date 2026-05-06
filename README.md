# DPL Formatter

DPL Formatter is a Streamlit operations tool for preparing warehouse order files for Royal Mail Click & Drop, adding tracking numbers back from Royal Mail label PDFs, and emailing fulfilment outputs to the correct recipients.

The daily workflow is now one tabbed process:

1. Orders
2. Labels & Tracking
3. Email / Finish

The app keeps uploaded order files and label PDFs in session state so the user can move between tabs without re-uploading files.

## Current production workflow

### 1. Orders tab

Upload the original CSV or Excel order file.

The app:

- validates required columns
- classifies each order as LBT, Parcel, Track24, or TrackParcel
- appends the shipping category to the order reference
- formats the Product Name field for Click & Drop
- checks Product Name length
- applies optional Product Name shortening rules
- generates Click & Drop CSV and Excel outputs

Important Product Name behavior:

- Product Name warning limit defaults to 95 characters.
- Spaces and line breaks count as characters.
- The app shows rows over the limit.
- Shortening rules are editable in the UI.
- Shortening rules only affect downloads when the checkbox is enabled.
- The CSV output only uses Product Name.
- Extended customs description is not currently used.

### 2. Labels & Tracking tab

After the user creates labels manually in Royal Mail Click & Drop, they return to the app and upload the labels PDF.

The app:

- remembers the original order file from the Orders tab
- extracts tracking numbers from the labels PDF
- verifies each tracking label against name and postcode
- supports skipping PDF pages with no tracking number
- adds a Tracking column to the original order file
- generates tracking CSV and Excel outputs

Skip-pages behavior:

- unchecked: strict mode, every PDF page must contain a tracking number
- checked: pages without tracking are skipped
- the app checks that tracking labels found equals order rows

### 3. Email / Finish tab

After tracking is generated, the app can send separate emails:

- Tracking CSV recipient is selected by lot.
- Labels PDF recipient is fixed.
- A confirmation checkbox is required before sending.

Current fixed recipients:

- Labels PDF: operationsinkstitch@gmail.com
- Lot X tracking CSV: info@inkstitch.co.uk
- DPL lot tracking CSV: teefusion786@gmail.com

The sender is configured through Streamlit secrets.

## Advanced tools

The old separate workflows are still available under Advanced tools:

- Formatting only
- Add tracking only

Daily use should use the tabbed workflow.

## Repository structure

dpl-formatter/
  app.py
  core/
    classification.py
    config.py
    email_sender.py
    file_io.py
    normalization.py
    tracking.py
    transform.py
  tests/
    test_classification.py
    test_email_sender.py
    test_tracking.py
    test_transform.py
  utils/
    metrics_logger.py
  docs/
  requirements.txt
  .github/workflows/ci.yml

## Local development

Create and activate a virtual environment:

    python -m venv venv
    .\venv\Scripts\Activate.ps1

Install dependencies:

    pip install -r requirements.txt

Run the app:

    streamlit run app.py

Run tests:

    python -m pytest
    python -m compileall .

## Required input columns

The formatting workflow expects:

- order reference
- product
- name
- address 1
- address 2
- city
- postcode

The tracking workflow requires at least:

- name
- postcode

## Secrets

Local secrets live in:

    .streamlit/secrets.toml

Hosted Streamlit secrets are configured in Streamlit Community Cloud.

Never commit real secrets.

See:

    docs/SECRETS_AND_DEPLOYMENT.md

## Current state and next steps

Read these files before continuing development:

- docs/CURRENT_STATE.md
- docs/NEXT_STEPS.md
- docs/RUNBOOK.md
- docs/DEVELOPMENT_LOG.md
