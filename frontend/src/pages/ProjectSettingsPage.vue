<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type {
  CustomFieldDefinition,
  CustomFieldType,
  OrgMembershipWithUser,
  Project,
  ProjectMembershipWithUser,
  Workflow,
} from "../api/types";
import AuditPanel from "../components/AuditPanel.vue";
import VlConfirmModal from "../components/VlConfirmModal.vue";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import type { VlLabelColor } from "../utils/labels";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const realtime = useRealtimeStore();

const project = ref<Project | null>(null);
const workflows = ref<Workflow[]>([]);

const loadingMeta = ref(false);
const error = ref("");

const savingWorkflow = ref(false);
const selectedWorkflowId = ref("");
const savingProgressPolicy = ref(false);
const progressPolicyDraft = ref<"subtasks_rollup" | "workflow_stage">("subtasks_rollup");

const projectMemberships = ref<ProjectMembershipWithUser[]>([]);
const orgMemberships = ref<OrgMembershipWithUser[]>([]);
const loadingMembers = ref(false);
const membersError = ref("");

const addRoleFilter = ref<"all" | "internal" | "client">("all");
const addUserId = ref("");
const addingMember = ref(false);
const addMemberError = ref("");

const removeMemberModalOpen = ref(false);
const pendingRemoveMembership = ref<ProjectMembershipWithUser | null>(null);
const removingMember = ref(false);
const removeMemberError = ref("");

const customFields = ref<CustomFieldDefinition[]>([]);
const loadingCustomFields = ref(false);
const customFieldsError = ref("");

const newCustomFieldName = ref("");
const newCustomFieldType = ref<CustomFieldType>("text");
const newCustomFieldOptions = ref("");
const newCustomFieldClientSafe = ref(false);
const creatingCustomField = ref(false);

const archiveFieldModalOpen = ref(false);
const pendingArchiveField = ref<CustomFieldDefinition | null>(null);
const archivingCustomField = ref(false);

const savingClientSafeFieldId = ref("");

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canEdit = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

function queryParamString(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === "string") {
    return value[0];
  }
  return "";
}

watch(
  () => [context.orgId, route.query.projectId],
  ([orgId, rawProjectId]) => {
    if (!orgId) {
      return;
    }
    const projectId = queryParamString(rawProjectId);
    if (!projectId) {
      return;
    }
    if (context.projectId === projectId) {
      return;
    }
    context.setProjectId(projectId);
  },
  { immediate: true }
);

const workflowNameById = computed(() => {
  const map: Record<string, string> = {};
  for (const w of workflows.value) {
    map[w.id] = w.name;
  }
  return map;
});

const internalProjectMembers = computed(() => projectMemberships.value.filter((m) => m.role !== "client"));
const clientProjectMembers = computed(() => projectMemberships.value.filter((m) => m.role === "client"));

const projectMemberUserIds = computed(() => new Set(projectMemberships.value.map((m) => m.user.id)));

const addableOrgMemberships = computed(() => {
  const out = orgMemberships.value.filter((m) => !projectMemberUserIds.value.has(m.user.id));
  if (addRoleFilter.value === "client") {
    return out.filter((m) => m.role === "client");
  }
  if (addRoleFilter.value === "internal") {
    return out.filter((m) => m.role !== "client");
  }
  return out;
});

function roleLabelColor(role: string): VlLabelColor {
  if (role === "admin") {
    return "red";
  }
  if (role === "pm") {
    return "purple";
  }
  if (role === "client") {
    return "teal";
  }
  return "blue";
}

