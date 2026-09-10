#!/usr/bin/env python3
"""
zenodo_deposit.py — create Zenodo DRAFT depositions for the Morphysm corpus.

This script NEVER publishes. There is no code path that calls the publish action;
see refuse_to_publish() below. Publication is done by hand in the Zenodo web UI,
because it is irreversible and public.

Credentials come from the environment only:
    export ZENODO_TOKEN=...          # never written to disk, never logged
Nothing is read from a file, and the token is never echoed.

Usage:
    python3 tools/zenodo_deposit.py                 # sandbox (default)
    python3 tools/zenodo_deposit.py --production    # real Zenodo, drafts only
    python3 tools/zenodo_deposit.py --only infernal-codex-of-cain
    python3 tools/zenodo_deposit.py --dry-run       # show payloads, no network

Doctrine note: the concept DOI is the source line and each version DOI is one state
of it. Revisions are deposited as new versions, never as replacements.
"""
import argparse, hashlib, json, os, pathlib, subprocess, sys, time
from datetime import date
import requests
import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
META = REPO / "tools" / "zenodo_metadata.yaml"

SANDBOX = "https://sandbox.zenodo.org"
PRODUCTION = "https://zenodo.org"

# Zenodo resource-type ids are "<upload_type>-<publication_type>" for publications.
def resource_type_id(d):
    if d["upload_type"] == "publication":
        return "publication-%s" % d["publication_type"]
    return d["upload_type"]


def refuse_to_publish(*_a, **_k):
    """Deliberate dead end. Publishing is irreversible and is done by a human."""
    raise SystemExit(
        "zenodo_deposit.py does not publish. Open the draft URL and publish in the "
        "web UI if that is what you intend.")


def build_metadata(defaults, dep):
    creator = defaults["creator"]
    if creator["type"] != "organizational":
        raise SystemExit(
            "creator.type must be 'organizational'. Zenodo's 'personal' type splits a "
            "name into family/given; a pen name must stay one unsplit string.")
    if "," in creator["name"]:
        print("  ! warning: creator name contains a comma; Zenodo may render it as "
              "'Family, Given'. Check the draft before publishing.")

    md = {
        "title": dep["title"],
        "publication_date": dep["publication_date"],
        "version": str(dep.get("version", "1")),
        "resource_type": {"id": resource_type_id(defaults)},
        "creators": [{"person_or_org": {"type": "organizational",
                                        "name": creator["name"]}}],
        "publisher": dep.get("publisher", defaults.get("publisher", "Zenodo")),
        "description": " ".join(dep["description"].split()),
        "subjects": [{"subject": k} for k in defaults.get("keywords", [])],
    }
    lic = dep.get("license", defaults.get("license"))
    if lic:
        md["rights"] = [{"id": lic}]
    rel = list(defaults.get("related_identifiers", [])) + list(dep.get("related_identifiers", []))
    if rel:
        md["related_identifiers"] = [
            {"identifier": r["identifier"],
             "relation_type": {"id": r["relation"]},
             "scheme": r.get("scheme", "url")} for r in rel]
    return md


def clean_token(raw):
    """Validate ZENODO_TOKEN before it reaches an HTTP header.

    A token pasted from the web UI's *shortened* display carries a Unicode ellipsis,
    and requests then dies with a bare "'latin-1' codec can't encode character
    '\u2026'" pointing at position 7 — which is simply the first character after
    "Bearer ". Catch it here and say what actually went wrong."""
    tok = raw.strip().strip("'\"")
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    if "\u2026" in tok or "..." in tok:
        raise SystemExit(
            "ZENODO_TOKEN contains an ellipsis, so it is a shortened display of the\n"
            "token rather than the token itself. Zenodo shows a token in full only once,\n"
            "at the moment you create it; afterwards the page renders it elided.\n"
            "Create a new token and copy it immediately, before leaving the page.")
    if not tok.isascii():
        bad = [c for c in tok if not c.isascii()]
        raise SystemExit(
            "ZENODO_TOKEN contains non-ASCII characters (%s), which cannot go in an\n"
            "HTTP header. Zenodo tokens are plain letters and digits — this looks like\n"
            "a copy-paste artefact such as a smart quote or an ellipsis."
            % ", ".join(repr(c) for c in dict.fromkeys(bad)))
    if not tok:
        raise SystemExit("ZENODO_TOKEN is empty after stripping quotes and whitespace.")
    if not tok.replace("_", "").replace("-", "").isalnum():
        raise SystemExit(
            "ZENODO_TOKEN does not look like a Zenodo token: expected only letters,\n"
            "digits, - and _. Check for stray characters from the paste.")
    if len(tok) < 40:
        raise SystemExit(
            "ZENODO_TOKEN is only %d characters. Zenodo personal access tokens are\n"
            "considerably longer, so this is probably truncated." % len(tok))
    return tok


