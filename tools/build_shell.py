#!/usr/bin/env python3
"""
build_shell.py — bake the multilingual Morphysm pamphlet shell.

Source of truth (editable):
  - English caption/body : panels/panel-XX-*/panel.md   (verified against index.html)
  - English structure    : index.html  (panel order, image src, alt, summary verb, dark panels via id)
  - uk / ru / pt content : uk/index.html, ru/index.html, pt/index.html

Output:
  - index.html  (single static shell — English baked in DOM for no-JS/crawlers,
                 uk/ru/pt baked into a JS DATA object, swapped in place by the
                 verbatim burn transition from morphysm-lang-switch.html)

No runtime fetch, no markdown parsing on Pages: everything is baked at build time.
"""
import re, json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML_LANG = {"en": "en", "uk": "uk", "ru": "ru", "pt": "pt-BR"}
LANGS = ["en", "uk", "ru", "pt"]

# ---------------------------------------------------------------- parsers
SEC_RE = re.compile(r'<section class="panel" id="(panel-\d+)">(.*?)</section>', re.S)

def parse_html(path):
    txt = path.read_text(encoding="utf-8")
    title = (re.search(r"<title>(.*?)</title>", txt, re.S) or [None, ""])[1].strip()
    desc  = (re.search(r'<meta name="description" content="(.*?)">', txt, re.S) or [None, ""])[1]
    foot  = re.search(r"<footer>.*?<img[^>]*alt=\"([^\"]*)\".*?<p[^>]*>(.*?)</p>", txt, re.S)
    sigil_alt = foot.group(1) if foot else "Morphysm sigil"
    footer    = foot.group(2).strip() if foot else ""
    panels = []
    for pid, block in SEC_RE.findall(txt):
        src = (re.search(r'<img src="([^"]+)"', block) or [None, ""])[1]
        alt = (re.search(r'alt="([^"]*)"', block) or [None, ""])[1]
        eager = 'loading="eager"' in block
        cap = (re.search(r"<figcaption[^>]*>(.*?)</figcaption>", block, re.S) or [None, ""])[1].strip()
        summ = (re.search(r"<summary>(.*?)</summary>", block, re.S) or [None, ""])[1].strip()
        content = (re.search(r'<div class="panel-body-content">(.*?)</div>', block, re.S) or [None, ""])[1]
        body = [p.strip() for p in re.findall(r"<p>(.*?)</p>", content, re.S)]
        panels.append(dict(id=pid, src=src, alt=alt, eager=eager,
                           caption=cap, summary=summ, body=body))
    return dict(title=title, desc=desc, footer=footer, sigil_alt=sigil_alt, panels=panels)

def parse_panel_md(md_dir):
    """Return (caption, [body paragraphs]) from a panel.md."""
    md = (md_dir / "panel.md").read_text(encoding="utf-8")
    cap = ""
    m = re.search(r"## Caption\s*\n+\*\*(.*?)\*\*", md, re.S)
    if m:
        cap = m.group(1).strip()
    body = []
    m = re.search(r"## Body \(expandable\)\s*\n(.*?)\n## ", md, re.S)
    if m:
        chunk = m.group(1).strip()
        body = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", chunk) if p.strip()]
    return cap, body

# ---------------------------------------------------------------- gather
report = []
en = parse_html(ROOT / "index.html")
meta = [dict(id=p["id"], src=p["src"], eager=p["eager"]) for p in en["panels"]]
N = len(meta)

# verify English panel.md == live index.html (do not alter English text)
md_dirs = sorted([d for d in (ROOT / "panels").iterdir() if d.is_dir()])
en_from_md_ok = True
mismatches = []
for i, d in enumerate(md_dirs):
    cap, body = parse_panel_md(d)
    live = en["panels"][i]
    if cap != live["caption"] or body != live["body"]:
        en_from_md_ok = False
        mismatches.append(live["id"])
report.append(f"English panel.md vs live index.html: "
              + ("identical for all 11 panels ✓" if en_from_md_ok
                 else f"MISMATCH in {mismatches} — using live index.html text, panel.md NOT applied"))

