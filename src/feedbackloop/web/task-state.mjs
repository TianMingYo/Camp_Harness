const POLLING_STATES = new Set([
  "draft",
  "running",
  "awaiting_action_approval",
]);

export function syncApprovalState(payload, approveButton) {
  approveButton.disabled = payload?.task?.state !== "awaiting_plan_approval";
}

export function shouldPollTask(payload) {
  return POLLING_STATES.has(payload?.task?.state);
}
