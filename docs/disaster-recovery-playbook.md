# Paperklip Disaster Recovery Playbook

Last updated: 2026-05-21 by devops-engineer audit (Prakash request — partner-driven
data-loss threat).

This playbook covers the scenario where someone with admin access to AWS account
`800769768617` (currently: `pinani`, `shrenikdoshi` + SSO admin) terminates the
Paperklip EC2 instance, deletes the EBS volume, removes the SES verified
identities, and/or wipes the Route 53 records that point at `taggiq.com` /
`fullypromoted.ie` / `kritno.com` mail subdomains.

The goal: rebuild Paperklip from cold backups into a clean AWS account and have
the email + voice pipeline operational again. Cold-start recovery is dominated by
SES production access (24–72 h) and Route 53 / DNS propagation — those windows
cannot be skipped. Everything else is hours.

---

## 1. What is backed up, where, and how fresh

| Asset | Location 1 (Mac) | Location 2 (Google Drive) | Cadence | Critical? |
|-------|------------------|---------------------------|---------|-----------|
| Postgres logical dump (`outreach_ec2_YYYY-MM-DD.sql.gz`) | `~/Documents/paperclip-outreach/backups/disaster-recovery/db/` | `gdrive:/paperclip-outreach-DR/db/` | Daily 23:00 via launchd | YES — all prospects, EmailLog, InboundEmail, CallLog, AIUsageLog, ProductBrain |
| Postgres data volume tar (`pgdata_YYYY-MM-DD.tgz`) | same path / `configs/` | same / `configs/` | Weekly (Sun) | Fallback if logical dump corrupt |
| Claude OAuth volume tar (`claude_auth_YYYY-MM-DD.tgz`) | same / `claude-auth/` | same / `claude-auth/` | Weekly (Sun) | NICE-TO-HAVE — token rotated by `claude setup-token` |
| Project deploy dir (`paperclip_project_YYYY-MM-DD.tar.gz` — incl. `.env`, `docker-compose.yml`, `docker/.env.cron`) | same / `configs/` | same / `configs/` | Weekly (Sun) | YES — secrets, container config, SMTP creds, API keys |
| AWS resource inventory (Route 53, SES DKIM, EC2 metadata, security groups, IAM) | same / `aws-inventory/` | same / `aws-inventory/` | Weekly (Sun) | YES — drives the rebuild |
| AMI snapshot in source AWS account | — | — | One-off (`paperclip-outreach-DR-*`) | Useful only if account survives |

**Backup script:** `/Users/pinani/.paperclip-scripts/backup_ec2_to_dr.sh`
**Schedule:** `~/Library/LaunchAgents/com.paperclip.backup-gdrive.plist` (23:00 daily)
**Heartbeat file:** `/tmp/paperclip_backup_OK` — must be < 36 h old at all times. Add to `brain_doctor` checks.
**Log:** `/tmp/paperclip_dr_backup.log`

**Code:** GitHub `skillblendltd/paperclip-outreach`. Independent of AWS — survives full account destruction.

---

## 2. What the partner can destroy

`shrenikdoshi` has `AdministratorAccess` on AWS account `800769768617`. Confirmed
read-only reconnaissance on 2026-05-18 21:15 UTC. They can, with a single API
call each:

- Terminate EC2 `i-0e1c6f4611b5a28e4` (paperclip-outreach-eu)
- Delete EBS volume `vol-069bb0932c42bfc9f` (30 GB — the entire Postgres data)
- Release Elastic IP `54.220.116.228` (`eipalloc-0214ba9a8d1900b20`)
- Deregister AMIs and delete snapshots — including the DR AMI we just took
- Delete SES verified identities (`mail.taggiq.com`, `mail.fullypromoted.ie`, `mail.kritno.com`, etc.) — re-verification needs 24–72 h
- Delete Route 53 hosted zones `taggiq.com` (34 records) and `kritno.com` (27 records) — domains continue to exist at the registrar but stop resolving until NS records are repointed
- Rotate or delete the SES SMTP IAM users — credential rotation requires re-deploying `.env` to all environments
- Disable / delete the `pinani` IAM user (locks you out)