langs = {}
status = {}
# English (authoritative, from index.html so text is provably unaltered)
langs["en"] = dict(htmlLang=HTML_LANG["en"], title=en["title"], desc=en["desc"],
                   footer=en["footer"], sigilAlt=en["sigil_alt"], summary=en["panels"][0]["summary"],
                   panels=[dict(caption=p["caption"], alt=p["alt"], body=p["body"]) for p in en["panels"]])
status["en"] = "live (default)"

FOLDER = {"uk": "uk", "ru": "ru", "pt": "pt-br"}  # lowercase scheme; pt content lives in pt-br/
for lang in ["uk", "ru", "pt"]:
    path = ROOT / FOLDER[lang] / "index.html"
    if not path.exists():
        langs[lang] = json.loads(json.dumps(langs["en"]))
        langs[lang]["htmlLang"] = HTML_LANG[lang]
        status[lang] = "FALLBACK → English (source file missing) — TODO translate"
        continue
    p = parse_html(path)
    if len(p["panels"]) != N:
        langs[lang] = json.loads(json.dumps(langs["en"]))
        langs[lang]["htmlLang"] = HTML_LANG[lang]
        status[lang] = f"FALLBACK → English (panel count {len(p['panels'])}≠{N}) — TODO fix"
        continue
    # per-panel: fall back to EN for any empty panel, note it
    panels, fellback = [], []
    for i, pp in enumerate(p["panels"]):
        if pp["caption"] and pp["body"]:
            panels.append(dict(caption=pp["caption"], alt=pp["alt"], body=pp["body"]))
        else:
            ep = en["panels"][i]
            panels.append(dict(caption=ep["caption"], alt=ep["alt"], body=ep["body"]))
            fellback.append(pp["id"])
    langs[lang] = dict(htmlLang=HTML_LANG[lang], title=p["title"], desc=p["desc"],
                       footer=p["footer"], sigilAlt=p["sigil_alt"],
                       summary=p["panels"][0]["summary"], panels=panels)
    status[lang] = "live" + (f" (panels {fellback} fell back to EN — TODO)" if fellback else "")

DATA = dict(meta=meta, langs=langs)

# ---------------------------------------------------------------- render helpers
def panel_html(m, pl, summary, indent="  "):
    loading = "eager" if m["eager"] else "lazy"
    body = "\n        ".join(f"<p>{t}</p>" for t in pl["body"])
    return (f'{indent}<section class="panel" id="{m["id"]}">\n'
            f'{indent}  <figure class="panel-image">\n'
            f'{indent}    <img src="{m["src"]}" alt="{pl["alt"]}" loading="{loading}">\n'
            f'{indent}    <figcaption class="panel-caption">{pl["caption"]}</figcaption>\n'
            f'{indent}  </figure>\n'
            f'{indent}  <details class="panel-body">\n'
            f'{indent}    <summary>{summary}</summary>\n'
            f'{indent}    <div class="panel-body-content">\n'
            f'        {body}\n'
            f'{indent}    </div>\n'
            f'{indent}  </details>\n'
            f'{indent}</section>')

static_en = "\n\n".join(panel_html(meta[i], langs["en"]["panels"][i], langs["en"]["summary"])
                        for i in range(N))

# inline SVG flags — VERBATIM from morphysm-lang-switch.html (British flag kept for EN)
FLAGS_JS = r'''const FLAGS = {
  en:{code:"EN", name:"English", svg:`<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#012169"/><path d="M0 0l60 40M60 0L0 40" stroke="#fff" stroke-width="8"/><path d="M0 0l60 40M60 0L0 40" stroke="#C8102E" stroke-width="4"/><path d="M30 0v40M0 20h60" stroke="#fff" stroke-width="13"/><path d="M30 0v40M0 20h60" stroke="#C8102E" stroke-width="7"/></svg>`},
  uk:{code:"UK", name:"Українська", svg:`<svg viewBox="0 0 60 40"><rect width="60" height="20" fill="#0057B7"/><rect y="20" width="60" height="20" fill="#FFD700"/></svg>`},
  ru:{code:"RU", name:"Русский", svg:`<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#fff"/><rect y="13.3" width="60" height="13.4" fill="#0039A6"/><rect y="26.7" width="60" height="13.3" fill="#D52B1E"/></svg>`},
  pt:{code:"PT", name:"Português (BR)", svg:`<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#009C3B"/><path d="M30 4 56 20 30 36 4 20Z" fill="#FFDF00"/><circle cx="30" cy="20" r="8" fill="#002776"/></svg>`}
};'''

