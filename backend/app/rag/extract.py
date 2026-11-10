from pathlib import Path


class ExtractionError(Exception):
    pass


def extract_pages(path: str, file_type: str) -> list[tuple[int, str]]:
    """Return [(page_number, text)]. Non-paged formats return a single page 1."""
    p = Path(path)
    if file_type == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        if reader.is_encrypted:
            raise ExtractionError("PDF is password protected")
        pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    elif file_type == "docx":
        from docx import Document
        d = Document(str(p))
        parts = [para.text for para in d.paragraphs if para.text.strip()]
        for table in d.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        pages = [(1, "\n\n".join(parts))]
    elif file_type in ("txt", "md"):
        pages = [(1, p.read_text(encoding="utf-8", errors="replace"))]
    else:
        raise ExtractionError(f"unsupported file type: {file_type}")
    if sum(len(t.strip()) for _, t in pages) < 20:
        raise ExtractionError("no extractable text found (scanned or empty document?)")
    return pages