`shrenikdoshi` cannot, without additional steps:

- Delete the GitHub repo (separate org/account)
- Delete the Google Drive backups (separate Google account)
- Delete the local Mac backup tree
- De-register the domains `taggiq.com`, `fullypromoted.ie`, `kritno.com` at the
  registrar (assumes the registrar account is separate from AWS — verify before
  needing it)

---

## 3. Pre-incident hardening (do these NOW, before the threat materializes)

These reduce blast radius without escalating tension with the partner.

1. **Enable MFA on the root account if not already.** Console → IAM → root MFA device → activate.
2. **Verify the root account email is one only you control.** Console → root → My Account → contact info. If it's a shared business email, change it.
3. **Set CloudTrail organization-wide audit logging to S3 + a different account** so deletions leave evidence even if they delete CloudTrail. (Skip if too expensive — the CloudTrail trail in `aws-cloudtrail-logs-800769768617-5cb1e125` already exists in S3, but a sufficiently motivated admin can empty that bucket too.)
4. **Snapshot AMI weekly** via Data Lifecycle Manager. (Manual one-off taken in this audit — `ami-083f8fe9c89cb8519`.)
5. **Export DKIM tokens to a written/printed page** — they are stable per identity and re-importing them speeds SES re-verification. See `backups/disaster-recovery/aws-inventory/ses_dkim_attributes.json`.
6. **Confirm domain registrar access.** Where are `taggiq.com`, `fullypromoted.ie`, `kritno.com` registered? Are NS records under your sole control? Document the registrar login in a password manager Shrenik does not have access to.
7. **Run the new DR backup script manually once a week** to confirm it's still working (`/Users/pinani/.paperclip-scripts/backup_ec2_to_dr.sh`). Watch the heartbeat file.

---

## 4. Detection — how you'll know it happened

| Signal | What it means |
|--------|--------------|
| Daily KPI email stops arriving | Cron not running — EC2 likely terminated |
| `*/10` reply monitor stops logging | Same as above |
| `https://api.example.com` / EC2 IP unreachable from your Mac | EC2 down |
| `/tmp/paperclip_backup_OK` heartbeat > 36 h old | EC2 down OR Mac couldn't reach it OR pg_dump errored |
| Inbound emails to `prakash@taggiq.com` start bouncing | SES identity deleted OR DKIM records wiped from Route 53 |
| `dig MX taggiq.com` returns NXDOMAIN | Route 53 zone deleted |
| AWS Console login fails for `pinani` | IAM user deleted/locked |

A `brain_doctor` extension (`campaigns/management/commands/brain_doctor.py`)
should be updated to check the heartbeat file and surface a CRITICAL finding if
it's stale — see Section 8.

---

## 5. Recovery phases

### Phase 0 — Triage (first 30 minutes)

**Goal: confirm scope, preserve evidence, stop the bleeding.**

1. Open AWS Console with `pinani` credentials (or root if available). Note: if
   `pinani` is locked out, log in as root.
2. Check CloudTrail event history for the last 24 h, filtered by `shrenikdoshi`:
   ```bash
   aws cloudtrail lookup-events --region eu-west-1 \
     --lookup-attributes AttributeKey=Username,AttributeValue=shrenikdoshi \
     --max-results 200 \
     --query 'Events[*].[EventTime,EventName,Resources[0].ResourceName]' \
     --output table
   ```
   Look for `TerminateInstances`, `DeleteVolume`, `DeleteSnapshot`, `DeleteIdentity`, `DeleteHostedZone`, `DeleteUser`, `DeleteAccessKey`.
3. **Revoke shrenikdoshi:** Console → IAM → users → shrenikdoshi → set both access
   keys to Inactive, delete console login profile, remove all attached policies.
   Do this immediately on confirmation of malicious activity.