data_js = "const DATA = " + json.dumps(DATA, ensure_ascii=False, indent=0).replace("\n", "") + ";"

HTML = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{en["title"]}</title>
  <meta name="description" content="{en["desc"]}">

  <meta property="og:title" content="{en["title"]}">
  <meta property="og:description" content="{en["desc"]}">
  <meta property="og:image" content="https://morphysm.github.io/no-thing/assets/og-card.png">
  <meta property="og:type" content="article">

  <style>
    /*
     * FONTS
     * System serif fallback for scaffold.
     * TODO: Replace with @font-face for EB Garamond or Cormorant Garamond
     * once font files are provided. No Google Fonts CDN.
     */
    :root {{
      --serif: Georgia, 'Times New Roman', serif;
      --bg:              #f0ede4;
      --fg:              #1a1a1a;
      --bg-dark:         #111111;
      --fg-dark:         #f0f0f0;
      --placeholder-bg:  #c8c4bc;
      --placeholder-dark:#2a2a2a;
      --body-max:        600px;
      --caption-size:    clamp(1.1rem, 3.2vw, 1.875rem);
      --ember:#ff5b1f; --ember-soft:#ff8a3d; --flagline:#1c1b1f; --flagdim:#6f6a63;
    }}

    *, *::before, *::after {{
      box-sizing: border-box;
    }}

    html, body {{
      margin: 0;
      padding: 0;
    }}

    body {{
      background-color: var(--bg);
      color: var(--fg);
      font-family: var(--serif);
    }}

    /* === PANEL === */

    .panel {{
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}

    /* === IMAGE ZONE === */

    .panel-image {{
      position: relative;
      background-color: var(--placeholder-bg);
      flex-shrink: 0;
    }}

    .panel-image img {{
      width: 100%;
      display: block;
    }}

    /* Caption: upper-left corner, overlaid on image */
    .panel-caption {{
      position: absolute;
      top: 1.25rem;
      left: 1.25rem;
      font-family: var(--serif);
      font-size: var(--caption-size);
      font-style: italic;
      color: var(--fg);
      line-height: 1.2;
      max-width: 58%;
      z-index: 1;
    }}

    /* === BODY TEXT ZONE === */

    .panel-body {{
      flex-grow: 1;
      max-width: var(--body-max);
      width: 100%;
      margin: 0 auto;
      padding: 2rem 1.25rem 2.5rem;
    }}

    .panel-body > summary {{
      font-family: var(--serif);
      font-size: 0.8125rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      cursor: pointer;
      list-style: none;
      padding: 0.5rem 0;
      border-bottom: 1px solid currentColor;
      color: var(--fg);
    }}

    .panel-body > summary::-webkit-details-marker {{
      display: none;
    }}

    .panel-body > summary::marker {{
      display: none;
    }}

    .panel-body-content {{
      padding-top: 1.75rem;
    }}

    .panel-body-content p {{
      font-size: 1rem;
      line-height: 1.75;
      margin: 0 0 1.25em;
    }}

    .panel-body-content p:last-child {{
      margin-bottom: 0;
    }}

    /* === DARK PANELS (9 and 10) === */

    #panel-09,
    #panel-10 {{
      background-color: var(--bg-dark);
      color: var(--fg-dark);
    }}

    #panel-09 .panel-image,
    #panel-10 .panel-image {{
      background-color: var(--placeholder-dark);
    }}

    #panel-09 .panel-caption,
    #panel-10 .panel-caption,
    #panel-09 .panel-body > summary,
    #panel-10 .panel-body > summary,
    #panel-09 .panel-body-content p,
    #panel-10 .panel-body-content p {{
      color: var(--fg-dark);
    }}

    /* === PANEL 00 — dark image, light caption === */

    #panel-00 .panel-caption {{
      color: var(--fg-dark);
    }}

    /* === PANELS 05, 07, 08 — dark images, light captions only === */

    #panel-05 .panel-caption,
    #panel-07 .panel-caption,
    #panel-08 .panel-caption {{
      color: var(--fg-dark);
    }}

    /* === PANEL 05 — bright sky requires legible backdrop on desktop === */

    @media (min-width: 769px) {{
      #panel-05 .panel-caption {{
        background: rgba(8, 2, 2, 0.60);
        padding: 0.45em 0.7em 0.45em 0.6em;
        border-left: 2px solid rgba(155, 28, 18, 0.65);
        border-radius: 0 2px 2px 0;
        text-shadow: 0 1px 4px rgba(0, 0, 0, 0.85);
      }}
    }}

