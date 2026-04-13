# EC2 Deployment Runbook — Paperclip Outreach (eu-west-1)

**Goal:** Move the autonomous outreach pipeline from Prakash's laptop to a production EC2 instance in `eu-west-1` (Ireland). Postgres in Docker, Claude CLI baked into the cron image, OAuth token persisted in a Docker named volume.

**Constraint:** Zero impact on running campaigns. Laptop cron keeps sending until EC2 has been validated for 48h. No double-sending — only ONE cron is active at any time.

**Status legend:** `[ ]` pending, `[x]` done, `[~]` in progress.

---

## Phase 0 — Pre-flight (already done)

- [x] `Dockerfile` updated: Node 20 + `@anthropic-ai/claude-code` baked in. Verified `claude --version` → `2.1.104`.
- [x] `docker-compose.yml` updated: `claude_auth` named volume on cron service, `TZ=Europe/Dublin`.
- [x] `campaigns/management/commands/handle_replies.py` updated: `CLAUDE_CLI = 'claude'` (PATH-resolved, no hardcoded laptop path).
- [x] New cron image built locally (`paperclip-outreach-cron:latest`). Running cron container deliberately NOT replaced — old image still serving live cron.
- [x] Postgres snapshot taken: `transfer/outreach_<timestamp>.dump` (custom format, ~2.6MB).

**Key discovery during pre-flight:** Auto-reply has been silently broken on the laptop cron for an unknown period — `handle_replies` was hardcoded to `/Users/pinani/.local/bin/claude` which doesn't exist inside the container. Replies were being *flagged* but never auto-sent. Prakash has been handling them manually via `/taggiq-email-expert` / `/fp-email-expert` slash commands. The EC2 cutover restores autonomous reply.

---

## Phase 1 — Local OAuth bootstrap (one-time, on laptop)

Goal: get a valid Claude OAuth token into a local Docker named volume so we can ship it to EC2.

```bash
# From paperclip-outreach repo root on the laptop
docker compose run --rm -it cron claude login
# -> Browser opens. Complete OAuth with the same Anthropic account
#    that has the Claude Max subscription you want to bill against.
# -> Token written to /root/.claude inside the throwaway container,
#    which is mounted to the named volume `paperclip-outreach_claude_auth`.

# Verify the token works
docker compose run --rm cron claude -p "say ok"
# -> Should print "ok" (or similar). If it errors, re-run claude login.
```

**Important:** This `docker compose run` creates a one-off container from the new image. It does NOT touch the running `outreach_cron` container. Live cron is unaffected.

After login, the OAuth token lives in the named volume. Verify:

```bash
docker volume inspect paperclip-outreach_claude_auth
docker run --rm -v paperclip-outreach_claude_auth:/data alpine ls -la /data
# -> should show .credentials.json, settings, etc.
```

- [ ] OAuth login completed
- [ ] `claude -p "ok"` returns successfully
- [ ] `claude_auth` volume contains credential files

---

## Phase 2 — Snapshot the OAuth volume for transfer

```bash
# From laptop, repo root
docker run --rm \
  -v paperclip-outreach_claude_auth:/data \
  -v "$(pwd)/transfer":/out \
  alpine tar czf /out/claude_auth.tgz -C /data .

ls -lh transfer/
# Should see:
#   outreach_<timestamp>.dump   (~2.6 MB)
#   claude_auth.tgz             (small, few KB)
```

- [ ] `transfer/claude_auth.tgz` exists

---

## Phase 3 — Provision EC2 in eu-west-1

**Why eu-west-1:** All customer data (UK + Ireland prospects, IMAP traffic, EU domains) belongs in EU for GDPR alignment. The old us-east-1 instance (`i-03a1303f3edede742`) will be terminated after Phase 7 validation.

### 3.1 Launch instance

| Setting | Value |
|---|---|
| Region | `eu-west-1` (Ireland) |
| Name | `paperclip-outreach-eu` |
| AMI | Amazon Linux 2023 (latest, ARM64 — Graviton) |
| Instance type | `t4g.small` (2 vCPU, 2 GB RAM, ARM, ~$12/mo) |
| Storage | 30 GB gp3 |
| Key pair | Create new or reuse — name it `paperclip-eu` |
| VPC | Default |
| Security group | New, named `paperclip-outreach-sg`, rules: SSH (22) from your IP only |
| IAM role | None for now |
| Tags | `Project=paperclip-outreach`, `Env=prod` |

