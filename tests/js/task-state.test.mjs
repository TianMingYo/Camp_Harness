import assert from "node:assert/strict";
import {
  shouldPollTask,
  syncApprovalState,
} from "../../src/feedbackloop/web/task-state.mjs";

const approveButton = { disabled: false };

const draft = { task: { state: "draft" } };
syncApprovalState(draft, approveButton);
assert.equal(approveButton.disabled, true);
assert.equal(shouldPollTask(draft), true);

const ready = { task: { state: "awaiting_plan_approval" } };
syncApprovalState(ready, approveButton);
assert.equal(approveButton.disabled, false);
assert.equal(shouldPollTask(ready), false);

const failed = { task: { state: "failed" } };
syncApprovalState(failed, approveButton);
assert.equal(approveButton.disabled, true);
assert.equal(shouldPollTask(failed), false);