/* === FOOTER === */

    footer {{
      background-color: var(--bg-dark);
      color: var(--fg-dark);
      text-align: center;
      padding: 3rem 1.25rem 4rem;
      font-size: 0.875rem;
      letter-spacing: 0.1em;
    }}

    footer p {{
      margin: 0;
    }}

    /* === OFFERING — the sigil itself is a quiet Ko-fi link ===
       breathe (resting pulse) + ignite (ember glow on hover/focus).
       NOTE: authored from description; morphysm-sigil-offering.html was not on disk. */

    .offering {{
      display: inline-block;
      line-height: 0;
      border-radius: 50%;
      text-decoration: none;
      outline: none;
    }}
    .sigil-mark {{
      display: block;
      margin: 0 auto 1.5rem;
      width: 72px;
      height: auto;
      opacity: 0.7;
      transition: opacity .5s ease, filter .5s ease, transform .5s ease;
      animation: sigil-breathe 5.5s ease-in-out infinite;
    }}
    @keyframes sigil-breathe {{
      0%, 100% {{ opacity: 0.55; filter: drop-shadow(0 0 2px rgba(255, 91, 31, 0.10)); }}
      50%      {{ opacity: 0.85; filter: drop-shadow(0 0 7px rgba(255, 91, 31, 0.28)); }}
    }}
    .offering:hover .sigil-mark,
    .offering:focus-visible .sigil-mark {{
      animation: none;                 /* ignite overrides the resting breathe */
      opacity: 1;
      transform: scale(1.04);
      filter: drop-shadow(0 0 10px rgba(255, 138, 61, 0.85))
              drop-shadow(0 0 22px rgba(255, 91, 31, 0.55));
    }}
    @media (prefers-reduced-motion: reduce) {{
      .sigil-mark {{ animation: none; opacity: 0.7; }}
    }}

    /* === LANGUAGE FLAG BAR (from morphysm-lang-switch.html) === */

    .flags {{
      position: fixed; top: 0; left: 0; right: 0; z-index: 60;
      display: flex; gap: 12px; justify-content: center;
      padding: 10px 12px 18px;
      background: linear-gradient(to bottom, rgba(7,7,8,0.92) 35%, rgba(7,7,8,0));
    }}
    .flag {{
      width: 42px; height: 28px; padding: 0; border: 1px solid var(--flagline);
      background: #000; cursor: pointer; border-radius: 2px; overflow: hidden;
      filter: grayscale(.55) brightness(.7);
      transition: filter .35s, transform .35s, box-shadow .35s; position: relative;
    }}
    .flag svg {{ display: block; width: 100%; height: 100%; }}
    .flag:hover {{ filter: grayscale(0) brightness(1); transform: translateY(-2px);
      box-shadow: 0 0 0 1px var(--ember), 0 6px 22px -8px var(--ember); }}
    .flag[aria-current="true"] {{ filter: grayscale(0) brightness(1.05);
      box-shadow: 0 0 0 1px var(--ember-soft); }}
    .flag .code {{
      position: absolute; inset: auto 0 -14px 0; text-align: center;
      font-family: ui-monospace, Menlo, Consolas, monospace;
      font-size: 8px; letter-spacing: .18em; color: var(--flagdim);
    }}

    /* === BURN-TRANSITION CANVAS + content cross-fade === */

    #fx {{ position: fixed; inset: 0; pointer-events: none; z-index: 50; }}
    #pamphlet {{ transition: opacity .28s ease; }}
    #pamphlet.gone {{ opacity: 0; }}

    @media (max-width: 768px) {{
      .panel-caption {{
        position: static;
        padding: 0.75rem 1.25rem 0;
      }}

      /* These panels set light caption colour for dark-image overlay.
         Below the image on a light background they must revert to dark. */
      #panel-00 .panel-caption,
      #panel-05 .panel-caption,
      #panel-07 .panel-caption,
      #panel-08 .panel-caption {{
        color: var(--fg);
      }}
    }}

    @media (min-width: 768px) {{
      .panel-body {{
        padding: 2.5rem 2rem 3rem;
      }}

      .panel-caption {{
        top: 1.5rem;
        left: 1.5rem;
      }}
    }}
  </style>
