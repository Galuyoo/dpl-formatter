# Etsy API Setup

Experimental workflow for generating daily Etsy order CSVs.

Goal:

1. Fetch paid/unshipped Etsy orders through the Etsy API.
2. Preview the data.
3. Download an Etsy review CSV.
4. Download a DPL input CSV.
5. Continue creating labels manually for now.

## Required values

From your Etsy developer app:

- Etsy API keystring / client ID
- Redirect URI
- Shop ID

Required read scope:

`transactions_r`

Later, for pushing tracking back to Etsy, we may need:

`transactions_w`

## Generate authorization URL

```powershell
python tools/etsy_oauth.py auth-url --client-id "YOUR_ETSY_KEYSTRING" --redirect-uri "YOUR_REDIRECT_URI" --scope "transactions_r"