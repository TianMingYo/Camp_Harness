# Render Public Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the safe mock WebUI through Render, publish the tested Docker image through public GHCR, and record a reproducible course-compliant delivery without merging Pull Request #1.

**Architecture:** A parsed configuration contract drives `render.yaml`, dynamic Docker port handling, GitHub-hosted container smoke, and a separate least-privilege GHCR publish job. The quality job exports the exact image that passed smoke as a short-lived artifact; the publish job loads that artifact instead of rebuilding it. External provisioning occurs only after independent review and green CI; the controller then verifies anonymous image access and the live public security boundary before recording real URLs. The student-authored reflection remains a final human-owned gate.

**Tech Stack:** Python 3.12, pytest, PyYAML `BaseLoader`, Docker, GitHub Actions, GitHub Container Registry, Render Blueprint, FastAPI/Uvicorn, PowerShell.

## Global Constraints

- Work only in `C:\Users\13900\Desktop\作业\智软训练营\.worktrees\feedback-loop-harness` on `feature/feedback-loop-harness`.
- Keep Pull Request #1 open; do not merge, force-push, delete the branch, or remove the worktree.
- Do not edit, stage, or commit the dirty main worktree's existing files.
- Every behavior/configuration change follows RED -> GREEN -> REFACTOR and records exact evidence in `AGENT_LOG.md`.
- The public service starts only `feedbackloop.api:demo_app`; it receives no real provider key, host repository path, persistent disk, or visitor-controlled execution permission.
- The Render service uses `plan: free`, `region: singapore`, branch `feature/feedback-loop-harness`, and `autoDeployTrigger: checksPass`.
- The public image path is exactly `ghcr.io/tianmingyo/camp_harness`; publish full commit SHA and `latest` tags on `push` only.
- Registry publication uses `${{ secrets.GITHUB_TOKEN }}` with `contents: read` and `packages: write`; add no long-lived registry secret.
- Changing the GHCR package to Public is irreversible and requires the already-recorded human approval plus a separate managed action approval at execution time.
- Never guess a Render URL, GHCR digest, CI result, or deployment result; record only observed values.
- `REFLECTION.md` content must be written by the student. The agent may organize or polish supplied text only with disclosure and explicit student approval.

---

## File Map

- `render.yaml`: one reproducible Render Docker Web Service and its branch, plan, health, and deploy gate.
- `Dockerfile`: public demo image, OCI source linkage, and `${PORT:-8000}` runtime behavior.
- `.github/workflows/ci.yml`: quality job with dynamic-port smoke plus dependent push-only GHCR publication.
- `tests/demo/test_render_delivery.py`: parsed Blueprint and Docker command/label contracts.
- `tests/demo/test_github_delivery.py`: exact GitHub Actions jobs, permissions, ordering, smoke, cleanup, and publish contract.
- `README.md`: public URL, Render architecture, sleep behavior, Deploy to Render link, and anonymous GHCR commands.
- `AGENT_LOG.md`: TDD evidence, reviews, approvals, external results, public URL, image digest, and deviations.
- `REFLECTION.md`: student-owned 1500-2500-character reflection; no agent-authored submission prose.

---

### Task 1: Render, Dynamic-Port Container, And GHCR Contract

**Files:**
- Create: `render.yaml`
- Create: `tests/demo/test_render_delivery.py`
- Modify: `Dockerfile`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/demo/test_github_delivery.py`
- Modify: `AGENT_LOG.md`

**Interfaces:**
- Consumes: `feedbackloop.api:demo_app`, `python -m pytest -q`, `python -m demo.scenario`, repository `Dockerfile`, GitHub-provided `GITHUB_TOKEN`.
- Produces: Render Blueprint service `feedbackloop-harness-demo`; Docker runtime honoring `PORT`; GitHub `quality` and `publish` jobs; short-lived artifact `feedbackloop-demo-image`; images `ghcr.io/tianmingyo/camp_harness:${{ github.sha }}` and `:latest`.

- [ ] **Step 1: Replace the workflow test with the stronger two-job contract**

Update `tests/demo/test_github_delivery.py` to this exact content:

```python
from pathlib import Path

import yaml