</head>
<body>

<nav class="flags" id="flags" aria-label="Language"></nav>

<main id="pamphlet">

{static_en}

</main>

<footer>
  <a class="offering" href="https://ko-fi.com/alexandercripple" target="_blank" rel="noopener" title="Support the work — Ko-fi">
    <img id="sigil-img" class="sigil-mark" src="assets/morphysm%20sigil%20STONE.png" alt="{en["sigil_alt"]}">
  </a>
  <p id="footer-credit">{en["footer"]}</p>
</footer>

<canvas id="fx"></canvas>

<script src="lang-data.js"></script>
<script>
/* Translations are pre-baked into lang-data.js (a static JS object literal generated at
   build time): no runtime fetch of panel sources, no client-side markdown parsing. */

/* ---- inline SVG flags (verbatim from morphysm-lang-switch.html) ---- */
{FLAGS_JS}

let current = "en";
const flagsEl = document.getElementById("flags");
const pamphletEl = document.getElementById("pamphlet");

function panelMarkup(m, pl, summary) {{
  const loading = m.eager ? "eager" : "lazy";
  const body = pl.body.map(t => `<p>${{t}}</p>`).join("\\n        ");
  return `  <section class="panel" id="${{m.id}}">
    <figure class="panel-image">
      <img src="${{m.src}}" alt="${{pl.alt}}" loading="${{loading}}">
      <figcaption class="panel-caption">${{pl.caption}}</figcaption>
    </figure>
    <details class="panel-body">
      <summary>${{summary}}</summary>
      <div class="panel-body-content">
        ${{body}}
      </div>
    </details>
  </section>`;
}}

function renderAll(lang) {{
  const L = DATA.langs[lang] || DATA.langs.en;
  document.documentElement.lang = L.htmlLang;
  if (L.title) document.title = L.title;
  const md = document.querySelector('meta[name="description"]');
  if (md && L.desc) md.setAttribute("content", L.desc);
  pamphletEl.innerHTML = DATA.meta
    .map((m, i) => panelMarkup(m, L.panels[i], L.summary)).join("\\n\\n");
  const fc = document.getElementById("footer-credit");
  if (fc && L.footer) fc.textContent = L.footer;
  const sg = document.getElementById("sigil-img");
  if (sg && L.sigilAlt) sg.alt = L.sigilAlt;
}}

function buildFlags() {{
  flagsEl.innerHTML = Object.entries(FLAGS).map(([k, f]) =>
    `<button class="flag" data-lang="${{k}}" aria-current="${{k === current}}"
       title="${{f.name}}">${{f.svg}}<span class="code">${{f.code}}</span></button>`).join("");
  flagsEl.querySelectorAll(".flag").forEach(b =>
    b.addEventListener("click", () => switchTo(b.dataset.lang)));
}}
function syncCurrent() {{
  flagsEl.querySelectorAll(".flag").forEach(b =>
    b.setAttribute("aria-current", b.dataset.lang === current));
}}

/* ---------- the disintegration (canvas + spawn/step verbatim) ---------- */
const cv = document.getElementById("fx"), ctx = cv.getContext("2d");
let DPR = Math.min(devicePixelRatio || 1, 2);
function fit() {{ cv.width = innerWidth * DPR; cv.height = innerHeight * DPR;
  cv.style.width = innerWidth + "px"; cv.style.height = innerHeight + "px"; }}
addEventListener("resize", fit); fit();

let busy = false;
function switchTo(lang) {{
  if (busy || lang === current) return;
  if (!DATA.langs[lang]) lang = "en";
  busy = true;
  const r = {{ left: 0, top: 0, width: innerWidth, height: innerHeight }}; // burn the viewport
  const parts = spawn(r);
  pamphletEl.classList.add("gone");          // old text fades as embers rise
  const t0 = performance.now();
  let swapped = false;
  (function frame(now) {{
    const t = Math.min((now - t0) / 1700, 1); // total ~1.7s
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.globalCompositeOperation = "lighter";
    for (const p of parts) step(p, t);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    if (!swapped && t > 0.46) {{                // midpoint: burn → dust, content swaps
      current = lang; renderAll(lang); syncCurrent();
      pamphletEl.classList.remove("gone");
      swapped = true;
    }}
    if (t < 1) {{ requestAnimationFrame(frame); }}
    else {{ ctx.clearRect(0, 0, cv.width, cv.height); busy = false; }}
  }})(t0);
}}

