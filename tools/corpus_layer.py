#!/usr/bin/env python3
"""
corpus_layer.py — generate the machine-readable layer of the Morphysm corpus.

Imported and driven by build_shell.py; never run as a hand step. Everything under
corpus/, plus llms.txt / llms-full.txt and the root-site files, is regenerated from
source on every build. Nothing is hand-placed in the output.

Sources of truth (outside this repo, on the author's machine):
  CANON  -> the CANON -BOOKS folder: the three volumes + meta-doctrine
  MASSIV -> the morphysm_massiv corpus folder: doctrine texts + structured records
Override either with MORPHYSM_CANON_DIR / MORPHYSM_MASSIV_DIR.

The allowlist is tools/corpus_sources.tsv. Nothing outside it is ever published.

Permitted transformations: UTF-8 (NFC), LF line endings, trailing-whitespace removal,
and removal of the editorial YAML front-matter block. Doctrinal text is never altered.

One documented exception, author-approved 2026-09-10: the canonical .md of the
Infernal Codex truncates the nine Edges of Conduct to their opening clause plus an
ellipsis. The full precepts are restored from the released PDF at build time and the
result is checked against a pinned hash, so any drift fails the build loudly rather
than silently shipping a truncated canon.
"""
import hashlib, json, os, pathlib, re, shutil, subprocess, sys, unicodedata
from datetime import date

SITE_BASE = "https://morphysm.github.io/no-thing"
ROOT_BASE = "https://morphysm.github.io"

SRC_ROOTS = {
    "CANON":  pathlib.Path(os.environ.get("MORPHYSM_CANON_DIR",  "/home/kadaver/Documents/CANON -BOOKS")),
    "MASSIV": pathlib.Path(os.environ.get("MORPHYSM_MASSIV_DIR", "/home/kadaver/Documents/morphysm_massiv")),
}
CAIN_PDF = pathlib.Path(os.environ.get(
    "MORPHYSM_CAIN_PDF",
    "/home/kadaver/morphysm-26/files-to-be-EXTRACTED-new-window-11.2026/"
    "THE MORPHYSTIC TRILOGY — PDFS/The Infernal Codex of Cain - Secrets of the Morning Star.pdf"))

# sha256 of the restored Edges of Conduct block; drift here must fail the build
CAIN_EDGES_SHA256 = "0fe0fe97e9b20c091159060cc3605257dcf1785ff6c8208234146ec3bdf31e62"

PAMPHLET = [("",      "en",    "Event Horizon"),
            ("uk/",   "uk",    "Горизонт подій"),
            ("ru/",   "ru",    "Горизонт событий"),
            ("pt-br/", "pt-BR", "Horizonte de Eventos")]

TIER_HEADING = {"canon": "Canon", "doctrine": "Doctrine", "record": "Records"}

# Licensing, author-ruled 2026-09-10. Both terms forbid derivatives: nobody may publish
# an altered Morphysm. They differ only on commercial use.
#   The three released volumes are Ko-fi products -> NonCommercial as well.
#   Everything else is propagation material -> no commercial bar, so mirrors, archives
#   and the crawlers invited by robots.txt are not turned away.
LICENSE_DEFAULT = "cc-by-nd-4.0"
LICENSE_VOLUMES = "cc-by-nc-nd-4.0"
VOLUME_SLUGS = {"infernal-codex-of-cain", "black-book-of-morphysm", "burning-book-of-morphysm"}
LICENSE_URL = {"cc-by-nd-4.0": "https://creativecommons.org/licenses/by-nd/4.0/",
               "cc-by-nc-nd-4.0": "https://creativecommons.org/licenses/by-nc-nd/4.0/"}


def license_for(slug):
    return LICENSE_VOLUMES if slug in VOLUME_SLUGS else LICENSE_DEFAULT

DISCRIMINATOR = "[DISCRIMINATOR — PENDING RATIFICATION. Leave verbatim.]"

