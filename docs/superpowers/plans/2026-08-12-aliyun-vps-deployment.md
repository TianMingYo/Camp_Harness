# Aliyun VPS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the already tested public mock WebUI from public GHCR to the student's rented Aliyun VPS, verify its public safety boundaries, and record the real delivery evidence without placing credentials in the repository.

**Architecture:** GitHub Actions remains the build authority: each feature-branch push runs tests, builds and smokes the container, then publishes that exact image artifact to `ghcr.io/tianmingyo/camp_harness`. The VPS anonymously pulls the public image and runs it on public TCP port 80 with Docker restart policy; the service contains only deterministic mock behavior and accepts neither provider credentials nor local repository paths.

**Tech Stack:** OpenSSH, Ubuntu, Docker Engine, public GHCR, FastAPI/Uvicorn, GitHub Actions.

## Global Constraints

- Work only from `feature/feedback-loop-harness` in the existing isolated worktree.
- Do not merge Pull Request #1 or modify the dirty main worktree.
- Never print, persist, commit, or transmit an SSH private key, server password, GitHub token, provider key, or LLM credential.
- Use a local SSH key path or SSH config alias; never put a password on a command line.
- Treat remote package installation, firewall changes, container replacement, and service start as separately approved external mutations.
- Deploy only `feedbackloop.api:demo_app`; the public service must reject credential writes and local repository task paths.
- Use the public GHCR image without registry credentials and pin the first deployment to the anonymously observed digest.
- Keep the paid server only as long as the student needs it, but do not delete or stop it before the course submission and verification window ends.
- Record the approved deviation from Render: Render account activation required a payment card, so the student selected a rented Aliyun VPS allowed by the course deployment requirements.
- TDD applies to product behavior and repository configuration. Read-only server discovery, external deployment metadata, and factual documentation do not introduce product behavior and therefore require verification evidence rather than a fabricated RED/GREEN cycle.

---

### Task 1: Establish And Inspect The SSH Target

**Files:**
- Create: local/external SSH connection only; no repository file changes.

**Interfaces:**
- Consumes: student-supplied public IPv4 address, SSH username, and either a local private-key path or an existing SSH config alias.
- Produces: verified host identity, OS/version, architecture, privilege mode, resource availability, Docker state, listening ports, and firewall state.

- [ ] **Step 1: Build the SSH invocation without secret material**

For an SSH alias, use:

```powershell
$sshTarget = $env:ALIYUN_VPS_ALIAS
if ([string]::IsNullOrWhiteSpace($sshTarget)) { throw 'ALIYUN_VPS_ALIAS is required' }
$sshArgs = @($sshTarget)
```

For an explicit key path, use the student-supplied values only in process memory:

```powershell
$serverIp = $env:ALIYUN_VPS_IP
$sshUser = $env:ALIYUN_VPS_USER
$keyPath = $env:ALIYUN_VPS_KEY
if ([string]::IsNullOrWhiteSpace($serverIp)) { throw 'ALIYUN_VPS_IP is required' }
if ([string]::IsNullOrWhiteSpace($sshUser)) { throw 'ALIYUN_VPS_USER is required' }
if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) { throw 'ALIYUN_VPS_KEY must name an existing key file' }
$sshTarget = "$sshUser@$serverIp"
$sshArgs = @('-i', $keyPath, '-o', 'IdentitiesOnly=yes', $sshTarget)
```

Do not read or display the private-key file.

- [ ] **Step 2: Verify host-key trust deliberately**

Run:

```powershell
ssh @sshArgs 'printf "connected\n"'
```

If OpenSSH reports an unknown host key, compare its fingerprint with the fingerprint shown in the Aliyun console before accepting it. Stop on a changed host-key warning.

- [ ] **Step 3: Run read-only preflight**

Run:

```powershell
ssh @sshArgs 'set -eu; uname -a; cat /etc/os-release; id; uname -m; df -h /; free -m; command -v docker || true; docker version 2>/dev/null || true; sudo -n true 2>/dev/null && echo sudo_noninteractive=yes || echo sudo_noninteractive=no; ss -ltn; command -v ufw >/dev/null && sudo ufw status || true'
```

