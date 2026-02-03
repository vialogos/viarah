<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import AuditPanel from "../components/AuditPanel.vue";
import { api, ApiError } from "../api";
import type { Workflow, WorkflowStage } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const props = defineProps<{ workflowId: string }>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const workflow = ref<Workflow | null>(null);
const stages = ref<WorkflowStage[]>([]);

const loading = ref(false);
const error = ref("");

const name = ref("");
const savingName = ref(false);

const newStageName = ref("");
const newStageIsQa = ref(false);
const newStageCountsAsWip = ref(true);
const addingStage = ref(false);

const stageSavingId = ref("");
const stageErrorById = ref<Record<string, string>>({});

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canEdit = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const workflowEventTypes = [
  "workflow.created",
  "workflow.updated",
  "workflow.deleted",
  "workflow_stage.created",
  "workflow_stage.updated",
  "workflow_stage.deleted",
  "project.workflow_assigned",
];

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  stageErrorById.value = {};

  if (!context.orgId) {
    workflow.value = null;
    stages.value = [];
    name.value = "";
    return;
  }

  loading.value = true;
  try {
    const res = await api.getWorkflow(context.orgId, props.workflowId);
    workflow.value = res.workflow;
    name.value = res.workflow.name;
    stages.value = res.stages;
  } catch (err) {
    workflow.value = null;
    stages.value = [];
    name.value = "";

    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgId, props.workflowId], () => void refresh(), { immediate: true });

async function saveName() {
  if (!context.orgId || !workflow.value) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  const nextName = name.value.trim();
  if (!nextName) {
    error.value = "Name is required.";
    return;
  }

  savingName.value = true;
  error.value = "";
  try {
    const res = await api.updateWorkflow(context.orgId, workflow.value.id, { name: nextName });
    workflow.value = res.workflow;
    name.value = res.workflow.name;
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
    savingName.value = false;
  }
}

async function addStage() {
  if (!context.orgId || !workflow.value) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  const stageName = newStageName.value.trim();
  if (!stageName) {
    error.value = "Stage name is required.";
    return;
  }

  addingStage.value = true;
  error.value = "";
  try {
    const res = await api.createWorkflowStage(context.orgId, workflow.value.id, {
      name: stageName,
      order: stages.value.length + 1,
      is_done: false,
      is_qa: newStageIsQa.value,
      counts_as_wip: newStageCountsAsWip.value,
    });
    stages.value = res.stages;
    newStageName.value = "";
    newStageIsQa.value = false;
    newStageCountsAsWip.value = true;
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
    addingStage.value = false;
  }
}

async function updateStage(stageId: string, patch: Partial<WorkflowStage>) {
  if (!context.orgId || !workflow.value) {
    return;
  }
  if (!canEdit.value) {
    stageErrorById.value = { ...stageErrorById.value, [stageId]: "Not permitted." };
    return;
  }

  stageSavingId.value = stageId;
  stageErrorById.value = { ...stageErrorById.value, [stageId]: "" };
  try {
    const res = await api.updateWorkflowStage(context.orgId, workflow.value.id, stageId, patch);
    stages.value = res.stages;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    stageErrorById.value = {
      ...stageErrorById.value,
      [stageId]: err instanceof Error ? err.message : String(err),
    };
  } finally {
    stageSavingId.value = "";
  }
}

async function deleteStage(stageId: string) {
  if (!context.orgId || !workflow.value) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }
  if (!confirm("Delete this stage?")) {
    return;
  }

  error.value = "";
  try {
    await api.deleteWorkflowStage(context.orgId, workflow.value.id, stageId);
    const res = await api.listWorkflowStages(context.orgId, workflow.value.id);
    stages.value = res.stages;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function deleteWorkflow() {
  if (!context.orgId || !workflow.value) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }
  if (!confirm("Delete this workflow?")) {
    return;
  }

  error.value = "";
  try {
    await api.deleteWorkflow(context.orgId, workflow.value.id);
    await router.push("/settings/workflows");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  }
}
</script>

