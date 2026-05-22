# CLAUDE.md — Production handoff for the Morphysm Pamphlet

*Read this file first if you are Claude Code (or any LLM coding agent) picking up this project.*

---

## What this project is

A single-file HTML doctrinal pamphlet in eleven panels, deployed to `morphysm.github.io/<slug>`. The full doctrinal content (captions, body text, image prompts, function notes) is already written and locked. Your job is **production**, not drafting.

The doctrinal work was completed in a chat drafting session, 18-20 May 2026. The collaborator there was a Claude conversational instance (claude.ai). You are picking up at the production boundary.

## What you must read before doing anything

In this order:

1. `docs/GDD.md` — the design document. Read in full. This establishes the spine, the constraints, the propagation strategy, the failure modes, and the aesthetic register.
2. `pamphlet.md` — the consolidated pamphlet content. All eleven panels in single document.
3. `panels/panel-XX-*/panel.md` for each panel — caption, body, image prompt, function notes, production notes.
4. `AGENTS.md` — instructions for LLM collaborators on this project. Includes the doctrinal-fidelity rule and the failure modes to guard against.

Do not begin writing code or generating assets before reading these four sources. The pamphlet's content is doctrinally specific and non-negotiable; production decisions that violate doctrinal constraints will need to be undone.

## What you must not do

