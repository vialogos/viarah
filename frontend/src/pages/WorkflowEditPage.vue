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
  <div class="stack">
    <pf-button variant="link" to="/settings/workflows">Back to workflows</pf-button>

    <pf-card>
      <pf-card-title>
        <div class="header">
          <div>
            <pf-title h="1" size="2xl">{{ workflow?.name || "Workflow" }}</pf-title>
            <pf-content v-if="workflow && !canEdit">
              <p class="muted">Read-only: only PM/admin can edit workflows.</p>
            </pf-content>
          </div>
          <pf-button variant="danger" :disabled="!workflow || !canEdit" @click="requestDeleteWorkflow">
            Delete workflow
          </pf-button>
        </div>
      </pf-card-title>

      <pf-card-body>
        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading workflow" />
        </div>
        <pf-alert v-else-if="error" inline variant="danger" :title="error" />
        <pf-empty-state v-else-if="!workflow">
          <pf-empty-state-header title="Not found" heading-level="h2" />
          <pf-empty-state-body>This workflow does not exist or is not accessible.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else>
          <pf-form class="form" @submit.prevent="saveName">
            <pf-form-group label="Name" field-id="workflow-edit-name">
              <div class="row">
                <pf-text-input id="workflow-edit-name" v-model="name" type="text" :disabled="savingName || !canEdit" />
                <pf-button type="submit" variant="secondary" :disabled="savingName || !canEdit">
                  {{ savingName ? "Saving…" : "Save" }}
                </pf-button>
              </div>
            </pf-form-group>
          </pf-form>

          <pf-title h="2" size="lg" class="stages-title">Stages</pf-title>
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
                    <pf-text-input
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
                    <pf-helper-text v-if="stageErrorById[stage.id]" class="small">
                      <pf-helper-text-item variant="warning">{{ stageErrorById[stage.id] }}</pf-helper-text-item>
                    </pf-helper-text>
                  </pf-td>
                  <pf-td data-label="Done">
                    <pf-radio
                      :id="`workflow-edit-done-${stage.id}`"
                      name="done-stage"
                      label=""
                      :aria-label="`Done stage ${stage.name}`"
                      :checked="stage.is_done"
                      :disabled="stageSavingId === stage.id || !canEdit"
                      @change="updateStage(stage.id, { is_done: true })"
                    />
                  </pf-td>
                  <pf-td data-label="QA">
                    <pf-checkbox
                      :id="`workflow-edit-qa-${stage.id}`"
                      label=""
                      :aria-label="`QA stage ${stage.name}`"
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
                    <pf-checkbox
                      :id="`workflow-edit-wip-${stage.id}`"
                      label=""
                      :aria-label="`WIP stage ${stage.name}`"
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
                    <pf-button
                      type="button"
                      variant="plain"
                      :disabled="stageSavingId === stage.id || !canEdit || stage.order === 1"
                      aria-label="Move stage up"
                      @click="updateStage(stage.id, { order: stage.order - 1 })"
                    >
                      ↑
                    </pf-button>
                    <pf-button
                      type="button"
                      variant="plain"
                      :disabled="stageSavingId === stage.id || !canEdit || stage.order === stages.length"
                      aria-label="Move stage down"
                      @click="updateStage(stage.id, { order: stage.order + 1 })"
                    >
                      ↓
                    </pf-button>
                    <pf-button
                      type="button"
                      variant="danger"
                      :disabled="stageSavingId === stage.id || !canEdit"
                      @click="requestDeleteStage(stage.id)"
                    >
                      Delete
                    </pf-button>
                  </pf-td>
                </pf-tr>
              </pf-tbody>
            </pf-table>
          </div>

          <pf-form class="add-stage" @submit.prevent="addStage">
            <pf-form-group label="New stage name" field-id="workflow-new-stage-name" class="grow">
              <pf-text-input
                id="workflow-new-stage-name"
                v-model="newStageName"
                type="text"
                :disabled="addingStage || !canEdit"
              />
            </pf-form-group>

            <pf-checkbox id="workflow-new-stage-qa" v-model="newStageIsQa" label="QA" :disabled="addingStage || !canEdit" />
            <pf-checkbox
              id="workflow-new-stage-wip"
              v-model="newStageCountsAsWip"
              label="WIP"
              :disabled="addingStage || !canEdit"
            />

            <pf-button type="submit" variant="secondary" :disabled="addingStage || !canEdit">
              {{ addingStage ? "Adding…" : "Add stage" }}
            </pf-button>
          </pf-form>

          <AuditPanel
            v-if="context.orgId"
            title="Workflow audit"
            :org-id="context.orgId"
            :workflow-id="workflow.id"
            :event-types="workflowEventTypes"
          />
        </div>
      </pf-card-body>
    </pf-card>
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
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.stages-title {
  margin-top: 1rem;
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

.small {
  font-size: 0.85rem;
  margin-top: 0.25rem;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}
</style>
