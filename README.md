# Office PDF Signer

Minimal Windows desktop app for viewing PDFs, adding short text, placing dates, and applying a simple visible signature.

## Why This Project Exists

This project was built around a very practical office workflow:

- open a PDF quickly
- read it comfortably
- add a name or short text
- place a date
- apply a visible signature
- save the result and move on

The main motivation was to avoid the friction of larger PDF tools such as Adobe Acrobat for simple day-to-day work. In that workflow, the full product often adds overhead that is not useful here:

- repeated login requirements
- forced account switching between computers
- many advanced functions that are rarely or never used
- too much interface complexity for a simple job

The goal of this app is not to be a full PDF editor. The goal is to do a small number of essential tasks well, with as little ceremony as possible.

## Design Intent

The app is intentionally built around a few principles:

- lightweight viewing first
- simple annotation instead of complex document editing
- visible signatures rather than advanced certificate workflows
- local desktop use on Windows without cloud dependence
- fast repeat use for office documents

## Current Features

- Open an existing PDF
- Continuous page viewing with thumbnails
- Zoom in, zoom out, fit width, fit height, and zoom percent
- Add short text such as names and titles
- Insert today's date
- Place a visible signature image
- Reuse a saved signature or choose a new one
- Move, edit, resize, or delete annotations
- Save as a new annotated PDF
- Remember the last opened PDF and last PDF directory

## What This App Is Not

- not a full PDF editor
- not a cloud signing platform
- not a login-based document service
- not a digital certificate signing tool
- not a replacement for every Acrobat feature

## Tech Stack

- Python
- PySide6
- PyMuPDF

## Project Layout

```text
office-pdf-signer/
  main.py
  requirements.txt
  src/office_pdf_signer/
    app.py
    ui/
    viewer/
    annotations/
    services/
```

## Run

```bash
python main.py
```