4. **Rotate `pinani`'s own access keys** (the existing key is `AKIA3U4MY7SU4QH6OFFH`). Console → IAM → pinani → create new key, update `~/.aws/credentials`, deactivate the old key. This handles the case where shrenik has previously exfiltrated your key.
5. Take inventory of what survived. Use the inventory list from Section 1.
6. **If EC2 is still running** but you expect it to be destroyed: SSH in, run
   `/Users/pinani/.paperclip-scripts/backup_ec2_to_dr.sh` manually to grab the
   freshest possible dump.

### Phase 1 — Decide: rebuild in the same account or a clean account?

| Stay in account `800769768617` | Move to fresh account |
|--------------------------------|-----------------------|
| Faster (no DNS swap, SES already verified) | Slower (1–3 day SES cold start) |
| Vulnerable to repeat attack if shrenikdoshi regains access | Permanent separation |
| Credits stay in place | Credits are stranded (use new account in same AWS Organization to share billing — see Section 7) |
| Other businesses (TaggIQ, Kritno) still in same blast radius | Forces separation of all three businesses |

**Recommendation:** If shrenikdoshi has been removed cleanly (IAM access revoked, root MFA on, no signs of follow-up), stay in `800769768617` and rebuild in place. If there's any doubt — including the possibility they retained credentials before being locked out — move to a fresh account.

### Phase 2 — Rebuild in place (same account, fast path)

**Assumes:** account intact, shrenikdoshi access revoked, just EC2 + EBS destroyed.

1. **Launch a replacement EC2 instance** from the DR AMI (taken 2026-05-21):
   ```bash
   aws ec2 run-instances --region eu-west-1 \
     --image-id ami-083f8fe9c89cb8519 \
     --instance-type t4g.small \
     --key-name paperclip-eu \
     --security-group-ids sg-05669e0a0b83385ba \
     --subnet-id subnet-0259b2309f7d79fd3 \
     --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=paperclip-outreach-eu-restored},{Key=Project,Value=paperclip-outreach}]'
   ```
2. **Associate the same Elastic IP** (if it still exists), or allocate a new one
   and update DNS:
   ```bash
   aws ec2 associate-address --region eu-west-1 \
     --instance-id <new-instance-id> \
     --allocation-id eipalloc-0214ba9a8d1900b20
   ```
3. **SSH in, validate** Docker containers come up:
   ```bash
   ssh -i ~/.ssh/paperclip-eu.pem ec2-user@<eip>
   cd /home/ec2-user/paperclip-outreach && docker compose up -d
   docker ps
   docker exec outreach_db psql -U outreach -d outreach -c 'select count(*) from prospects;'
   ```
4. **Re-authenticate Claude CLI** (token in AMI snapshot will be expired):
   ```bash
   docker exec -it outreach_cron claude setup-token
   ```
5. **Confirm SES still works** — try a test send. If SES identities were deleted, skip to Phase 4.
6. **Done.** Total wall time: ~30 min if AMI is intact.

If the AMI was also deleted but EBS snapshots survived: launch a fresh Amazon
Linux 2023 aarch64 instance, attach the EBS snapshot as `/dev/xvda`, boot. If
nothing in the account survived: Phase 3.

### Phase 3 — Rebuild in a fresh AWS account (cold start)

**Wall time: 24 h optimistic, 72 h realistic** — SES production access is the
bottleneck.

#### 3a. Create the new AWS account (~30 min)

- Sign up with a fresh root email (one only you control, e.g.
  `prakash+paperclip-dr@yourdomain.com`).
- Enable MFA on root immediately. Use a hardware key (YubiKey) if possible.
- Create an IAM user `pinani` with `AdministratorAccess`, MFA enabled.
- Optionally: create the new account as a sub-account inside an AWS
  Organization rooted at your existing master account. Same root user, same
  consolidated billing, same credits. Permissions are isolated — Shrenik on
  account A cannot reach account B. See Section 7.
- Generate a new EC2 key pair: `paperclip-eu-dr.pem`. Save to `~/.ssh/`.

#### 3b. Recreate networking (~20 min)

