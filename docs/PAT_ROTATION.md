# cron-job.org PAT rotation runbook

cron-job.org pings the GitHub API every 5 min to `workflow_dispatch` the `watch`
workflow (GitHub's own free-tier schedule is throttled to ~2–3h, so this is the
real 5-min driver). It authenticates with a GitHub **fine-grained PAT** sent as an
`Authorization: Bearer <token>` header.

Rotate when the token nears expiry or is exposed. **Order matters** — create + swap
+ test *before* revoking, so the 5-min pings never break.

## 1. Create a new fine-grained PAT

github.com/settings/personal-access-tokens/new (as **mrmadison14**):

- **Name:** `tcg-watcher cron-job.org dispatch`
- **Expiration:** your call — longer = fewer breakages, shorter = safer. Recommend
  **1 year** (max) since scope is tiny; set a calendar reminder to rotate.
- **Resource owner:** mrmadison14
- **Repository access:** Only select repositories → **mrmadison14/tcg-restock-watcher**
- **Permissions → Repository:**
  - **Actions: Read and write**  ← required to trigger `workflow_dispatch`
  - Metadata: Read-only (auto-selected, mandatory)
  - nothing else
- Generate → copy the token. **Do not paste it into chat** (that re-exposes it).

## 2. Swap it into cron-job.org

cron-job.org → the tcg-watcher job → **Headers** → edit the `Authorization` header
value to `Bearer <NEW_PAT>`. Leave the URL, method (POST), and body (`{"ref":"main"}`)
and the other headers (`Accept: application/vnd.github+json`) unchanged. Save.

## 3. Test (expect HTTP 204)

Either hit **Test run** in cron-job.org (execution history should show **204**), or
from a terminal:

```bash
curl -sS -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <NEW_PAT>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/mrmadison14/tcg-restock-watcher/actions/workflows/watch.yml/dispatches \
  -d '{"ref":"main"}' -w "\nHTTP %{http_code}\n"
```

`HTTP 204` = success (a new `workflow_dispatch` watch run will appear within seconds:
`gh run list --workflow=watch --event workflow_dispatch --limit 3`).
`401/403` = token/permission wrong — fix before step 4.

## 4. Revoke the old PAT

Only after step 3 shows 204: github.com/settings/tokens → the old
`tcg-watcher` token → **Revoke**. The exposed token is now dead.
