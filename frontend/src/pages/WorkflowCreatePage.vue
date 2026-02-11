<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

type StageDraft = {
  key: string;
  name: string;
  is_done: boolean;
  is_qa: boolean;
  counts_as_wip: boolean;
};

function makeKey(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const name = ref("");
const stages = ref<StageDraft[]>([
  { key: makeKey(), name: "Backlog", is_done: false, is_qa: false, counts_as_wip: false },
  { key: makeKey(), name: "In Progress", is_done: false, is_qa: false, counts_as_wip: true },
  { key: makeKey(), name: "QA", is_done: false, is_qa: true, counts_as_wip: true },
  { key: makeKey(), name: "Done", is_done: true, is_qa: false, counts_as_wip: false },
]);

const saving = ref(false);
const error = ref("");

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canEdit = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

function selectDoneStage(selectedKey: string) {
  stages.value = stages.value.map((s) => ({ ...s, is_done: s.key === selectedKey }));
}

function addStage() {
  stages.value = [
    ...stages.value,
    { key: makeKey(), name: "", is_done: false, is_qa: false, counts_as_wip: true },
  ];
}

function removeStage(key: string) {
  if (stages.value.length <= 1) {
    return;
  }
  const removed = stages.value.find((s) => s.key === key);
  stages.value = stages.value.filter((s) => s.key !== key);
  if (removed?.is_done) {
    const last = stages.value[stages.value.length - 1];
    if (last) {
      selectDoneStage(last.key);
    }
  }
}

function moveStage(key: string, direction: -1 | 1) {
  const idx = stages.value.findIndex((s) => s.key === key);
  if (idx < 0) {
    return;
  }
  const nextIdx = idx + direction;
  if (nextIdx < 0 || nextIdx >= stages.value.length) {
    return;
  }

  const next = [...stages.value];
  const moved = next.splice(idx, 1)[0];
  if (!moved) {
    return;
  }
  next.splice(nextIdx, 0, moved);
  stages.value = next;
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function submit() {
  error.value = "";
  if (!context.orgId) {
    error.value = "Select an org to continue.";
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  const trimmedName = name.value.trim();
  if (!trimmedName) {
    error.value = "Workflow name is required.";
    return;
  }

  const stagePayloads = stages.value.map((s, idx) => ({
    name: s.name.trim(),
    order: idx + 1,
    is_done: s.is_done,
    is_qa: s.is_qa,
    counts_as_wip: s.counts_as_wip,
  }));

  if (stagePayloads.some((s) => !s.name)) {
    error.value = "All stages must have a name.";
    return;
  }

  if (stagePayloads.filter((s) => s.is_done).length !== 1) {
    error.value = "Select exactly one done stage.";
    return;
  }

  saving.value = true;
  try {
    const res = await api.createWorkflow(context.orgId, { name: trimmedName, stages: stagePayloads });
    await router.push(`/settings/workflows/${res.workflow.id}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Not permitted.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div>
    <RouterLink to="/settings/workflows">← Back to workflows</RouterLink>

    <div class="card">
      <h1 class="page-title">Create workflow</h1>
      <p class="muted">Workflows are scoped to the selected org.</p>

      <p v-if="!context.orgId" class="muted">Select an org to continue.</p>
      <p v-else-if="!canEdit" class="muted">Only PM/admin can create workflows.</p>

      <div class="form">
        <label class="field">
          <span class="label">Name</span>
          <input v-model="name" type="text" :disabled="saving || !canEdit || !context.orgId" />
        </label>

        <h2 class="section-title">Stages</h2>
        <div class="table-wrap">
          <pf-table aria-label="Workflow stage draft table">
            <pf-thead>
              <pf-tr>
                <pf-th>#</pf-th>
                <pf-th>Name</pf-th>
                <pf-th>Done</pf-th>
                <pf-th>QA</pf-th>
                <pf-th>WIP</pf-th>
                <pf-th>Actions</pf-th>
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="(stage, idx) in stages" :key="stage.key">
                <pf-td class="mono" data-label="#">{{ idx + 1 }}</pf-td>
                <pf-td data-label="Name">
                  <input
                    v-model="stage.name"
                    type="text"
                    placeholder="Stage name"
                    :disabled="saving || !canEdit || !context.orgId"
                  />
                </pf-td>
                <pf-td data-label="Done">
                  <input
                    type="radio"
                    name="done"
                    :checked="stage.is_done"
                    :disabled="saving || !canEdit || !context.orgId"
                    @change="selectDoneStage(stage.key)"
                  />
                </pf-td>
                <pf-td data-label="QA">
                  <input
                    v-model="stage.is_qa"
                    type="checkbox"
                    :disabled="saving || !canEdit || !context.orgId"
                  />
                </pf-td>
                <pf-td data-label="WIP">
                  <input
                    v-model="stage.counts_as_wip"
                    type="checkbox"
                    :disabled="saving || !canEdit || !context.orgId"
                  />
                </pf-td>
                <pf-td class="actions" data-label="Actions">
                  <button
                    type="button"
                    :disabled="saving || !canEdit || !context.orgId || idx === 0"
                    @click="moveStage(stage.key, -1)"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    :disabled="saving || !canEdit || !context.orgId || idx === stages.length - 1"
                    @click="moveStage(stage.key, 1)"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    :disabled="saving || !canEdit || !context.orgId || stages.length <= 1"
                    @click="removeStage(stage.key)"
                  >
                    Remove
                  </button>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>
        </div>

        <div class="footer">
          <button type="button" :disabled="saving || !canEdit || !context.orgId" @click="addStage">
            Add stage
          </button>
          <div class="spacer" />
          <button type="button" :disabled="saving || !canEdit || !context.orgId" @click="submit">
            {{ saving ? "Creating…" : "Create workflow" }}
          </button>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.label {
  font-size: 0.9rem;
  color: var(--muted);
}

.section-title {
  margin: 0.5rem 0 0 0;
  font-size: 1.1rem;
}

.table-wrap {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
}

.actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  justify-content: flex-end;
}

.footer {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.spacer {
  flex: 1;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}
</style>