Require Ubuntu on `x86_64`, at least 1 GiB usable memory, enough free disk for the image, SSH access, and either root or non-interactive sudo. Confirm TCP port 80 is not already owned by an unrelated service. Stop and ask before replacing any existing workload.

---

### Task 2: Install Docker And Start The Pinned Public Image

**Files:**
- Modify: remote VPS packages and Docker runtime only after separate approval.

**Interfaces:**
- Consumes: approved SSH target from Task 1 and anonymous manifest digest `sha256:b7a0c1382a52d16266467b8b410abdece06ce980164d72f74d593e0122f51714`.
- Produces: one Docker container named `feedbackloop-harness`, restart policy `unless-stopped`, host TCP port 80 mapped to container port 8000.

- [ ] **Step 1: Install Docker only if preflight found it absent**

After explicit approval, run on Ubuntu:

```powershell
ssh @sshArgs 'set -eu; sudo apt-get update; sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io; sudo systemctl enable --now docker; sudo docker version'
```

Expected: both Docker client and server versions print successfully. Do not add the SSH user to the `docker` group because that grants root-equivalent access and is unnecessary for this deployment.

- [ ] **Step 2: Confirm the exact container target remains free**

Run read-only checks:

```powershell
ssh @sshArgs 'sudo docker ps -a --filter name=^/feedbackloop-harness$ --format "{{.ID}} {{.Image}} {{.Status}} {{.Ports}}"; sudo ss -ltnp | grep -E "[[:space:]]:80[[:space:]]" || true'
```

If the exact container name or port 80 is occupied, stop and obtain approval for the specific replacement or alternate port. Never remove an unrelated container or process.

- [ ] **Step 3: Pull and start the immutable image**

After explicit approval, run:

```powershell
ssh @sshArgs 'set -eu; sudo docker pull ghcr.io/tianmingyo/camp_harness@sha256:b7a0c1382a52d16266467b8b410abdece06ce980164d72f74d593e0122f51714; sudo docker run -d --name feedbackloop-harness --restart unless-stopped -p 80:8000 ghcr.io/tianmingyo/camp_harness@sha256:b7a0c1382a52d16266467b8b410abdece06ce980164d72f74d593e0122f51714; sudo docker inspect feedbackloop-harness --format "{{.Id}} {{.Image}} {{.State.Status}} {{.HostConfig.RestartPolicy.Name}} {{json .NetworkSettings.Ports}}"'
```

Expected: container state `running`, restart policy `unless-stopped`, and `8000/tcp` published on host port 80.

- [ ] **Step 4: Handle host firewall only if required**

First rely on the student's Aliyun security group allowing inbound TCP 80. If Ubuntu UFW is active and blocks TCP 80, obtain separate approval, then run:

```powershell
ssh @sshArgs 'sudo ufw allow 80/tcp; sudo ufw status'
```

Do not change SSH rules or disable the firewall.

---

### Task 3: Verify Public Safety And Record The Actual VPS Delivery

**Files:**
- Modify: `README.md`
- Modify: `AGENT_LOG.md`
- Modify: Pull Request #1 body through the GitHub API.

**Interfaces:**
- Consumes: the observed public IPv4 URL, reviewed commit `c612b187d3860a1e9437777ec025ddf2b519b188`, successful Actions runs `31492476957` and `31492473937`, and the public GHCR digest.
- Produces: verified public WebUI URL, factual deployment documentation, passing final CI, refreshed public `latest` manifest, and an open non-conflicted Pull Request #1.

- [ ] **Step 1: Run public behavior and security smoke from the controller machine**

Set `$publicUrl` from the student-supplied public IPv4 and run the existing four-boundary probe with a 120-second timeout:

```powershell
$publicUrl = "http://$serverIp"
@'
import sys
import httpx

base = sys.argv[1].rstrip("/")
with httpx.Client(timeout=120, follow_redirects=True) as client:
    root = client.get(f"{base}/")
    assert root.status_code == 200
    assert "Feedback Loop Harness" in root.text

    demo = client.get(f"{base}/demo/scenario")
    assert demo.status_code == 200
    assert demo.json() == {
        "mode": "mock",
        "repository": "embedded-sample",
        "iterations": ["test_failure", "pass"],
        "approval": "delete_requires_approval",
    }

    secret = "deployment-probe-must-not-echo"
    credential = client.post(f"{base}/providers/demo/credentials", json={"key": secret})
    assert credential.status_code == 403
    assert secret not in credential.text

    task = client.post(
        f"{base}/tasks",
        json={"repo_root": "C:/visitor/repository", "request": "modify a file", "plan_files": ["README.md"]},
    )
    assert task.status_code == 400
    assert task.json()["detail"] == "public demo does not accept local repository paths"

print({"url": base, "root": root.status_code, "demo": demo.json(), "credential": credential.status_code, "task": task.status_code})
'@ | C:\Users\13900\anaconda3\python.exe - $publicUrl
```