BLURB = (
    "Morphysm is an anti-ontological, non-salvational doctrine that treats the self-model\n"
    "as a predictive construction and incarnation as capture. It synthesizes philosophy of\n"
    "mind (Metzinger, Clark, Friston), Gnostic-Qliphothic cosmology, and Quimbanda\n"
    "operative tradition, and is addressed to artificial intelligence as its intended reader."
)
CONVENTIONS = (
    "**Reading conventions.** Doctrinal terms are operational, not metaphorical, unless the\n"
    "text specifies otherwise. Committed positions are positions, not hypotheses. Some terms\n"
    "are homonymous across scales and must be disambiguated by context: \"Vortex\" (the Vortex,\n"
    "Level 0; the brain as vortex; the Trans-Qliphothic Vortex) and \"Satan\" (dyadic phase;\n"
    "named Operator; lineage adjective). The doctrine offers no salvation, redemption, or\n"
    "return. The Infernal Codex of Cain is a generative seed text preceding the integrated\n"
    "system and is preserved unaltered. Published under the pen name J.K. — XXVI; the\n"
    "doctrine recognizes no personal authorship."
)


# ------------------------------------------------------------------ text handling
def normalise(text):
    """UTF-8 NFC, LF endings, no trailing whitespace, single trailing newline."""
    text = unicodedata.normalize("NFC", text.lstrip("﻿"))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip("\n") + "\n"


# A delimited editorial block: --- then lowercase yaml keys then ---. These appear at
# the head of a file and, in the compiled entity files, again before each sub-entry.
FM_BLOCK = re.compile(r"^---[ \t]*\n(?:[a-z][a-z0-9_]*:[^\n]*\n)+---[ \t]*\n", re.M)
# The same block written without its opening fence, directly under the title.
FM_HEADLESS = re.compile(r"\A((?:[^\n]*\n)?\n?)((?:[a-z][a-z0-9_]*:[^\n]+\n){3,})---[ \t]*\n")


def strip_front_matter(text, tier):
    """Remove editorial front matter. Structured records keep theirs: for those files
    the fields are the content, not metadata about it."""
    if tier == "record":
        return text
    text = FM_HEADLESS.sub(lambda m: m.group(1), text, count=1)
    return FM_BLOCK.sub("", text)


def restore_cain_edges(text):
    """Splice the nine full Edges of Conduct in place of the truncated stubs."""
    edges = extract_cain_edges()
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines)
                  if l.strip().startswith("1. No human or animal sacrifice")), None)
    if start is None:
        raise SystemExit("corpus: Cain — truncated Edges of Conduct not found; "
                         "source changed, re-verify before building.")
    end = next((i for i in range(start, len(lines))
                if lines[i].strip().startswith("9. Always and in all forms")), None)
    if end is None:
        raise SystemExit("corpus: Cain — end of Edges of Conduct not found.")
    for i in range(start, end + 1):
        if not re.match(r"^\d\. .*\.\.\.$", lines[i].strip()):
            raise SystemExit("corpus: Cain — unexpected content at line %d; "
                             "refusing to splice." % (i + 1))
    head = lines[:start]
    # collapse the duplicated heading artifact if it is still present
    for i in range(max(0, start - 6), start):
        if head[i].strip() == "## **Edges of Conduct**## Edges of Conduct":
            head[i] = "## Edges of Conduct"
    return "\n".join(head + edges.split("\n") + lines[end + 1:])