> Note: `t4g.small` (Graviton/ARM) is cheaper and faster than `t3.small`. The Dockerfile already targets multi-arch via Playwright fallback. If issues arise, fall back to `t3.small` (x86_64).

### 3.2 Allocate Elastic IP

```
EC2 Console -> Elastic IPs -> Allocate -> eu-west-1
-> Associate to paperclip-outreach-eu
```

Record the IP: `_______________`

This IP is permanent. If SES or IMAP whitelists ever depend on it, you only configure once.

### 3.3 SSH in and install Docker

```bash
ssh -i ~/.ssh/paperclip-eu.pem ec2-user@<elastic-ip>

# On the instance:
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Docker Compose v2 plugin
DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-aarch64 \
  -o $DOCKER_CONFIG/cli-plugins/docker-compose
chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose

# Re-login for the docker group to take effect
exit
ssh -i ~/.ssh/paperclip-eu.pem ec2-user@<elastic-ip>

docker --version
docker compose version
```

- [ ] EC2 instance running in eu-west-1
- [ ] Elastic IP attached
- [ ] Docker + Compose plugin working
- [ ] SSH key saved locally

---

## Phase 4 — Ship code, secrets, dump, and Claude auth

### 4.1 Clone repo on EC2

```bash
# On EC2
cd ~
git clone https://github.com/skillblendltd/paperclip-outreach.git
cd paperclip-outreach
git status   # confirm on main, clean
```

### 4.2 Copy `.env` from laptop

```bash
# From laptop
scp -i ~/.ssh/paperclip-eu.pem .env ec2-user@<elastic-ip>:~/paperclip-outreach/.env
```

`.env` must contain at minimum:
- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD` (use a strong one for prod, NOT `localdev`)
- AWS SES creds (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`)
- IMAP / SMTP creds for Zoho + Google Workspace mailboxes
- Vapi keys
- Anything else the laptop `.env` has

> **Generate a NEW POSTGRES_PASSWORD for prod.** Don't reuse `localdev`. Update the `.env` on EC2 only — laptop keeps its own.

### 4.3 Copy Postgres dump and Claude auth tarball

```bash
# From laptop
scp -i ~/.ssh/paperclip-eu.pem transfer/outreach_*.dump ec2-user@<elastic-ip>:~/
scp -i ~/.ssh/paperclip-eu.pem transfer/claude_auth.tgz ec2-user@<elastic-ip>:~/
```

### 4.4 Restore Claude auth into a fresh Docker volume on EC2

```bash
# On EC2, before first `docker compose up`:
docker volume create paperclip-outreach_claude_auth
docker run --rm \
  -v paperclip-outreach_claude_auth:/data \
  -v ~:/in \
  alpine tar xzf /in/claude_auth.tgz -C /data

# Verify
docker run --rm -v paperclip-outreach_claude_auth:/data alpine ls -la /data
# Should see .credentials.json etc.
```

- [ ] Repo cloned on EC2
- [ ] `.env` copied (with NEW Postgres password)
- [ ] Postgres dump copied
- [ ] `claude_auth.tgz` copied and restored into volume

---

## Phase 5 — Bring up Postgres + restore data

```bash
# On EC2, in ~/paperclip-outreach
docker compose up -d postgres
docker compose ps   # postgres should be healthy

# Restore the dump
cat ~/outreach_*.dump | docker exec -i outreach_db pg_restore -U outreach -d outreach --clean --if-exists --no-owner

# Verify row counts match laptop
docker exec outreach_db psql -U outreach -d outreach -c "SELECT 'prospects', COUNT(*) FROM campaigns_prospect UNION ALL SELECT 'email_logs', COUNT(*) FROM campaigns_emaillog UNION ALL SELECT 'templates', COUNT(*) FROM campaigns_emailtemplate UNION ALL SELECT 'campaigns', COUNT(*) FROM campaigns_campaign;"
```

Expected (from snapshot taken 2026-04-13):
- prospects: ~6604
- email_logs: ~6731
- templates: ~146
- campaigns: ~18

If counts match → restore good. If they don't → STOP, debug.