<template>
  <div>
    <RouterLink to="/settings/workflows">← Back to workflows</RouterLink>

    <div class="card">
      <div v-if="!context.orgId" class="muted">Select an org to continue.</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!workflow" class="muted">Not found.</div>
      <div v-else>
        <div class="header">
          <div>
            <h1 class="page-title">{{ workflow.name }}</h1>
            <p v-if="!canEdit" class="muted">Read-only: only PM/admin can edit workflows.</p>
          </div>
          <button type="button" class="danger" :disabled="!canEdit" @click="deleteWorkflow">
            Delete workflow
          </button>
        </div>

        <div class="form">
          <label class="field">
            <span class="label">Name</span>
            <div class="row">
              <input v-model="name" type="text" :disabled="savingName || !canEdit" />
              <button type="button" :disabled="savingName || !canEdit" @click="saveName">
                {{ savingName ? "Saving…" : "Save" }}
              </button>
            </div>
          </label>
        </div>

        <h2 class="section-title">Stages</h2>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Done</th>
                <th>QA</th>
                <th>WIP</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr v-for="stage in stages" :key="stage.id">
                <td class="mono">{{ stage.order }}</td>
                <td>
                  <input
                    :value="stage.name"
                    type="text"
                    :disabled="stageSavingId === stage.id || !canEdit"
                    @change="
                      (e) =>
                        updateStage(stage.id, {
                          name: (e.target as HTMLInputElement).value.trim(),
                        })
                    "
                  />
                  <div v-if="stageErrorById[stage.id]" class="error small">
                    {{ stageErrorById[stage.id] }}
                  </div>
                </td>
                <td>
                  <input
                    type="radio"
                    name="done-stage"
                    :checked="stage.is_done"
                    :disabled="stageSavingId === stage.id || !canEdit"
                    @change="updateStage(stage.id, { is_done: true })"
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    :checked="stage.is_qa"
                    :disabled="stageSavingId === stage.id || !canEdit"
                    @change="
                      (e) =>
                        updateStage(stage.id, {
                          is_qa: (e.target as HTMLInputElement).checked,
                        })
                    "
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    :checked="stage.counts_as_wip"
                    :disabled="stageSavingId === stage.id || !canEdit"
                    @change="
                      (e) =>
                        updateStage(stage.id, {
                          counts_as_wip: (e.target as HTMLInputElement).checked,
                        })
                    "
                  />
                </td>
                <td class="actions">
                  <button
                    type="button"
                    :disabled="stageSavingId === stage.id || !canEdit || stage.order === 1"
                    @click="updateStage(stage.id, { order: stage.order - 1 })"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    :disabled="
                      stageSavingId === stage.id || !canEdit || stage.order === stages.length
                    "
                    @click="updateStage(stage.id, { order: stage.order + 1 })"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    :disabled="stageSavingId === stage.id || !canEdit"
                    @click="deleteStage(stage.id)"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="add-stage">
          <label class="field grow">
            <span class="label">New stage name</span>
            <input v-model="newStageName" type="text" :disabled="addingStage || !canEdit" />
          </label>

          <label class="toggle">
            <input v-model="newStageIsQa" type="checkbox" :disabled="addingStage || !canEdit" />
            <span class="muted">QA</span>
          </label>

          <label class="toggle">
            <input
              v-model="newStageCountsAsWip"
              type="checkbox"
              :disabled="addingStage || !canEdit"
            />
            <span class="muted">WIP</span>
          </label>

          <button type="button" :disabled="addingStage || !canEdit" @click="addStage">
            {{ addingStage ? "Adding…" : "Add stage" }}
          </button>
        </div>

        <AuditPanel
          v-if="context.orgId"
          title="Workflow audit"
          :org-id="context.orgId"
          :workflow-id="workflow.id"
          :event-types="workflowEventTypes"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.danger {
  border-color: #fecaca;
  color: var(--danger);
}

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

.row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.section-title {
  margin: 1.25rem 0 0.5rem 0;
  font-size: 1.1rem;
}

.table-wrap {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th,
.table td {
  padding: 0.5rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  justify-content: flex-end;
}

.add-stage {
  margin-top: 0.75rem;
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.grow {
  flex: 1;
  min-width: 260px;
}

.toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding-bottom: 0.25rem;
}

.small {
  font-size: 0.85rem;
  margin-top: 0.25rem;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}
</style>

