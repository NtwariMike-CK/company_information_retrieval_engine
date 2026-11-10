"""Convert the Markdown used in this project's documents to a clean PDF (headings, paragraphs, lists, tables, code blocks,
block quotes, images). Usage:  python docs/report/md_to_pdf.py input.md output.pdf "Footer title"
Images are resolved relative to the Markdown file; a missing image becomes a yellow placeholder box."""
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, KeepTogether, ListFlowable, ListItem, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

BLUE, DARK, GREY = colors.HexColor("#1d4ed8"), colors.HexColor("#0b1220"), colors.HexColor("#475569")
SUBS = {"\u2192": "->", "\u2190": "<-", "\u2265": ">=", "\u2264": "<=", "\u2713": "[ok]", "\u2717": "[x]", "\u2014": "-", "\u00a0": " ", "\u2260": "!=", "\u00b1": "+/-",
        "\u2248": "~", "\u2022": "-", "\u03bc": "u", "\u2212": "-", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2013": "-"}


def clean(t: str) -> str:
    for a, b in SUBS.items():
        t = t.replace(a, b)
    return t.encode("cp1252", "ignore").decode("cp1252")


def inline(t: str) -> str:
    t = escape(clean(t))
    t = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8" backColor="#e2e8f0">\1</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<font color="#1d4ed8">\1</font>', t)
    return t


class Numbered(canvas.Canvas):
    footer = ""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._s = []

    def showPage(self):
        self._s.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        for st in self._s:
            self.__dict__.update(st)
            self.setFont("Helvetica", 7)
            self.setFillColor(GREY)
            self.drawString(1.8 * cm, 0.9 * cm, self.footer)
            self.drawRightString(A4[0] - 1.8 * cm, 0.9 * cm, f"Page {self._pageNumber} of {len(self._s)}")
            super().showPage()
        super().save()


def convert(src: Path, out: Path, footer: str = ""):
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=9.2, leading=12.4, textColor=DARK, spaceAfter=4)
    st = {"b": base,
          "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=14.5, leading=18, textColor=BLUE, spaceBefore=12, spaceAfter=5),
          "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=BLUE, spaceBefore=9, spaceAfter=3),
          "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=6, spaceAfter=2),
          "title": ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=BLUE, spaceAfter=6),
          "cell": ParagraphStyle("c", parent=base, fontSize=7.8, leading=9.6, spaceAfter=0),
          "head": ParagraphStyle("hd", parent=base, fontName="Helvetica-Bold", fontSize=7.8, leading=9.6, textColor=colors.white, spaceAfter=0),
          "quote": ParagraphStyle("q", parent=base, leftIndent=10, textColor=GREY, borderPadding=3),
          "code": ParagraphStyle("cd", fontName="Courier", fontSize=7.4, leading=9, textColor=DARK)}
    W = A4[0] - 3.6 * cm
    lines = src.read_text(encoding="utf-8").splitlines()
    el, i, first = [], 0, True
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            code, i = [], i + 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(clean(lines[i])[:140]); i += 1
            box = Table([[Preformatted("\n".join(code), st["code"])]], colWidths=[W])
            box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")), ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            el += [box, Spacer(1, 5)]; i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            lvl, txt = len(m.group(1)), m.group(2)
            if lvl == 1 and first:
                el.append(Paragraph(inline(txt), st["title"])); first = False
            else:
                el.append(Paragraph(inline(txt), st[f"h{min(lvl - 1, 3)}" if lvl > 1 else "h1"]))
            i += 1; continue
        if ln.strip() in ("---", "***"):
            el.append(Spacer(1, 4)); i += 1; continue
        im = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", ln.strip())
        if im:
            p = (src.parent / im.group(2)).resolve()
            if p.exists():
                iw, ih = ImageReader(str(p)).getSize()
                w = min(W, 15 * cm); h = w * ih / iw
                if h > 12 * cm:
                    w, h = w * 12 * cm / h, 12 * cm
                el.append(KeepTogether([Image(str(p), width=w, height=h), Paragraph(f"<font size=8 color='#475569'>{inline(im.group(1))}</font>", st["b"])]))
            else:
                box = Table([[Paragraph(f"<b>[SCREENSHOT TO ADD]</b> {inline(im.group(1))}<br/><font size=7>expected file: {escape(im.group(2))}</font>", st["cell"])]], colWidths=[W])
                box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fde68a")), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b45309")), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
                el += [box, Spacer(1, 4)]
            i += 1; continue
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                if not re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            n = max(len(r) for r in rows)
            rows = [r + [""] * (n - len(r)) for r in rows]
            wts = [min(48, max(11, sum(len(r[c]) for r in rows) / len(rows))) for c in range(n)]
            widths = [W * w / sum(wts) for w in wts]
            data = [[Paragraph(inline(c), st["head"] if ri == 0 else st["cell"]) for c in r] for ri, r in enumerate(rows)]
            t = Table(data, colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
            el += [t, Spacer(1, 6)]; continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", ln):
            items = []
            ordered = bool(re.match(r"^\s*\d+\.", ln))
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                indent = len(lines[i]) - len(lines[i].lstrip())
                items.append((indent, re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))); i += 1
            flow = [ListItem(Paragraph(inline(t), base), leftIndent=14 + 12 * (ind // 2)) for ind, t in items]
            el.append(ListFlowable(flow, bulletType="1" if ordered else "bullet", start=1 if ordered else None, bulletFontSize=8, leftIndent=12, bulletColor=BLUE))
            el.append(Spacer(1, 3)); continue
        if ln.startswith(">"):
            q = []
            while i < len(lines) and lines[i].startswith(">"):
                q.append(lines[i].lstrip("> ").rstrip()); i += 1
            box = Table([[Paragraph(inline(" ".join(q)), st["quote"])]], colWidths=[W])
            box.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 2, BLUE), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff"))]))
            el += [box, Spacer(1, 4)]; continue
        if not ln.strip():
            i += 1; continue
        para = [ln.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,4}\s|```|\s*([-*]|\d+\.)\s+|\s*\||>|!\[)", lines[i]):
            para.append(lines[i].strip()); i += 1
        el.append(Paragraph(inline(" ".join(para)), base))
    Numbered.footer = footer
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.7 * cm, title=footer).build(el, canvasmaker=Numbered)


if __name__ == "__main__":
    a = sys.argv
    convert(Path(a[1]), Path(a[2]), a[3] if len(a) > 3 else "")
    from pypdf import PdfReader
    print(f"{a[2]}: {len(PdfReader(a[2]).pages)} pages")
