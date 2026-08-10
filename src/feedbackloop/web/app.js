const status = document.querySelector("#status");
const button = document.querySelector("#create");
const approve = document.querySelector("#approve");
let currentTask = null;
let poller = null;

async function refresh(id) {
  const response = await fetch(`/tasks/${id}`);
  status.textContent = JSON.stringify(await response.json(), null, 2);
}

function startPolling(id) {
  if (poller) clearInterval(poller);
  poller = setInterval(() => refresh(id), 1200);
}

button.addEventListener("click", async () => {
  const response = await fetch("/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      repo_root: document.querySelector("#repo").value,
      request: document.querySelector("#request").value,
    }),
  });
  const task = await response.json();
  status.textContent = JSON.stringify(task, null, 2);
  if (task.id) {
    currentTask = task.id;
    approve.disabled = false;
    await refresh(task.id);
  }
});

approve.addEventListener("click", async () => {
  if (!currentTask) return;
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

document.querySelector("#save-key").addEventListener("click", () => {
  const input = document.querySelector("#key");
  credential("POST", { key: input.value }).finally(() => { input.value = ""; });
});
document.querySelector("#clear-key").addEventListener("click", () => credential("DELETE"));