def _workflow() -> dict:
    root = Path(__file__).parents[2]
    return yaml.load(
        (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_github_workflow_runs_quality_and_dynamic_port_smoke():
    workflow = _workflow()
    assert workflow["name"] == "CI"
    assert set(workflow["on"]) == {"push", "pull_request"}
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"quality", "publish"}

    quality = workflow["jobs"]["quality"]
    assert quality["runs-on"] == "ubuntu-latest"
    steps = quality["steps"]
    assert steps[:6] == [
        {"uses": "actions/checkout@v4"},
        {
            "uses": "actions/setup-python@v5",
            "with": {"python-version": "3.12"},
        },
        {"run": 'python -m pip install ".[test]"'},
        {"run": "python -m pytest -q"},
        {"run": "python -m demo.scenario"},
        {"run": "docker build -t feedbackloop-demo ."},
    ]
    assert steps[6]["name"] == "Smoke dynamic-port container"
    assert steps[6]["run"].splitlines() == [
        "docker run -d --name feedbackloop-smoke -e PORT=10000 -p 10000:10000 feedbackloop-demo",
        "curl --fail --retry 20 --retry-delay 1 --retry-all-errors http://127.0.0.1:10000/demo/scenario -o /tmp/demo-scenario.json",
        "python -c 'import json; from pathlib import Path; data=json.loads(Path(\"/tmp/demo-scenario.json\").read_text()); assert data == {\"mode\": \"mock\", \"repository\": \"embedded-sample\", \"iterations\": [\"test_failure\", \"pass\"], \"approval\": \"delete_requires_approval\"}'",
    ]
    assert steps[7] == {
        "name": "Clean up smoke container",
        "if": "always()",
        "run": "docker rm -f feedbackloop-smoke || true",
    }
    branch_push = (
        "github.event_name == 'push' && "
        "github.ref == 'refs/heads/feature/feedback-loop-harness'"
    )
    assert steps[8] == {
        "name": "Save tested image",
        "if": branch_push,
        "run": "docker save feedbackloop-demo -o feedbackloop-demo.tar",
    }
    assert steps[9] == {
        "name": "Upload tested image",
        "if": branch_push,
        "uses": "actions/upload-artifact@v4",
        "with": {
            "name": "feedbackloop-demo-image",
            "path": "feedbackloop-demo.tar",
            "retention-days": "1",
        },
    }


def test_github_workflow_publishes_ghcr_only_after_push_quality():
    publish = _workflow()["jobs"]["publish"]
    assert publish["if"] == (
        "github.event_name == 'push' && "
        "github.ref == 'refs/heads/feature/feedback-loop-harness'"
    )
    assert publish["needs"] == "quality"
    assert publish["runs-on"] == "ubuntu-latest"
    assert publish["permissions"] == {"contents": "read", "packages": "write"}
    assert publish["steps"][:3] == [
        {
            "uses": "actions/download-artifact@v4",
            "with": {"name": "feedbackloop-demo-image"},
        },
        {"run": "docker load --input feedbackloop-demo.tar"},
        {
            "uses": "docker/login-action@v3",
            "with": {
                "registry": "ghcr.io",
                "username": "${{ github.actor }}",
                "password": "${{ secrets.GITHUB_TOKEN }}",
            },
        },
    ]
    assert publish["steps"][3]["name"] == "Publish tested image"
    assert publish["steps"][3]["run"].splitlines() == [
        "docker tag feedbackloop-demo ghcr.io/tianmingyo/camp_harness:${{ github.sha }}",
        "docker tag feedbackloop-demo ghcr.io/tianmingyo/camp_harness:latest",
        "docker push ghcr.io/tianmingyo/camp_harness:${{ github.sha }}",
        "docker push ghcr.io/tianmingyo/camp_harness:latest",
    ]
```

- [ ] **Step 2: Add failing Render and Docker contracts**

Create `tests/demo/test_render_delivery.py`:

```python
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_render_blueprint_deploys_safe_feature_branch_after_checks():
    blueprint = yaml.load(
        (ROOT / "render.yaml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert blueprint == {
        "services": [
            {
                "type": "web",
                "name": "feedbackloop-harness-demo",
                "runtime": "docker",
                "plan": "free",
                "region": "singapore",
                "repo": "https://github.com/TianMingYo/Camp_Harness",
                "branch": "feature/feedback-loop-harness",
                "dockerfilePath": "./Dockerfile",
                "dockerContext": ".",
                "healthCheckPath": "/",
                "autoDeployTrigger": "checksPass",
            }
        ]
    }


def test_docker_image_links_source_and_honors_render_port():
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    assert (
        'LABEL org.opencontainers.image.source="https://github.com/TianMingYo/Camp_Harness"'
        in lines
    )
    command_line = next(line for line in lines if line.startswith("CMD "))
    assert json.loads(command_line.removeprefix("CMD ")) == [
        "sh",
        "-c",
        'exec python -m uvicorn feedbackloop.api:demo_app --host 0.0.0.0 --port "${PORT:-8000}"',
    ]
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_render_delivery.py tests/demo/test_github_delivery.py -q
```

Expected failures:

- `FileNotFoundError` for absent `render.yaml`;
- missing OCI source label and fixed-port Docker command mismatch;
- workflow job set `{'quality'}` does not match `{'quality', 'publish'}`;
- existing workflow has no dynamic-port smoke or GHCR publish contract.

- [ ] **Step 4: Add the minimal Render Blueprint**

Create `render.yaml`:

```yaml
services:
  - type: web
    name: feedbackloop-harness-demo
    runtime: docker
    plan: free
    region: singapore
    repo: https://github.com/TianMingYo/Camp_Harness
    branch: feature/feedback-loop-harness
    dockerfilePath: ./Dockerfile
    dockerContext: .
    healthCheckPath: /
    autoDeployTrigger: checksPass
```

- [ ] **Step 5: Make the Docker command Render-compatible and link its source**

Replace `Dockerfile` with:

```dockerfile
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/TianMingYo/Camp_Harness"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY demo ./demo
RUN python -m pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn feedbackloop.api:demo_app --host 0.0.0.0 --port \"${PORT:-8000}\""]
```

- [ ] **Step 6: Add quality smoke and dependent GHCR publication**

Replace `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install ".[test]"
      - run: python -m pytest -q
      - run: python -m demo.scenario
      - run: docker build -t feedbackloop-demo .
      - name: Smoke dynamic-port container
        run: |
          docker run -d --name feedbackloop-smoke -e PORT=10000 -p 10000:10000 feedbackloop-demo
          curl --fail --retry 20 --retry-delay 1 --retry-all-errors http://127.0.0.1:10000/demo/scenario -o /tmp/demo-scenario.json
          python -c 'import json; from pathlib import Path; data=json.loads(Path("/tmp/demo-scenario.json").read_text()); assert data == {"mode": "mock", "repository": "embedded-sample", "iterations": ["test_failure", "pass"], "approval": "delete_requires_approval"}'
      - name: Clean up smoke container
        if: always()
        run: docker rm -f feedbackloop-smoke || true
      - name: Save tested image
        if: github.event_name == 'push' && github.ref == 'refs/heads/feature/feedback-loop-harness'
        run: docker save feedbackloop-demo -o feedbackloop-demo.tar
      - name: Upload tested image
        if: github.event_name == 'push' && github.ref == 'refs/heads/feature/feedback-loop-harness'
        uses: actions/upload-artifact@v4
        with:
          name: feedbackloop-demo-image
          path: feedbackloop-demo.tar
          retention-days: 1

  publish:
    if: github.event_name == 'push' && github.ref == 'refs/heads/feature/feedback-loop-harness'
    needs: quality
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: feedbackloop-demo-image
      - run: docker load --input feedbackloop-demo.tar
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Publish tested image
        run: |
          docker tag feedbackloop-demo ghcr.io/tianmingyo/camp_harness:${{ github.sha }}
          docker tag feedbackloop-demo ghcr.io/tianmingyo/camp_harness:latest
          docker push ghcr.io/tianmingyo/camp_harness:${{ github.sha }}
          docker push ghcr.io/tianmingyo/camp_harness:latest
```

- [ ] **Step 7: Run focused GREEN and complete regression**

Run:

```powershell
C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_render_delivery.py tests/demo/test_github_delivery.py -q
C:\Users\13900\anaconda3\python.exe -m pytest -q
ruff check src tests demo
C:\Users\13900\anaconda3\python.exe -m compileall -q src demo tests
C:\Users\13900\anaconda3\python.exe -m demo.scenario
git diff --check
```

Expected: focused and full pytest pass with only the documented Windows symlink skip and TestClient warning; Ruff and compileall exit zero; demo reports `corrected_after_feedback=true`, `policy_blocked=true`, `used_network=false`, `final_state=succeeded`; diff check exits zero.

- [ ] **Step 8: Record exact TDD evidence and commit**

Append the actual RED/GREEN command outputs, mutation rationale, Docker-local limitation, and reviewer handoff to `AGENT_LOG.md`. Then run:

```powershell
git add render.yaml Dockerfile .github/workflows/ci.yml tests/demo/test_render_delivery.py tests/demo/test_github_delivery.py AGENT_LOG.md
git commit -m "ci: add public deployment and image delivery"
```

The task is complete only after an independent reviewer approves the complete task range.

---

### Task 2: Publish And Verify GitHub CI And Public GHCR

**Files:**
- Modify: remote branch and GitHub package metadata only; no source file change is expected.

**Interfaces:**
- Consumes: reviewed Task 1 commit, Pull Request #1, GitHub Actions `quality` and `publish` jobs.
- Produces: green final CI run, private-first GHCR package, human-approved Public visibility, anonymous `latest` manifest digest.

- [ ] **Step 1: Push the reviewed Task 1 range normally**

Run:

```powershell
git status --short
git push
```

Expected: clean worktree before push; no force; feature upstream advances normally.

- [ ] **Step 2: Verify both GitHub jobs on the pushed SHA**

Use the existing in-memory Git credential with the GitHub REST API. Query Pull Request #1 for `head.sha`, then query Actions runs and jobs for that SHA. Require:

- `quality` conclusion `success`;
- dynamic-port smoke step conclusion `success`;
- `publish` conclusion `success` on the `push` event;
- `pull_request` event runs `quality` but skips `publish`.

Do not use a previous SHA's success as evidence for the current head.

- [ ] **Step 3: Open the package settings and make GHCR Public**

Open:

```text
https://github.com/users/TianMingYo/packages/container/package/camp_harness/settings
```

The student/controller confirms the package name, chooses **Change visibility -> Public**, types the package confirmation requested by GitHub, and accepts the irreversible change. Do not change visibility before the first successful publish job creates the package.

- [ ] **Step 4: Verify anonymous registry access**

Run without a GitHub credential:

```powershell
$anonymous = Invoke-RestMethod -Uri 'https://ghcr.io/token?scope=repository:tianmingyo/camp_harness:pull'
$headers = @{
  Authorization = "Bearer $($anonymous.token)"
  Accept = 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json'
}
$manifest = Invoke-WebRequest -Uri 'https://ghcr.io/v2/tianmingyo/camp_harness/manifests/latest' -Headers $headers -UseBasicParsing
[pscustomobject]@{
  status = $manifest.StatusCode
  digest = $manifest.Headers['Docker-Content-Digest']
} | ConvertTo-Json -Compress
```

Expected: HTTP `200` and a non-empty `sha256:` digest. Do not print the anonymous bearer token.

- [ ] **Step 5: Record the external result for final documentation**

Retain these observed values for Task 3:

- Task 1 Git commit SHA;
- successful Actions run URLs and job conclusions;
- package page URL;
- anonymous `latest` digest;
- timestamp of the irreversible Public visibility action.

Do not edit `AGENT_LOG.md` yet; Task 3 records all external delivery results with the real Render URL in one documentation commit.

---

### Task 3: Provision Render, Verify Public Boundaries, And Record Delivery

**Files:**
- Modify: `README.md`
- Modify: `AGENT_LOG.md`
- Modify: Pull Request #1 body through the GitHub API.

**Interfaces:**
- Consumes: reviewed and published feature head, public GHCR digest, branch-specific Render Blueprint URL.
- Produces: the live Render HTTPS URL copied from the service dashboard, verified public safety responses, reproducible README, and final deployment audit.

- [ ] **Step 1: Open the branch-specific Render Blueprint**

Open this exact URL in the user's browser:

```text
https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FTianMingYo%2FCamp_Harness%2Ftree%2Ffeature%2Ffeedback-loop-harness
```

The student signs in, authorizes the public GitHub repository if prompted, reviews one service named `feedbackloop-harness-demo`, confirms `Free`, and creates it. Do not add environment variables, secrets, databases, persistent disks, or paid instances.

- [ ] **Step 2: Wait for a live deployment and capture the real URL**

Use the Render dashboard to require:

- Blueprint sync succeeds;
- Docker build succeeds;
- health check `/` succeeds;
- live deploy commit equals the reviewed GitHub head.

Copy the actual `onrender.com` URL from the service dashboard. Do not derive it from the requested service name.

- [ ] **Step 3: Run the public behavior and security smoke**

Set `$publicUrl` to the observed URL and run:

```powershell
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
    credential = client.post(
        f"{base}/providers/demo/credentials",
        json={"key": secret},
    )
    assert credential.status_code == 403
    assert secret not in credential.text

    task = client.post(
        f"{base}/tasks",
        json={
            "repo_root": "C:/visitor/repository",
            "request": "modify a file",
            "plan_files": ["README.md"],
        },
    )
    assert task.status_code == 400
    assert task.json()["detail"] == "public demo does not accept local repository paths"

print({"url": base, "root": root.status_code, "demo": demo.json(), "credential": credential.status_code, "task": task.status_code})
'@ | C:\Users\13900\anaconda3\python.exe - $publicUrl
```

Expected: root `200`, exact deterministic demo JSON, credential `403`, task `400`, and no secret echo. Allow up to 120 seconds for a free-instance cold start.

- [ ] **Step 4: Update README with observed delivery facts**

Add a `## Public deployment` section after `## Distribution` containing:

```markdown
## Public deployment

- Source: `feature/feedback-loop-harness` through Pull Request #1
- Architecture: GitHub push -> `quality` tests/container smoke -> GHCR publish -> Render `checksPass` deploy
- Render plan: Free Web Service in Singapore, Docker runtime, `/` health check, ephemeral filesystem, no secrets

Free Render services sleep after 15 minutes without inbound traffic. The first request after idle can take about one minute while the service starts.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FTianMingYo%2FCamp_Harness%2Ftree%2Ffeature%2Ffeedback-loop-harness)
```

Immediately below the heading, add a first bullet `- WebUI: ` followed by the exact `$publicUrl` value captured from the Render dashboard. Do not type an inferred service URL.

Extend `## Distribution` with:

```powershell
docker pull ghcr.io/tianmingyo/camp_harness:latest
docker run --rm -p 8000:8000 ghcr.io/tianmingyo/camp_harness:latest
```

Remove the obsolete Known Limits statement that says the public deployment URL is not configured. Add the actual free-tier sleep and ephemeral-state limitations instead.

- [ ] **Step 5: Record external actions and TDD applicability**

Append to `AGENT_LOG.md`:

- design and plan commit hashes;
- Task 1 RED/GREEN/review commit hashes;
- final `quality` and `publish` run URLs and conclusions;
- GHCR package URL, irreversible Public visibility approval, and anonymous digest;
- Render Blueprint approval, observed service URL, live commit SHA, and public security-smoke results;
- explanation that Task 3 changes external metadata and human documentation only, so no new product behavior TDD cycle applies;
- remaining `REFLECTION.md` student-owned gate.

- [ ] **Step 6: Verify and commit the documentation**

Run:

```powershell
rg -n "onrender.com|ghcr.io/tianmingyo/camp_harness|Deploy to Render|checksPass" README.md AGENT_LOG.md
git diff --check
git status --short
```

Expected: real Render URL present; public GHCR path present; no unresolved deployment marker; only README and audit log modified.

Then run:

```powershell
git add README.md AGENT_LOG.md
git commit -m "docs: record public deployment and distribution"
git push
```

- [ ] **Step 7: Require final automation on the documentation head**

For the new head SHA, require:

- GitHub `quality` success including dynamic-port smoke;
- GitHub `publish` success with SHA and `latest` tags;
- anonymous `latest` manifest resolves to the new digest;
- Render auto-deploy after checks succeeds and reports the new head;
- the public security smoke still passes.

- [ ] **Step 8: Update Pull Request #1 without merging**

Through the GitHub REST API, build the external-delivery section from the observed `$publicUrl`:

```powershell
$externalDelivery = @"
## External delivery
- public WebUI: $publicUrl
- public container: ghcr.io/tianmingyo/camp_harness:latest
- GitHub quality, container smoke, and publish jobs pass on the current head
- REFLECTION.md remains student-authored and must be completed before submission
"@
```

Use `$externalDelivery` in the API payload. Confirm PR state remains `open`, base `main`, head `feature/feedback-loop-harness`, and mergeable state is not conflicted.

---

### Task 4: Student Reflection And Final Submission Gate

**Files:**
- Modify: `REFLECTION.md` only after the student supplies the content.
- Modify: `AGENT_LOG.md` only to disclose any AI organization/polishing assistance.

**Interfaces:**
- Consumes: student's own judgments and project evidence in `SPEC_PROCESS.md`, `AGENT_LOG.md`, and Git history.
- Produces: student-approved 1500-2500-character Chinese reflection and final green repository head.

- [ ] **Step 1: Interview the student one question at a time**

Collect the student's own answers for all eight existing prompts in `REFLECTION.md`. Ask for concrete personal judgments, at least two named RED -> GREEN examples, one subagent deviation example, and one criticism of Superpowers assumptions. Do not draft answers on the student's behalf.

- [ ] **Step 2: Organize only supplied content**

After the student provides answers, organize them into a coherent reflection. Preserve the student's claims and tone. If wording is polished, add a final disclosure such as:

```markdown
> 本文观点、案例与判断由学生本人提供；AI 仅协助结构整理与语言润色。
```

The student reviews and explicitly approves the full text before it is written to `REFLECTION.md`.

- [ ] **Step 3: Verify reflection scope and required topics**

Run a character count and topic scan:

```powershell
$text = Get-Content -Raw -Encoding UTF8 REFLECTION.md
$plain = $text -replace '\s', ''
[pscustomobject]@{
  characters_without_whitespace = $plain.Length
  has_tdd = $text -match 'TDD|RED|GREEN|红|绿'
  has_subagent = $text -match 'subagent'
  has_spec_plan = $text -match 'SPEC|PLAN'
  has_credentials_distribution = $text -match '凭据|key|分发|容器'
  has_criticism = $text -match '批判|不足|形式|假设'
} | ConvertTo-Json -Compress
```

Expected: 1500-2500 non-whitespace characters and every topic flag `true`. This check validates coverage only; it does not replace student authorship review.

- [ ] **Step 4: Commit only after explicit student approval**

Run:

```powershell
git add REFLECTION.md AGENT_LOG.md
git commit -m "docs: add student reflection"
git push
```

- [ ] **Step 5: Perform final end-to-end verification**

Require the final reflection head to satisfy:

```powershell
C:\Users\13900\anaconda3\python.exe -m pytest -q
ruff check src tests demo
C:\Users\13900\anaconda3\python.exe -m compileall -q src demo tests
C:\Users\13900\anaconda3\python.exe -m demo.scenario
git diff --check
git status --short --branch
```

Also require final GitHub `quality` and `publish` jobs success, anonymous GHCR access, Render deployment success, live public security smoke, public repository visibility, and PR #1 remaining open. Preserve the branch and worktree for PR feedback.

## Plan Self-Review

- **Spec coverage:** Task 1 covers Blueprint, dynamic port, health contract, GitHub container smoke, least-privilege GHCR publication, and TDD/review evidence. Task 2 covers real CI, irreversible public package visibility, and anonymous registry verification. Task 3 covers Render provisioning, observed URL/security behavior, reproducible README, final automation, and PR metadata. Task 4 covers the non-delegable student reflection and final repository head.
- **Plan completeness:** Runtime URLs and digests are always captured into named variables before documentation or API updates. Every code/configuration step contains exact content, and every external step defines its observable success condition.
- **Interface consistency:** Branch, repository, service name, registry path, image tags, Render region/plan, health path, workflow job names, and public API expectations match the approved design throughout.
- **Scope:** Delivery configuration, public distribution, cloud deployment, and the human reflection are sequential parts of one final course-delivery workflow; no unrelated product feature or refactor is included.