```bash
export AWS_PROFILE=paperclip-dr
export AWS_REGION=eu-west-1

# VPC + subnet (or use default VPC if simpler)
VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 --query 'Vpc.VpcId' --output text)
SUBNET_ID=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 --availability-zone eu-west-1a --query 'Subnet.SubnetId' --output text)
IGW_ID=$(aws ec2 create-internet-gateway --query 'InternetGateway.InternetGatewayId' --output text)
aws ec2 attach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID
# (add route table + route to igw)

# Security group — same rules as backups/disaster-recovery/aws-inventory/ec2_paperclip_securitygroup.json
SG_ID=$(aws ec2 create-security-group --vpc-id $VPC_ID --group-name paperclip-outreach-sg --description "Paperclip Outreach SSH only from Prakash IP" --query 'GroupId' --output text)
# Re-apply each rule from the JSON. CIDR ranges from the inventory:
for cidr in 80.233.56.0/22 86.43.182.242/32 80.233.48.210/32 80.233.48.0/20 80.233.39.18/32 80.233.0.0/16; do
  aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22 --cidr $cidr
done
```

#### 3c. Submit SES production access request immediately (this is the long pole)

**Do this before anything else — it runs in the background while you do the rest.**

```bash
# 1. Verify the sending domains in the new account
aws ses verify-domain-identity --domain mail.taggiq.com
aws ses verify-domain-identity --domain mail.fullypromoted.ie
aws ses verify-domain-identity --domain mail.kritno.com
aws ses verify-domain-identity --domain prakash@fullypromoted.ie  # if needed

# 2. Generate DKIM tokens — note them, you'll add to Route 53 / registrar in 3d
aws ses verify-domain-dkim --domain mail.taggiq.com
aws ses verify-domain-dkim --domain mail.fullypromoted.ie
aws ses verify-domain-dkim --domain mail.kritno.com

# 3. Request production access in the AWS Console:
#    SES → Account dashboard → "Request production access"
#    Use case: B2B sales outreach for software/franchise prospects, opted-in
#    contacts only, suppression list managed via SES + internal DB.
#    Typical resolution: 24–72 h. Have a plausible reply ready in case AWS
#    asks for content samples, bounce/complaint handling description.
```

**While SES processes the request, continue with the rest of the rebuild. SES sending
will be disabled (sandbox: only verified addresses) until production access is granted.**

#### 3d. Repoint DNS to the new infrastructure

Two paths depending on whether Route 53 in the old account was destroyed:

**Path A — taggiq.com Route 53 zone still exists in account `800769768617`:**
Easier — just create new records pointing at the new EC2's EIP. Update DKIM
records with the new tokens. Keep using Route 53 in the old account if you
trust it; otherwise see Path B.

**Path B — old Route 53 zone is destroyed:**

1. Create a new hosted zone in the DR account:
   ```bash
   aws route53 create-hosted-zone --name taggiq.com --caller-reference $(date +%s)
   ```
2. AWS gives you 4 new nameservers. **At the domain registrar** (Namecheap /
   GoDaddy / wherever taggiq.com is registered), update the NS records to point
   at these new nameservers. Propagation: 1–24 h.
3. Re-create all records from
   `backups/disaster-recovery/aws-inventory/route53_taggiq.com_records.json`.
   Filter out the NS and SOA records (those are auto-created):
   ```bash
   jq '.ResourceRecordSets[] | select(.Type != "NS" and .Type != "SOA")' \
     backups/disaster-recovery/aws-inventory/route53_taggiq.com_records.json
   ```
   Re-insert one by one with `aws route53 change-resource-record-sets`.

The critical records for Paperklip:

- `mail.taggiq.com` MX → `inbound-smtp.eu-west-1.amazonaws.com` (or Zoho)
- `mail.taggiq.com` TXT (SPF) → `v=spf1 include:amazonses.com -all`
- `_amazonses.mail.taggiq.com` TXT → SES verification token (NEW token from step 3c)
- `*._domainkey.mail.taggiq.com` CNAME → SES DKIM CNAMEs (NEW tokens from step 3c)
- `mail.taggiq.com` TXT (DMARC) → `v=DMARC1; p=quarantine; rua=mailto:...`

