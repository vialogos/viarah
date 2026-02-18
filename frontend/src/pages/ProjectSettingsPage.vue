<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import AuditPanel from "../components/AuditPanel.vue";
import { api, ApiError } from "../api";
import type { ProgressPolicy, Project, Workflow } from "../api/types";
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
const savingProgressPolicy = ref(false);
const error = ref("");
const selectedWorkflowId = ref("");
const progressPolicyDraft = ref<ProgressPolicy>("subtasks_rollup");

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
      if (project.value.progress_policy) {
        progressPolicyDraft.value = project.value.progress_policy;
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
        <p class="muted">Assign a workflow to the selected project (initial assignment only).</p>
      </pf-content>

      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
      </pf-empty-state>
      <pf-empty-state v-else-if="!context.projectId">
        <pf-empty-state-header title="Select a project" heading-level="h2" />
        <pf-empty-state-body>Select a project to continue.</pf-empty-state-body>
      </pf-empty-state>
      <div v-else-if="loading" class="loading-row">
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
                :disabled="savingProgressPolicy"
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
              :disabled="saving || workflows.length === 0"
            >
              <pf-form-select-option v-for="wf in workflows" :key="wf.id" :value="wf.id">
                {{ wf.name }}
              </pf-form-select-option>
            </pf-form-select>
          </pf-form-group>

          <pf-button
            type="submit"
            variant="primary"
            :disabled="saving || !canEdit || workflows.length === 0 || !selectedWorkflowId"
          >
            {{ saving ? "Assigning…" : "Assign workflow" }}
          </pf-button>
        </pf-form>

        <pf-helper-text v-if="!canEdit || workflows.length === 0" class="note">
          <pf-helper-text-item v-if="!canEdit">Only PM/admin can assign workflows.</pf-helper-text-item>
          <pf-helper-text-item v-if="workflows.length === 0">
            No workflows exist yet. Create one under Workflow Settings.
          </pf-helper-text-item>
        </pf-helper-text>

        <AuditPanel
          v-if="context.orgId && project"
          title="Project audit"
          :org-id="context.orgId"
          :project-id="project.id"
          :event-types="['project.workflow_assigned']"
        />
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.title {
  font-weight: 600;
}

.project-meta {
  margin-bottom: 0.75rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}

.assign {
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

.note {
  margin-top: 0.75rem;
}
</style>