function roleDisplay(role: string): string {
  return role ? role.toUpperCase() : "";
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refreshMeta() {
  error.value = "";

  if (!context.orgId || !context.projectId) {
    project.value = null;
    workflows.value = [];
    selectedWorkflowId.value = "";
    return;
  }

  loadingMeta.value = true;
  try {
    const [projectRes, workflowsRes] = await Promise.all([
      api.getProject(context.orgId, context.projectId),
      api.listWorkflows(context.orgId),
    ]);
      project.value = projectRes.project;
      workflows.value = workflowsRes.workflows;
      if (project.value.progress_policy === "workflow_stage") {
        progressPolicyDraft.value = "workflow_stage";
      } else {
        progressPolicyDraft.value = "subtasks_rollup";
      }

    if (!selectedWorkflowId.value) {
      selectedWorkflowId.value = workflows.value[0]?.id ?? "";
    }
  } catch (err) {
    project.value = null;
    workflows.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingMeta.value = false;
  }
}

async function refreshMembers() {
  membersError.value = "";
  addMemberError.value = "";

  if (!context.orgId || !context.projectId) {
    projectMemberships.value = [];
    orgMemberships.value = [];
    addUserId.value = "";
    return;
  }

  loadingMembers.value = true;
  try {
    const [projectRes, orgRes] = await Promise.all([
      api.listProjectMemberships(context.orgId, context.projectId),
      api.listOrgMemberships(context.orgId),
    ]);
    projectMemberships.value = projectRes.memberships;
    orgMemberships.value = orgRes.memberships;

    if (addUserId.value && !addableOrgMemberships.value.some((m) => m.user.id === addUserId.value)) {
      addUserId.value = "";
    }
  } catch (err) {
    projectMemberships.value = [];
    orgMemberships.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    membersError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingMembers.value = false;
  }
}

async function refreshCustomFields() {
  customFieldsError.value = "";

  if (!context.orgId || !context.projectId) {
    customFields.value = [];
    return;
  }

  loadingCustomFields.value = true;
  try {
    const res = await api.listCustomFields(context.orgId, context.projectId);
    customFields.value = res.custom_fields;
  } catch (err) {
    customFields.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    customFieldsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingCustomFields.value = false;
  }
}

async function refreshAll() {
  await Promise.all([refreshMeta(), refreshMembers(), refreshCustomFields()]);
}

watch(() => [context.orgId, context.projectId], () => void refreshAll(), { immediate: true });

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

let refreshMetaTimeoutId: number | null = null;
function scheduleRefreshMeta() {
  if (refreshMetaTimeoutId != null) {
    return;
  }
  refreshMetaTimeoutId = window.setTimeout(() => {
    refreshMetaTimeoutId = null;
    if (loadingMeta.value) {
      return;
    }
    void refreshMeta();
  }, 250);
}

let refreshMembersTimeoutId: number | null = null;
function scheduleRefreshMembers() {
  if (refreshMembersTimeoutId != null) {
    return;
  }
  refreshMembersTimeoutId = window.setTimeout(() => {
    refreshMembersTimeoutId = null;
    if (loadingMembers.value) {
      return;
    }
    void refreshMembers();
  }, 250);
}

let refreshCustomFieldsTimeoutId: number | null = null;
function scheduleRefreshCustomFields() {
  if (refreshCustomFieldsTimeoutId != null) {
    return;
  }
  refreshCustomFieldsTimeoutId = window.setTimeout(() => {
    refreshCustomFieldsTimeoutId = null;
    if (loadingCustomFields.value) {
      return;
    }
    void refreshCustomFields();
  }, 250);
}

const unsubscribeRealtime = realtime.subscribe((event) => {
  if (event.type !== "audit_event.created") {
    return;
  }
  if (!context.orgId || !context.projectId) {
    return;
  }
  if (event.org_id && event.org_id !== context.orgId) {
    return;
  }
  if (!isRecord(event.data)) {
    return;
  }

  const auditEventType = typeof event.data.event_type === "string" ? event.data.event_type : "";
  const meta = isRecord(event.data.metadata) ? event.data.metadata : {};
  const projectId = String(meta.project_id ?? "");
  if (projectId && projectId !== context.projectId) {
    return;
  }

  if (
    auditEventType.startsWith("project.") ||
    auditEventType.startsWith("workflow.") ||
    auditEventType === "project.workflow_assigned"
  ) {
    scheduleRefreshMeta();
    return;
  }

  if (auditEventType.startsWith("project_membership.") || auditEventType.startsWith("org_membership.")) {
    scheduleRefreshMembers();
    return;
  }

  if (auditEventType.startsWith("custom_field.")) {
    scheduleRefreshCustomFields();
  }
});

onBeforeUnmount(() => {
  unsubscribeRealtime();
  if (refreshMetaTimeoutId != null) {
    window.clearTimeout(refreshMetaTimeoutId);
    refreshMetaTimeoutId = null;
  }
  if (refreshMembersTimeoutId != null) {
    window.clearTimeout(refreshMembersTimeoutId);
    refreshMembersTimeoutId = null;
  }
  if (refreshCustomFieldsTimeoutId != null) {
    window.clearTimeout(refreshCustomFieldsTimeoutId);
    refreshCustomFieldsTimeoutId = null;
  }
});

async function assignWorkflow() {
  error.value = "";
  if (!context.orgId || !context.projectId) {
    return;
  }
  if (!project.value) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }
  if (project.value.workflow_id) {
    error.value = "Workflow is already assigned; reassignment is blocked in v1.";
    return;
  }
  if (!selectedWorkflowId.value) {
    error.value = "Select a workflow to assign.";
    return;
  }

  savingWorkflow.value = true;
  try {
    const res = await api.setProjectWorkflow(context.orgId, context.projectId, selectedWorkflowId.value);
    project.value = res.project;
    await context.refreshProjects();
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
    savingWorkflow.value = false;
  }
}