Repeat for `mail.fullypromoted.ie` and `mail.kritno.com`.

#### 3e. Launch EC2 + restore Postgres (~1 h)

1. **Launch instance:** Amazon Linux 2023 aarch64, `t4g.small`, attach to new SG and subnet, key name `paperclip-eu-dr`.
2. **Install Docker:** `sudo dnf install -y docker && sudo systemctl enable --now docker && sudo usermod -aG docker ec2-user`.
3. **Clone repo:** `git clone https://github.com/skillblendltd/paperclip-outreach.git /home/ec2-user/paperclip-outreach`.
4. **Restore secrets:** From `backups/disaster-recovery/configs/paperclip_project_*.tar.gz`, extract `.env`, `docker-compose.yml`, `docker-compose.override.yml`, `docker/.env.cron` and put them in place on the new EC2. **Update any AWS-related env vars** (SES SMTP creds, S3 keys) with new account values.
5. **Start containers, restore DB:**
   ```bash
   cd /home/ec2-user/paperclip-outreach
   docker compose up -d outreach_db
   sleep 10
   gunzip -c /tmp/outreach_ec2_<YYYY-MM-DD>.sql.gz | docker exec -i outreach_db psql -U outreach -d outreach
   docker compose up -d  # bring up rest
   docker exec outreach_db psql -U outreach -d outreach -c 'select count(*) from prospects;'
   ```
6. **Restore Claude OAuth** (or re-auth fresh):
   ```bash
   # Easier: just re-auth
   docker exec -it outreach_cron claude setup-token
   ```
7. **Reapply EIP** (allocate a new one, associate). Update DNS A records to point at the new EIP.

#### 3f. Wait for SES production access

Until SES exits sandbox, sequences cannot send to non-verified addresses. You
can verify a small whitelist of addresses for testing in the meantime.

When SES production access is granted:
1. Re-create the `paperclip-bounces` SES configuration set with SNS bounce notifications (`backups/disaster-recovery/aws-inventory/ses_config_paperclip_bounces.json` documents the structure).
2. Re-create the `paperclip-bounce-poller` IAM user with the inline policy from `backups/disaster-recovery/aws-inventory/iam_policy_paperclip-bounce-poller_paperclip-bounce-poller-policy.json`. Generate new access keys, update them in the EC2 `.env`.
3. Re-create the SES SMTP users — there are 2 in the inventory. Generate new SMTP credentials. Update the EC2 `.env` with the new values.

#### 3g. Verification

```bash
# Pipeline checks
ssh ec2-user@<new-eip>
docker ps  # all containers up
docker exec outreach_cron crontab -l  # cron jobs installed
docker exec outreach_cron python manage.py brain_doctor  # health check

# End-to-end
docker exec outreach_cron python manage.py send_sequences --dry-run --status
docker exec outreach_cron python manage.py check_replies --mailbox taggiq

# Smoke test a single email
docker exec outreach_cron python manage.py shell -c "
from campaigns.email_service import EmailService
EmailService().send_reply(to='prakash@taggiq.com', subject='DR smoke test', body='If you see this, DR worked.', campaign_id=1)
"
```

---

## 6. Time estimates

| Scenario | Best case | Realistic |
|----------|-----------|-----------|
| Just EC2 terminated, AMI intact, same account | 30 min | 1 h |
| EC2 + EBS destroyed, AMI intact, same account | 1 h | 2 h |
| Full account loss, new account, SES production access fast-tracked | 24 h (mostly SES wait) | 48 h |
| Full account loss, new account, SES production access standard | 48 h | 72 h |
| Full account loss, new account, domain registrar also compromised | 5 d | 7 d (registrar dispute is the long pole) |

---

## 7. The "second AWS account" question, explained

You asked: "how does a second AWS account work — credits stay in current one?"

