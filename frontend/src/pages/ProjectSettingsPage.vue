<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import AuditPanel from "../components/AuditPanel.vue";
import { api, ApiError } from "../api";
import type { Project, Workflow } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const project = ref<Project | null>(null);
const workflows = ref<Workflow[]>([]);

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const selectedWorkflowId = ref("");

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

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  if (!context.orgId || !context.projectId) {
    project.value = null;
    workflows.value = [];
    selectedWorkflowId.value = "";
    return;
  }

  loading.value = true;
  try {
    const [projectRes, workflowsRes] = await Promise.all([
      api.getProject(context.orgId, context.projectId),
      api.listWorkflows(context.orgId),
    ]);
    project.value = projectRes.project;
    workflows.value = workflowsRes.workflows;

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
    loading.value = false;
  }
}

watch(() => [context.orgId, context.projectId], () => void refresh(), { immediate: true });

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

  saving.value = true;
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
    saving.value = false;
  }
}
</script>

<template>
  <div>
    <h1 class="page-title">Project Settings</h1>
    <p class="muted">Assign a workflow to the selected project (initial assignment only).</p>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>
    <p v-else-if="!context.projectId" class="card">Select a project to continue.</p>

    <div v-else class="card">
      <div v-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!project" class="muted">Not found.</div>
      <div v-else>
        <div class="row">
          <div>
            <div class="muted">Project</div>
            <div class="title">{{ project.name }}</div>
          </div>
          <div class="muted mono">{{ project.id }}</div>
        </div>

        <div v-if="project.workflow_id" class="card locked">
          <div class="muted">Assigned workflow</div>
          <div class="title">
            {{ workflowNameById[project.workflow_id] ?? project.workflow_id }}
          </div>
          <p class="muted">
            Reassignment is blocked in v1 to avoid orphaning existing work without migration tooling.
          </p>
        </div>

        <div v-else class="assign">
          <label class="field grow">
            <span class="label">Workflow</span>
            <select v-model="selectedWorkflowId" :disabled="saving || workflows.length === 0">
              <option v-for="wf in workflows" :key="wf.id" :value="wf.id">
                {{ wf.name }}
              </option>
            </select>
          </label>

          <button
            type="button"
            :disabled="saving || !canEdit || workflows.length === 0 || !selectedWorkflowId"
            @click="assignWorkflow"
          >
            {{ saving ? "Assigning…" : "Assign workflow" }}
          </button>
        </div>

        <p v-if="!canEdit" class="muted note">Only PM/admin can assign workflows.</p>
        <p v-if="workflows.length === 0" class="muted note">
          No workflows exist yet. Create one under Workflow Settings.
        </p>

        <AuditPanel
          v-if="context.orgId && project"
          title="Project audit"
          :org-id="context.orgId"
          :project-id="project.id"
          :event-types="['project.workflow_assigned']"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
}

.title {
  font-weight: 600;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}

.locked {
  margin-top: 0.75rem;
  border-color: #c7d2fe;
  background: #eef2ff;
}

.assign {
  margin-top: 0.75rem;
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
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

.grow {
  flex: 1;
  min-width: 260px;
}

.note {
  margin-top: 0.75rem;
}
</style>

