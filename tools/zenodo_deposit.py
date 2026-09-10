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
import argparse, hashlib, json, os, pathlib, sys
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
    rel = dep.get("related_identifiers", defaults.get("related_identifiers", []))
    if rel:
        md["related_identifiers"] = [
            {"identifier": r["identifier"],
             "relation_type": {"id": r["relation"]},
             "scheme": r.get("scheme", "url")} for r in rel]
    return md


def api(session, base, method, path, **kw):
    r = session.request(method, base + path, timeout=120, **kw)
    if r.status_code >= 400:
        body = r.text[:800]
        raise SystemExit("Zenodo %s %s -> HTTP %d\n%s" % (method, path, r.status_code, body))
    return r


def deposit(session, base, defaults, dep, dry_run):
    files = [REPO / f for f in dep["files"]]
    for f in files:
        if not f.exists():
            raise SystemExit("missing file for %s: %s" % (dep["slug"], f))

    payload = {"access": {"record": "public", "files": "public"},
               "files": {"enabled": True},
               "metadata": build_metadata(defaults, dep)}

    print("\n=== %s ===" % dep["slug"])
    print("  title    : %s" % payload["metadata"]["title"])
    print("  creator  : %s (organizational, unsplit)"
          % payload["metadata"]["creators"][0]["person_or_org"]["name"])
    print("  type     : %s" % payload["metadata"]["resource_type"]["id"])
    print("  licence  : %s" % (payload["metadata"].get("rights") or "UNSET (null)"))
    for f in files:
        print("  file     : %-42s %9d B  sha256 %s"
              % (f.relative_to(REPO), f.stat().st_size,
                 hashlib.sha256(f.read_bytes()).hexdigest()[:16]))
    if dry_run:
        print("  --dry-run: payload below, nothing sent")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return None

    r = api(session, base, "POST", "/api/records", json=payload)
    rec = r.json()
    rid = rec["id"]

    for f in files:
        key = f.name
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

    if not defaults.get("license") and not all(d.get("license") for d in deps):
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
        session.headers["Authorization"] = "Bearer %s" % token

    print("target: %s   mode: DRAFTS ONLY (this script cannot publish)" % base)
    results = [r for r in (deposit(session, base, defaults, d, a.dry_run) for d in deps) if r]
    if results:
        out = REPO / "tools" / ("zenodo_drafts_%s.json" % ("production" if a.production else "sandbox"))
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\n%d draft(s) created. Summary written to %s" % (len(results), out.relative_to(REPO)))
        print("Nothing was published.")


if __name__ == "__main__":
    main()
