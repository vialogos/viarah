<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Client, Project, Workflow } from "../api/types";
import VlConfirmModal from "../components/VlConfirmModal.vue";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const realtime = useRealtimeStore();

const workflows = ref<Workflow[]>([]);
const loadingWorkflows = ref(false);
const workflowsError = ref("");

const clients = ref<Client[]>([]);
const loadingClients = ref(false);
const clientsError = ref("");

const createModalOpen = ref(false);
const creating = ref(false);
const createError = ref("");
const newName = ref("");
const newDescription = ref("");
const newClientId = ref("");

const editModalOpen = ref(false);
const saving = ref(false);
const editError = ref("");
const editingProject = ref<Project | null>(null);
const editName = ref("");
const editDescription = ref("");
const editWorkflowId = ref("");
const editClientId = ref("");

const deleteModalOpen = ref(false);
const deleting = ref(false);
const deleteError = ref("");
const pendingDeleteProject = ref<Project | null>(null);

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canEdit = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const workflowNameById = computed(() => {
  const map: Record<string, string> = {};
  for (const w of workflows.value) {
    map[w.id] = w.name;
  }
  return map;
});

function queryFlagTruthy(value: unknown): boolean {
  const raw = Array.isArray(value) ? value[0] : value;
  if (typeof raw !== "string") {
    return false;
  }
  const normalized = raw.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refreshWorkflows() {
  workflowsError.value = "";
  if (!context.orgId) {
    workflows.value = [];
    return;
  }

  loadingWorkflows.value = true;
  try {
    const res = await api.listWorkflows(context.orgId);
    workflows.value = res.workflows;
  } catch (err) {
    workflows.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    workflowsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingWorkflows.value = false;
  }
}

async function refreshClients() {
  clientsError.value = "";
  if (!context.orgId) {
    clients.value = [];
    return;
  }

  loadingClients.value = true;
  try {
    const res = await api.listClients(context.orgId);
    clients.value = res.clients;
  } catch (err) {
    clients.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    clientsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingClients.value = false;
  }
}

async function refresh() {
  deleteError.value = "";
  await Promise.all([context.refreshProjects(), refreshWorkflows(), refreshClients()]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

let refreshTimeoutId: number | null = null;
function scheduleRefresh() {
  if (refreshTimeoutId != null) {
    return;
  }
  refreshTimeoutId = window.setTimeout(() => {
    refreshTimeoutId = null;
    if (loadingWorkflows.value || loadingClients.value) {
      return;
    }
    void refresh();
  }, 250);
}

const unsubscribeRealtime = realtime.subscribe((event) => {
  if (event.type !== "audit_event.created") {
    return;
  }
  if (!context.orgId) {
    return;
  }
  if (event.org_id && event.org_id !== context.orgId) {
    return;
  }
  if (!isRecord(event.data)) {
    return;
  }
  const eventType = typeof event.data.event_type === "string" ? event.data.event_type : "";
  if (
    eventType.startsWith("project.") ||
    eventType.startsWith("workflow.") ||
    eventType.startsWith("client.")
  ) {
    scheduleRefresh();
  }
});

onBeforeUnmount(() => {
  unsubscribeRealtime();
  if (refreshTimeoutId != null) {
    window.clearTimeout(refreshTimeoutId);
    refreshTimeoutId = null;
  }
});

function clearCreateQueryParam() {
  if (!("create" in route.query)) {
    return;
  }

  const nextQuery = { ...route.query };
  delete nextQuery.create;
  void router.replace({ query: nextQuery });
}

function openCreateModal() {
  createError.value = "";
  newClientId.value = "";
  createModalOpen.value = true;
}

async function createProject() {
  createError.value = "";
  if (!context.orgId) {
    createError.value = "Select an org first.";
    return;
  }
  if (!canEdit.value) {
    createError.value = "Not permitted.";
    return;
  }

  const name = newName.value.trim();
  if (!name) {
    createError.value = "Name is required.";
    return;
  }

  creating.value = true;
  try {
    const payload: Record<string, unknown> = {
      name,
      description: newDescription.value.trim() ? newDescription.value.trim() : undefined,
    };
    if (newClientId.value) {
      payload.client_id = newClientId.value;
    }
    const res = await api.createProject(context.orgId, payload as { name: string; description?: string; client_id?: string | null });
    newName.value = "";
    newDescription.value = "";
    newClientId.value = "";
    createModalOpen.value = false;

    await context.refreshProjects();
    context.setProjectId(res.project.id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      createError.value = "Not permitted.";
      return;
    }
    createError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creating.value = false;
  }
}

function openEditModal(project: Project) {
  editError.value = "";
  editingProject.value = project;
  editName.value = project.name;
  editDescription.value = project.description;
  editWorkflowId.value = project.workflow_id ?? "";
  editClientId.value = project.client_id ?? "";
  editModalOpen.value = true;
}

async function saveProject() {
  editError.value = "";
  if (!context.orgId) {
    editError.value = "Select an org first.";
    return;
  }
  if (!editingProject.value) {
    editError.value = "No project selected.";
    return;
  }
  if (!canEdit.value) {
    editError.value = "Not permitted.";
    return;
  }

  const name = editName.value.trim();
  if (!name) {
    editError.value = "Name is required.";
    return;
  }

  saving.value = true;
  try {
    await api.updateProject(context.orgId, editingProject.value.id, {
      name,
      description: editDescription.value.trim(),
      workflow_id: editWorkflowId.value ? editWorkflowId.value : null,
      client_id: editClientId.value ? editClientId.value : null,
    });
    editModalOpen.value = false;
    editingProject.value = null;

    await context.refreshProjects();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      editError.value = "Not permitted.";
      return;
    }
    editError.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}

function requestDelete(project: Project) {
  deleteError.value = "";
  pendingDeleteProject.value = project;
  deleteModalOpen.value = true;
}

async function deleteProject() {
  deleteError.value = "";
  if (!context.orgId) {
    deleteError.value = "Select an org first.";
    return;
  }
  if (!pendingDeleteProject.value) {
    deleteError.value = "No project selected.";
    return;
  }
  if (!canEdit.value) {
    deleteError.value = "Not permitted.";
    return;
  }

  deleting.value = true;
  try {
    await api.deleteProject(context.orgId, pendingDeleteProject.value.id);
    deleteModalOpen.value = false;
    pendingDeleteProject.value = null;
    await context.refreshProjects();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      deleteError.value = "Not permitted.";
      return;
    }
    deleteError.value = err instanceof Error ? err.message : String(err);
  } finally {
    deleting.value = false;
  }
}

watch(
  () => context.orgId,
  () => {
    void refresh();
  },
  { immediate: true }
);

watch(
  () => route.query.create,
  (value) => {
    if (!queryFlagTruthy(value)) {
      return;
    }
    openCreateModal();
    clearCreateQueryParam();
  },
  { immediate: true }
);
</script>

<template>
  <div class="stack">
    <pf-card>
      <pf-card-title>
        <div class="header">
          <div>
            <pf-title h="1" size="2xl">Projects</pf-title>
            <pf-content>
              <p class="muted">Create and manage projects (PM/admin only).</p>
            </pf-content>
          </div>

          <div class="controls">
            <pf-button
              variant="secondary"
              :disabled="!context.orgId || context.loadingProjects || loadingWorkflows || loadingClients"
              @click="refresh"
            >
              Refresh
            </pf-button>
            <pf-button
              v-if="canEdit"
              variant="primary"
              :disabled="!context.orgId"
              @click="openCreateModal"
            >
              Create project
            </pf-button>
          </div>
        </div>
      </pf-card-title>

      <pf-card-body>
        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to view and manage projects.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else-if="context.loadingProjects || loadingWorkflows || loadingClients" class="loading-row">
          <pf-spinner size="md" aria-label="Loading projects" />
        </div>

        <div v-else>
          <pf-alert v-if="context.error" inline variant="danger" :title="context.error" />
          <pf-alert v-if="workflowsError" inline variant="warning" :title="workflowsError" />
          <pf-alert v-if="clientsError" inline variant="warning" :title="clientsError" />
          <pf-alert v-if="deleteError" inline variant="danger" :title="deleteError" />

          <pf-empty-state v-if="context.projects.length === 0">
            <pf-empty-state-header title="No projects yet" heading-level="h2" />
            <pf-empty-state-body>Create a project to start organizing work items.</pf-empty-state-body>
          </pf-empty-state>

          <pf-table v-else aria-label="Projects list">
            <pf-thead>
              <pf-tr>
                <pf-th>Project</pf-th>
                <pf-th class="muted">Client</pf-th>
                <pf-th class="muted">Workflow</pf-th>
                <pf-th class="muted">Updated</pf-th>
                <pf-th />
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="project in context.projects" :key="project.id">
                <pf-td data-label="Project">
                  <div class="title-row">
                    <span class="name">{{ project.name }}</span>
                    <VlLabel v-if="project.id === context.projectId" color="green">Current</VlLabel>
                  </div>
                  <div v-if="project.description" class="muted small">{{ project.description }}</div>
                </pf-td>

                <pf-td class="muted" data-label="Client">
                  <span v-if="project.client?.name">{{ project.client.name }}</span>
                  <span v-else class="muted">—</span>
                </pf-td>

                <pf-td class="muted" data-label="Workflow">
                  <span v-if="project.workflow_id">
                    {{ workflowNameById[project.workflow_id] ?? project.workflow_id }}
                  </span>
                  <span v-else class="muted">—</span>
                </pf-td>

                <pf-td class="muted" data-label="Updated">
                  <VlLabel color="blue">Updated {{ formatTimestamp(project.updated_at) }}</VlLabel>
                </pf-td>

                <pf-td data-label="Actions">
                  <div class="actions">
                    <pf-button
                      v-if="project.id !== context.projectId"
                      variant="link"
                      :disabled="!context.orgId"
                      @click="context.setProjectId(project.id)"
                    >
                      Set current
                    </pf-button>
                    <pf-button variant="link" :disabled="!canEdit" @click="openEditModal(project)">
                      Edit
                    </pf-button>
                    <pf-button variant="link" :disabled="!canEdit" @click="requestDelete(project)">
                      Delete
                    </pf-button>
                  </div>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>

          <pf-helper-text v-if="!canEdit" class="note">
            <pf-helper-text-item>Only PM/admin can create, edit, or delete projects.</pf-helper-text-item>
          </pf-helper-text>
        </div>
      </pf-card-body>
    </pf-card>
  </div>

  <pf-modal v-model:open="createModalOpen" title="Create project" variant="medium">
    <pf-form class="modal-form" @submit.prevent="createProject">
      <pf-form-group label="Name" field-id="project-create-name">
        <pf-text-input id="project-create-name" v-model="newName" type="text" placeholder="Project name" />
      </pf-form-group>
      <pf-form-group label="Description (optional)" field-id="project-create-description">
        <pf-textarea id="project-create-description" v-model="newDescription" rows="4" />
      </pf-form-group>
      <pf-form-group label="Client (optional)" field-id="project-create-client">
        <pf-form-select id="project-create-client" v-model="newClientId" :disabled="loadingClients">
          <pf-form-select-option value="">(unassigned)</pf-form-select-option>
          <pf-form-select-option v-for="client in clients" :key="client.id" :value="client.id">
            {{ client.name }}
          </pf-form-select-option>
        </pf-form-select>
      </pf-form-group>

      <pf-alert v-if="createError" inline variant="danger" :title="createError" />
    </pf-form>

    <template #footer>
      <pf-button variant="primary" :disabled="creating || !canEdit" @click="createProject">
        {{ creating ? "Creating…" : "Create" }}
      </pf-button>
      <pf-button variant="link" :disabled="creating" @click="createModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>

  <pf-modal v-model:open="editModalOpen" title="Edit project" variant="medium">
    <pf-form v-if="editingProject" class="modal-form" @submit.prevent="saveProject">
      <pf-form-group label="Name" field-id="project-edit-name">
        <pf-text-input id="project-edit-name" v-model="editName" type="text" />
      </pf-form-group>
      <pf-form-group label="Description" field-id="project-edit-description">
        <pf-textarea id="project-edit-description" v-model="editDescription" rows="4" />
      </pf-form-group>
      <pf-form-group label="Client" field-id="project-edit-client">
        <pf-form-select id="project-edit-client" v-model="editClientId" :disabled="loadingClients">
          <pf-form-select-option value="">(unassigned)</pf-form-select-option>
          <pf-form-select-option v-for="client in clients" :key="client.id" :value="client.id">
            {{ client.name }}
          </pf-form-select-option>
        </pf-form-select>
      </pf-form-group>
      <pf-form-group label="Workflow" field-id="project-edit-workflow">
        <pf-form-select id="project-edit-workflow" v-model="editWorkflowId" :disabled="workflows.length === 0">
          <pf-form-select-option value="">(unassigned)</pf-form-select-option>
          <pf-form-select-option v-for="wf in workflows" :key="wf.id" :value="wf.id">
            {{ wf.name }}
          </pf-form-select-option>
        </pf-form-select>
      </pf-form-group>

      <pf-alert v-if="editError" inline variant="danger" :title="editError" />
    </pf-form>

    <template #footer>
      <pf-button variant="primary" :disabled="saving || !canEdit" @click="saveProject">
        {{ saving ? "Saving…" : "Save" }}
      </pf-button>
      <pf-button variant="link" :disabled="saving" @click="editModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>

  <VlConfirmModal
    v-model:open="deleteModalOpen"
    title="Delete project"
    :body="`Delete project '${pendingDeleteProject?.name ?? ''}'? This will permanently delete its work items.`"
    confirm-label="Delete project"
    confirm-variant="danger"
    :loading="deleting"
    @confirm="deleteProject"
  />
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
  margin-bottom: 0.75rem;
}

.controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.name {
  font-weight: 600;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.note {
  margin-top: 0.75rem;
}
</style>
