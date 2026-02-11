<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import AuditPanel from "../components/AuditPanel.vue";
import VlConfirmModal from "../components/VlConfirmModal.vue";
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
const deleteStageModalOpen = ref(false);
const pendingDeleteStageId = ref<string | null>(null);
const deletingStage = ref(false);
const deleteWorkflowModalOpen = ref(false);
const deletingWorkflow = ref(false);

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

function requestDeleteStage(stageId: string) {
  pendingDeleteStageId.value = stageId;
  deleteStageModalOpen.value = true;
}

async function deleteStage() {
  if (!context.orgId || !workflow.value) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  const stageId = pendingDeleteStageId.value;
  if (!stageId) {
    return;
  }

  error.value = "";
  deletingStage.value = true;
  try {
    await api.deleteWorkflowStage(context.orgId, workflow.value.id, stageId);
    const res = await api.listWorkflowStages(context.orgId, workflow.value.id);
    stages.value = res.stages;
    pendingDeleteStageId.value = null;
    deleteStageModalOpen.value = false;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    deletingStage.value = false;
  }
}

function requestDeleteWorkflow() {
  deleteWorkflowModalOpen.value = true;
}

async function deleteWorkflow() {
  if (!context.orgId || !workflow.value) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  error.value = "";
  deletingWorkflow.value = true;
  try {
    await api.deleteWorkflow(context.orgId, workflow.value.id);
    deleteWorkflowModalOpen.value = false;
    await router.push("/settings/workflows");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    deletingWorkflow.value = false;
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
          <button type="button" class="danger" :disabled="!canEdit" @click="requestDeleteWorkflow">
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
          <pf-table aria-label="Workflow stages table">
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
              <pf-tr v-for="stage in stages" :key="stage.id">
                <pf-td class="mono" data-label="#">
                  {{ stage.order }}
                </pf-td>
                <pf-td data-label="Name">
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
                </pf-td>
                <pf-td data-label="Done">
                  <input
                    type="radio"
                    name="done-stage"
                    :checked="stage.is_done"
                    :disabled="stageSavingId === stage.id || !canEdit"
                    @change="updateStage(stage.id, { is_done: true })"
                  />
                </pf-td>
                <pf-td data-label="QA">
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
                </pf-td>
                <pf-td data-label="WIP">
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
                </pf-td>
                <pf-td class="actions" data-label="Actions">
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
                    @click="requestDeleteStage(stage.id)"
                  >
                    Delete
                  </button>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>
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
    <VlConfirmModal
      v-model:open="deleteWorkflowModalOpen"
      title="Delete workflow"
      body="Delete this workflow?"
      confirm-label="Delete workflow"
      confirm-variant="danger"
      :loading="deletingWorkflow"
      @confirm="deleteWorkflow"
    />
    <VlConfirmModal
      v-model:open="deleteStageModalOpen"
      title="Delete stage"
      body="Delete this stage?"
      confirm-label="Delete stage"
      confirm-variant="danger"
      :loading="deletingStage"
      @confirm="deleteStage"
    />
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
