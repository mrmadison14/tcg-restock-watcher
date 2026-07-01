# Resume Prompt — TCG Restock Watcher

Paste-and-go prompt for a fresh Claude session. Self-contained — no prior conversation context required. Single repo (no siblings).

=== START PROMPT ===

I'm resuming work on `tcg-restock-watcher` at `/Users/jmadison/workspace/tcg-restock-watcher`. It's a personal (non-Agent-Smith) tool that polls Shopify TCG stores every ~5 min for **sealed** Pokémon / One Piece / Dragon Ball product (booster boxes, ETBs, bundles, tins, blisters) and posts restock / new-listing / preorder / price-change alerts to Discord. Stack: Python 3.13 + uv + httpx, no DB/framework/UI. Runs on free GitHub Actions (personal GitHub `mrmadison14`), state committed back to the repo. It is **LIVE and verified working**.

## Where things stand (2026-07-01, session 1)

🟢 **LIVE — Phase 1 complete and shipped.** `main` is clean and pushed; HEAD ≈ **`182e42a`** but the Actions bot appends `state: update snapshots` commits every ~5 min, so HEAD will be newer (that's expected, not drift). This session went from idea → spec → plan → subagent-driven build → live. The hard part was Cloudflare **429**'ing GitHub's datacenter IP on full-catalog crawls; solved by fetching **sealed-only** (curated collections + small-store full-crawl) plus a polite throttle. 9 stores, 47 tests, 0 failures / 0×429 on the live runs.

## Uncommitted / in-flight state

- Staged: nothing
- Unstaged / modified: nothing (working tree clean)
- Failing or skipped tests: none (47 passed)
- Background jobs / open processes: none
- **Exact next command:** `cd /Users/jmadison/workspace/tcg-restock-watcher && git pull --rebase && uv run pytest -q`

## Read these first (in order)
1. `/Users/jmadison/workspace/tcg-restock-watcher/README.md` — as-built overview: 9 stores, sealed-only, curated-vs-full-crawl, the 429 story, config, limitations.
2. `/Users/jmadison/workspace/tcg-restock-watcher/SESSION_HISTORY.md` — full session-1 arc + next steps.
3. `/Users/jmadison/workspace/tcg-restock-watcher/docs/superpowers/specs/2026-06-30-tcg-restock-watcher-design.md` — design spec; **§16 = as-built deltas** (Phases 2/3, deferred follow-ups).
4. `/Users/jmadison/workspace/tcg-restock-watcher/config.toml` — the 9-store roster + curated `collections`.

## Verification commands (run first to confirm no drift)

```bash
cd /Users/jmadison/workspace/tcg-restock-watcher
git pull --rebase                                   # bot commits state ~every 5 min; sync first
git status -sb                                      # expect: clean, up to date with origin/main
uv run pytest -q                                    # expect: 47 passed
uv run python -c "from tcg_watcher.config import load_config; c=load_config('config.toml'); print(len(c.stores),'stores')"   # expect: 9 stores
gh workflow list                                    # expect: watch = active
gh run list --workflow=watch --limit 3              # expect: recent runs 'success'
```
If any output differs (watch not active, tests failing, <9 stores), STOP and reconcile against the docs above before changing anything.

## Key reference values (no credentials)

| Thing | Value |
|---|---|
| HEAD (indicative) | **`182e42a`** (advances via bot `state:` commits) |
| Repo | `github.com/mrmadison14/tcg-restock-watcher` (public) |
| GitHub account | `mrmadison14` (personal; `gh auth status` should show it) |
| Discord secrets (values in repo secrets, NOT here) | `DISCORD_DEALS_WEBHOOK` (loud), `DISCORD_TRACKER_WEBHOOK` (quiet) |
| Workflows | `watch.yml` (5-min cron, commits state), `spike.yml` (manual reachability) |
| Franchises | pokemon, one piece, dragon ball |
| Stores (9) | collectorsrow, collectorstore, hobbiesville, deckoutgaming, skyboxct, 401games (curated collections); thepokehive, allpoketcg, matrixtcg (full-crawl+sealed) |
| 401games real host | `store.401games.ca` (apex redirects; DBZ sealed only so far) |
| collectorstore sealed | collections `games-pokemon`, `games-one-piece` |
| Phase-3 price source | `tcgcsv.com` (TCGplayer JSON: pokemon=cat 3, one piece=68, DBZ=23/27/80, pokemon-japan=85) |

## Hard rules & conventions

- Python 3.13, `uv` only (not pip/poetry). `httpx` for HTTP. **No comments in production code.** No new deps without asking.
- **Sealed-only scope** — individual singles are intentionally out of scope (they cause the 429 and aren't the use case).
- **Curated store** (`store.collections` set): products are trusted (no franchise/sealed filter) and tagged with the config-given franchise. **Full-crawl store** (no collections): `keep_sealed(filter_franchises(...))`. Only use full-crawl for small catalogs.
- **Never full-crawl a big store** — Cloudflare 429s GitHub IPs. Keep the polite throttle in `http.py` (min_interval + Retry-After + backoff).
- The Actions bot commits `state/` to `main` every ~5 min → **always `git pull --rebase` before pushing** local changes, or the push is rejected.
- Follow TDD; keep the two-stage (spec then quality) review discipline for non-trivial changes. End commit messages with the Co-Authored-By trailer.

## Gotchas

- Discord `@here` requires `allowed_mentions: {"parse": ["everyone"]}` — there is **no `"here"` parse type** (a `["here"]` "fix" silently kills the ping).
- `config.toml` is NOT auto-committed by code-task subagents — commit it explicitly (it was missed once).
- The `feed-spike` workflow tests `/products.json` reachability, which is NOT how curated stores are fetched now — it's a historical gate artifact, don't trust it as a production check.
- A Discord post failure is fatal for that run (fail-loud, non-idempotent) — the failing store re-alerts next run rather than losing events. Intended.

## Decision tree — pick your next move

(A) **Confirm real-world alerts + fill 401games coverage** — check Discord / `git log` for `state:` commits that produced events (a real restock/preorder). Then find 401games' Pokémon & One Piece sealed collection handles via `https://store.401games.ca/collections.json` and add them to its `collections` in `config.toml` (currently DBZ-sealed only). Commit, pull --rebase, push; trigger `gh workflow run watch` to verify.
(B) **Phase 3 — TCGplayer deal-flagging** — add a market-price oracle from `tcgcsv.com` so #deals fires loud only when a listing is below TCGplayer market (sealed-first fuzzy match, USD-normalized for CAD stores). See spec §9. New plan via writing-plans, then subagent-driven build.
(C) **Phase 2 — non-Shopify sites** — add adapters for pokelegendstcg + bulbacards (Wix) and rarecandy (Next.js). Best-effort, isolated per-adapter. Spike each site's data path first.
(D) **Minor polish (Task 15)** — in `adapters/shopify.py`: drop bare `"bundle"` from `_SEALED_MARKERS` (over-matches) and use `it["id"]`/`v["id"]` to crash on a missing required id instead of stringifying `None`. Full-crawl path only; low priority.
(E) Something else — describe.

=== END PROMPT ===

## Note for the next session

This session took the project from a one-line idea to a live, verified GitHub-Actions watcher in one sitting, using the superpowers brainstorm→spec→plan→subagent-driven-development flow with per-task spec+quality reviews. The defining challenge was Cloudflare rate-limiting (429) of GitHub's datacenter IPs on full-catalog crawls — resolved by pivoting to **sealed-only** fetching (curated Shopify collections for big stores, full-crawl+sealed-filter for small ones) plus a polite HTTP layer (throttle + Retry-After + retries), which both fixed the 429 and sharpened alerts to what James actually buys. James is hands-on and course-corrects well (he caught the collectorstore drop and the GitLab→GitHub account mix-up) — surface findings and confirm scope changes rather than deciding silently. Standing preferences observed: verify before claiming done (we live-ran on GitHub twice to confirm), keep everything under `~/workspace/`, and prefer the narrowest correct scope. Phase 1 is fully shipped; everything remaining (Phases 2/3, 401games coverage, minor polish) is optional and captured above.