async function addProjectMember() {
  addMemberError.value = "";
  if (!context.orgId || !context.projectId) {
    addMemberError.value = "Select an org and project first.";
    return;
  }
  if (!canEdit.value) {
    addMemberError.value = "Not permitted.";
    return;
  }
  if (!addUserId.value) {
    addMemberError.value = "Select a user to add.";
    return;
  }

  addingMember.value = true;
  try {
    await api.addProjectMembership(context.orgId, context.projectId, addUserId.value);
    addUserId.value = "";
    await refreshMembers();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      addMemberError.value = "Not permitted.";
      return;
    }
    addMemberError.value = err instanceof Error ? err.message : String(err);
  } finally {
    addingMember.value = false;
  }
}

function requestRemoveProjectMember(membership: ProjectMembershipWithUser) {
  removeMemberError.value = "";
  pendingRemoveMembership.value = membership;
  removeMemberModalOpen.value = true;
}

async function removeProjectMember() {
  removeMemberError.value = "";
  if (!context.orgId || !context.projectId) {
    removeMemberError.value = "Select an org and project first.";
    return;
  }
  if (!canEdit.value) {
    removeMemberError.value = "Not permitted.";
    return;
  }
  const membership = pendingRemoveMembership.value;
  if (!membership) {
    removeMemberError.value = "No membership selected.";
    return;
  }

  removingMember.value = true;
  try {
    await api.deleteProjectMembership(context.orgId, context.projectId, membership.id);
    removeMemberModalOpen.value = false;
    pendingRemoveMembership.value = null;
    await refreshMembers();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      removeMemberError.value = "Not permitted.";
      return;
    }
    removeMemberError.value = err instanceof Error ? err.message : String(err);
  } finally {
    removingMember.value = false;
  }
}

