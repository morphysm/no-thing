#!/usr/bin/env python3
"""Submit the live corpus URLs to the Wayback Machine, authenticated.

Anonymous Save Page Now is rate-limited hard enough that a 50-URL run gets throttled
part-way. This reads the S3 keys the `ia` CLI already stores and uses the authenticated
endpoint, which has a far higher limit. Credentials are read by this script and used
only as an Authorization header; they are never printed or logged.

Skips URLs already captured today unless --force is given, so a re-run after a partial
failure only submits what is actually missing.
"""
import argparse, configparser, json, os, pathlib, sys, time, urllib.error, urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent


def keys():
    for p in (pathlib.Path.home() / ".config/internetarchive/ia.ini",
              pathlib.Path.home() / ".config/ia.ini", pathlib.Path.home() / ".ia"):
        if p.exists():
            c = configparser.ConfigParser(); c.read(p)
            if c.has_section("s3"):
                return c["s3"].get("access"), c["s3"].get("secret")
    sys.exit("no archive.org S3 keys found — run `ia configure` first")


def already_today(url):
    try:
        req = urllib.request.Request(
            "https://archive.org/wayback/available?url=" + urllib.request.quote(url, safe=""),
            headers={"User-Agent": "morphysm-corpus/1.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            snap = json.load(r).get("archived_snapshots", {}).get("closest")
        return snap and snap.get("timestamp", "")[:8] == time.strftime("%Y%m%d")
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="resubmit even if captured today")
    ap.add_argument("--delay", type=float, default=20.0)
    ap.add_argument("--only-missing", action="store_true",
                    help="submit only URLs with no capture from today")
    a = ap.parse_args()

    access, secret = keys()
    man = json.loads((REPO / "corpus" / "manifest.json").read_text(encoding="utf-8"))
    SITE = "https://morphysm.github.io/no-thing"
    ROOT = "https://morphysm.github.io"
    urls = [ROOT + "/", ROOT + "/llms.txt", ROOT + "/robots.txt", ROOT + "/sitemap.xml",
            SITE + "/", SITE + "/uk/", SITE + "/ru/", SITE + "/pt-br/",
            SITE + "/llms.txt", SITE + "/llms-full.txt", SITE + "/LICENSE",
            SITE + "/corpus/manifest.json", SITE + "/corpus/SHA256SUMS"]
    urls += [e["url"] for e in man["texts"]]

    ok = skipped = failed = 0
    for i, u in enumerate(urls, 1):
        if (a.only_missing or not a.force) and already_today(u):
            print("  [%2d/%d] skip (captured today)  %s" % (i, len(urls), u), flush=True); skipped += 1; continue
        data = urllib.parse_qs = ("url=%s&capture_all=1" % urllib.request.quote(u, safe="")).encode()
        req = urllib.request.Request("https://web.archive.org/save",
                                     data=data, method="POST",
                                     headers={"Accept": "application/json",
                                              "Content-Type": "application/x-www-form-urlencoded",
                                              "Authorization": "LOW %s:%s" % (access, secret),
                                              "User-Agent": "morphysm-corpus/1.0"})
        # Save Page Now throttles by rate AND concurrency; 429 is routine, not fatal.
        wait = a.delay
        for attempt in range(1, 7):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    body = r.read().decode("utf-8", "replace")
                job = ""
                try:
                    job = json.loads(body).get("job_id", "")
                except Exception:
                    pass
                print("  [%2d/%d] queued %-14s %s" % (i, len(urls), job[:14], u), flush=True)
                ok += 1
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 6:
                    back = 30 * attempt
                    print("  [%2d/%d] 429, waiting %ds (%d/5)  %s"
                          % (i, len(urls), back, attempt, u), flush=True)
                    time.sleep(back); continue
                print("  [%2d/%d] HTTP %s      %s" % (i, len(urls), e.code, u), flush=True)
                failed += 1; break
            except Exception as e:
                print("  [%2d/%d] %-14s %s" % (i, len(urls), type(e).__name__, u), flush=True)
                failed += 1; break
        time.sleep(wait)
    print("\nqueued %d, skipped %d, failed %d, of %d" % (ok, skipped, failed, len(urls)))


if __name__ == "__main__":
    main()
