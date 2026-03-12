# DPL Formatter

**DPL Formatter** is a lightweight operational automation tool that
converts warehouse order exports into **Royal Mail Click & Drop--ready
shipment files**.

The application eliminates manual shipping classification and formatting
by automatically determining the correct shipment type and producing a
clean CSV file ready for Click & Drop import.

This project is part of a broader portfolio of **automation and
infrastructure systems designed to improve operational reliability in
e-commerce environments.**

------------------------------------------------------------------------

# Overview

In warehouse environments handling hundreds of daily orders, preparing
shipment imports for Royal Mail Click & Drop typically requires:

-   manual classification of shipment type\
-   manual modification of order references\
-   handling multi-product orders\
-   detecting tracked vs untracked shipments\
-   ensuring formatting compatibility with Click & Drop

DPL Formatter automates this process using deterministic rule-based
processing.

The application allows staff to:

1.  Upload a standard order export file\
2.  Automatically classify each order for shipping\
3.  Review a preview of the processed output\
4.  Download a Click & Drop compatible CSV

The system removes repetitive manual work from the shipping workflow and
ensures consistent formatting.

------------------------------------------------------------------------

# Architecture

The application follows a deterministic transformation pipeline
consisting of three layers.

### Input Layer

Responsible for ingesting warehouse export files and validating their
structure.

Supported formats:

-   CSV
-   XLSX
-   XLS

The system verifies that required columns exist before processing
begins.

------------------------------------------------------------------------

### Processing Layer

The processing engine performs rule-based classification and
transformation.

Core processing tasks:

-   product quantity detection\
-   shipment classification\
-   tracking marker detection\
-   product name formatting\
-   order reference transformation

The system applies deterministic rules to ensure predictable outputs.

------------------------------------------------------------------------

### Output Layer

The output layer generates files compatible with Royal Mail Click &
Drop.

Outputs include:

-   Click & Drop compatible CSV
-   Excel file for verification
-   summary metrics dashboard

Each processed order produces exactly one output row.

------------------------------------------------------------------------

# Key Features

### Automatic Shipping Classification

Orders are automatically classified into one of four shipment types.

  Type              Description
  ----------------- --------------------------
  **LBT**           Letterbox small shipment
  **Parcel**        Standard parcel
  **Track24**       Tracked small shipment
  **TrackParcel**   Tracked parcel shipment

Classification uses product rules and tracking detection.

------------------------------------------------------------------------

### Multi-Product Detection

Orders containing multiple products are detected automatically.

Products are counted using comma-separated product strings in the
export:

TSHIRT-ABC-M-X1\
TSHIRT-ABC-M-X1, TSHIRT-DEF-L-X1

Product count is calculated using:

product_count = commas + 1

This ensures multi-item orders are classified correctly.

------------------------------------------------------------------------

### Tracking Detection

Tracking markers are detected from **auxiliary columns in the same
row**, rather than the primary order fields.

Supported tracking keywords:

tracked\
tracked 24\
track24\
track 24

This reflects how the warehouse export embeds shipping indicators.

------------------------------------------------------------------------

### Click & Drop Compatible Output

The generated CSV contains the columns required by Royal Mail Click &
Drop:

order reference\
Name\
Address 1\
Address 2\
City\
Postcode\
Product Name

The order reference is automatically suffixed with the detected shipment
type:

12345.Track24\
12346.LBT\
12347.Parcel

This allows the file to be imported directly into Click & Drop without
modification.

------------------------------------------------------------------------

# Shipping Classification Rules

The system determines shipment type using deterministic rules.

  LBT Eligible   Tracked   Result
  -------------- --------- -------------
  Yes            No        LBT
  Yes            Yes       Track24
  No             No        Parcel
  No             Yes       TrackParcel

### LBT Eligibility

A product qualifies as LBT if:

-   it contains a T-shirt identifier
-   it is not a large size
-   it contains only one product

Large sizes include:

3XL\
4XL\
5XL\
XXXL\
XXXXL\
XXXXXL

------------------------------------------------------------------------

# Example Workflow

1.  Export orders from the warehouse system\
2.  Upload the file to DPL Formatter\
3.  The system processes each row automatically\
4.  Review the preview table\
5.  Download the generated Click & Drop CSV

Typical processing time for files under **400 rows** is near-instant.

------------------------------------------------------------------------

# Data Processing Guarantees

The system uses deterministic rule-based processing.

Properties of the transformation pipeline:

-   no probabilistic logic
-   no external dependencies during classification
-   one input row produces exactly one output row
-   product quantities derived explicitly from comma separators

This ensures reproducible and predictable outputs.

------------------------------------------------------------------------

# Running the Application

Install dependencies:

pip install -r requirements.txt

Run locally:

streamlit run app.py

------------------------------------------------------------------------

# Repository Structure

dpl-formatter ├── app.py ├── requirements.txt ├── README.md └──
.gitignore

------------------------------------------------------------------------

# Design Philosophy

The system was designed with the same principles used in larger
automation systems:

-   deterministic processing
-   operational reliability
-   minimal user friction
-   predictable outputs

Even small operational tools can remove significant manual workload when
designed with clear rule-based logic.

------------------------------------------------------------------------

# Future Evolution

Although currently deployed as a lightweight operational tool, the
system could evolve into:

-   automated order ingestion pipelines
-   direct Click & Drop API integration
-   shipping rule optimisation
-   integration with warehouse management systems

This project represents a practical example of converting operational
workflows into deterministic automation systems.

------------------------------------------------------------------------

# License

Internal operational tool --- repository provided for documentation and
demonstration purposes.
