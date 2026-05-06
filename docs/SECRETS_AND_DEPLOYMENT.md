# Secrets and Deployment

Do not commit real secrets.

## Local secrets

Local secrets file:

    .streamlit/secrets.toml

## Streamlit Community Cloud secrets

Hosted secrets are configured in:

    Streamlit app -> Settings -> Secrets

## Email secrets

For Gmail SMTP:

[email]
smtp_host = "smtp.gmail.com"
smtp_port = 587
username = "galuyoo.shopify@gmail.com"
password = "GOOGLE_APP_PASSWORD"
from_email = "galuyoo.shopify@gmail.com"
use_tls = true

Use a Google App Password, not the normal Gmail password.

## Metrics secrets

METRICS_SHEET_ID = "..."
METRICS_WORKSHEET = "events"

[google_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."

The Google Sheet must be shared with the service account client_email as Editor.

## Etsy secrets

Etsy is not production-ready yet.

Future shape may include:

[etsy]
api_key = "ETSY_KEYSTRING"
access_token = "ETSY_ACCESS_TOKEN"
refresh_token = "ETSY_REFRESH_TOKEN"
shop_id = "ETSY_SHOP_ID"

Do not add Etsy secrets until the API key is approved and live testing begins.

## Deployment checklist

Before merging to main:

    python -m pytest
    python -m compileall .

Manual checks:

- Orders tab works
- Product Name safety check works
- Click & Drop CSV downloads
- Labels & Tracking tab remembers order file
- Labels PDF upload works
- Tracking CSV downloads
- Email / Finish tab appears after tracking
- Email requires confirmation
- Admin Metrics loads locally