RETRY_STATUS = {500, 502, 503, 504}


def api(session, base, method, path, _tries=5, **kw):
    """Zenodo returns transient 5xx and gateway timeouts under load, especially on
    large uploads. Retry those with backoff rather than losing a run part-way."""
    delay = 3
    for attempt in range(1, _tries + 1):
        try:
            r = session.request(method, base + path, timeout=300, **kw)
        except requests.RequestException as e:
            if attempt == _tries:
                raise SystemExit("Zenodo %s %s failed after %d attempts: %s"
                                 % (method, path, _tries, e))
            print("    %s %s — %s; retrying in %ds (%d/%d)"
                  % (method, path, type(e).__name__, delay, attempt, _tries))
            time.sleep(delay); delay = min(delay * 2, 60); continue
        if r.status_code in RETRY_STATUS and attempt < _tries:
            print("    %s %s — HTTP %d; retrying in %ds (%d/%d)"
                  % (method, path, r.status_code, delay, attempt, _tries))
            time.sleep(delay); delay = min(delay * 2, 60); continue
        break
    if r.status_code >= 400:
        hint = ""
        if r.status_code == 403:
            hint = ("\n\nA 403 here almost always means token scope. Zenodo's own quickstart\n"
                    "grants BOTH deposit:write and deposit:actions; with deposit:write alone,\n"
                    "record creation and file upload are frequently refused.\n"
                    "Run  python3 tools/zenodo_deposit.py --check  to see exactly what your\n"
                    "token can do.")
        elif r.status_code == 401:
            hint = "\n\nThe token was rejected. Sandbox and production tokens are not interchangeable."
        raise SystemExit("Zenodo %s %s -> HTTP %d\n%s%s"
                         % (method, path, r.status_code, r.text[:600], hint))
    return r


def check(session, base):
    """Preflight: report exactly what this token is allowed to do, then clean up."""
    print("checking token against %s\n" % base)
    r = session.get(base + "/api/user/records", timeout=60)
    print("  read  (GET /api/user/records)      HTTP %d  %s"
          % (r.status_code, "ok" if r.ok else "FAILED"))
    if r.status_code in (401, 403):
        # Which site does this token actually belong to? Ask the other one.
        other = PRODUCTION if base == SANDBOX else SANDBOX
        try:
            o = requests.get(other + "/api/user/records",
                             headers=dict(session.headers), timeout=60)
            print("  read  (GET %s)  HTTP %d  %s"
                  % (other, o.status_code, "ok" if o.ok else "also refused"))
            if o.ok:
                raise SystemExit(
                    "\nFOUND IT: this token works on %s, not on %s.\n"
                    "Either create a token on %s, or run with %s."
                    % (other, base, base,
                       "--production" if other == PRODUCTION else "no --production flag"))
        except requests.RequestException:
            pass
        raise SystemExit(
            "\nThe token is not accepted by %s at all — this fails on the very first\n"
            "read, before any deposit is attempted. In order of likelihood:\n"
            "  1. the token was created on the OTHER site. %s tokens do not work here.\n"
            "  2. the token is missing scopes. Grant deposit:write AND deposit:actions.\n"
            "  3. the paste is damaged. Create a new token and copy it immediately.\n"
            "Zenodo answers 403 rather than 401 for an unrecognised token, so a 403 here\n"
            "does not necessarily mean your scopes are wrong."
            % (base, "Production" if base == SANDBOX else "Sandbox"))

    probe = {"access": {"record": "public", "files": "public"},
             "files": {"enabled": True},
             "metadata": {"title": "scope probe (delete me)",
                          "publication_date": date.today().isoformat(),
                          "resource_type": {"id": "publication-book"},
                          "creators": [{"person_or_org": {"type": "organizational",
                                                          "name": "probe"}}]}}
    r = session.post(base + "/api/records", json=probe, timeout=60)
    print("  create (POST /api/records)         HTTP %d  %s"
          % (r.status_code, "ok" if r.ok else "FAILED"))
    if not r.ok:
        print("\n  %s" % r.text[:300])
        raise SystemExit(
            "\nRecord creation is refused. Add the deposit:actions scope to the token\n"
            "(Zenodo's quickstart grants deposit:write AND deposit:actions), or create a\n"
            "new token with both. This script still never publishes — see refuse_to_publish().")
    rid = r.json()["id"]

    r2 = session.post(base + "/api/records/%s/draft/files" % rid,
                      json=[{"key": "probe.txt"}], timeout=60)
    print("  upload (POST draft/files)          HTTP %d  %s"
          % (r2.status_code, "ok" if r2.ok else "FAILED"))
    if r2.ok:
        r3 = session.put(base + "/api/records/%s/draft/files/probe.txt/content" % rid,
                         data=b"probe", headers={"Content-Type": "application/octet-stream"},
                         timeout=60)
        print("  content (PUT file content)         HTTP %d  %s"
              % (r3.status_code, "ok" if r3.ok else "FAILED"))

    d = session.delete(base + "/api/records/%s/draft" % rid, timeout=60)
    print("  cleanup (DELETE draft)             HTTP %d  %s"
          % (d.status_code, "probe draft removed" if d.ok else
             "COULD NOT DELETE — remove record %s by hand" % rid))
    print("\nToken is usable." if r2.ok else "\nFile upload refused — add deposit:actions.")


