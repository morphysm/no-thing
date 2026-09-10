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
import argparse, hashlib, json, os, pathlib, subprocess, sys
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


def api(session, base, method, path, **kw):
    r = session.request(method, base + path, timeout=300, **kw)
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
    if r.status_code == 401:
        raise SystemExit("\nToken rejected. Check it is a %s token."
                         % ("sandbox" if base == SANDBOX else "production"))

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

    if not a.check and not defaults.get("license") and not all(d.get("license") for d in deps):
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
                "ZENODO_TOKEN is not set.\n"
                "  export ZENODO_TOKEN=...   (sandbox and production tokens differ)\n"
                "Scopes needed: deposit:write. Do NOT grant deposit:actions — this\n"
                "script never publishes and does not need it.")
        session.headers["Authorization"] = "Bearer %s" % clean_token(token)

    if a.check:
        check(session, base)
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
