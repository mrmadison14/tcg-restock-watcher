# Egress-IP Scoping — beating Cloudflare's evening 429 storm

**Date:** 2026-07-10 · **Status:** scoping / decision pending (no code written)

## Problem

During US evening peak the `watch` job degrades hard: a 2026-07-10 21:00Z run was
`ok=3 failed=25`. **Every failure is a 429** (`HTTPStatusError`), not a code error.

## Root cause (evidence)

Cloudflare rate-limits **GitHub Actions' shared hosted-runner IP pool**. The pool serves
millions of requests across all GitHub users, so its reputation is bad and Cloudflare throttles
it hardest at peak. Confirmed:

- The only stores that succeed at peak are the **non-Cloudflare** ones: `rarecandy` (fetched via
  its own `api.rarecandy.com` host) and the two **Wix** stores (`Pepyaka` server). All 28
  Cloudflare-fronted Shopify stores 429.
- The **same fetches succeed from a normal IP** (local dry-runs pulled all 31 stores fine).
- Off-peak the same code runs `ok=28..31` clean (13h green streak on 07-07).

So it is purely the **egress IP**, not our code, throttle, or the stores blocking us. The
07-07 fail-fast fix stopped 429s from *stretching* runs, but can't make Cloudflare stop
throttling a bad IP. The only real fix is to **fetch from a better-reputation IP**.

## Options

| # | Approach | IP reputation | Cost | Ops/effort | Reliability |
|---|---|---|---|---|---|
| A | **Residential proxy** via httpx `proxy=` (keep GitHub Actions) | excellent | ~pennies–$/mo (tiny JSON, per-GB) | tiny (1 secret + ~5 LOC, fallback if unset) | high |
| B | **Small VPS** runs the watcher on cron (leave GitHub Actions as backstop) | good (dedicated low-volume IP) | ~$4–6/mo | high (provision, deploy, secrets, git-push PAT) | high |
| C | **Mac via launchd** as primary + GitHub Actions as backstop | excellent (residential) | $0 | medium (launchd + local env/secrets) | medium (Mac-uptime dependent) |
| D | Shard stores across runs / raise throttle | unchanged | $0 | low | **won't work** — the IP is pre-throttled regardless of *our* volume |
| E | Accept peak degradation (do nothing) | n/a | $0 | none | off-peak fine; evening drops Shopify stores |

Notes:
- **A** is the smallest change: `http.make_httpx_get` already builds the `httpx.Client`; add
  `proxy=os.environ.get("FETCH_PROXY")` (no-op when unset → current behavior). Only the store-fetch
  client uses it; the Discord poster stays direct. httpx 0.28.1 supports `proxy=` natively — **no new dep**.
  Datacenter proxies do **not** help (same reputation class as GitHub); it must be **residential**.
  Volume is a few MB/day of JSON, so residential per-GB pricing is trivially cheap.
- **C** maps well to the actual failure window: evening peak is when the Mac is most likely awake, and
  overnight (Mac may sleep) is exactly when Cloudflare is quiet and GitHub Actions already works. The
  launchd pinger was prepared once (session 2) but never loaded. `commit_state.sh` is already
  concurrency-safe, so a Mac run + a GitHub run committing state won't clobber.
- **B** is the most bulletproof but the most moving parts for a hobby watcher.

## Recommendation

1. **Primary: Option A (residential proxy).** Least disruptive — the entire architecture
   (GitHub Actions + cron-job.org + state-commit) stays; one secret + a few lines; set-and-forget;
   cost is pennies for our payload size. Pick a residential provider with a static endpoint
   (e.g. Webshare/IPRoyal-style); store the `user:pass@host:port` URL as the `FETCH_PROXY` repo secret.
2. **$0 alternative: Option C (Mac primary + GitHub backstop)** if paying for/managing a proxy
   account isn't wanted and Mac-uptime coverage of the evening window is acceptable.
3. Reject **D** (doesn't address IP reputation) and **E** (leaves the gap).

## Implementation sketch (Option A)

- `http.py`: `client = httpx.Client(..., proxy=os.environ.get("FETCH_PROXY") or None)` in
  `make_httpx_get` only. TDD: assert the proxy is passed through when the env var is set, and
  that an unset env var preserves today's direct-connection behavior.
- `watch.yml`: add `FETCH_PROXY: ${{ secrets.FETCH_PROXY }}` to the Run-watcher step env.
- Verify: one live run at evening peak should flip `ok=3 failed=25` → `ok=31 failed=0`.
- Keep the Discord poster and the 2.5s throttle unchanged; keep 429 fail-fast as the safety net.

## Open decision for the owner

Cost/ops vs. free-but-uptime: **(A)** cheap paid proxy, zero ops, set-and-forget · **(C)** free, some
local setup + Mac-uptime dependency · **(B)** most robust, ~$5/mo + real ops. Recommendation: **A**.