function parseCustomFieldOptions(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function createCustomField() {
  customFieldsError.value = "";
  if (!context.orgId || !context.projectId) {
    customFieldsError.value = "Select an org and project first.";
    return;
  }
  if (!canEdit.value) {
    customFieldsError.value = "Not permitted.";
    return;
  }

  const name = newCustomFieldName.value.trim();
  if (!name) {
    customFieldsError.value = "Name is required.";
    return;
  }

  const payload: {
    name: string;
    field_type: CustomFieldType;
    options?: string[];
    client_safe: boolean;
  } = {
    name,
    field_type: newCustomFieldType.value,
    client_safe: newCustomFieldClientSafe.value,
  };

  if (newCustomFieldType.value === "select" || newCustomFieldType.value === "multi_select") {
    payload.options = parseCustomFieldOptions(newCustomFieldOptions.value);
  }

  creatingCustomField.value = true;
  try {
    await api.createCustomField(context.orgId, context.projectId, payload);
    newCustomFieldName.value = "";
    newCustomFieldOptions.value = "";
    newCustomFieldType.value = "text";
    newCustomFieldClientSafe.value = false;
    await refreshCustomFields();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      customFieldsError.value = "Not permitted.";
      return;
    }
    customFieldsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingCustomField.value = false;
  }
}

function requestArchiveCustomField(field: CustomFieldDefinition) {
  customFieldsError.value = "";
  pendingArchiveField.value = field;
  archiveFieldModalOpen.value = true;
}

async function archiveCustomField() {
  customFieldsError.value = "";
  if (!context.orgId) {
    customFieldsError.value = "Select an org first.";
    return;
  }
  if (!canEdit.value) {
    customFieldsError.value = "Not permitted.";
    return;
  }
  const field = pendingArchiveField.value;
  if (!field) {
    customFieldsError.value = "No field selected.";
    return;
  }

  archivingCustomField.value = true;
  try {
    await api.deleteCustomField(context.orgId, field.id);
    archiveFieldModalOpen.value = false;
    pendingArchiveField.value = null;
    await refreshCustomFields();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      customFieldsError.value = "Not permitted.";
      return;
    }
    customFieldsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    archivingCustomField.value = false;
  }
}

async function toggleClientSafe(field: CustomFieldDefinition, nextValue: boolean) {
  customFieldsError.value = "";
  if (!context.orgId) {
    return;
  }
  if (!canEdit.value) {
    customFieldsError.value = "Not permitted.";
    return;
  }

  const prior = field.client_safe;
  field.client_safe = nextValue;

  savingClientSafeFieldId.value = field.id;
  try {
    await api.updateCustomField(context.orgId, field.id, { client_safe: nextValue });
  } catch (err) {
    field.client_safe = prior;
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      customFieldsError.value = "Not permitted.";
      return;
    }
    customFieldsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingClientSafeFieldId.value = "";
  }
}

async function saveProgressPolicy() {
  error.value = "";
  if (!context.orgId || !context.projectId || !project.value) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  savingProgressPolicy.value = true;
  try {
    const res = await api.updateProject(context.orgId, context.projectId, {
      progress_policy: progressPolicyDraft.value,
    });
    project.value = res.project;
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
    savingProgressPolicy.value = false;
  }
}
</script>

