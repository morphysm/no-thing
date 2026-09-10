#!/usr/bin/env python3
"""
pdf_set_author.py — set or remove the /Author entry in a PDF's document-info
dictionary without touching a single existing byte of the file.

Editing metadata in place would shift every byte offset after the change and
invalidate the cross-reference table. Re-encoding with Ghostscript or mutool would
rewrite the page content streams of a book full of images. Neither is acceptable for
a text that must stay faithful to its released edition.

This does two things, and needs both:

1. It blanks the original /Author entry IN PLACE, overwriting those bytes with spaces.
   PDF dictionaries tolerate arbitrary whitespace between entries, so the byte count is
   unchanged and every offset in the cross-reference table stays valid. This is what
   actually removes the old name: an incremental update alone would leave the original
   string sitting in the file, recoverable with `strings`.

2. It appends a standards-conformant *incremental update* — a replacement Info object,
   a new cross-reference section and a new trailer — so the file declares the new
   Author. A reader uses the last trailer and sees it.

Every original byte that carries content — every page, every glyph, every image — is
untouched at its original offset. The only bytes overwritten are the old /Author entry
itself.

Only /Author is changed. /Creator, /Producer, /CreationDate and /ModDate are copied
across byte-for-byte.

Usage:
    python3 tools/pdf_set_author.py in.pdf out.pdf --author "Alexander Cripple"
    python3 tools/pdf_set_author.py in.pdf out.pdf --remove
"""
import argparse, pathlib, re, sys


def pdf_text_string(s):
    """UTF-16BE hex string with BOM — the form this file already uses."""
    return b"<FEFF" + s.encode("utf-16-be").hex().upper().encode("ascii") + b">"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--author"); g.add_argument("--remove", action="store_true")
    a = ap.parse_args()

    d = pathlib.Path(a.src).read_bytes()

    m = re.search(rb"/Info\s+(\d+)\s+(\d+)\s+R", d)
    if not m:
        sys.exit("no /Info reference in trailer")
    num, gen = int(m.group(1)), int(m.group(2))

    om = re.search(rb"(?m)^%d %d obj\b" % (num, gen), d)
    if not om:
        sys.exit("Info object %d %d not found" % (num, gen))
    body_start = d.index(b"<<", om.end())
    body_end = d.index(b">>", body_start) + 2
    body = d[body_start:body_end]

    if not re.search(rb"/Author\s*(<[0-9A-Fa-f]*>|\([^)]*\))", body):
        sys.exit("no /Author entry to change")
    if a.remove:
        new_body = re.sub(rb"/Author\s*(<[0-9A-Fa-f]*>|\([^)]*\))", b"", body, count=1)
    else:
        new_body = re.sub(rb"/Author\s*(<[0-9A-Fa-f]*>|\([^)]*\))",
                          b"/Author" + pdf_text_string(a.author), body, count=1)

    sx = re.findall(rb"startxref\s+(\d+)", d)
    if not sx:
        sys.exit("no startxref")
    prev = int(sx[-1])
    size = int(re.search(rb"/Size\s+(\d+)", d[d.rindex(b"trailer"):]).group(1))
    idm = re.search(rb"/ID\s*\[[^\]]*\]", d[d.rindex(b"trailer"):])
    id_part = idm.group(0) if idm else b""

    out = bytearray(d)

    # 1. scrub the original entry in place: same byte count, name physically gone
    am = re.search(rb"/Author\s*(<[0-9A-Fa-f]*>|\([^)]*\))", bytes(out))
    out[am.start():am.end()] = b" " * (am.end() - am.start())
    scrubbed = am.end() - am.start()

    if not out.endswith(b"\n"):
        out += b"\r\n"
    obj_off = len(out)
    out += b"%d %d obj\r\n" % (num, gen) + new_body + b"\r\nendobj\r\n"

    xref_off = len(out)
    out += b"xref\r\n%d 1\r\n" % num
    out += b"%010d %05d n \r\n" % (obj_off, gen)          # entries are exactly 20 bytes
    out += (b"trailer\r\n<</Size %d/Root %s/Info %d %d R/Prev %d%s>>\r\n"
            % (size,
               re.search(rb"/Root\s+\d+\s+\d+\s+R", d[d.rindex(b"trailer"):]).group(0)[6:],
               num, gen, prev, id_part))
    out += b"startxref\r\n%d\r\n%%%%EOF\r\n" % xref_off

    pathlib.Path(a.dst).write_bytes(bytes(out))
    print("old /Author scrubbed     : %d bytes overwritten in place with spaces" % scrubbed)
    print("content bytes preserved  : %d of %d (offsets unchanged)" % (len(d) - scrubbed, len(d)))
    print("appended                 : %d bytes (incremental update)" % (len(out) - len(d)))
    print("new /Author              : %s" % ("(removed)" if a.remove else a.author))


if __name__ == "__main__":
    main()
