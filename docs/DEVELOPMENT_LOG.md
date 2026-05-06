# Development Log

## Completed

### Foundation refactor

- Moved business logic from app.py into core/
- Added foundation tests
- Added CI validation
- Added PR checklist and safer .gitignore

### One-page fulfilment workflow

- Added full workflow in one app flow
- Remembered uploaded order file in session state
- Added tracking step on same page
- Added download buttons for tracking CSV/Excel

### Email workflow

- Added SMTP email sender
- Added fixed recipients
- Added lot-based tracking CSV recipient
- Added labels PDF recipient
- Added confirmation checkbox before send
- Added email sender tests

### Tracking improvements

- Added optional skip-pages-without-tracking mode
- Added tests for strict and skip behavior
- Quick Check compares rows to tracking labels found when skip mode is enabled

### Metrics improvements

- Extended metrics fields
- Added workflow/tracking/email metrics
- Fixed Admin Metrics local read range to avoid duplicate blank headers from messy Google Sheets

### Product Name safety

- Added Product Name warning limit
- Added over-limit table
- Added editable shortening rules
- Added checkbox to use rules for downloads
- Repacked shortened Product Name lines
- Preserved commas and safe line breaks

### Tabbed UI

- Converted daily workflow to tabs:
  - Orders
  - Labels & Tracking
  - Email / Finish
- Moved old separate workflows into Advanced tools

## Paused / not finished

### Etsy API

Paused because Etsy API key is pending Etsy approval.

### Product label physical layout

Still needs real label tests to confirm best Product Name limit and default rules.

### Inbox automation

Future idea, not started.