**Three options, ranked by recommendation:**

### Option A (recommended): New account inside AWS Organizations

- Log in to `800769768617` as root → AWS Organizations → Create AWS account
- New email (must be different from existing root). E.g. `prakash+paperklip-dr@yourdomain.com`.
- New root password + MFA. Shrenik has no access to it because Organizations sub-accounts have isolated IAM. **Even though they're admin in the master, they're nothing in the sub-account.**
- **Billing:** consolidated. Charges in the sub-account roll up to the master. Your existing $X credits in the master cover the sub-account's bill until depleted.
- **Effort:** ~30 min.
- **Risk:** if root of the master account (`800769768617`) is compromised, the attacker can move the sub-account out from under you. So root MFA on the master is mandatory.

### Option B: Standalone new account (different root)

- Sign up fresh at aws.amazon.com with a new email and credit card.
- Completely independent. No credits transferable.
- Lose access to your existing credits ($X stranded in the master account).
- **Safest from a permissions perspective** (no master-sub link).
- **Effort:** ~30 min, plus you start paying real money for the DR account.

### Option C: Just better backups, no second account

- What we did today.
- Pulls everything to your Mac + Google Drive.
- DR recovery still requires standing up an account when the worst happens (so add 30 min to the timeline above).
- Cheapest, simplest, no defensive posture change visible to Shrenik.

**My recommendation: Option A.** You get a clean DR account with separated permissions, your credits still cover it, and Shrenik sees no change. When you're ready, we can pre-stage the DR account with copies of the AMI snapshot, the SES domain verifications (so they're already warmed up — no 72-h cold start), and the EBS snapshot. Cold failover becomes warm failover.

---

## 8. Detection hooks to add to brain_doctor

`brain_doctor` currently checks Claude CLI auth. Extend it to also check:

```python
# campaigns/management/commands/brain_doctor.py
def check_backup_heartbeat(self):
    heartbeat = Path('/tmp/paperclip_backup_OK')
    if not heartbeat.exists():
        return Finding('CRITICAL', 'No backup heartbeat file - DR backup has never succeeded')
    age = time.time() - heartbeat.stat().st_mtime
    if age > 36 * 3600:
        return Finding('CRITICAL', f'Backup heartbeat is {age//3600:.0f} h old (threshold 36h)')
    return Finding('OK', f'Backup heartbeat fresh ({age//3600:.1f} h ago)')
```

Run it daily from cron alongside the Claude auth check.

---

## 9. Open questions for Prakash

1. **Domain registrars** — where is `taggiq.com`, `fullypromoted.ie`, `kritno.com` registered? Document the registrar accounts in a password manager Shrenik does not have access to. Without registrar access you cannot repoint DNS in a full-DR scenario.
2. **Root account contact email** for `800769768617` — is it `skillblendltd@gmail.com` or something else? If shared with Shrenik, change it.
3. **SSO users** — IAM Identity Center is enabled (`AWSReservedSSO_AdministratorAccess` role exists). Check who has SSO admin and whether they need it.
4. **Shrenik's second access key** (`AKIA3U4MY7SUYQTAVHMZ`, created 2026-05-11) — was that legitimate (new laptop)? If you don't know what it's for, deactivate it.
5. **Decision:** Phase 2 (rebuild in place) is the default. Decide in advance whether you'd jump straight to Phase 3 (fresh account) for any partial-destruction scenario as a defensive posture.

---

## 10. What this playbook deliberately doesn't cover

- TaggIQ production rebuild. Same AWS account, much bigger system (CloudFront, ALB, RDS, S3 media buckets, multi-tenant storefronts). Needs its own DR playbook.
- Kritno rebuild. Same.
- Recovering Vapi call recordings (stored in Vapi's account, not AWS — separate vendor).
- Recovering data from third-party services where Paperklip is the consumer (Zoho IMAP archive, Google Workspace, OpenAI / Anthropic usage logs).
- Legal / commercial fallout of a partner dispute. Talk to a lawyer.
