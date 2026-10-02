"""Local notice input parsing shared by the app and synthetic component demo."""

import io


def extract_pdf_text(file_bytes):
    """Use the app's existing text-PDF behavior; no OCR or service client."""
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    return "".join(page.extract_text() or "" for page in reader.pages)
