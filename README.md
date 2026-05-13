# Office PDF Signer

Minimal Windows desktop app for viewing PDFs, adding short text, placing dates, and applying a simple visible signature.

## Version 1 Scope

- Open an existing PDF
- View pages with zoom
- Add short text such as names and titles
- Insert today's date
- Add a visible signature
- Move or delete placed items
- Save as a new PDF

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

## Next Steps

1. Build the main window and toolbar
2. Add a PDF viewer with page rendering
3. Add overlay models for text, date, and signature
4. Export overlays into a new PDF

## Run

```bash
python main.py
```