/* soft radial fire sprites — built once, drawn additively so the blobs
   overlap into a continuous sheet of flame instead of discrete sparkles */
function makeSprite(stops) {{
  const d = 128, c = document.createElement("canvas");
  c.width = c.height = d;
  const g = c.getContext("2d");
  const gr = g.createRadialGradient(d / 2, d / 2, 0, d / 2, d / 2, d / 2);
  for (const s of stops) gr.addColorStop(s[0], s[1]);
  g.fillStyle = gr; g.fillRect(0, 0, d, d);
  return c;
}}
const SPRITE_HOT = makeSprite([  // yellow-white core flames
  [0, "rgba(255,247,210,1)"], [0.22, "rgba(255,212,64,0.95)"],
  [0.55, "rgba(255,92,12,0.40)"], [1, "rgba(255,40,0,0)"]]);
const SPRITE_RED = makeSprite([  // deep red tongues
  [0, "rgba(255,140,28,0.95)"], [0.40, "rgba(226,28,6,0.55)"],
  [1, "rgba(110,0,0,0)"]]);

function spawn(r) {{
  const N = Math.min(Math.floor(r.width * r.height / 900), 900);
  const a = [];
  for (let i = 0; i < N; i++) {{
    a.push({{
      x: (r.left + Math.random() * r.width) * DPR,
      y: (r.top + (0.2 + Math.random() * 0.8) * r.height) * DPR, // rise from below
      vx: (Math.random() - 0.5) * 0.6 * DPR,
      vy: -(1.4 + Math.random() * 3.6) * DPR,                    // strong, varied updraft
      sway: (0.6 + Math.random() * 1.6) * DPR,
      sz: 11 + Math.random() * 30,                              // big, soft, overlapping
      a0: 0.35 + Math.random() * 0.5,
      tw: Math.random() * 6.28,
      hot: Math.random() < 0.62,                               // yellow cores vs red tongues
      seed: Math.random()
    }});
  }}
  return a;
}}
function step(p, t) {{
  // one continuous updraft: blobs rise, sway, swell, then burn out — no twinkle
  p.x += p.vx + Math.sin(t * 6 + p.tw) * p.sway;
  p.y += p.vy;
  p.vy *= 1.012;                                            // accelerate as it consumes
  const env = t < 0.5 ? (t / 0.5) : (1 - (t - 0.5) / 0.5); // build, then die by t=1
  let a = Math.max(0, env) * p.a0 * (0.9 + 0.1 * Math.sin(t * 7 + p.tw)); // gentle breathe
  if (a <= 0) return;
  const s = (p.sz * (1 + t * 1.7)) * DPR;                  // flames grow as the fire builds
  ctx.globalAlpha = a < 1 ? a : 1;
  ctx.drawImage(p.hot ? SPRITE_HOT : SPRITE_RED, p.x - s / 2, p.y - s / 2, s, s);
}}

/* init — English already in the DOM statically (no-JS / crawler safe) */
buildFlags(); syncCurrent();
</script>

</body>
</html>
'''

(ROOT / "index.html").write_text(HTML, encoding="utf-8")
(ROOT / "lang-data.js").write_text(
    "// AUTO-GENERATED by tools/build_shell.py — do not hand-edit.\n"
    "// Source of truth: panels (EN panel.md) and uk|ru|pt-br/index.html.\n"
    "// Baked content keyed by language + panel index; consumed by index.html.\n"
    + data_js + "\n", encoding="utf-8")

print("=== BUILD REPORT ===")
for line in report:
    print(line)
print(f"panels: {N}")
for lang in LANGS:
    print(f"  {lang:>2} ({HTML_LANG[lang]}): {status[lang]}")
print(f"wrote {ROOT / 'index.html'} ({len((ROOT/'index.html').read_text(encoding='utf-8'))} bytes)")
print(f"wrote {ROOT / 'lang-data.js'} ({len((ROOT/'lang-data.js').read_text(encoding='utf-8'))} bytes)")