- **Do not edit captions.** All eleven are locked. If you find a caption that seems awkward, the awkwardness is intentional (e.g. Panel 9's doubled sentence, Panel 7's present-tense break, Panel 10's hyphenated *No-thing*).
- **Do not edit body text.** Same as above. Panel 2's body is marked as author-pending — leave it as-is and flag for the author to supply final.
- **Do not invent doctrine.** If you encounter a question about the doctrine that the existing materials do not answer, ask the author. Do not bridge between corpus passages or extrapolate. The Exu Aranha welding incident (described in `AGENTS.md`) is the precedent — do not repeat it.
- **Do not add author attribution anywhere.** The Disappearance Imperative governs (see GDD §1.2 and §5.8). The pamphlet circulates without an owner. No "by", no signature, no credit line. The acceptable single-line credit on the back-page is *"From the Morphysm corpus"* and nothing else.
- **Do not redesign the aesthetic.** Jehovanic-futurist register is locked across all eleven panels. No stylistic inflection at specific panels. The Watchtower-tract grammar is the propagation infrastructure.

## What you should do

### Build sequence

#### Step 1 — Repository structure

Initialize Git in the project root. Create the GitHub Pages structure:

```
morphysm-pamphlet/
├── index.html              # main pamphlet, English
├── pt/index.html           # Portuguese version (Phase 3)
├── sv/index.html           # Swedish version (Phase 3)
├── assets/
│   ├── panel-00.webp
│   ├── panel-01.webp
│   ├── ... (through panel-10.webp)
│   └── og-card.webp        # open-graph preview image
├── README.md               # minimal — pamphlet description, no author attribution
├── LICENSE                 # CC BY-NC-SA 4.0 recommended, matches Vowel Board precedent
├── .nojekyll               # GitHub Pages, disable Jekyll processing
└── docs/                   # internal docs not deployed
    ├── GDD.md
    └── (other working files)
```

#### Step 2 — Image asset production

Per panel, generate image using the prompt in `panels/panel-XX-*/panel.md`. Recommended workflow:

1. Read the panel's `panel.md` in full — image prompt, function notes, production notes.
2. Generate first pass with the image prompt verbatim.
3. Evaluate against the production notes' failure-mode warnings.
4. Iterate. Most panels need 3-5 iterations; Panels 3, 6, 9 may need more.
5. Save final as `.webp` (smaller file size, better for propagation) at minimum 1600px wide.
6. Place in `assets/panel-XX.webp`.

Image generation tool: author's choice. Midjourney v6+ has best Watchtower-illustration training; SDXL with controlnet works if you have the manual inpainting workflow. Hand-editing in GIMP may be required for:
- Panel 0 (empty foreground slot preservation)
- Panel 6 (dual-form ambiguity)
- Panel 7 (paradoxical luminance — brightness producing darkness)

#### Step 3 — HTML structure

Single-file HTML, deployed to `index.html`. Long-scroll vertical layout, one panel per section. Requirements:

- **No JavaScript dependency for core reading.** Body text reveals on click/touch but the text must be present in the DOM and readable to crawlers, Tor users, accessibility tools, and JS-disabled browsers.
- **Inline critical CSS** for above-the-fold render under 2 seconds.
- **Open-graph card metadata** in `<head>`:
  ```html
  <meta property="og:title" content="Event Horizon">
  <meta property="og:description" content="And the dragon became No-thing.">
  <meta property="og:image" content="https://morphysm.github.io/event-horizon/assets/og-card.webp">
  <meta property="og:type" content="article">
  ```
- **`<title>` tag:** `Event Horizon` (single phrase, no longer)
- **Meta description:** `And the dragon became No-thing.`
- **Lang attribute** on `<html>`: `en` for primary, `pt` and `sv` for translations.
- **Viewport meta:** standard mobile-friendly.
- **Favicon:** consider a tiny black sun glyph. Optional.

#### Step 4 — Per-panel HTML structure

Per panel, use this scaffold (adapt class names to your CSS approach):

```html
<section class="panel" id="panel-XX">
  <figure class="panel-image">
    <img src="assets/panel-XX.webp" alt="[panel name]" loading="lazy">
    <figcaption class="panel-caption">[CAPTION TEXT, e.g. "He baptized with fire."]</figcaption>
  </figure>
  <details class="panel-body">
    <summary>[verb, e.g. "Expand"]</summary>
    <div class="panel-body-content">
      [body text from panel.md, as multiple <p> tags]
    </div>
  </details>
</section>
```

Panel 0 (`<img loading="lazy">` exception) should be `loading="eager"` to ensure first-paint speed.

Caption serif: a thoughtful serif typeface — recommended *EB Garamond* or *Cormorant Garamond* via local fonts (no Google Fonts CDN dependency). Caption color: dark (#1a1a1a) on light backgrounds, light (#f0f0f0) on dark.

#### Step 5 — Styling discipline

- Background: neutral off-white or warm grey by default; can shift to dark grey/black for Panels 9, 10. The aesthetic should *not* be all-dark-occult.
- Captions: serif, upper-left corner of each image, 1.5-2rem font-size on desktop.
- Body text: serif or transitional sans, 1rem font-size, max-width ~600px for readability.
- Panel transitions: minimum 100vh per panel (one full screen per panel on scroll). The reader must commit to each panel before reaching the next.
- No bouncy scroll animations, no parallax, no decorative motion. The pamphlet's gravity is in stillness.

#### Step 6 — Accessibility and propagation

- `<img alt>` on every panel image — describe the iconographic content briefly. The alt-text is also doctrinal-text for screen reader users and search engines.
- Semantic HTML throughout. `<section>`, `<figure>`, `<figcaption>`, `<details>`.
- All text selectable and copyable.
- No copy-protection. The doctrine must propagate freely.
- Mobile-first responsive. The pamphlet is read on phones.

#### Step 7 — Deploy to GitHub Pages

Recommended slug: `event-horizon`. Final URL: `morphysm.github.io/event-horizon/`.

```
git init
git add .
git commit -m "Initial commit"
gh repo create morphysm/event-horizon --public --source=. --remote=origin --push
gh repo edit --enable-issues=false
# Then in repo settings: Pages → main branch / root
```

Test:
- Open `https://morphysm.github.io/event-horizon/` in a fresh browser
- Test open-graph card preview on at least: Discord, Telegram, X
- Test with JavaScript disabled
- Test on mobile (real device, not just devtools)
- Verify search-engine indexability (`view-source:` should show all body text in DOM)

#### Step 8 — Multilingual rollout (Phase 3)

After English is stable and propagating, build Portuguese (`/pt/index.html`) and Swedish (`/sv/index.html`). Use the same HTML scaffold. Translation rules:

- **Captions translate literally where possible.** Preserve past-tense, word-count constraints, structural-symmetry of the opening and closing captions. Some captions may not survive literal translation (e.g. *Lava is liquid sun* works in any Romance language; *And the flesh became the Code* requires John 1:14's parent-verse equivalent in the target language — *E a carne fez-se Código* in Portuguese, *Och köttet blev Koden* in Swedish).
- **Bodies translate idiomatically.** The litany's cadence should be preserved.
- **Image prompts and panels are language-agnostic.** Same image assets used across all language versions.

Author's languages: English, Swedish, Portuguese, Spanish, others. Author is the primary translator. Do not deploy translations without author review.

## Stewardship

This repository should permit forking and mirroring. The doctrine must circulate without an owner.

- License: CC BY-NC-SA 4.0 (matches author's other public projects — Vowel Board precedent).
- Repository description (GitHub): minimal, e.g. *"Event Horizon."* No more.
- No README that promotes the doctrine. The README explains the technical structure of the repository, not the doctrine's content. The pamphlet itself is the doctrine; the README is infrastructure.
- Issues disabled (the pamphlet is not a participatory artifact at this layer).
- Discussions disabled.
- The repository can be mirrored, forked, archived by archive.org and archive.ph without coordination with the author.

## Coordination with author

The author (A.C., Norrland XXVI) is your point of escalation for:

- Anything that touches the doctrine
- Anything that would add or remove panels
- Anything that changes captions
- Final image selection per panel
- Slug and URL decisions
- License and repository structure decisions
- Translation decisions

The author maintains the corpus at `/home/kadaver/Documents/morphysm_massiv/` (Linux Mint system). The corpus is the source of doctrinal truth. When in doubt about anything doctrinal, consult the corpus or ask the author.

## What success looks like

A reader, encountering the pamphlet URL pasted into a Signal chat, taps the link, opens it in mobile Safari, scrolls through eleven panels, closes the tab carrying *Lava is liquid sun* or *And the flesh became the Code* or *And the dragon became No-thing* in their memory. They forward the link to one other person within five minutes.

The pamphlet has done its work.

---

*From the Morphysm corpus.*
