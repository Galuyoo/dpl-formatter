![CI](https://github.com/Galuyoo/dpl-formatter/actions/workflows/ci.yml/badge.svg)


# DPL Formatter

**DPL Formatter** is a lightweight automation tool designed to convert
warehouse order exports into **Royal Mail Click & Drop compatible
shipment files**, and to automatically merge **tracking numbers back
into the original orders** after labels are generated.

The system removes repetitive manual formatting work in shipping
workflows by automatically classifying shipment types, generating a
Click & Drop import file, and later attaching tracking numbers to the
same orders dataset.

This project is part of a broader portfolio focused on **automation,
operational tooling, and infrastructure systems that improve reliability
in e‑commerce logistics environments**.

------------------------------------------------------------------------

# Complete Workflow

DPL Formatter supports the **full operational shipping workflow** used
in warehouse environments.

The process consists of two steps.

## 1. Formatting Orders for Click & Drop

Users upload a standard order export file.

The application:

-   validates the file
-   classifies shipment types
-   formats the dataset for Royal Mail Click & Drop
-   generates a clean CSV ready for label generation

This file can then be uploaded directly into **Royal Mail Click & Drop**
to generate shipping labels.

------------------------------------------------------------------------

## 2. Merging Tracking Codes Back Into Orders

After labels are generated, Click & Drop produces a **labels PDF** where
each page contains a shipping label and tracking number.

DPL Formatter allows users to:

1.  upload the original orders file
2.  upload the labels PDF
3.  automatically extract tracking numbers
4.  verify each order against its corresponding label page
5.  generate a new file containing a **Tracking column**

Verification ensures that each order row matches the correct label page
by checking:

-   recipient name
-   postcode

This guarantees that tracking numbers are applied to the correct
customers.

The resulting file can then be used to:

-   send tracking notifications to customers
-   upload tracking numbers to stores or marketplaces
-   maintain shipment records

------------------------------------------------------------------------

# Overview

In warehouse environments handling large volumes of daily orders,
preparing shipment imports for Royal Mail Click & Drop typically
requires:

-   manual shipment classification
-   modifying order references
-   detecting tracked shipments
-   handling multi-product orders
-   ensuring formatting compatibility

DPL Formatter automates this process using a **deterministic
transformation pipeline**.

Users can:

1.  Upload a standard order export file
2.  Automatically classify shipment type
3.  Preview processed results
4.  Download a Click & Drop compatible CSV

------------------------------------------------------------------------

# Tracking Code Extraction

The system can extract Royal Mail tracking numbers directly from label
PDFs.

Each label page contains a tracking barcode and associated tracking
number.

Example:

YT 1644 3183 1GB\
QM 8440 4148 7GB

During processing the system:

1.  reads the labels PDF
2.  extracts the tracking number from each page
3.  matches the page to the corresponding order row
4.  verifies name and postcode
5.  appends the tracking number to the dataset

Output column:

-   Tracking

------------------------------------------------------------------------

# Architecture

The application follows a simple **three‑layer processing
architecture**.

## Input Layer

Responsible for file ingestion and validation.

Supported formats:

-   CSV
-   XLSX
-   XLS

Before processing begins, the system validates that all required columns
exist in the uploaded file.

This prevents malformed files from entering the processing pipeline.

------------------------------------------------------------------------

## Processing Layer

The core processing engine applies **rule‑based classification and
transformation**.

Key operations include:

-   shipment classification
-   product quantity detection
-   tracking marker detection
-   product name formatting
-   order reference transformation

All rules are deterministic, ensuring predictable outputs for identical
inputs.

------------------------------------------------------------------------

## Output Layer

The system generates files compatible with Royal Mail Click & Drop.

Outputs include:

-   Click & Drop compatible CSV
-   Excel export for verification
-   summary processing metrics
-   orders file with merged **Tracking column**

Each input row produces **exactly one output row**, ensuring a clear
transformation pipeline.

------------------------------------------------------------------------

# Deployment

The application is deployed using **Streamlit**.

Local development:

streamlit run app.py

Production deployment can be handled through Streamlit Cloud or other
hosting platforms, allowing users to upload files directly through the
web interface.

------------------------------------------------------------------------

# Repository Structure

dpl-formatter\
├── app.py\
├── utils/\
│ └── metrics_logger.py\
├── requirements.txt\
├── README.md\
└── .gitignore

------------------------------------------------------------------------

# Local Development

Install dependencies:

```powershell
pip install -r requirements.txt
```

------------------------------------------------------------------------

# Future Improvements

Possible future developments include:

-   direct Click & Drop API integration
-   automated order ingestion pipelines
-   automated tracking updates to e‑commerce platforms
-   expanded shipping rule configuration
-   integration with warehouse management systems

------------------------------------------------------------------------

# License

Internal operational tool provided for documentation and demonstration
purposes.
