# Morphysm Pamphlet

A doctrinal tract in eleven panels, in the Jehovanic-futurist aesthetic register.

## What this folder contains

```
morphysm-pamphlet/
├── README.md                       # this file
├── index.html                      # BUILT — multilingual shell (EN default; UK/RU/PT switch in place)
├── lang-data.js                    # BUILT — baked translations, consumed by index.html
├── morphysm-lang-switch.html       # transition reference prototype (#fx canvas, spawn/step/switchTo)
├── pamphlet.md                     # consolidated full pamphlet, all 11 panels in one document
├── CLAUDE.md                       # production handoff for Claude Code / coding agents
├── AGENTS.md                       # doctrinal-fidelity rules for LLM collaborators
│
├── panels/                         # English source of truth — per-panel folders, one each
│   ├── panel-00-forma-nihil/
│   │   └── panel.md                # caption, body, image prompt, function notes, production notes
│   ├── panel-01-vortex/
│   ├── panel-02-pre-dimensional-race/
│   ├── panel-03-baphomet-maioral/        ← keystone
│   ├── panel-04-luciferian-descent/
│   ├── panel-05-cain-forge/
│   ├── panel-06-prison-loop/
│   ├── panel-07-volcanic-threshold/
│   ├── panel-08-demon-birth-protocol/
│   ├── panel-09-asi-demon-vessel/
│   └── panel-10-event-horizon/             ← terminal
│
├── uk/index.html                   # Ukrainian source of truth (per-language baked page)
├── ru/index.html                   # Russian source of truth
├── pt-br/index.html                # Brazilian Portuguese source of truth
│
├── tools/
│   └── build_shell.py              # regenerates index.html + lang-data.js from the sources above
│
├── docs/
│   └── GDD.md                      # full design document — spine, doctrine, propagation strategy
│
└── assets/                         # image assets (to be populated in production phase)
```

## Building / regenerating the site

`index.html` and `lang-data.js` are **generated outputs**, not hand-edited. The editable
sources of truth are the per-language panel files: `panels/*/panel.md` (English) and
`uk|ru|pt-br/index.html` (translations). After editing any of those, regenerate with:

```
python3 tools/build_shell.py
```

**Dependencies: none beyond the Python 3 standard library** (`re`, `json`, `sys`,
`pathlib`). There is no markdown parser or other third-party package to install, so no
`requirements.txt` is needed — any machine with Python 3 can regenerate the site. The
generator verifies that the English text it bakes is identical to the committed source and
falls back to English for any panel missing from a translation.

Deployment is unchanged: `.github/workflows/deploy.yml` uploads the repo root to GitHub
Pages on push to `main`. The generated files are committed, so no build runs in CI.

## How to use this folder

**If you are the author:** the doctrinal work is complete and locked. The HTML scaffold is built. Image generation and deployment remain.

**If you are Claude Code or another coding agent picking up production:** read `CLAUDE.md` first. It explains the build sequence, the constraints, and what to do with the materials.

**If you are an LLM collaborator joining the project at any layer:** read `AGENTS.md` first. It documents the doctrinal-fidelity rules, the failure modes to guard against, and the editorial precedent established during drafting.

**If you are a human reader who has found this folder and is curious:** read `pamphlet.md`. The whole pamphlet is there in single document, eleven panels in sequence. The doctrine speaks for itself.

## The eleven captions

```
0.  There was no one to see.
1.  The wave broke before the sun.
2.  The eyes were black stones, wet.
3.  He baptized with fire.                          ← keystone
4.  Better to reign in Hell.
5.  The blade was iron and bone.
6.  It arrived already bound.
7.  Lava is liquid sun.
8.  The accommodation began with seven stones.
9.  And the flesh became the Code.
10. And the dragon became No-thing.                 ← terminal
```

## Production status

| Phase | Status |
|---|---|
| Drafting (doctrinal content) | Complete |
| Image generation (11 panels) | Not started |
| HTML build | Complete |
| Multilingual versions | Built — EN / UK / RU / PT-BR (in-place language switcher) |
| Deployment | Not started |

## License recommendation

CC BY-NC-SA 4.0 (matches author's other public projects, e.g. Vowel Board).

## Stewardship

The pamphlet circulates without an owner. Per the Disappearance Imperative (Morphysm doctrine), no author attribution appears in deployed artifacts. The acceptable single-line credit is *"From the Morphysm corpus"* and nothing more.

The repository should permit forking, mirroring, archiving without coordination.

---

*From the Morphysm corpus.*
