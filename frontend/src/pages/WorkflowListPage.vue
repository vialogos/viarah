<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Workflow, WorkflowStageCategory, WorkflowStageTemplateRow } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const workflows = ref<Workflow[]>([]);
const loading = ref(false);
const error = ref("");

type StageDraft = {
  key: string;
  name: string;
  category: WorkflowStageCategory;
  progress_percent: number;
  is_qa: boolean;
  counts_as_wip: boolean;
};

function makeKey(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const defaultsLoading = ref(false);
const defaultsSaving = ref(false);
const defaultsError = ref("");
const stageDrafts = ref<StageDraft[]>([]);
const orgOverrideActive = ref(false);

const currentRole = computed(() => session.effectiveOrgRole(context.orgId));

const canEdit = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const defaultsMode = computed<"none" | "global" | "org">(() => {
  if (context.orgScope === "all") {
    return "global";
  }
  if (context.orgId) {
    return "org";
  }
  return "none";
});

const canEditGlobalDefaults = computed(() =>
  session.platformRole !== "none" || session.memberships.some((m) => m.role === "admin" || m.role === "pm")
);

const canEditDefaults = computed(() => {
  if (defaultsMode.value === "global") {
    return canEditGlobalDefaults.value;
  }
  if (defaultsMode.value === "org") {
    return canEdit.value;
  }
  return false;
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  if (!context.orgId || context.orgScope === "all") {
    workflows.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listWorkflows(context.orgId);
    workflows.value = res.workflows;
  } catch (err) {
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

function stageDraftsFromTemplate(template: WorkflowStageTemplateRow[]): StageDraft[] {
  return (template ?? []).map((row) => ({
    key: makeKey(),
    name: String(row.name || ""),
    category: row.category,
    progress_percent: Number(row.progress_percent) || 0,
    is_qa: Boolean(row.is_qa),
    counts_as_wip: Boolean(row.counts_as_wip),
  }));
}

function defaultStageTemplate(): WorkflowStageTemplateRow[] {
  return [
    { name: "Backlog", category: "backlog", progress_percent: 0, is_qa: false, counts_as_wip: false },
    { name: "In Progress", category: "in_progress", progress_percent: 33, is_qa: false, counts_as_wip: true },
    { name: "QA", category: "qa", progress_percent: 67, is_qa: true, counts_as_wip: true },
    { name: "Done", category: "done", progress_percent: 100, is_qa: false, counts_as_wip: false },
  ];
}

function addStage() {
  stageDrafts.value = [
    ...stageDrafts.value,
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
  if (stageDrafts.value.length <= 1) {
    return;
  }
  stageDrafts.value = stageDrafts.value.filter((s) => s.key !== key);
}

function moveStage(key: string, direction: -1 | 1) {
  const idx = stageDrafts.value.findIndex((s) => s.key === key);
  if (idx < 0) {
    return;
  }
  const nextIdx = idx + direction;
  if (nextIdx < 0 || nextIdx >= stageDrafts.value.length) {
    return;
  }

  const next = [...stageDrafts.value];
  const moved = next.splice(idx, 1)[0];
  if (!moved) {
    return;
  }
  next.splice(nextIdx, 0, moved);
  stageDrafts.value = next;
}

function validateTemplate(rows: StageDraft[]): string | null {
  if (rows.length < 1) {
    return "At least one stage is required.";
  }
  if (rows.some((row) => !row.name.trim())) {
    return "All stages must have a name.";
  }
  if (rows.filter((row) => row.category === "done").length !== 1) {
    return "Select exactly one done stage category.";
  }
  if (rows.some((row) => row.progress_percent < 0 || row.progress_percent > 100)) {
    return "Stage progress must be between 0 and 100.";
  }
  return null;
}

async function refreshDefaults() {
  defaultsError.value = "";
  stageDrafts.value = [];
  orgOverrideActive.value = false;

  if (defaultsMode.value === "none") {
    return;
  }

  defaultsLoading.value = true;
  try {
    if (defaultsMode.value === "global") {
      const res = await api.getSettingsDefaults();
      stageDrafts.value = stageDraftsFromTemplate(res.defaults.workflow.stage_template ?? defaultStageTemplate());
      return;
    }

    const res = await api.getOrgDefaults(context.orgId);
    orgOverrideActive.value = res.overrides.workflow.stage_template !== null;
    stageDrafts.value = stageDraftsFromTemplate(
      res.effective.workflow.stage_template ?? res.defaults.workflow.stage_template ?? defaultStageTemplate()
    );
  } catch (err) {
    stageDrafts.value = stageDraftsFromTemplate(defaultStageTemplate());
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    defaultsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    defaultsLoading.value = false;
  }
}

async function saveDefaults() {
  defaultsError.value = "";
  if (!canEditDefaults.value) {
    defaultsError.value = "Not permitted.";
    return;
  }

  const validation = validateTemplate(stageDrafts.value);
  if (validation) {
    defaultsError.value = validation;
    return;
  }

  const payload: WorkflowStageTemplateRow[] = stageDrafts.value.map((row) => ({
    name: row.name.trim(),
    category: row.category,
    progress_percent: row.progress_percent,
    is_qa: row.is_qa,
    counts_as_wip: row.counts_as_wip,
  }));

  defaultsSaving.value = true;
  try {
    if (defaultsMode.value === "global") {
      await api.patchSettingsDefaults({ workflow: { stage_template: payload } });
    } else if (defaultsMode.value === "org" && context.orgId) {
      await api.patchOrgDefaults(context.orgId, { workflow: { stage_template: payload } });
    }
    await refreshDefaults();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    defaultsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    defaultsSaving.value = false;
  }
}

async function clearOrgOverride() {
  defaultsError.value = "";
  if (!context.orgId) {
    return;
  }
  if (!canEdit.value) {
    defaultsError.value = "Not permitted.";
    return;
  }

  defaultsSaving.value = true;
  try {
    await api.patchOrgDefaults(context.orgId, { workflow: { stage_template: null } });
    await refreshDefaults();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    defaultsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    defaultsSaving.value = false;
  }
}

watch(() => context.orgId, () => void refresh(), { immediate: true });
watch(() => [context.orgScope, context.orgId], () => void refreshDefaults(), { immediate: true });
</script>

<template>
  <div class="stack">
    <pf-card>
      <pf-card-title>
        <pf-title h="2" size="lg">Workflow defaults</pf-title>
      </pf-card-title>
      <pf-card-body>
        <pf-content>
          <p class="muted">
            Used to prefill the stages when creating a new workflow.
            <span v-if="defaultsMode === 'global'">These defaults apply to all orgs unless overridden.</span>
          </p>
        </pf-content>

        <pf-empty-state v-if="defaultsMode === 'none'">
          <pf-empty-state-header title="Select an org (or All orgs)" heading-level="h3" />
          <pf-empty-state-body>Choose a scope in the context menu to edit defaults.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else-if="defaultsLoading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading workflow defaults" />
        </div>
        <pf-alert v-else-if="defaultsError" inline variant="danger" :title="defaultsError" />
        <div v-else class="defaults-stack">
          <pf-helper-text v-if="defaultsMode === 'org'">
            <pf-helper-text-item>
              <VlLabel v-if="orgOverrideActive" color="orange">Overridden</VlLabel>
              <VlLabel v-else color="grey" variant="outline">Using global defaults</VlLabel>
            </pf-helper-text-item>
          </pf-helper-text>

          <div class="table-wrap">
            <pf-table aria-label="Workflow default stage template">
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
                <pf-tr v-for="(stage, idx) in stageDrafts" :key="stage.key">
                  <pf-td class="mono" data-label="#">{{ idx + 1 }}</pf-td>
                  <pf-td data-label="Name">
                    <pf-text-input v-model="stage.name" type="text" placeholder="Stage name" :disabled="defaultsSaving" />
                  </pf-td>
                  <pf-td data-label="Category">
                    <pf-form-select v-model="stage.category" :disabled="defaultsSaving">
                      <pf-form-select-option value="backlog">Backlog</pf-form-select-option>
                      <pf-form-select-option value="in_progress">In progress</pf-form-select-option>
                      <pf-form-select-option value="qa">QA</pf-form-select-option>
                      <pf-form-select-option value="done">Done</pf-form-select-option>
                    </pf-form-select>
                  </pf-td>
                  <pf-td data-label="Progress">
                    <pf-text-input
                      v-model.number="stage.progress_percent"
                      type="number"
                      min="0"
                      max="100"
                      :disabled="defaultsSaving || stage.category === 'done'"
                    />
                  </pf-td>
                  <pf-td data-label="QA">
                    <pf-checkbox
                      v-model="stage.is_qa"
                      label=""
                      :aria-label="`QA stage ${stage.name || idx + 1}`"
                      :disabled="defaultsSaving || stage.category === 'done'"
                    />
                  </pf-td>
                  <pf-td data-label="WIP">
                    <pf-checkbox
                      v-model="stage.counts_as_wip"
                      label=""
                      :aria-label="`WIP stage ${stage.name || idx + 1}`"
                      :disabled="defaultsSaving || stage.category === 'done'"
                    />
                  </pf-td>
                  <pf-td class="row-actions" data-label="Actions">
                    <pf-button variant="secondary" :disabled="defaultsSaving" @click="moveStage(stage.key, -1)">↑</pf-button>
                    <pf-button variant="secondary" :disabled="defaultsSaving" @click="moveStage(stage.key, 1)">↓</pf-button>
                    <pf-button variant="danger" :disabled="defaultsSaving" @click="removeStage(stage.key)">Remove</pf-button>
                  </pf-td>
                </pf-tr>
              </pf-tbody>
            </pf-table>
          </div>

          <div class="actions">
            <pf-button variant="secondary" :disabled="defaultsSaving" @click="addStage">Add stage</pf-button>
            <pf-button variant="primary" :disabled="defaultsSaving || !canEditDefaults" @click="saveDefaults">
              {{ defaultsSaving ? "Saving…" : "Save defaults" }}
            </pf-button>
            <pf-button
              v-if="defaultsMode === 'org' && orgOverrideActive"
              variant="link"
              :disabled="defaultsSaving"
              @click="clearOrgOverride"
            >
              Use global defaults
            </pf-button>
          </div>

          <pf-helper-text v-if="!canEditDefaults" class="note">
            <pf-helper-text-item>Only PM/admin can update workflow defaults.</pf-helper-text-item>
          </pf-helper-text>
        </div>
      </pf-card-body>
    </pf-card>

    <pf-card>
      <pf-card-title>
        <div class="header">
          <div>
            <pf-title h="1" size="2xl">Workflows</pf-title>
            <pf-content>
              <p class="muted">Configure workflow stage ordering and flags for an org.</p>
            </pf-content>
          </div>
          <pf-button v-if="canEdit" variant="primary" to="/settings/workflows/new">Create workflow</pf-button>
        </div>
      </pf-card-title>

      <pf-card-body>
        <pf-empty-state v-if="!context.orgId || context.orgScope === 'all'">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to manage workflows.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading workflows" />
        </div>
        <pf-alert v-else-if="error" inline variant="danger" :title="error" />
        <pf-empty-state v-else-if="workflows.length === 0">
          <pf-empty-state-header title="No workflows yet" heading-level="h2" />
          <pf-empty-state-body>Create one to define stage ordering for this org.</pf-empty-state-body>
        </pf-empty-state>

        <pf-data-list v-else compact aria-label="Workflows">
          <pf-data-list-item v-for="workflow in workflows" :key="workflow.id">
            <pf-data-list-cell>
              <RouterLink class="name" :to="`/settings/workflows/${workflow.id}`">
                {{ workflow.name }}
              </RouterLink>
              <div class="meta">
                <VlLabel color="blue">Updated {{ formatTimestamp(workflow.updated_at) }}</VlLabel>
              </div>
            </pf-data-list-cell>
            <pf-data-list-cell align-right>
              <pf-button variant="link" :to="`/settings/workflows/${workflow.id}`">Open</pf-button>
            </pf-data-list-cell>
          </pf-data-list-item>
        </pf-data-list>

        <pf-helper-text v-if="!canEdit" class="note">
          <pf-helper-text-item>
            You can view workflows, but only PM/admin can create or edit them.
          </pf-helper-text-item>
        </pf-helper-text>
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

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.defaults-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.table-wrap {
  overflow-x: auto;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

.row-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
}

.meta {
  display: flex;
  gap: 0.5rem;
}

.name {
  font-weight: 600;
  color: var(--text);
  text-decoration: none;
}

.name:hover {
  text-decoration: underline;
}

.note {
  margin-top: 0.75rem;
}
</style>