def sha256(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


CACHE = REPO / "tools" / ".deposit-cache"


def prepare_pdfs(cfg, dep):
    """Resolve the released PDFs, scrubbing embedded identity where the metadata says to.

    Every PDF is checked against its pinned source hash first, so a changed or swapped
    release fails loudly instead of being deposited unnoticed. Nothing is published
    from an unverified file."""
    root = pathlib.Path(os.environ.get("MORPHYSM_TRILOGY_PDFS", cfg["pdf_root"]))
    out = []
    for spec in dep.get("pdfs", []):
        src = root / spec["file"]
        if not src.exists():
            raise SystemExit("released PDF not found: %s\n"
                             "Set MORPHYSM_TRILOGY_PDFS to the folder holding them." % src)
        got = sha256(src)
        if got != spec["source_sha256"]:
            raise SystemExit(
                "released PDF does not match its pinned hash:\n  %s\n"
                "  expected %s\n  got      %s\n"
                "This is not the edition that was verified. Refusing to deposit."
                % (src, spec["source_sha256"], got))
        if not spec.get("set_author"):
            out.append((src, spec["file"], "byte-faithful"))
            continue
        CACHE.mkdir(exist_ok=True)
        dst = CACHE / spec["file"]
        if not dst.exists() or sha256(dst) != spec["result_sha256"]:
            subprocess.run([sys.executable, str(REPO / "tools" / "pdf_set_author.py"),
                            str(src), str(dst), "--author", spec["set_author"]],
                           check=True, capture_output=True)
        got = sha256(dst)
        if got != spec["result_sha256"]:
            raise SystemExit("scrubbed PDF hash mismatch for %s\n  expected %s\n  got      %s"
                             % (spec["file"], spec["result_sha256"], got))
        out.append((dst, spec["file"], "author set to %r, original identity scrubbed"
                    % spec["set_author"]))
    return out


def expand_from_manifest(dep):
    """Resolve corpus files from the built manifest, so the deposited set cannot drift
    out of step with the corpus that was actually generated."""
    spec = dep.get("files_from_manifest")
    if not spec:
        return []
    man = json.loads((REPO / "corpus" / "manifest.json").read_text(encoding="utf-8"))
    exclude = set(spec.get("exclude_slugs", []))
    out = []
    for e in man["texts"]:
        if e["slug"] in exclude:
            continue
        if spec.get("license") and e["license"] != spec["license"]:
            continue
        out.append((REPO / "corpus" / (e["slug"] + ".txt"), e["slug"] + ".txt",
                    e["license"]))
    licenses = {n for _, _, n in out}
    dep_license = dep.get("license")
    if dep_license and licenses - {dep_license}:
        raise SystemExit(
            "deposition %r is %s but would carry text licensed %s.\n"
            "A record must not misstate the terms of the text inside it."
            % (dep["slug"], dep_license, ", ".join(sorted(licenses - {dep_license}))))
    return [(p, k, "") for p, k, _ in out]


def deposit(session, base, cfg, defaults, dep, dry_run):
    files = [(REPO / f, pathlib.Path(f).name, "") for f in dep["files"]]
    files += expand_from_manifest(dep)
    for f, _, _ in files:
        if not f.exists():
            raise SystemExit("missing file for %s: %s" % (dep["slug"], f))
    files += prepare_pdfs(cfg, dep)

    payload = {"access": {"record": "public", "files": "public"},
               "files": {"enabled": True},
               "metadata": build_metadata(defaults, dep)}

    print("\n=== %s ===" % dep["slug"])
    print("  title    : %s" % payload["metadata"]["title"])
    print("  creator  : %s (organizational, unsplit)"
          % payload["metadata"]["creators"][0]["person_or_org"]["name"])
    print("  type     : %s" % payload["metadata"]["resource_type"]["id"])
    print("  licence  : %s" % (payload["metadata"].get("rights") or "UNSET (null)"))
    for f, key, note in files:
        print("  file     : %-46s %10d B  sha256 %s%s"
              % (key, f.stat().st_size, sha256(f)[:16],
                 "  <- " + note if note else ""))
    if dry_run:
        print("  --dry-run: payload below, nothing sent")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return None

    r = api(session, base, "POST", "/api/records", json=payload)
    rec = r.json()
    rid = rec["id"]

    for f, key, _note in files:
        api(session, base, "POST", "/api/records/%s/draft/files" % rid,
            json=[{"key": key}])
        api(session, base, "PUT", "/api/records/%s/draft/files/%s/content" % (rid, key),
            data=f.read_bytes(),
            headers={"Content-Type": "application/octet-stream"})
        api(session, base, "POST", "/api/records/%s/draft/files/%s/commit" % (rid, key))

    draft_url = "%s/uploads/%s" % (base, rid)
    doi = (rec.get("pids", {}).get("doi", {}) or {}).get("identifier")
    print("  DRAFT    : %s" % draft_url)
    print("  reserved DOI: %s" % (doi or "(assigned on publish)"))
    print("  NOT PUBLISHED — publish by hand in the web UI.")
    return {"slug": dep["slug"], "record_id": rid, "draft_url": draft_url, "doi": doi}


def verify(session, base, production):
    """Read back every draft and check it says what we meant it to say."""
    f = REPO / "tools" / ("zenodo_drafts_%s.json" % ("production" if production else "sandbox"))
    if not f.exists():
        raise SystemExit("no draft summary at %s — run a deposit first" % f)
    problems = []
    for row in json.loads(f.read_text(encoding="utf-8")):
        try:
            r = api(session, base, "GET", "/api/records/%s/draft" % row["record_id"])
        except SystemExit as e:
            problems.append((row["slug"], str(e))); continue
        if not r.ok:
            problems.append((row["slug"], "cannot read draft: HTTP %d" % r.status_code)); continue
        d = r.json()
        md = d.get("metadata", {}) or {}
        print("\n=== %s  (%s) ===" % (row["slug"], row["draft_url"]))
        print("  title    : %s" % md.get("title"))
        pub = md.get("publisher") or md.get("imprint_publisher")
        print("  publisher: %r%s" % (pub, "  (imprint_publisher)"
                                     if not md.get("publisher") and pub else ""))
        print("  state    : %s" % (d.get("state") or
                                   ("published" if d.get("is_published") else "draft")))
        errs = d.get("errors") or []
        if errs:
            print("  VALIDATION ERRORS Zenodo reports on this draft:")
            for e in errs:
                if isinstance(e, dict):
                    print("    %-28s %s" % (e.get("field"), e.get("message") or e.get("messages")))
                else:
                    print("    %s" % e)
            problems.append((row["slug"], "%d validation error(s) block publishing" % len(errs)))
        if not pub:
            problems.append((row["slug"], "publisher missing — Zenodo blocks DOI registration"))

        # Zenodo accepts the InvenioRDM shape on write but may hand back either that or
        # the legacy deposit shape on read. Handle both rather than guess.
        for c in md.get("creators", []) or []:
            po = c.get("person_or_org") or c
            name = po.get("name")
            ctype = po.get("type", "(legacy: no type field)")
            split = po.get("family_name") or po.get("given_name")
            print("  creator  : %r  type=%s%s"
                  % (name, ctype, "  SPLIT into family/given!" if split else ""))
            if split:
                problems.append((row["slug"], "creator SPLIT: family=%r given=%r"
                                 % (po.get("family_name"), po.get("given_name"))))
            if name and name != "J.K. \u2014 XXVI":
                problems.append((row["slug"], "creator name is %r" % name))
            if not name:
                print("    raw creator object: %s" % json.dumps(c, ensure_ascii=False)[:200])
                problems.append((row["slug"], "creator name not readable from response"))

        rights = md.get("rights") or md.get("license")
        print("  licence  : %s" % rights)
        if not rights:
            problems.append((row["slug"], "no licence on the draft"))
        print("  version  : %s   date: %s" % (md.get("version"), md.get("publication_date")))
        for ri in md.get("related_identifiers", []) or []:
            rel = ri.get("relation_type")
            rel = rel.get("id") if isinstance(rel, dict) else (rel or ri.get("relation"))
            print("  related  : %-14s %s" % (rel, ri.get("identifier")))

        ents = draft_files(d)
        print("  files    : %d" % len(ents))
        for key, ent in sorted(ents.items()):
            local = None
            pdf_root = pathlib.Path(os.environ.get(
                "MORPHYSM_TRILOGY_PDFS",
                "/home/kadaver/morphysm-26/files-to-be-EXTRACTED-new-window-11.2026/"
                "THE MORPHYSTIC TRILOGY — PDFS"))
            for cand in (REPO / "corpus" / key, REPO / key, CACHE / key, pdf_root / key):
                if cand.exists():
                    local = cand; break
            chk = ent.get("checksum") or ""
            mark = "?"
            if local is None:
                problems.append((row["slug"], "no local copy of %s to verify against" % key))
            if local and chk:
                import hashlib as _h
                mark = "ok" if _h.md5(local.read_bytes()).hexdigest() == chk else "MISMATCH"
                if mark == "MISMATCH":
                    problems.append((row["slug"], "file %s differs from local" % key))
            print("    %-58s %10s B  %s" % (key[:58], ent.get("size"), mark))
    print("\n" + ("PROBLEMS:" if problems else "All four drafts check out. Nothing is published."))
    for s, m in problems:
        print("  %-28s %s" % (s, m))


def draft_files(payload):
    """Normalise a draft's file list. Zenodo returns the InvenioRDM shape
    {"entries": {key: {...}}} or the legacy list [{"filename":..., "checksum":...}]
    depending on the record; accept either and return {key: {size, checksum}}."""
    raw = payload.get("files")
    out = {}
    if isinstance(raw, dict):
        for key, ent in (raw.get("entries") or {}).items():
            chk = ent.get("checksum") or ""
            out[key] = {"size": ent.get("size"),
                        "checksum": chk[4:] if chk.startswith("md5:") else chk}
    elif isinstance(raw, list):
        for f in raw:
            key = f.get("key") or f.get("filename")
            if not key:
                continue
            chk = f.get("checksum") or ""
            out[key] = {"size": f.get("size") or f.get("filesize"),
                        "checksum": chk[4:] if chk.startswith("md5:") else chk}
    return out


def refresh(session, base, cfg, defaults, production):
    """Re-upload only the files of an existing draft whose bytes have changed.

    Editing the corpus after depositing leaves the draft stale. Deleting and recreating
    would re-upload everything, including an 81 MB PDF, to fix a file that may be a few
    kilobytes. This compares each draft file's checksum against the local copy and
    replaces only what actually differs."""
    import hashlib as _h
    f = REPO / "tools" / ("zenodo_drafts_%s.json" % ("production" if production else "sandbox"))
    if not f.exists():
        raise SystemExit("no draft summary at %s — nothing to refresh" % f)
    rows = {r["slug"]: r for r in json.loads(f.read_text(encoding="utf-8"))}
    total = 0
    for dep in cfg["depositions"]:
        row = rows.get(dep["slug"])
        if not row:
            continue
        rid = row["record_id"]
        local = {k: p for p, k, _ in
                 [(REPO / x, pathlib.Path(x).name, "") for x in dep["files"]]
                 + expand_from_manifest(dep) + prepare_pdfs(cfg, dep)}
        r = api(session, base, "GET", "/api/records/%s/draft" % rid)
        entries = draft_files(r.json())
        stale = []
        for key, path in local.items():
            ent = entries.get(key)
            if ent is None:
                stale.append((key, path, "missing from draft")); continue
            chk = ent.get("checksum") or ""
            if chk and _h.md5(path.read_bytes()).hexdigest() != chk:
                stale.append((key, path, "bytes differ"))
        print("\n=== %s (%s) ===" % (dep["slug"], row["draft_url"]))
        if not stale:
            print("  up to date — %d files" % len(local)); continue
        for key, path, why in stale:
            print("  replacing %-46s (%s, %d B)" % (key[:46], why, path.stat().st_size))
            if key in entries:
                api(session, base, "DELETE", "/api/records/%s/draft/files/%s" % (rid, key))
            api(session, base, "POST", "/api/records/%s/draft/files" % rid, json=[{"key": key}])
            api(session, base, "PUT", "/api/records/%s/draft/files/%s/content" % (rid, key),
                data=path.read_bytes(), headers={"Content-Type": "application/octet-stream"})
            api(session, base, "POST", "/api/records/%s/draft/files/%s/commit" % (rid, key))
            total += 1
    print("\n%d file(s) replaced. Nothing was published." % total)


def fix_publisher(session, base, cfg, production):
    """Set the publisher on legacy depositions, read-modify-write.

    These records live in Zenodo's legacy deposit system: state is 'unsubmitted', files
    come back as a list, creators carry no type wrapper. Writing metadata.publisher via
    the RDM draft endpoint reports success but does not persist there. Legacy books
    carry the publisher as imprint_publisher, so set that, and metadata.publisher
    alongside it, without touching any other field."""
    f = REPO / "tools" / ("zenodo_drafts_%s.json" % ("production" if production else "sandbox"))
    rows = json.loads(f.read_text(encoding="utf-8"))
    for row in rows:
        rid = row["record_id"]
        cur = api(session, base, "GET", "/api/deposit/depositions/%s" % rid).json()
        md = dict(cur.get("metadata") or {})
        before = (md.get("imprint_publisher"), md.get("publisher"))
        md["imprint_publisher"] = "Zenodo"
        md["publisher"] = "Zenodo"
        api(session, base, "PUT", "/api/deposit/depositions/%s" % rid,
            json={"metadata": md})
        back = api(session, base, "GET", "/api/deposit/depositions/%s" % rid).json()
        bmd = back.get("metadata") or {}
        got = bmd.get("imprint_publisher") or bmd.get("publisher")
        print("  %-28s was=%s  now=%r  %s"
              % (row["slug"], before, got, "OK" if got else "STILL NOT SET"))
    print("\nNothing was published.")


def update_metadata(session, base, cfg, defaults, production):
    """Re-send metadata to existing drafts. Zenodo refuses to publish without a
    publisher field, which the original payload omitted; this repairs all four drafts
    identically rather than hand-editing each in the web form."""
    f = REPO / "tools" / ("zenodo_drafts_%s.json" % ("production" if production else "sandbox"))
    if not f.exists():
        raise SystemExit("no draft summary at %s" % f)
    rows = {r["slug"]: r for r in json.loads(f.read_text(encoding="utf-8"))}
    for dep in cfg["depositions"]:
        row = rows.get(dep["slug"])
        if not row:
            continue
        rid = row["record_id"]
        cur = api(session, base, "GET", "/api/records/%s/draft" % rid).json()
        md = build_metadata(defaults, dep)
        body = {"access": cur.get("access", {"record": "public", "files": "public"}),
                "files": {"enabled": True},
                "metadata": md}
        api(session, base, "PUT", "/api/records/%s/draft" % rid, json=body)
        print("  %-28s publisher=%r  updated  %s"
              % (dep["slug"], md["publisher"], row["draft_url"]))
    print("\nMetadata updated on all drafts. Nothing was published.")


def list_mine(session, base):
    """Ask Zenodo what this account actually owns, with DOIs and publish state.

    Searching the public index is unreliable right after publishing, and a legacy
    deposit's id is not the published record's id, so guessing URLs from outside does
    not work. This asks authoritatively."""
    for path in ("/api/deposit/depositions?size=50&sort=mostrecent",
                 "/api/user/records?size=50&sort=newest"):
        try:
            r = api(session, base, "GET", path)
        except SystemExit as e:
            print("  %s -> %s" % (path, str(e).splitlines()[0])); continue
        data = r.json()
        items = data if isinstance(data, list) else data.get("hits", {}).get("hits", [])
        print("\n=== %s — %d item(s) ===" % (path.split("?")[0], len(items)))
        for d in items:
            md = d.get("metadata", {}) or {}
            title = (md.get("title") or d.get("title") or "")[:52]
            doi = (d.get("doi") or (d.get("pids", {}).get("doi", {}) or {}).get("identifier"))
            concept = (d.get("conceptdoi")
                       or ((d.get("parent", {}) or {}).get("pids", {}) or {})
                       .get("doi", {}).get("identifier"))
            state = d.get("state") or ("published" if d.get("is_published") else "draft")
            print("  id=%-10s rec=%-10s %-10s" % (d.get("id"), d.get("record_id") or "-", state))
            print("     title  : %s" % title)
            print("     doi    : %s" % doi)
            print("     concept: %s" % concept)
            if d.get("links", {}).get("record_html") or d.get("links", {}).get("self_html"):
                print("     url    : %s" % (d["links"].get("record_html")
                                            or d["links"].get("self_html")))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sandbox", action="store_true", default=True,
                    help="use sandbox.zenodo.org (default)")
    ap.add_argument("--production", action="store_true",
                    help="use zenodo.org — still drafts only, never published")
    ap.add_argument("--only", metavar="SLUG", help="deposit a single volume")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the payloads and send nothing")
    ap.add_argument("--fix-publisher", action="store_true",
                    help="set the publisher on legacy depositions so Zenodo will publish")
    ap.add_argument("--list", action="store_true", dest="list_mine",
                    help="list the depositions/records this account owns, with DOIs")
    ap.add_argument("--update-metadata", action="store_true",
                    help="re-send metadata to existing drafts (e.g. after adding a field)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-upload only the files of an existing draft whose bytes changed")
    ap.add_argument("--verify", action="store_true",
                    help="read back the drafts already created and check their metadata")
    ap.add_argument("--check", action="store_true",
                    help="preflight: report what the token is allowed to do, then clean up")
    ap.add_argument("--allow-unset-license", action="store_true",
                    help="proceed even though licence is null")
    a = ap.parse_args()

    base = PRODUCTION if a.production else SANDBOX
    cfg = yaml.safe_load(META.read_text(encoding="utf-8"))
    defaults, deps = cfg["defaults"], cfg["depositions"]
    if a.only:
        deps = [d for d in deps if d["slug"] == a.only]
        if not deps:
            raise SystemExit("no deposition with slug %r" % a.only)

    if not (a.check or a.verify or a.refresh or a.update_metadata or a.list_mine
            or a.fix_publisher) and not defaults.get("license") and not all(d.get("license") for d in deps):
        if not a.allow_unset_license:
            raise SystemExit(
                "licence is null in tools/zenodo_metadata.yaml.\n"
                "Zenodo requires a licence for open-access records. Set one, or pass\n"
                "--allow-unset-license to create drafts without it and set it in the UI.")

    token = os.environ.get("ZENODO_TOKEN")
    session = requests.Session()
    if not a.dry_run:
        if not token:
            raise SystemExit(
                "ZENODO_TOKEN is not set in this shell. It does not survive a new\n"
                "terminal, so export it again here:\n"
                "  export ZENODO_TOKEN=...\n"
                "Sandbox and production tokens are not interchangeable. Grant BOTH\n"
                "deposit:write and deposit:actions — Zenodo refuses record creation\n"
                "with deposit:write alone. This script still never publishes: there is\n"
                "no call to the publish action anywhere in it.")
        session.headers["Authorization"] = "Bearer %s" % clean_token(token)

    if a.check:
        check(session, base)
        return
    if a.verify:
        verify(session, base, a.production)
        return
    if a.refresh:
        refresh(session, base, cfg, defaults, a.production)
        return
    if a.fix_publisher:
        fix_publisher(session, base, cfg, a.production)
        return
    if a.list_mine:
        list_mine(session, base)
        return
    if a.update_metadata:
        update_metadata(session, base, cfg, defaults, a.production)
        return

    print("target: %s   mode: DRAFTS ONLY (this script cannot publish)" % base)
    results = [r for r in (deposit(session, base, cfg, defaults, d, a.dry_run) for d in deps) if r]
    if results:
        out = REPO / "tools" / ("zenodo_drafts_%s.json" % ("production" if a.production else "sandbox"))
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\n%d draft(s) created. Summary written to %s" % (len(results), out.relative_to(REPO)))
        print("Nothing was published.")


if __name__ == "__main__":
    main()