<template>
  <pf-card>
    <pf-card-title>
      <pf-title h="1" size="2xl">Project Settings</pf-title>
    </pf-card-title>

    <pf-card-body>
      <pf-content>
        <p class="muted">
          Project-level admin surfaces: workflow assignment, project membership, and custom field configuration.
        </p>
      </pf-content>

      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
      </pf-empty-state>

      <pf-empty-state v-else-if="!context.projectId">
        <pf-empty-state-header title="Select a project" heading-level="h2" />
        <pf-empty-state-body>Select a project to continue.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else class="stack">
        <pf-card>
          <pf-card-body>
            <div v-if="loadingMeta" class="loading-row">
              <pf-spinner size="md" aria-label="Loading project settings" />
            </div>
            <pf-alert v-else-if="error" inline variant="danger" :title="error" />
            <pf-empty-state v-else-if="!project">
              <pf-empty-state-header title="Not found" heading-level="h2" />
              <pf-empty-state-body>This project does not exist or is not accessible.</pf-empty-state-body>
            </pf-empty-state>

            <div v-else>
              <pf-description-list class="project-meta" horizontal compact>
                <pf-description-list-group>
                  <pf-description-list-term>Project</pf-description-list-term>
                  <pf-description-list-description>{{ project.name }}</pf-description-list-description>
                </pf-description-list-group>
                <pf-description-list-group>
                  <pf-description-list-term>Project id</pf-description-list-term>
                  <pf-description-list-description>
                    <span class="mono">{{ project.id }}</span>
                  </pf-description-list-description>
                </pf-description-list-group>
              </pf-description-list>
            </div>
          </pf-card-body>
        </pf-card>

        <pf-card id="project-members">
          <pf-card-title>
            <div class="header">
              <div>
                <pf-title h="2" size="xl">Project members</pf-title>
                <pf-content>
                  <p class="muted">
                    Members and clients are project-scoped. Org members only see projects they’re added to (except PM/admin).
                  </p>
                  <p class="muted">
                    Only <strong>active</strong> org members (invite accepted → org membership exists) can be added to projects. If someone
                    isn’t listed below, invite them from <RouterLink to="/team">Team</RouterLink> and have them accept.
                  </p>
                </pf-content>
              </div>

              <div class="controls">
              </div>
            </div>
          </pf-card-title>

          <pf-card-body>
            <div v-if="loadingMembers" class="loading-row">
              <pf-spinner size="md" aria-label="Loading project members" />
            </div>
            <pf-alert v-else-if="membersError" inline variant="danger" :title="membersError" />
            <div v-else>
              <pf-form class="add-member" @submit.prevent="addProjectMember">
                <pf-form-group label="Filter" field-id="project-member-filter">
                  <pf-form-select id="project-member-filter" v-model="addRoleFilter" :disabled="addingMember">
                    <pf-form-select-option value="all">All org members</pf-form-select-option>
                    <pf-form-select-option value="internal">Internal (admin/pm/member)</pf-form-select-option>
                    <pf-form-select-option value="client">Clients only</pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>

                <pf-form-group label="Add org member" field-id="project-member-user" class="grow">
                  <pf-form-select
                    id="project-member-user"
                    v-model="addUserId"
                    :disabled="addingMember || addableOrgMemberships.length === 0"
                  >
                    <pf-form-select-option value="">(select)</pf-form-select-option>
                    <pf-form-select-option
                      v-for="m in addableOrgMemberships"
                      :key="m.user.id"
                      :value="m.user.id"
                    >
                      {{ m.user.display_name || m.user.email }} ({{ m.role }}) — {{ m.user.email }}
                    </pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>

                <pf-button
                  type="submit"
                  variant="primary"
                  :disabled="addingMember || !canEdit || !addUserId"
                >
                  {{ addingMember ? "Adding…" : "Add" }}
                </pf-button>
              </pf-form>

              <pf-alert v-if="addMemberError" inline variant="danger" :title="addMemberError" class="spacer" />

              <pf-title h="3" size="lg" class="subhead">Internal team</pf-title>
              <pf-empty-state v-if="internalProjectMembers.length === 0">
                <pf-empty-state-header title="No internal members" heading-level="h3" />
                <pf-empty-state-body>
                  Add internal org members to make task assignment project-scoped. If you don’t see someone in the “Add org member” list,
                  they are not active yet (candidates cannot be staffed on projects).
                </pf-empty-state-body>
              </pf-empty-state>
              <pf-table v-else aria-label="Internal project members">
                <pf-thead>
                  <pf-tr>
                    <pf-th>User</pf-th>
                    <pf-th>Org role</pf-th>
                    <pf-th>Added</pf-th>
                    <pf-th />
                  </pf-tr>
                </pf-thead>
                <pf-tbody>
                  <pf-tr v-for="m in internalProjectMembers" :key="m.id">
                    <pf-td data-label="User">
                      <div class="title-row">
                        <span class="name">{{ m.user.display_name || "—" }}</span>
                      </div>
                      <div class="muted small">{{ m.user.email }}</div>
                    </pf-td>
                    <pf-td data-label="Org role">
                      <VlLabel :color="roleLabelColor(m.role)">{{ roleDisplay(m.role) }}</VlLabel>
                    </pf-td>
                    <pf-td data-label="Added">{{ formatTimestamp(m.created_at) }}</pf-td>
                    <pf-td data-label="Actions">
                      <pf-button
                        variant="danger"
                        small
                        :disabled="!canEdit || removingMember"
                        @click="requestRemoveProjectMember(m)"
                      >
                        Remove
                      </pf-button>
                    </pf-td>
                  </pf-tr>
                </pf-tbody>
              </pf-table>

              <pf-title h="3" size="lg" class="subhead">Clients</pf-title>
              <pf-empty-state v-if="clientProjectMembers.length === 0">
                <pf-empty-state-header title="No client members" heading-level="h3" />
                <pf-empty-state-body>
                  Add org client users to scope client access (projects list and client-safe tasks).
                </pf-empty-state-body>
              </pf-empty-state>
              <pf-table v-else aria-label="Client project members">
                <pf-thead>
                  <pf-tr>
                    <pf-th>User</pf-th>
                    <pf-th>Org role</pf-th>
                    <pf-th>Added</pf-th>
                    <pf-th />
                  </pf-tr>
                </pf-thead>
                <pf-tbody>
                  <pf-tr v-for="m in clientProjectMembers" :key="m.id">
                    <pf-td data-label="User">
                      <div class="title-row">
                        <span class="name">{{ m.user.display_name || "—" }}</span>
                      </div>
                      <div class="muted small">{{ m.user.email }}</div>
                    </pf-td>
                    <pf-td data-label="Org role">
                      <VlLabel :color="roleLabelColor(m.role)">{{ roleDisplay(m.role) }}</VlLabel>
                    </pf-td>
                    <pf-td data-label="Added">{{ formatTimestamp(m.created_at) }}</pf-td>
                    <pf-td data-label="Actions">
                      <pf-button
                        variant="danger"
                        small
                        :disabled="!canEdit || removingMember"
                        @click="requestRemoveProjectMember(m)"
                      >
                        Remove
                      </pf-button>
                    </pf-td>
                  </pf-tr>
                </pf-tbody>
              </pf-table>

              <pf-helper-text v-if="!canEdit" class="note">
                <pf-helper-text-item>Only PM/admin can manage project membership.</pf-helper-text-item>
              </pf-helper-text>

              <pf-alert v-if="removeMemberError" inline variant="danger" :title="removeMemberError" class="spacer" />
            </div>
          </pf-card-body>
        </pf-card>

        <pf-card>
          <pf-card-title>
            <div class="header">
              <div>
                <pf-title h="2" size="xl">Custom fields</pf-title>
                <pf-content>
                  <p class="muted">Project-scoped fields used on tasks and subtasks.</p>
                </pf-content>
              </div>
              <div class="controls">
              </div>
            </div>
          </pf-card-title>

          <pf-card-body>
            <div v-if="loadingCustomFields" class="loading-row">
              <pf-spinner size="md" aria-label="Loading custom fields" />
            </div>
            <pf-alert v-else-if="customFieldsError" inline variant="danger" :title="customFieldsError" />

            <div v-else>
              <pf-empty-state v-if="customFields.length === 0">
                <pf-empty-state-header title="No custom fields yet" heading-level="h3" />
                <pf-empty-state-body>Create one to capture project-specific metadata.</pf-empty-state-body>
              </pf-empty-state>

              <pf-table v-else aria-label="Custom fields">
                <pf-thead>
                  <pf-tr>
                    <pf-th>Name</pf-th>
                    <pf-th>Type</pf-th>
                    <pf-th>Client safe</pf-th>
                    <pf-th />
                  </pf-tr>
                </pf-thead>
                <pf-tbody>
                  <pf-tr v-for="field in customFields" :key="field.id">
                    <pf-td data-label="Name">
                      <div class="title-row">
                        <span class="name">{{ field.name }}</span>
                        <VlLabel v-if="field.archived_at" color="grey">ARCHIVED</VlLabel>
                      </div>
                    </pf-td>
                    <pf-td data-label="Type">
                      <VlLabel color="teal">{{ field.field_type }}</VlLabel>
                    </pf-td>
                    <pf-td data-label="Client safe">
                      <pf-checkbox
                        :id="`field-safe-${field.id}`"
                        :model-value="field.client_safe"
                        :disabled="!canEdit || Boolean(field.archived_at) || savingClientSafeFieldId === field.id"
                        label=""
                        @update:model-value="toggleClientSafe(field, Boolean($event))"
                      />
                    </pf-td>
                    <pf-td data-label="Actions">
                      <pf-button
                        variant="danger"
                        small
                        :disabled="!canEdit || Boolean(field.archived_at) || archivingCustomField"
                        @click="requestArchiveCustomField(field)"
                      >
                        Archive
                      </pf-button>
                    </pf-td>
                  </pf-tr>
                </pf-tbody>
              </pf-table>

              <pf-form v-if="canEdit" class="new-field" @submit.prevent="createCustomField">
                <pf-title h="3" size="md">Add field</pf-title>
                <div class="new-field-row">
                  <pf-form-group label="Name" field-id="new-field-name">
                    <pf-text-input
                      id="new-field-name"
                      v-model="newCustomFieldName"
                      type="text"
                      placeholder="e.g., Priority"
                    />
                  </pf-form-group>

                  <pf-form-group label="Type" field-id="new-field-type">
                    <pf-form-select id="new-field-type" v-model="newCustomFieldType">
                      <pf-form-select-option value="text">Text</pf-form-select-option>
                      <pf-form-select-option value="number">Number</pf-form-select-option>
                      <pf-form-select-option value="date">Date</pf-form-select-option>
                      <pf-form-select-option value="select">Select</pf-form-select-option>
                      <pf-form-select-option value="multi_select">Multi-select</pf-form-select-option>
                    </pf-form-select>
                  </pf-form-group>

                  <pf-form-group label="Options" field-id="new-field-options">
                    <pf-text-input
                      id="new-field-options"
                      v-model="newCustomFieldOptions"
                      :disabled="newCustomFieldType !== 'select' && newCustomFieldType !== 'multi_select'"
                      type="text"
                      placeholder="Comma-separated (select types only)"
                    />
                  </pf-form-group>

                  <pf-checkbox id="new-field-client-safe" v-model="newCustomFieldClientSafe" label="Client safe" />

                  <pf-button type="submit" variant="primary" :disabled="creatingCustomField">
                    {{ creatingCustomField ? "Creating…" : "Create" }}
                  </pf-button>
                </div>
              </pf-form>

              <pf-helper-text v-else class="note">
                <pf-helper-text-item>Only PM/admin can manage custom fields.</pf-helper-text-item>
              </pf-helper-text>
            </div>
          </pf-card-body>
        </pf-card>

        <pf-card>
          <pf-card-title>
            <div class="header">
              <div>
                <pf-title h="2" size="xl">Workflow</pf-title>
                <pf-content>
                  <p class="muted">Assign a workflow to the selected project (initial assignment only).</p>
                </pf-content>
              </div>
              <div class="controls">
              </div>
            </div>
          </pf-card-title>

          <pf-card-body>
            <div v-if="loadingMeta" class="loading-row">
              <pf-spinner size="md" aria-label="Loading workflow settings" />
            </div>
            <pf-alert v-else-if="error" inline variant="danger" :title="error" />
            <div v-else-if="project">
              <template v-if="project.workflow_id">
                <pf-alert inline variant="info" title="Workflow assigned">
                  <div class="title">
                    {{ workflowNameById[project.workflow_id] ?? project.workflow_id }}
                  </div>
                  <div class="muted">
                    Reassignment is blocked in v1 to avoid orphaning existing work without migration tooling.
                  </div>
                </pf-alert>

                <pf-form class="assign" @submit.prevent="saveProgressPolicy">
                  <pf-form-group
                    label="Default progress policy"
                    field-id="project-settings-progress-policy"
                    class="grow"
                  >
                    <pf-form-select
                      id="project-settings-progress-policy"
                      v-model="progressPolicyDraft"
                      :disabled="savingProgressPolicy || !canEdit"
                    >
                      <pf-form-select-option value="subtasks_rollup">Subtasks rollup</pf-form-select-option>
                      <pf-form-select-option value="workflow_stage">Workflow stage</pf-form-select-option>
                    </pf-form-select>
                  </pf-form-group>

                  <pf-button type="submit" variant="secondary" :disabled="savingProgressPolicy || !canEdit">
                    {{ savingProgressPolicy ? "Saving…" : "Save policy" }}
                  </pf-button>
                </pf-form>
              </template>

              <pf-form v-else class="assign" @submit.prevent="assignWorkflow">
                <pf-form-group label="Workflow" field-id="project-settings-workflow" class="grow">
                  <pf-form-select
                    id="project-settings-workflow"
                    v-model="selectedWorkflowId"
                    :disabled="savingWorkflow || workflows.length === 0"
                  >
                    <pf-form-select-option v-for="wf in workflows" :key="wf.id" :value="wf.id">
                      {{ wf.name }}
                    </pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>

                <pf-button
                  type="submit"
                  variant="primary"
                  :disabled="savingWorkflow || !canEdit || workflows.length === 0 || !selectedWorkflowId"
                >
                  {{ savingWorkflow ? "Assigning…" : "Assign workflow" }}
                </pf-button>
              </pf-form>

              <pf-helper-text v-if="!canEdit || workflows.length === 0" class="note">
                <pf-helper-text-item v-if="!canEdit">Only PM/admin can assign workflows.</pf-helper-text-item>
                <pf-helper-text-item v-if="workflows.length === 0">
                  No workflows exist yet. Create one under Workflow Settings.
                </pf-helper-text-item>
              </pf-helper-text>
            </div>
          </pf-card-body>
        </pf-card>

        <AuditPanel
          v-if="context.orgId && context.projectId"
          title="Project settings audit"
          :org-id="context.orgId"
          :project-id="context.projectId"
          :event-types="[
            'project.workflow_assigned',
            'project_membership.added',
            'project_membership.removed',
            'custom_field.created',
            'custom_field.updated',
            'custom_field.archived',
          ]"
        />

        <VlConfirmModal
          v-model:open="removeMemberModalOpen"
          title="Remove project member"
          :body="`Remove ${pendingRemoveMembership?.user.display_name || pendingRemoveMembership?.user.email || ''} from this project?`"
          confirm-label="Remove"
          confirm-variant="danger"
          :loading="removingMember"
          @confirm="removeProjectMember"
        />

        <VlConfirmModal
          v-model:open="archiveFieldModalOpen"
          title="Archive custom field"
          :body="`Archive custom field '${pendingArchiveField?.name ?? ''}'?`"
          confirm-label="Archive field"
          confirm-variant="danger"
          :loading="archivingCustomField"
          @confirm="archiveCustomField"
        />
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.project-meta {
  margin-bottom: 0.75rem;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}

.title {
  font-weight: 600;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.name {
  font-weight: 600;
}

.muted {
  color: var(--pf-t--global--text--color--subtle);
}

.small {
  font-size: 0.875rem;
}

.add-member {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.grow {
  flex: 1;
  min-width: 260px;
}

.subhead {
  margin-top: 1rem;
}

.spacer {
  margin-top: 0.75rem;
}

.assign {
  margin-top: 0.75rem;
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.note {
  margin-top: 0.75rem;
}

.new-field {
  margin-top: 1rem;
}

.new-field-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.75rem;
}
</style>