- [ ] Postgres up and healthy on EC2
- [ ] Restore complete
- [ ] Row counts match laptop snapshot

---

## Phase 6 — Bring up web + cron, but leave cron jobs DISABLED initially

We do NOT want EC2 cron to start firing until we've smoke-tested everything and stopped the laptop cron in the same window. Otherwise we double-send.

### 6.1 Bring up web service first

```bash
docker compose up -d web
docker compose logs -f web   # watch for migrate + runserver, ctrl-C when stable
```

### 6.2 Build cron image on EC2 and verify Claude

```bash
docker compose build cron
docker compose run --rm cron claude --version
# -> 2.1.104 (Claude Code)

docker compose run --rm cron claude -p "say ok"
# -> "ok" (uses the OAuth token from the volume)
```

If `claude -p "ok"` fails → the volume restore didn't take. Re-do Phase 4.4.

### 6.3 Smoke test management commands (read-only, no sends)

```bash
docker compose run --rm cron python manage.py check
docker compose run --rm cron python manage.py send_sequences --dry-run --status
docker compose run --rm cron python manage.py check_replies --mailbox taggiq --dry-run
docker compose run --rm cron python manage.py check_replies --mailbox fp --dry-run
```

All four must succeed. If any fail → STOP.

- [ ] Web up
- [ ] Cron image built
- [ ] `claude --version` and `claude -p "ok"` work in cron container
- [ ] `manage.py check` passes
- [ ] `send_sequences --dry-run --status` shows expected eligible counts
- [ ] `check_replies --dry-run` connects to all mailboxes successfully

---

## Phase 7 — Cutover (the only delicate moment)

This is the only step where we touch the running laptop cron. Do it in this exact order:

### 7.1 Stop the laptop cron

```bash
# On laptop
docker compose stop cron
docker compose ps   # cron should be Exited; web + postgres still up
```

The laptop cron container is now stopped. No more sends from laptop. **Web and Postgres on the laptop stay up** for development.

### 7.2 Take a final delta dump (catch any DB writes since the first dump)

If significant time has passed (>30 min) between the original `pg_dump` and now, take a second dump from the laptop and re-restore on EC2 to catch any inbound emails / status updates.

```bash
# On laptop
docker exec outreach_db pg_dump -U outreach -Fc -d outreach > transfer/outreach_final.dump
scp -i ~/.ssh/paperclip-eu.pem transfer/outreach_final.dump ec2-user@<elastic-ip>:~/

# On EC2
docker compose stop web cron 2>/dev/null
cat ~/outreach_final.dump | docker exec -i outreach_db pg_restore -U outreach -d outreach --clean --if-exists --no-owner
docker compose up -d web
```

### 7.3 Start the EC2 cron (this enables auto-sending from EC2)

```bash
# On EC2
docker compose up -d cron
docker compose ps   # all three healthy
docker compose logs cron --tail=50
```

The cron entrypoint installs the cron jobs and starts the daemon. The next `*/10` tick will run `handle_replies`. The next 11:00 Dublin weekday will run `send_sequences`.

### 7.4 Watch the first real cron tick

```bash
# On EC2
docker exec outreach_cron tail -f /tmp/outreach_reply_monitor.log
# Wait for the next :00 / :10 / :20 / ... boundary
# Should see: IMAP poll, then if any replies are flagged, Claude generates reply
```

- [ ] Laptop cron stopped
- [ ] Final delta dump applied (if needed)
- [ ] EC2 cron started
- [ ] First reply-monitor tick observed in EC2 logs
- [ ] No errors in `/tmp/outreach_reply_monitor.log`

---

## Phase 8 — 48-hour validation window

For the next 48 hours, EC2 is the only thing sending. Monitor:

1. **Reply monitor (every 10 min):**
   `docker exec outreach_cron tail -f /tmp/outreach_reply_monitor.log`

2. **Daily send (next 11:00 Dublin weekday):**
   `docker exec outreach_cron tail -f /tmp/campaigns_daily.log`

3. **Backup (next 23:00):**
   `docker exec outreach_cron tail -f /tmp/outreach_backup.log`

4. **Container health:**
   `docker compose ps`

If anything looks off → start laptop cron back up (`docker compose up -d cron` on laptop), stop EC2 cron, debug.

