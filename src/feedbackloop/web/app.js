import { shouldPollTask, syncApprovalState } from "./task-state.mjs";

const status = document.querySelector("#status");
const button = document.querySelector("#create");
const approve = document.querySelector("#approve");
let currentTask = null;
let poller = null;

async function decideApproval(id, decision) {
  const response = await fetch(`/approvals/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  status.textContent = JSON.stringify(await response.json(), null, 2);
  if (currentTask) await refresh(currentTask);
}

function renderApprovals(approvals = []) {
  const container = document.querySelector("#pending-approvals");
  container.replaceChildren();
  for (const item of approvals.filter((entry) => entry.approval.decision === "pending")) {
    const approval = item.approval;
    const action = item.action;
    const row = document.createElement("div");
    row.className = "approval-row";
    const reason = document.createElement("span");
    reason.textContent = `${approval.reason}: ${action.type} ${action.path_or_command}`;
    const allow = document.createElement("button");
    allow.textContent = "Allow";
    allow.addEventListener("click", () => decideApproval(approval.id, "allowed"));
    const deny = document.createElement("button");
    deny.textContent = "Deny";
    deny.className = "secondary";
    deny.addEventListener("click", () => decideApproval(approval.id, "denied"));
    row.append(reason, allow, deny);
    container.append(row);
  }
}

async function refresh(id) {
  const response = await fetch(`/tasks/${id}`);
  const payload = await response.json();
  status.textContent = JSON.stringify(payload, null, 2);
  renderApprovals(payload.approvals);
  syncApprovalState(payload, approve);
  if (!shouldPollTask(payload) && poller) {
    clearInterval(poller);
    poller = null;
  }
  return payload;
}

function startPolling(id) {
  if (poller) clearInterval(poller);
  poller = setInterval(() => refresh(id), 1200);
}

button.addEventListener("click", async () => {
  let validationArgs;
  let planFiles;
  try {
    validationArgs = JSON.parse(document.querySelector("#validation-args").value || "[]");
    if (!Array.isArray(validationArgs) || validationArgs.some((item) => typeof item !== "string")) {
      throw new TypeError("Validation arguments must be a JSON string array");
    }
    planFiles = JSON.parse(document.querySelector("#plan-files").value || "[]");
    if (!Array.isArray(planFiles) || planFiles.some((item) => typeof item !== "string")) {
      throw new TypeError("Plan files must be a JSON string array");
    }
  } catch (error) {
    status.textContent = error.message;
    return;
  }
  const validationExecutable = document.querySelector("#validation-executable").value.trim();
  const body = {
    repo_root: document.querySelector("#repo").value,
    request: document.querySelector("#request").value,
    provider: document.querySelector("#provider").value,
    base_url: document.querySelector("#base-url").value,
    model: document.querySelector("#model").value,
    plan_files: planFiles,
  };
  if (validationExecutable) {
    body.validation_commands = [{
      kind: "test",
      executable: validationExecutable,
      args: validationArgs,
    }];
  }
  const response = await fetch("/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const task = await response.json();
  status.textContent = JSON.stringify(task, null, 2);
  if (task.id) {
    currentTask = task.id;
    approve.disabled = true;
    const payload = await refresh(task.id);
    if (shouldPollTask(payload)) startPolling(task.id);
  }
});

approve.addEventListener("click", async () => {
  if (!currentTask) return;
  approve.disabled = true;
  const response = await fetch(`/tasks/${currentTask}/plan/approve`, { method: "POST" });
  status.textContent = JSON.stringify(await response.json(), null, 2);
  startPolling(currentTask);
});

document.querySelector("#demo").addEventListener("click", async () => {
  const response = await fetch("/demo/scenario");
  status.textContent = JSON.stringify(await response.json(), null, 2);
});

async function credential(method, body) {
  const provider = encodeURIComponent(document.querySelector("#provider").value);
  const response = await fetch(`/providers/${provider}/credentials`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json();
  document.querySelector("#credential-status").textContent = payload.configured ? "Configured" : "Not configured";
}

async function refreshCredentialStatus() {
  const provider = encodeURIComponent(document.querySelector("#provider").value);
  const response = await fetch(`/providers/${provider}/credentials`);
  if (!response.ok) return;
  const payload = await response.json();
  document.querySelector("#credential-status").textContent = payload.configured ? "Configured" : "Not configured";
}

document.querySelector("#save-key").addEventListener("click", () => {
  const input = document.querySelector("#key");
  credential("POST", { key: input.value }).finally(() => { input.value = ""; });
});
document.querySelector("#clear-key").addEventListener("click", () => credential("DELETE"));
document.querySelector("#provider").addEventListener("change", refreshCredentialStatus);
refreshCredentialStatus();
