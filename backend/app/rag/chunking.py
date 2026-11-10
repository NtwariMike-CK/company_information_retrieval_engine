"""Chunking strategies: parent_child | recursive | fixed. Sizes are in characters.
Language-aware mode keeps English and Kinyarwanda text in separate chunks (a chunk never mixes languages),
protects abbreviations / decimals / numbered lists from false sentence breaks, and keeps headings with their text."""
import re

SEPS = ("\n\n", "\n", ". ", "; ", ", ", " ")
DOT = "\u2024"   # placeholder for protected dots
ABBR = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|Eng|Hon|Nyak|No|Nos|Fig|vs|etc|St|Ltd|Inc|Co|Sr|Jr|ig|nk|n\.k|e\.g|i\.e)\.", re.I)
DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")
LIST_MARK = re.compile(r"(?m)^(\s*\d{1,3})\.(?=\s)")


def protect(text: str) -> str:
    text = ABBR.sub(lambda m: m.group(0)[:-1] + DOT, text)
    text = DECIMAL.sub(DOT, text)
    return LIST_MARK.sub(lambda m: m.group(1) + DOT, text)


def unprotect(text: str) -> str:
    return text.replace(DOT, ".")


def attach_headings(text: str) -> str:
    """A short line without sentence punctuation followed by a paragraph is a heading: glue it to what follows."""
    paras = re.split(r"\n\s*\n", text)
    out, i = [], 0
    while i < len(paras):
        p = paras[i].strip()
        is_heading = p and len(p) < 90 and "\n" not in p and not re.search(r"[.!?:;,]$", p)
        if is_heading and i + 1 < len(paras):
            out.append(p + "\n" + paras[i + 1].strip())
            i += 2
        else:
            out.append(p)
            i += 1
    return "\n\n".join(x for x in out if x)


def split_text(text: str, size: int, overlap: int = 0) -> list[str]:
    def rec(t: str, i: int) -> list[str]:
        if len(t) <= size:
            return [t]
        if i >= len(SEPS):
            return [t[k:k + size] for k in range(0, len(t), size)]
        sep, out, cur = SEPS[i], [], ""
        for part in t.split(sep):
            cand = part if not cur else cur + sep + part
            if len(cand) <= size:
                cur = cand
                continue
            if cur:
                out.append(cur)
            if len(part) > size:
                out.extend(rec(part, i + 1))
                cur = ""
            else:
                cur = part
        if cur:
            out.append(cur)
        return out

    pieces = [unprotect(p).strip() for p in rec(protect(text), 0) if p.strip()]
    if overlap > 0 and len(pieces) > 1:
        with_overlap = [pieces[0]]
        for prev, cur in zip(pieces, pieces[1:]):
            tail = prev[-overlap:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            with_overlap.append((tail + " " + cur).strip())
        pieces = with_overlap
    return pieces


def fixed_split(text: str, size: int, overlap: int) -> list[str]:
    step = max(1, size - overlap)
    return [text[i:i + size].strip() for i in range(0, len(text), step) if text[i:i + size].strip()]


def language_segments(text: str, detector) -> list[tuple[str | None, str]]:
    """Group consecutive paragraphs of the same language. Paragraphs whose language is unclear inherit the current one."""
    segs, buf, cur = [], [], None
    for p in (x for x in re.split(r"\n\s*\n", text) if x.strip()):
        lg = detector.detect(p) if detector else None
        if lg is not None and cur is not None and lg != cur:
            segs.append((cur, "\n\n".join(buf)))
            buf = []
        if lg is not None:
            cur = lg
        buf.append(p)
    if buf:
        segs.append((cur, "\n\n".join(buf)))
    return segs


def chunk_pages(pages, cfg, detector=None):
    """Returns (parents, children). parents: [{index, content, page, lang}], children: [{index, parent_index, content, page, lang}]."""
    parents, children = [], []
    for page_no, text in pages:
        if not text.strip():
            continue
        segments = language_segments(text, detector) if getattr(cfg, "language_aware", True) else [(None, text)]
        for lang, seg in segments:
            seg = attach_headings(seg) if getattr(cfg, "language_aware", True) else seg
            if cfg.strategy == "parent_child":
                for ptext in split_text(seg, cfg.parent_size, 0):
                    pi = len(parents)
                    parents.append({"index": pi, "content": ptext, "page": page_no, "lang": lang})
                    for ctext in split_text(ptext, cfg.child_size, cfg.overlap):
                        children.append({"index": len(children), "parent_index": pi, "content": ctext, "page": page_no, "lang": lang})
            else:
                pieces = fixed_split(seg, cfg.chunk_size, cfg.overlap) if cfg.strategy == "fixed" else split_text(seg, cfg.chunk_size, cfg.overlap)
                for c in pieces:
                    children.append({"index": len(children), "parent_index": None, "content": c, "page": page_no, "lang": lang})
    return parents, children