- [ ] First reply auto-handled successfully on EC2
- [ ] First 11:00 send_sequences run completed without errors
- [ ] First nightly backup completed
- [ ] No restart loops or container crashes

---

## Phase 9 — Retire old infra

Only after Phase 8 passes cleanly:

1. **Laptop cron** → leave stopped permanently. Laptop becomes dev-only. Web + Postgres can stay up for development.
2. **us-east-1 instance** (`i-03a1303f3edede742`) → terminate. Release its Elastic IP (if any).
3. **Update `CLAUDE.md`** → reflect: cron lives on EC2 eu-west-1, Sprint 4 done, deployment runbook reference.
4. **Add weekly healthcheck cron on EC2** — runs `claude -p "ok"` and `pg_dump --schema-only` validation, alerts on failure.

- [ ] Laptop cron stopped permanently
- [ ] us-east-1 instance terminated
- [ ] CLAUDE.md updated
- [ ] Weekly healthcheck cron added

---

## Rollback procedure

If at any point during Phase 7-8 things go sideways:

```bash
# On laptop
docker compose up -d cron     # restart laptop cron immediately
docker compose ps             # verify cron Up

# On EC2
docker compose stop cron      # stop EC2 cron
```

Laptop cron resumes sending. EC2 stays running for debugging but doesn't fire jobs. No double-send risk because only one cron is active at a time.

The Postgres dump is one-way (laptop → EC2). If EC2 has captured new replies/sends since cutover, those would need to be dumped back. To minimize this risk, keep the validation window short (24-48h) and revert quickly if needed.

---

## Risks

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| OAuth token expires/revoked → `handle_replies` silently fails on EC2 | Medium | High | Phase 9 weekly healthcheck. Loud Python logging of subprocess exit codes (already in handle_replies). |
| EBS disk failure → Postgres data loss | Low | High | Nightly `pg_dump` to Google Drive (existing `backup_to_gdrive.sh`). 14-day retention. Test restore once before declaring "done". |
| SES IP reputation tied to old us-east-1 IP | Low | Med | SES uses domain auth (DKIM/SPF), not IP. EU SES region is also a config decision — check `AWS_DEFAULT_REGION` in `.env`. May want to switch to `eu-west-1` SES too. |
| Double-send (laptop AND EC2 cron both fire) | Low | High | Phase 7 explicitly stops laptop cron BEFORE starting EC2 cron. Single point of activation. |
| Postgres dump → restore mismatch | Low | High | Phase 5 row count check. STOP if counts don't match. |
| ARM image incompatibility on Graviton (`t4g.small`) | Low | Med | Image is built from `python:3.13-slim` which has multi-arch support. Playwright Chromium has an ARM64 fallback. If issues → fall back to `t3.small` (x86_64). |
| GDPR — UK customer data routed via us-east-1 SES | Med | Med | Audit `AWS_DEFAULT_REGION`. If SES is `us-east-1`, plan to migrate to `eu-west-1` SES with new domain identity. Out of scope for this runbook. |

---

## Decisions log

- **2026-04-13** — Region: eu-west-1 (Ireland) chosen over us-east-1. Rationale: GDPR alignment, all customers in Europe, latency to EU mailboxes.
- **2026-04-13** — Database: Postgres in Docker on EC2 (not RDS). Rationale: zero extra cost, identical to local dev, can migrate to RDS later when pilot revenue justifies it.
- **2026-04-13** — Claude auth: subscription OAuth (not API key). Rationale: Prakash explicitly wants to use Claude Max subscription, not pay-per-token.
- **2026-04-13** — Instance type: `t4g.small` (Graviton). Rationale: cheaper than `t3.small` (~$12 vs $15/mo), faster ARM cores, more than enough for outreach workload.
- **2026-04-13** — Domain / TLS / landing page: deferred. Direct IP + SSH-only access for now. Additive later.
- **2026-04-13** — Stack discovery: laptop is already running on Postgres (Sprint 4 effectively done). CLAUDE.md was stale. No SQLite migration needed.
- **2026-04-13** — Hidden bug found: `handle_replies` was silently failing on laptop because `/Users/pinani/.local/bin/claude` doesn't exist inside the container. Replies were flagged but never auto-sent. Fix shipped in same Dockerfile change.
