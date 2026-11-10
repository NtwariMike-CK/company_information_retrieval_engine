import re, unicodedata
from collections import Counter

PAGE_NO = re.compile(r"^\s*(page\s*)?\d+(\s*(of|/)\s*\d+)?\s*$", re.I)


def clean_pages(pages, cfg, file_type: str, detector=None):
    """Returns (cleaned_pages, eda_stats). EDA stats are stored on the processing job."""
    chars_in = sum(len(t) for _, t in pages)
    stats = {"pages": len(pages), "chars_in": chars_in,
             "empty_pages": sum(1 for _, t in pages if not t.strip()), "header_footer_lines_removed": 0}

    texts = []
    for _, t in pages:
        if cfg.normalize_unicode:
            t = unicodedata.normalize("NFKC", t)
            # Kinyarwanda relies on the apostrophe (n'ubwo, y'abo, w'u): make every variant the same character
            t = t.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'").replace("\u00b4", "'").replace("`", "'")
        t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t).replace("\r\n", "\n").replace("\r", "\n")
        texts.append(t)

    if cfg.remove_headers_footers and len(texts) >= 3:
        counts = Counter()
        for t in texts:
            for line in {re.sub(r"\d+", "#", l.strip()) for l in t.split("\n") if l.strip()}:
                counts[line] += 1
        repeated = {l for l, c in counts.items() if c >= max(3, 0.6 * len(texts)) and len(l) < 100}
        new = []
        for t in texts:
            kept = []
            for l in t.split("\n"):
                if re.sub(r"\d+", "#", l.strip()) in repeated or PAGE_NO.match(l):
                    stats["header_footer_lines_removed"] += 1
                else:
                    kept.append(l)
            new.append("\n".join(kept))
        texts = new

    out = []
    for t in texts:
        if cfg.fix_hyphenation:
            t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)
        if cfg.merge_soft_wraps and file_type == "pdf":
            t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)
        if cfg.collapse_whitespace:
            t = re.sub(r"[ \t]+", " ", t)
            t = re.sub(r" ?\n ?", "\n", t)
            t = re.sub(r"\n{3,}", "\n\n", t)
        out.append(t.strip())

    paras_total = dup = 0
    seen = set()
    final = []
    for (n, _), t in zip(pages, out):
        kept = []
        for para in t.split("\n\n"):          # always measure duplicates (EDA); drop only if configured
            key = para.strip().lower()
            if len(key) > 40:
                paras_total += 1
                if key in seen:
                    dup += 1
                    if cfg.drop_duplicate_paragraphs:
                        continue
                seen.add(key)
            kept.append(para)
        t = "\n\n".join(kept)
        final.append((n, t))
    if detector is not None:
        dist: dict[str, int] = {}
        for _, t in final:
            for k, v in detector.distribution(t).items():
                dist[k] = dist.get(k, 0) + v
        stats["paragraphs_by_language"] = dist
    words = sum(len(t.split()) for _, t in final)
    stats.update({"chars_out": sum(len(t) for _, t in final), "words": words,
                  "avg_words_per_page": round(words / max(1, len(final)), 1),
                  "duplicate_paragraph_ratio": round(dup / paras_total, 3) if paras_total else 0.0})
    return final, stats