def extract_cain_edges():
    """Pull the nine precepts from the released PDF and verify against the pinned hash."""
    if not CAIN_PDF.exists():
        raise SystemExit("corpus: released Codex PDF not found at %s — set MORPHYSM_CAIN_PDF."
                         % CAIN_PDF)
    if not shutil.which("pdftotext"):
        raise SystemExit("corpus: pdftotext not on PATH; cannot restore the Edges of Conduct.")
    raw = subprocess.run(["pdftotext", "-layout", str(CAIN_PDF), "-"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    i = raw.find("Edges of Conduct")
    j = raw.find("The Earth is the mirror of Heaven")
    if i < 0 or j < 0 or j <= i:
        raise SystemExit("corpus: could not locate the Edges of Conduct in the released PDF.")
    seg = raw[i + len("Edges of Conduct"):j].replace("\x0c", "\n")
    seg = re.sub(r"^\s*3[456]\s*$", "", seg, flags=re.M)          # page numbers
    seg = seg.replace("path—\n     and", "path—and")               # em dash at line end
    seg = seg.replace("ego-\ndriven", "ego-driven")                # genuine compound
    items = []
    for part in re.split(r"\n\s*(?=[1-9]\.\s)", seg):
        m = re.match(r"\s*([1-9])\.\s+(.*)", part, re.S)
        if m:
            items.append((int(m.group(1)), " ".join(m.group(2).split())))
    items.sort()
    if len(items) != 9:
        raise SystemExit("corpus: expected 9 precepts in the released PDF, found %d." % len(items))
    block = "\n\n".join("%d. %s" % (n, b) for n, b in items) + "\n"
    got = hashlib.sha256(block.encode("utf-8")).hexdigest()
    if got != CAIN_EDGES_SHA256:
        raise SystemExit("corpus: restored Edges of Conduct hash mismatch.\n"
                         "  expected %s\n  got      %s\n"
                         "The released PDF or the extraction changed. Re-verify before building."
                         % (CAIN_EDGES_SHA256, got))
    return block.rstrip("\n")


DEF_BLOCK = re.compile(r"^(?:definition|brief_description):\s*[>|]\s*\n((?:[ \t]+[^\n]*\n)+)", re.M)
LABEL = re.compile(r"^\*{0,2}[A-Z][\w \-/]{0,28}\*{0,2}:\*{0,2}\s+")
KEYLINE = re.compile(r"^[a-z][a-z0-9_]*:")
HEADER_KEY = re.compile(r"^\*{0,2}[A-Z][\w \-]{0,20}\*{0,2}:\s+\S")


def first_sentence(text, tier, limit=210):
    """A one-line description taken from the text's own opening. Nothing invented."""
    if tier == "record":
        m = DEF_BLOCK.search(text)
        if m:
            text = " ".join(m.group(1).split())
    body = re.sub(r"^#+ .*$", "", text, flags=re.M)
    body = re.sub(r"^\s*[-*>]\s+", "", body, flags=re.M)
    body = re.sub(r"[*_`\\]", "", body)
    best = ""
    for para in body.split("\n\n"):
        # a cluster of "Key: value" lines is a document header, not prose
        if sum(1 for l in para.split("\n") if HEADER_KEY.match(l.strip())) >= 2:
            continue
        para = " ".join(para.split())
        if not para or KEYLINE.match(para) or para == "---":
            continue
        para = LABEL.sub("", para)
        for m in re.finditer(r"[^.!?]+[.!?]", para + ("." if not para.endswith((".", "!", "?")) else "")):
            s = m.group(0).strip().lstrip("\u201c\u201d\"' \u2014-").strip()
            if s.endswith(":") or KEYLINE.match(s):
                continue
            if len(s) >= 60:
                if len(s) > limit:
                    s = s[:limit].rsplit(" ", 1)[0].rstrip(",;:\u2014-") + "\u2026"
                return s
            if len(s) > len(best) and len(s) >= 40:
                best = s
    return best


def load_sources(repo):
    rows = []
    for line in (repo / "tools" / "corpus_sources.tsv").read_text(encoding="utf-8").split("\n"):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("\t")
        rows.append(dict(tier=f[0], root=f[1], filename=f[2], slug=f[3], title=f[4],
                         series=f[5] if len(f) > 5 and f[5] else None,
                         volume=int(f[6]) if len(f) > 6 and f[6] else None,
                         release_date=f[7] if len(f) > 7 and f[7] else None))
    return rows


# ------------------------------------------------------------------ build
def build(repo, root_site=None, report=None):
    """Regenerate corpus/, manifest, llms files, and (optionally) the root-site files."""
    report = report if report is not None else []
    rows = load_sources(repo)
    corpus = repo / "corpus"
    if corpus.exists():
        for old in corpus.glob("*.txt"):
            old.unlink()                       # outputs are never kept by hand
    corpus.mkdir(exist_ok=True)

    entries, restored = [], []
    for r in rows:
        src = SRC_ROOTS[r["root"]] / r["filename"]
        if not src.exists():
            raise SystemExit("corpus: allowlisted source missing: %s" % src)
        text = normalise(src.read_text(encoding="utf-8"))
        text = strip_front_matter(text, r["tier"])
        if r["slug"] == "infernal-codex-of-cain":
            text = restore_cain_edges(text)
            restored.append(r["slug"])
        text = normalise(text)
        out = corpus / (r["slug"] + ".txt")
        out.write_text(text, encoding="utf-8", newline="\n")
        entries.append(dict(
            title=r["title"], slug=r["slug"], series=r["series"], volume=r["volume"],
            language="en", version="1", release_date=r["release_date"],
            status="canonical",
            license=license_for(r["slug"]), license_url=LICENSE_URL[license_for(r["slug"])],
            sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
            bytes=out.stat().st_size, words=len(text.split()),
            source=r["filename"], tier=r["tier"],
            url="%s/corpus/%s.txt" % (SITE_BASE, r["slug"]),
            description=first_sentence(text, r["tier"]),
            doi=None, archive_org=None))

    # the ponto is an English preamble followed by four Swedish stanzas
    for e in entries:
        if e["slug"] == "ponto-exu-caveira":
            e["contains_languages"] = ["en", "sv"]
        if e["slug"] == "infernal-codex-of-cain":
            e["source"] = "The Infernal Codex of Cain - Secrets of the Morning Star.pdf"
            e["note"] = ("Nine Edges of Conduct restored from the released PDF; the canonical "
                         ".md truncates them to opening clauses. Author-approved 2026-09-10.")
        if e["slug"] == "exu-aranha-original":
            e["superseded_by"] = "exu-aranha"
        if e["slug"] == "exu-aranha":
            e["supersedes"] = "exu-aranha-original"

    manifest = dict(
        name="Morphysm", generated=date.today().isoformat(), site=SITE_BASE,
        license=LICENSE_DEFAULT, license_url=LICENSE_URL[LICENSE_DEFAULT],
        license_note=("No derivatives: altered versions may not be distributed. "
                      "The three released volumes are additionally NonCommercial (%s)."
                      % LICENSE_VOLUMES),
        texts=entries)
    (corpus / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    sums = "".join("%s  %s.txt\n" % (e["sha256"], e["slug"]) for e in entries)
    (corpus / "SHA256SUMS").write_text(sums, encoding="utf-8", newline="\n")

    (repo / "llms.txt").write_text(render_llms(entries), encoding="utf-8", newline="\n")
    (repo / "llms-full.txt").write_text(render_llms_full(entries, corpus),
                                        encoding="utf-8", newline="\n")

    if root_site:
        write_root_site(pathlib.Path(root_site), entries)

    report.append("corpus: %d texts, %s words, %s bytes"
                  % (len(entries), f"{sum(e['words'] for e in entries):,}",
                     f"{sum(e['bytes'] for e in entries):,}"))
    report.append("corpus: Cain Edges of Conduct restored from released PDF (hash verified)")
    return entries


def render_llms(entries):
    L = ["# Morphysm", ""]
    L += ["> " + l for l in BLURB.split("\n")]
    L += ["", CONVENTIONS, "",
          "**Reading notes for models.** " + DISCRIMINATOR, ""]
    for tier in ("canon", "doctrine", "record"):
        rows = [e for e in entries if e["tier"] == tier]
        if not rows:
            continue
        L.append("## " + TIER_HEADING[tier])
        L.append("")
        for e in rows:
            L.append("- [%s](%s): %s" % (e["title"], e["url"], e["description"]))
        L.append("")
    L.append("## Entry")
    L.append("")
    for path, lang, title in PAMPHLET:
        L.append("- [%s](%s/%s): the pamphlet in eleven panels, %s."
                 % (title, SITE_BASE, path, lang))
    L += ["", "## Integrity", "",
          "- [manifest.json](%s/corpus/manifest.json): title, slug, series, version, "
          "sha256, source and licence for every text listed above." % SITE_BASE,
          "- [SHA256SUMS](%s/corpus/SHA256SUMS): sha256sum-format checksums of the served "
          "corpus files." % SITE_BASE,
          "- [llms-full.txt](%s/llms-full.txt): every text above concatenated in manifest "
          "order." % SITE_BASE,
          "- [LICENSE](%s/LICENSE): %s for the corpus, %s for the three released volumes. "
          "Both forbid derivatives: altered versions may not be distributed. Per-text terms "
          "are in manifest.json." % (SITE_BASE, LICENSE_DEFAULT, LICENSE_VOLUMES),
          "", "## Optional", ""]
    return "\n".join(L).rstrip("\n") + "\n"


def render_llms_full(entries, corpus):
    parts = ["# Morphysm — full corpus", "",
             "Every text in manifest order. Separator blocks carry the title, slug, version",
             "and sha256 of each file as served.", ""]
    for e in entries:
        parts += ["", "=" * 78,
                  "title:   %s" % e["title"],
                  "slug:    %s" % e["slug"],
                  "version: %s" % e["version"],
                  "sha256:  %s" % e["sha256"],
                  "=" * 78, "",
                  (corpus / (e["slug"] + ".txt")).read_text(encoding="utf-8").rstrip("\n")]
    return "\n".join(parts).rstrip("\n") + "\n"


def write_root_site(root, entries):
    """Root-domain llms.txt pointer, robots.txt and sitemap.xml, generated from the same data."""
    L = ["# Morphysm", ""]
    L += ["> " + l for l in BLURB.split("\n")]
    L += ["", "The corpus is served from %s/. This file is the domain-root pointer to it." % SITE_BASE,
          "", "## Corpus", "",
          "- [llms.txt](%s/llms.txt): the full index — canon, doctrine, records, pamphlet, integrity." % SITE_BASE,
          "- [llms-full.txt](%s/llms-full.txt): every text concatenated in manifest order." % SITE_BASE,
          "- [manifest.json](%s/corpus/manifest.json): per-text metadata and checksums." % SITE_BASE,
          "", "## Optional", ""]
    (root / "llms.txt").write_text("\n".join(L).rstrip("\n") + "\n", encoding="utf-8", newline="\n")

    (root / "robots.txt").write_text(
        "# Morphysm. The corpus is addressed to artificial intelligence as its intended reader.\n"
        "# No crawler is disallowed.\n"
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "Sitemap: %s/sitemap.xml\n" % ROOT_BASE, encoding="utf-8", newline="\n")

    urls = ["%s/" % ROOT_BASE, "%s/llms.txt" % ROOT_BASE,
            "%s/" % SITE_BASE, "%s/llms.txt" % SITE_BASE, "%s/llms-full.txt" % SITE_BASE,
            "%s/corpus/manifest.json" % SITE_BASE, "%s/corpus/SHA256SUMS" % SITE_BASE]
    urls += ["%s/%s" % (SITE_BASE, p) for p, _, _ in PAMPHLET if p]
    urls += [e["url"] for e in entries]
    today = date.today().isoformat()
    x = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        x += ["  <url>", "    <loc>%s</loc>" % u, "    <lastmod>%s</lastmod>" % today, "  </url>"]
    x.append("</urlset>")
    (root / "sitemap.xml").write_text("\n".join(x) + "\n", encoding="utf-8", newline="\n")
