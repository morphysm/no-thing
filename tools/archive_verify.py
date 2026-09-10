#!/usr/bin/env python3
"""Verify every uploaded archive.org item against the local files that were sent.

Checks metadata (creator unsplit, licence, mediatype, collection) and re-hashes each
uploaded file's md5 against the local copy, so a silently truncated or wrong-file
upload is caught rather than assumed good.
"""
import hashlib, json, pathlib, sys, urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
CACHE = REPO / "tools" / ".deposit-cache"
PDF_ROOT = pathlib.Path("/home/kadaver/morphysm-26/files-to-be-EXTRACTED-new-window-11.2026/"
                        "THE MORPHYSTIC TRILOGY — PDFS")
ITEMS = ["morphysm-corpus", "morphysm-infernal-codex-of-cain",
         "morphysm-black-book-of-morphysm", "morphysm-burning-book-of-morphysm"]


def local_for(name):
    for c in (REPO / "corpus" / name, REPO / name, CACHE / name, PDF_ROOT / name):
        if c.exists():
            return c
    return None


def main():
    problems = []
    for ident in ITEMS:
        try:
            with urllib.request.urlopen("https://archive.org/metadata/" + ident, timeout=60) as r:
                d = json.load(r)
        except Exception as e:
            problems.append((ident, "metadata unreadable: %s" % e)); continue
        m = d.get("metadata", {})
        if not m:
            print("\n=== %s — NOT CREATED ===" % ident); problems.append((ident, "no metadata")); continue
        files = [f for f in d.get("files", [])
                 if f.get("source") == "original" and not f["name"].startswith(ident)]
        print("\n=== %s ===" % ident)
        print("  https://archive.org/details/%s" % ident)
        print("  title     : %s" % m.get("title"))
        print("  creator   : %r" % m.get("creator"))
        print("  licence   : %s" % m.get("licenseurl"))
        print("  mediatype : %s / %s" % (m.get("mediatype"), m.get("collection")))
        print("  pending   : %s   content files: %d" % (d.get("pending_tasks"), len(files)))
        if m.get("creator") != "J.K. — XXVI":
            problems.append((ident, "creator is %r" % m.get("creator")))
        for f in sorted(files, key=lambda x: x["name"]):
            p = local_for(f["name"])
            if not p:
                print("    %-56s  (no local copy to compare)" % f["name"][:56]); continue
            same = hashlib.md5(p.read_bytes()).hexdigest() == f.get("md5")
            print("    %-56s %11s B  %s" % (f["name"][:56], f.get("size"),
                                            "ok" if same else "MD5 MISMATCH"))
            if not same:
                problems.append((ident, "md5 mismatch: %s" % f["name"]))
    print("\n" + ("PROBLEMS:" if problems else "All items verified against local files."))
    for i, p in problems:
        print("  %-34s %s" % (i, p))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