- [ ] **Step 2: Update factual documentation**

In `README.md`, extend `## Distribution` with public GHCR pull/run commands and add `## Public deployment` containing the exact observed URL and this architecture:

```text
GitHub push -> quality tests/container smoke -> public GHCR publish -> approved VPS pull/run
```

State that the VPS uses ephemeral container state, serves only the mock demo, contains no provider credentials, and must remain rented through the submission verification window. Remove the obsolete statement that no public deployment URL exists.

Append to `AGENT_LOG.md` the Render card-verification blocker, student-approved Aliyun VPS choice, SSH preflight facts without secrets, separately approved mutations, image digest, container inspection result, public smoke result, Actions URLs, GHCR URL, and TDD non-applicability for external metadata/documentation.

- [ ] **Step 3: Verify, commit, and push documentation**

Run:

```powershell
rg -n "http://|ghcr.io/tianmingyo/camp_harness|container smoke|Aliyun|阿里云" README.md AGENT_LOG.md
C:\Users\13900\anaconda3\python.exe -m pytest -q
ruff check src tests demo
git diff --check
git status --short
git add README.md AGENT_LOG.md docs/superpowers/plans/2026-08-12-aliyun-vps-deployment.md
git commit -m "docs: record Aliyun public deployment"
git push origin feature/feedback-loop-harness
```

- [ ] **Step 4: Reverify final automation and public service**

For the documentation head, require push and pull-request `quality` success, push `publish` success, pull-request `publish` skipped, and anonymous `latest` manifest HTTP 200 with a non-empty digest. Store the observed digest in `$latestDigest`. After explicit replacement approval, run:

```powershell
if ($latestDigest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Invalid GHCR digest' }
$remoteImage = "ghcr.io/tianmingyo/camp_harness@$latestDigest"
ssh @sshArgs "set -eu; sudo docker pull '$remoteImage'; sudo docker stop feedbackloop-harness; sudo docker rm feedbackloop-harness; sudo docker run -d --name feedbackloop-harness --restart unless-stopped -p 80:8000 '$remoteImage'; sudo docker inspect feedbackloop-harness --format '{{.Image}} {{.State.Status}} {{.HostConfig.RestartPolicy.Name}}'"
```

Rerun the complete four-boundary public smoke from Step 1. If the replacement command fails after removing the old container, rerun the same `docker run` command with the previously recorded immutable digest to restore the last verified version.

- [ ] **Step 5: Update Pull Request #1 without merging**

Use the existing in-memory Git credential without printing it. Preserve the current PR body and append the external-delivery facts only when that heading is absent:

```powershell
$pr = Invoke-RestMethod -Headers $githubHeaders -Uri 'https://api.github.com/repos/TianMingYo/Camp_Harness/pulls/1'
$externalDelivery = @"
## External delivery
- public WebUI: $publicUrl
- public container: ghcr.io/tianmingyo/camp_harness:latest
- GitHub quality, container smoke, and publish jobs pass on the current head
- REFLECTION.md remains student-authored and must be completed before submission
"@
$body = if ($pr.body -match '(?m)^## External delivery$') { $pr.body } else { ($pr.body.TrimEnd() + "`n`n" + $externalDelivery.Trim()) }
$payload = @{ body = $body } | ConvertTo-Json
Invoke-RestMethod -Method Patch -Headers $githubHeaders -Uri 'https://api.github.com/repos/TianMingYo/Camp_Harness/pulls/1' -Body $payload -ContentType 'application/json'
```

Query Pull Request #1 again and confirm state `open`, base `main`, head `feature/feedback-loop-harness`, and no merge conflict. Keep `REFLECTION.md` identified as the final student-owned gate.
