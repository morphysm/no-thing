#!/usr/bin/env python3
"""
archive_org.py — generate the exact `ia upload` commands for the Morphysm corpus.

This script PRINTS commands. It never uploads and never touches credentials: run
`ia configure` yourself, then run the printed commands yourself. archive.org uploads
are permanent and public, so each one is a deliberate act, not a side effect.

    python3 tools/archive_org.py            # print the upload commands
    python3 tools/archive_org.py --wayback  # print the Save Page Now URL list

Metadata comes from corpus/manifest.json and tools/zenodo_metadata.yaml, so the items
describe exactly what was built rather than a hand-kept copy.
"""
import argparse, json, pathlib, shlex

REPO = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://morphysm.github.io/no-thing"
ROOT = "https://morphysm.github.io"

LICENSE_URL = {"cc-by-nd-4.0": "https://creativecommons.org/licenses/by-nd/4.0/",
               "cc-by-nc-nd-4.0": "https://creativecommons.org/licenses/by-nc-nd/4.0/"}

SUBJECTS = ["Morphysm", "anti-ontology", "self-model", "philosophy of mind",
            "Gnosticism", "Qliphoth", "Quimbanda", "demonology",
            "artificial intelligence"]

ITEMS = [
    dict(slug="infernal-codex-of-cain", ident="morphysm-infernal-codex-of-cain-v1",
         title="The Infernal Codex of Cain: Secrets of the Morning Star",
         date="2026-02-04",
         pdf="The Infernal Codex of Cain - Secrets of the Morning Star.pdf",
         desc="Volume I of the Morphystic Trilogy. A generative seed text preceding the "
              "integrated system, preserved unaltered. The nine Edges of Conduct are "
              "restored from the released edition; every checksum is recorded in "
              "manifest.json."),
    dict(slug="black-book-of-morphysm", ident="morphysm-black-book-of-morphysm-v1",
         title="The Black Book of Morphysm (Extended, AI Integration)",
         date="2026-02-27",
         pdf="THE BLACK BOOK OF MORPHYSM EXTENDED VERSION 2026.pdf",
         desc="Volume II of the Morphystic Trilogy, extended AI-integration edition."),
    dict(slug="burning-book-of-morphysm", ident="morphysm-burning-book-of-morphysm-v1",
         title="The Burning Book of Morphysm 2 (AI)",
         date="2026-01-25",
         pdf="THE BURNING BOOK OF MORPHYSM.pdf",
         desc="Volume III of the Morphystic Trilogy."),
    dict(slug=None, ident="morphysm-corpus-v1",
         title="The Morphysm Corpus",
         date="2026-09-10", pdf=None,
         desc="The Morphysm corpus as a single body: the meta-doctrine, the doctrine "
              "texts, and the structured entity and concept records, as served plain "
              "text. manifest.json gives the title, slug, licence and sha256 of every "
              "file, so any individual text may be cited by slug and checksum."),
]

VOLUMES = {"infernal-codex-of-cain", "black-book-of-morphysm", "burning-book-of-morphysm"}


def manifest():
    return json.loads((REPO / "corpus" / "manifest.json").read_text(encoding="utf-8"))


def files_for(item, man):
    if item["slug"]:
        out = [REPO / "corpus" / (item["slug"] + ".txt")]
        cached = REPO / "tools" / ".deposit-cache" / item["pdf"]
        pdf_root = pathlib.Path(
            "/home/kadaver/morphysm-26/files-to-be-EXTRACTED-new-window-11.2026/"
            "THE MORPHYSTIC TRILOGY — PDFS")
        out.append(cached if cached.exists() else pdf_root / item["pdf"])
        out.append(REPO / "corpus" / "manifest.json")
        return out
    out = [REPO / "corpus" / (e["slug"] + ".txt") for e in man["texts"]
           if e["slug"] not in VOLUMES]
    return out + [REPO / "corpus" / "manifest.json", REPO / "corpus" / "SHA256SUMS",
                  REPO / "llms.txt", REPO / "LICENSE"]


def licence_of(item, man):
    if item["slug"]:
        return next(e["license"] for e in man["texts"] if e["slug"] == item["slug"])
    return "cc-by-nd-4.0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wayback", action="store_true",
                    help="print the Save Page Now URL list instead")
    a = ap.parse_args()
    man = manifest()

    if a.wayback:
        urls = [ROOT + "/", ROOT + "/llms.txt", SITE + "/", SITE + "/uk/", SITE + "/ru/",
                SITE + "/pt-br/", SITE + "/llms.txt", SITE + "/llms-full.txt",
                SITE + "/LICENSE", SITE + "/corpus/manifest.json",
                SITE + "/corpus/SHA256SUMS"]
        urls += [e["url"] for e in man["texts"]]
        print("# Wayback Machine — Save Page Now. %d URLs." % len(urls))
        print("# Permanent and public. Run only on an explicit go.")
        for u in urls:
            print("curl -sS -o /dev/null -w '%%{http_code} %s\\n' 'https://web.archive.org/save/%s'"
                  % (u, u))
        return

    print("# archive.org uploads — PERMANENT AND PUBLIC.")
    print("# Run `ia configure` first. Run one item at a time, on an explicit go.\n")
    for item in ITEMS:
        lic = licence_of(item, man)
        files = files_for(item, man)
        missing = [f for f in files if not f.exists()]
        if missing:
            print("# !! missing: %s" % ", ".join(str(m) for m in missing))
        total = sum(f.stat().st_size for f in files if f.exists())
        print("# %s — %d files, %s" % (item["ident"], len(files), f"{total:,} bytes"))
        cmd = ["ia", "upload", item["ident"]]
        cmd += [str(f) for f in files]
        cmd += ["--metadata=mediatype:texts",
                "--metadata=collection:opensource",
                "--metadata=creator:J.K. — XXVI",
                "--metadata=title:%s" % item["title"],
                "--metadata=date:%s" % item["date"],
                "--metadata=language:eng",
                "--metadata=licenseurl:%s" % LICENSE_URL[lic],
                "--metadata=description:%s" % " ".join(item["desc"].split()),
                "--metadata=external-identifier:%s/corpus/manifest.json" % SITE,
                "--metadata=originalurl:%s/" % SITE]
        cmd += ["--metadata=subject:%s" % s for s in SUBJECTS]
        print(" ".join(shlex.quote(c) for c in cmd))
        print()


if __name__ == "__main__":
    main()
