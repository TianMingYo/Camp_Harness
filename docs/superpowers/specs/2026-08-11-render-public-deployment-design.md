# Render Public Deployment Design

**Date:** 2026-08-11

**Goal:** Publish the deterministic public mock WebUI at a reproducible HTTPS URL while preserving Pull Request #1, keeping real credentials and local repositories outside the public service, and satisfying the course deployment and CI/CD requirements.

## Approved Direction

Use a Render Blueprint backed by the public GitHub repository `https://github.com/TianMingYo/Camp_Harness` and branch `feature/feedback-loop-harness`. The Pull Request remains open and is not merged. Render builds the repository Dockerfile and publishes a free Web Service at an `onrender.com` URL.

Render was selected over a manual dashboard-only service because Blueprint configuration is reviewable and reproducible. Railway's free allowance is smaller and Fly.io does not provide a general free tier suitable for this course deployment. Temporary tunnels are excluded because their URLs and processes are not reliable through the submission deadline.

## Deployment Architecture

Add a root `render.yaml` containing one service with these fixed properties:

- `name: feedbackloop-harness-demo`
- `type: web`
- `runtime: docker`
- `plan: free`
- `region: singapore`
- repository `https://github.com/TianMingYo/Camp_Harness`
- branch `feature/feedback-loop-harness`
- Dockerfile and build context at the repository root
- `healthCheckPath: /`
- `autoDeployTrigger: checksPass`

The branch-specific provisioning link is `https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FTianMingYo%2FCamp_Harness%2Ftree%2Ffeature%2Ffeedback-loop-harness`. Render recommends disabling auto-deploy for generic templates that many unrelated users duplicate. This Blueprint is for the project owner's single course deployment, so `checksPass` is deliberately used to provide the required CI/CD gate.

The Docker image continues to start `feedbackloop.api:demo_app`. The container command binds to `0.0.0.0` and reads Render's `PORT`, falling back to `8000` for local `docker run` compatibility. No database or persistent disk is provisioned because the public demo intentionally uses disposable state.

## Public Security Boundary

The deployed service exposes only `demo_app`, never the full local composition root. It uses the deterministic mock mechanism and temporary built-in repository. The public instance must continue to reject:

- credential creation, update, and deletion;
- arbitrary local repository paths;
- real provider configuration and LLM keys;
- visitor-controlled shell, network, or Git push execution.

No Render secret or environment variable is required. The Blueprint, README, logs, and deployment output must contain no API tokens. Render's ephemeral filesystem is acceptable because the public demo is stateless by design.

## CI/CD Flow

GitHub remains the source of truth. Each feature-branch push runs the existing `quality` job. The job must:

1. install the package and test dependencies;
2. run the complete pytest suite;
3. run the deterministic offline mechanism demo;
4. build the Docker image;
5. start the image with `PORT=10000`;
6. perform an HTTP smoke request against `/demo/scenario` and confirm the expected deterministic JSON;
7. remove the smoke container even when the request fails.

Render deploys a commit only after the linked GitHub checks pass. This makes the deployment sequence `push -> GitHub tests/build/smoke -> Render deploy` and prevents a failed branch head from replacing the public service.

## Repository Changes

- Create `render.yaml` for the Render Blueprint.
- Create a parsed Blueprint delivery test.
- Update the Dockerfile to honor `${PORT:-8000}` without changing `demo_app`.
- Extend the GitHub Actions contract and workflow with a dynamic-port container smoke test and cleanup.
- Update README with deployment architecture, Deploy to Render link, free-tier sleep behavior, operational verification, and the real public URL after provisioning.
- Update `AGENT_LOG.md` with exact RED/GREEN evidence, Render authorization, external deployment results, URL checks, and any justified deviation.
- Leave `REFLECTION.md` as a student-owned template until the student supplies their own judgments and examples.

## TDD And Review

Before changing delivery configuration, add focused tests that require:

- the exact Render service type, runtime, plan, region, repository, branch, health check, and checks-pass deployment trigger;
- a Docker command that starts `demo_app` and honors the runtime `PORT` with local fallback;
- ordered GitHub Actions steps that run the image on port `10000`, smoke `/demo/scenario`, and clean up.

Run the focused tests and confirm RED against the current tree. Add only the minimal Blueprint, Docker, and workflow changes required for GREEN. Run the full suite, Ruff, compileall, offline demo, and diff checks. Use an independent reviewer before external provisioning.

Because Docker is unavailable locally, dynamic-port container execution is verified by GitHub-hosted CI. A successful Docker build alone is insufficient; the smoke request must pass on the exact commit deployed by Render.

## Provisioning And Verification

After the implementation commits pass review and GitHub Actions:

1. Open the branch-specific Render Blueprint deployment URL.
2. The student signs in to Render and authorizes the public GitHub repository when prompted.
3. Review the Blueprint and create the free service; do not select a paid instance or add secrets.
4. Wait for the first deployment to become live and capture the actual `onrender.com` URL.
5. Verify `/` returns the WebUI and `/demo/scenario` returns the deterministic successful mechanism result.
6. Verify public credential and task-creation boundaries remain denied.
7. Add the real URL to README and the audit log, push, and require both final GitHub CI and Render redeployment to pass.

The URL is never guessed or recorded before a live response is observed. Render free services may sleep after 15 minutes without traffic, so README must state that the first request after idle can take about one minute.

## Failure Handling

- Blueprint validation failure: correct the smallest invalid field through a focused RED/GREEN test.
- GitHub CI failure: inspect the first failing test or container-smoke step and do not provision or redeploy that head.
- Render build/start failure: use the first root-cause log entry; do not switch to an unstable public tunnel.
- Health or security check failure: keep the URL out of the final README until the deployed behavior is corrected and independently verified.
- Render authentication or account restriction: stop without creating paid resources and report the exact external blocker.

## Reflection Boundary

The agent will not author the required 1500-2500-character personal reflection. After deployment, the student can answer the existing prompts using their own experience. The agent may organize or polish the student's supplied text only if the final file discloses that limited assistance. Project facts in `SPEC_PROCESS.md`, `AGENT_LOG.md`, and Git history can be used as evidence, but personal judgments must come from the student.

## External References

- Render Blueprint specification: https://render.com/docs/blueprint-spec
- Render Docker deployment: https://render.com/docs/docker
- Render health checks: https://render.com/docs/health-checks
- Render free service limitations: https://render.com/docs/free
- Deploy to Render button: https://render.com/docs/deploy-to-render
