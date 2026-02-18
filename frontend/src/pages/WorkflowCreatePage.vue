<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

type StageDraft = {
  key: string;
  name: string;
  category: "backlog" | "in_progress" | "qa" | "done";
  progress_percent: number;
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
  {
    key: makeKey(),
    name: "Backlog",
    category: "backlog",
    progress_percent: 0,
    is_qa: false,
    counts_as_wip: false,
  },
  {
    key: makeKey(),
    name: "In Progress",
    category: "in_progress",
    progress_percent: 33,
    is_qa: false,
    counts_as_wip: true,
  },
  { key: makeKey(), name: "QA", category: "qa", progress_percent: 67, is_qa: true, counts_as_wip: true },
  { key: makeKey(), name: "Done", category: "done", progress_percent: 100, is_qa: false, counts_as_wip: false },
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

function addStage() {
  stages.value = [
    ...stages.value,
    {
      key: makeKey(),
      name: "",
      category: "in_progress",
      progress_percent: 50,
      is_qa: false,
      counts_as_wip: true,
    },
  ];
}

function removeStage(key: string) {
  if (stages.value.length <= 1) {
    return;
  }
  stages.value = stages.value.filter((s) => s.key !== key);
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
    category: s.category,
    progress_percent: s.progress_percent,
    is_qa: s.is_qa,
    counts_as_wip: s.counts_as_wip,
  }));

  if (stagePayloads.some((s) => !s.name)) {
    error.value = "All stages must have a name.";
    return;
  }

  if (stagePayloads.filter((s) => s.category === "done").length !== 1) {
    error.value = "Select exactly one done stage category.";
    return;
  }

  if (stagePayloads.some((s) => s.progress_percent < 0 || s.progress_percent > 100)) {
    error.value = "Stage progress must be between 0 and 100.";
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
  <div class="stack">
    <pf-button variant="link" to="/settings/workflows">Back to workflows</pf-button>

    <pf-card>
      <pf-card-title>
        <pf-title h="1" size="2xl">Create workflow</pf-title>
      </pf-card-title>
      <pf-card-body>
        <pf-content>
          <p class="muted">Workflows are scoped to the selected org.</p>
        </pf-content>

        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
        </pf-empty-state>
        <pf-empty-state v-else-if="!canEdit">
          <pf-empty-state-header title="Not permitted" heading-level="h2" />
          <pf-empty-state-body>Only PM/admin can create workflows.</pf-empty-state-body>
        </pf-empty-state>

        <pf-form v-else class="form" @submit.prevent="submit">
          <pf-form-group label="Name" field-id="create-workflow-name">
            <pf-text-input id="create-workflow-name" v-model="name" type="text" :disabled="saving" />
          </pf-form-group>

          <pf-title h="2" size="lg">Stages</pf-title>
          <div class="table-wrap">
            <pf-table aria-label="Workflow stage draft table">
              <pf-thead>
                <pf-tr>
                  <pf-th>#</pf-th>
                  <pf-th>Name</pf-th>
                  <pf-th>Category</pf-th>
                  <pf-th>Progress</pf-th>
                  <pf-th>QA</pf-th>
                  <pf-th>WIP</pf-th>
                  <pf-th>Actions</pf-th>
                </pf-tr>
              </pf-thead>
              <pf-tbody>
                <pf-tr v-for="(stage, idx) in stages" :key="stage.key">
                  <pf-td class="mono" data-label="#">{{ idx + 1 }}</pf-td>
                  <pf-td data-label="Name">
                    <pf-text-input
                      v-model="stage.name"
                      type="text"
                      placeholder="Stage name"
                      :disabled="saving"
                    />
                  </pf-td>
                  <pf-td data-label="Category">
                    <pf-form-select
                      :id="`create-workflow-category-${stage.key}`"
                      v-model="stage.category"
                      :disabled="saving"
                    >
                      <pf-form-select-option value="backlog">Backlog</pf-form-select-option>
                      <pf-form-select-option value="in_progress">In progress</pf-form-select-option>
                      <pf-form-select-option value="qa">QA</pf-form-select-option>
                      <pf-form-select-option value="done">Done</pf-form-select-option>
                    </pf-form-select>
                  </pf-td>
                  <pf-td data-label="Progress">
                    <pf-text-input
                      :id="`create-workflow-progress-${stage.key}`"
                      v-model.number="stage.progress_percent"
                      type="number"
                      min="0"
                      max="100"
                      :disabled="saving || stage.category === 'done'"
                    />
                  </pf-td>
                  <pf-td data-label="QA">
                    <pf-checkbox
                      :id="`create-workflow-qa-${stage.key}`"
                      v-model="stage.is_qa"
                      label=""
                      :aria-label="`QA stage ${stage.name || idx + 1}`"
                      :disabled="saving || stage.category === 'done'"
                    />
                  </pf-td>
                  <pf-td data-label="WIP">
                    <pf-checkbox
                      :id="`create-workflow-wip-${stage.key}`"
                      v-model="stage.counts_as_wip"
                      label=""
                      :aria-label="`WIP stage ${stage.name || idx + 1}`"
                      :disabled="saving || stage.category === 'done'"
                    />
                  </pf-td>
                  <pf-td class="actions" data-label="Actions">
                    <pf-button
                      type="button"
                      variant="plain"
                      :disabled="saving || idx === 0"
                      aria-label="Move stage up"
                      @click="moveStage(stage.key, -1)"
                    >
                      ↑
                    </pf-button>
                    <pf-button
                      type="button"
                      variant="plain"
                      :disabled="saving || idx === stages.length - 1"
                      aria-label="Move stage down"
                      @click="moveStage(stage.key, 1)"
                    >
                      ↓
                    </pf-button>
                    <pf-button
                      type="button"
                      variant="danger"
                      :disabled="saving || stages.length <= 1"
                      @click="removeStage(stage.key)"
                    >
                      Remove
                    </pf-button>
                  </pf-td>
                </pf-tr>
              </pf-tbody>
            </pf-table>
          </div>

          <div class="footer">
            <pf-button type="button" variant="secondary" :disabled="saving" @click="addStage">
              Add stage
            </pf-button>
            <div class="spacer" />
            <pf-button type="submit" variant="primary" :disabled="saving">
              {{ saving ? "Creating…" : "Create workflow" }}
            </pf-button>
          </div>

          <pf-alert v-if="error" inline variant="danger" :title="error" />
        </pf-form>
      </pf-card-body>
    </pf-card>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.table-wrap {
  overflow: auto;
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
