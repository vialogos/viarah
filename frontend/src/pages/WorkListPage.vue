<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type {
  CustomFieldDefinition,
  CustomFieldType,
  Epic,
  SavedView,
  Subtask,
  Task,
  WorkflowStage,
} from "../api/types";
import VlConfirmModal from "../components/VlConfirmModal.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatPercent, formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const tasks = ref<Task[]>([]);
const epics = ref<Epic[]>([]);
const stages = ref<WorkflowStage[]>([]);
const savedViews = ref<SavedView[]>([]);
const customFields = ref<CustomFieldDefinition[]>([]);

const loading = ref(false);
const loadingSavedViews = ref(false);
const loadingCustomFields = ref(false);
const error = ref("");
const epicsError = ref("");

type SubtaskState = { loading: boolean; error: string; subtasks: Subtask[] };
const subtasksByTaskId = ref<Record<string, SubtaskState>>({});
const expandedTaskIds = ref<Record<string, boolean>>({});

const projectWorkflowId = computed(() => {
  const project = context.projects.find((p) => p.id === context.projectId);
  return project?.workflow_id ?? null;
});

const epicById = computed(() => {
  const map: Record<string, Epic> = {};
  for (const epic of epics.value) {
    map[epic.id] = epic;
  }
  return map;
});

const stageNameById = computed(() => {
  const map: Record<string, string> = {};
  for (const stage of stages.value) {
    map[stage.id] = stage.name;
  }
  return map;
});

function stageLabel(stageId: string | null | undefined): string {
  if (!stageId) {
    return "(unassigned)";
  }
  return stageNameById.value[stageId] ?? stageId;
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

const STATUS_OPTIONS = [
  { value: "backlog", label: "Backlog" },
  { value: "in_progress", label: "In progress" },
  { value: "qa", label: "QA" },
  { value: "done", label: "Done" },
] as const;

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManageCustomization = computed(
  () => currentRole.value === "admin" || currentRole.value === "pm"
);

const selectedSavedViewId = ref("");
const selectedStatuses = ref<string[]>([]);
const search = ref("");
const sortField = ref<"created_at" | "updated_at" | "title">("created_at");
const sortDirection = ref<"asc" | "desc">("asc");
const groupBy = ref<"none" | "status">("none");

const newCustomFieldName = ref("");
const newCustomFieldType = ref<CustomFieldType>("text");
const newCustomFieldOptions = ref("");
const newCustomFieldClientSafe = ref(false);
const creatingCustomField = ref(false);
const deletingSavedView = ref(false);
const deleteSavedViewModalOpen = ref(false);
const archivingCustomField = ref(false);
const archiveFieldModalOpen = ref(false);
const pendingArchiveField = ref<CustomFieldDefinition | null>(null);

function buildSavedViewPayload() {
  return {
    filters: { status: selectedStatuses.value, search: search.value },
    sort: { field: sortField.value, direction: sortDirection.value },
    group_by: groupBy.value,
  };
}

function applySavedView(view: SavedView) {
  selectedStatuses.value = [...(view.filters?.status ?? [])];
  search.value = view.filters?.search ?? "";
  sortField.value = view.sort?.field ?? "created_at";
  sortDirection.value = view.sort?.direction ?? "asc";
  groupBy.value = view.group_by ?? "none";
}

async function refreshWork() {
  error.value = "";
  epicsError.value = "";

  if (!context.orgId || !context.projectId) {
    tasks.value = [];
    epics.value = [];
    expandedTaskIds.value = {};
    subtasksByTaskId.value = {};
    return;
  }

  loading.value = true;
  expandedTaskIds.value = {};
  subtasksByTaskId.value = {};
  try {
    const [tasksResult, epicsResult] = await Promise.allSettled([
      api.listTasks(context.orgId, context.projectId),
      api.listEpics(context.orgId, context.projectId),
    ]);

    if (tasksResult.status === "fulfilled") {
      tasks.value = tasksResult.value.tasks;
    } else {
      tasks.value = [];
      const reason = tasksResult.reason;
      if (reason instanceof ApiError && reason.status === 401) {
        await handleUnauthorized();
        return;
      }
      error.value = reason instanceof Error ? reason.message : String(reason);
    }

    if (epicsResult.status === "fulfilled") {
      epics.value = epicsResult.value.epics;
    } else {
      epics.value = [];
      const reason = epicsResult.reason;
      if (reason instanceof ApiError && reason.status === 401) {
        await handleUnauthorized();
        return;
      }
      if (reason instanceof ApiError && reason.status === 403) {
        epicsError.value = "Epics are not available for your role; showing tasks only.";
      } else {
        epicsError.value = reason instanceof Error ? reason.message : String(reason);
      }
    }
  } finally {
    loading.value = false;
  }
}

async function refreshStages() {
  if (!context.orgId || !projectWorkflowId.value) {
    stages.value = [];
    return;
  }

  try {
    const res = await api.listWorkflowStages(context.orgId, projectWorkflowId.value);
    stages.value = res.stages;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    stages.value = [];
  }
}

async function refreshSavedViews() {
  if (!context.orgId || !context.projectId) {
    savedViews.value = [];
    selectedSavedViewId.value = "";
    return;
  }

  loadingSavedViews.value = true;
  try {
    const res = await api.listSavedViews(context.orgId, context.projectId);
    savedViews.value = res.saved_views;

    if (selectedSavedViewId.value && !savedViews.value.some((v) => v.id === selectedSavedViewId.value)) {
      selectedSavedViewId.value = "";
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    savedViews.value = [];
    selectedSavedViewId.value = "";
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingSavedViews.value = false;
  }
}

async function refreshCustomFields() {
  if (!context.orgId || !context.projectId) {
    customFields.value = [];
    return;
  }

  loadingCustomFields.value = true;
  try {
    const res = await api.listCustomFields(context.orgId, context.projectId);
    customFields.value = res.custom_fields;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    customFields.value = [];
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingCustomFields.value = false;
  }
}

async function refreshAll() {
  await Promise.all([refreshWork(), refreshSavedViews(), refreshCustomFields(), refreshStages()]);
}

watch(
  () => [context.orgId, context.projectId],
  () => {
    selectedSavedViewId.value = "";
    selectedStatuses.value = [];
    search.value = "";
    sortField.value = "created_at";
    sortDirection.value = "asc";
    groupBy.value = "none";
    void refreshAll();
  },
  { immediate: true }
);

watch(selectedSavedViewId, (next) => {
  if (!next) {
    return;
  }

  const view = savedViews.value.find((v) => v.id === next);
  if (!view) {
    return;
  }

  applySavedView(view);
});

const filteredTasks = computed(() => {
  const needle = search.value.trim().toLowerCase();
  const allowedStatuses = new Set(selectedStatuses.value);

  const items = tasks.value.filter((task) => {
    if (allowedStatuses.size && !allowedStatuses.has(task.status)) {
      return false;
    }
    if (needle && !task.title.toLowerCase().includes(needle)) {
      return false;
    }
    return true;
  });

  const dir = sortDirection.value === "asc" ? 1 : -1;
  items.sort((a, b) => {
    if (sortField.value === "title") {
      return a.title.localeCompare(b.title) * dir;
    }
    const aVal = Date.parse((a as any)[sortField.value] ?? "");
    const bVal = Date.parse((b as any)[sortField.value] ?? "");
    return (aVal - bVal) * dir;
  });

  return items;
});

const tasksByEpicId = computed(() => {
  const map: Record<string, Task[]> = {};
  for (const task of filteredTasks.value) {
    const key = task.epic_id || "unknown";
    if (!map[key]) {
      map[key] = [];
    }
    map[key].push(task);
  }
  return map;
});

const taskGroups = computed(() => {
  if (groupBy.value === "none") {
    return [{ key: "all", label: "", tasks: filteredTasks.value }];
  }

  const groups: Array<{ key: string; label: string; tasks: Task[] }> = [];
  for (const option of STATUS_OPTIONS) {
    const groupTasks = filteredTasks.value.filter((task) => task.status === option.value);
    if (!groupTasks.length) {
      continue;
    }
    groups.push({ key: option.value, label: option.label, tasks: groupTasks });
  }
  return groups;
});

function formatCustomFieldValue(field: CustomFieldDefinition, value: unknown): string {
  if (value == null) {
    return "";
  }

  if (field.field_type === "multi_select") {
    return Array.isArray(value) ? value.join(", ") : String(value);
  }

  return String(value);
}

function displayFieldsForTask(task: Task): Array<{ id: string; label: string }> {
  const map = new Map((task.custom_field_values ?? []).map((v) => [v.field_id, v.value]));
  const items: Array<{ id: string; label: string }> = [];
  for (const field of customFields.value) {
    const value = map.get(field.id);
    if (value == null) {
      continue;
    }
    items.push({ id: field.id, label: `${field.name}: ${formatCustomFieldValue(field, value)}` });
  }
  return items;
}

async function loadSubtasks(taskId: string) {
  if (!context.orgId) {
    return;
  }

  const prior = subtasksByTaskId.value[taskId];
  subtasksByTaskId.value = {
    ...subtasksByTaskId.value,
    [taskId]: { loading: true, error: "", subtasks: prior?.subtasks ?? [] },
  };

  try {
    const res = await api.listSubtasks(context.orgId, taskId);
    subtasksByTaskId.value = {
      ...subtasksByTaskId.value,
      [taskId]: { loading: false, error: "", subtasks: res.subtasks },
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    subtasksByTaskId.value = {
      ...subtasksByTaskId.value,
      [taskId]: {
        loading: false,
        error: err instanceof Error ? err.message : String(err),
        subtasks: [],
      },
    };
  }
}

async function toggleTask(taskId: string) {
  const next = { ...expandedTaskIds.value, [taskId]: !expandedTaskIds.value[taskId] };
  expandedTaskIds.value = next;

  if (next[taskId] && !subtasksByTaskId.value[taskId]) {
    await loadSubtasks(taskId);
  }
}

async function createSavedView() {
  if (!context.orgId || !context.projectId) {
    return;
  }

  const name = window.prompt("Saved view name");
  if (!name || !name.trim()) {
    return;
  }

  error.value = "";
  try {
    const res = await api.createSavedView(context.orgId, context.projectId, {
      name: name.trim(),
      ...buildSavedViewPayload(),
    });
    await refreshSavedViews();
    selectedSavedViewId.value = res.saved_view.id;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function updateSavedView() {
  if (!context.orgId || !selectedSavedViewId.value) {
    return;
  }

  error.value = "";
  try {
    await api.updateSavedView(context.orgId, selectedSavedViewId.value, buildSavedViewPayload());
    await refreshSavedViews();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function requestDeleteSavedView() {
  if (!selectedSavedViewId.value) {
    return;
  }
  deleteSavedViewModalOpen.value = true;
}

async function deleteSavedView() {
  if (!context.orgId || !selectedSavedViewId.value) {
    return;
  }

  error.value = "";
  deletingSavedView.value = true;
  try {
    await api.deleteSavedView(context.orgId, selectedSavedViewId.value);
    selectedSavedViewId.value = "";
    deleteSavedViewModalOpen.value = false;
    await refreshSavedViews();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    deletingSavedView.value = false;
  }
}

function parseCustomFieldOptions(raw: string): string[] {
  const parts = raw
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  return Array.from(new Set(parts));
}

async function createCustomField() {
  if (!context.orgId || !context.projectId) {
    return;
  }

  const name = newCustomFieldName.value.trim();
  if (!name) {
    error.value = "custom field name is required";
    return;
  }

  const payload: {
    name: string;
    field_type: CustomFieldType;
    options?: string[];
    client_safe?: boolean;
  } = {
    name,
    field_type: newCustomFieldType.value,
    client_safe: newCustomFieldClientSafe.value,
  };
  if (newCustomFieldType.value === "select" || newCustomFieldType.value === "multi_select") {
    payload.options = parseCustomFieldOptions(newCustomFieldOptions.value);
  }

  creatingCustomField.value = true;
  error.value = "";
  try {
    await api.createCustomField(context.orgId, context.projectId, payload);
    newCustomFieldName.value = "";
    newCustomFieldOptions.value = "";
    newCustomFieldType.value = "text";
    newCustomFieldClientSafe.value = false;
    await refreshCustomFields();
    await refreshWork();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingCustomField.value = false;
  }
}

function requestArchiveCustomField(field: CustomFieldDefinition) {
  pendingArchiveField.value = field;
  archiveFieldModalOpen.value = true;
}

async function archiveCustomField() {
  if (!context.orgId) {
    return;
  }

  const field = pendingArchiveField.value;
  if (!field) {
    return;
  }

  error.value = "";
  archivingCustomField.value = true;
  try {
    await api.deleteCustomField(context.orgId, field.id);
    pendingArchiveField.value = null;
    archiveFieldModalOpen.value = false;
    await refreshCustomFields();
    await refreshWork();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    archivingCustomField.value = false;
  }
}

async function toggleClientSafe(field: CustomFieldDefinition) {
  if (!context.orgId) {
    return;
  }

  error.value = "";
  try {
    await api.updateCustomField(context.orgId, field.id, { client_safe: field.client_safe });
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
    <h1 class="page-title">Work</h1>
    <p class="muted">Tasks scoped to the selected org + project.</p>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>
    <p v-else-if="!context.projectId" class="card">Select a project to continue.</p>

    <div v-else>
      <div class="card">
        <div class="toolbar">
          <div class="toolbar-row">
            <label class="toolbar-label">
              Saved view
              <select v-model="selectedSavedViewId">
                <option value="">(none)</option>
                <option v-for="view in savedViews" :key="view.id" :value="view.id">
                  {{ view.name }}
                </option>
              </select>
            </label>

            <span v-if="loadingSavedViews" class="muted">Loading views…</span>

            <div v-if="canManageCustomization" class="toolbar-actions">
              <button type="button" @click="createSavedView">Save new</button>
              <button type="button" :disabled="!selectedSavedViewId" @click="updateSavedView">
                Update
              </button>
              <button type="button" :disabled="!selectedSavedViewId" @click="requestDeleteSavedView">
                Delete
              </button>
            </div>
          </div>

          <div class="toolbar-row">
            <label class="toolbar-label">
              Search
              <input v-model="search" type="search" placeholder="Filter by title…" />
            </label>

            <fieldset class="status-filters">
              <legend class="muted">Status</legend>
              <label v-for="option in STATUS_OPTIONS" :key="option.value" class="status-filter">
                <input v-model="selectedStatuses" type="checkbox" :value="option.value" />
                {{ option.label }}
              </label>
            </fieldset>

            <label class="toolbar-label">
              Sort
              <select v-model="sortField">
                <option value="created_at">Created</option>
                <option value="updated_at">Updated</option>
                <option value="title">Title</option>
              </select>
            </label>

            <label class="toolbar-label">
              Direction
              <select v-model="sortDirection">
                <option value="asc">Asc</option>
                <option value="desc">Desc</option>
              </select>
            </label>

            <label class="toolbar-label">
              Group
              <select v-model="groupBy">
                <option value="none">None</option>
                <option value="status">Status</option>
              </select>
            </label>
          </div>
        </div>

        <div v-if="loading" class="muted">Loading…</div>
        <div v-else-if="error" class="error">{{ error }}</div>
        <div v-else-if="filteredTasks.length === 0" class="muted">No tasks yet.</div>
        <div v-else>
          <p v-if="epicsError" class="muted">{{ epicsError }}</p>

          <div v-if="groupBy === 'status'" class="stack">
            <section v-for="group in taskGroups" :key="group.key" class="status-group">
              <h2 class="group-title">{{ group.label }}</h2>

              <ul class="list">
                <li v-for="task in group.tasks" :key="task.id" class="task">
                  <div class="task-row">
                    <button type="button" class="toggle" @click="toggleTask(task.id)">
                      {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                    </button>
                    <RouterLink class="task-link" :to="`/work/${task.id}`">
                      {{ task.title }}
                    </RouterLink>
                    <span v-if="task.epic_id" class="muted chip">
                      {{ epicById[task.epic_id]?.title ?? task.epic_id }}
                    </span>
                    <span class="muted chip">{{ task.status }}</span>
                    <span class="muted chip">Progress {{ formatPercent(task.progress) }}</span>
                    <span class="muted chip">Updated {{ formatTimestamp(task.updated_at) }}</span>
                  </div>

                  <div v-if="displayFieldsForTask(task).length" class="custom-values">
                    <span v-for="item in displayFieldsForTask(task)" :key="item.id" class="pill">
                      {{ item.label }}
                    </span>
                  </div>

                  <div v-if="expandedTaskIds[task.id]" class="subtasks">
                    <div v-if="subtasksByTaskId[task.id]?.loading" class="muted">
                      Loading subtasks…
                    </div>
                    <div v-else-if="subtasksByTaskId[task.id]?.error" class="error">
                      {{ subtasksByTaskId[task.id]?.error }}
                    </div>
                    <div
                      v-else-if="(subtasksByTaskId[task.id]?.subtasks?.length ?? 0) === 0"
                      class="muted"
                    >
                      No subtasks yet.
                    </div>
                    <ul v-else class="subtask-list">
                      <li
                        v-for="subtask in subtasksByTaskId[task.id]?.subtasks ?? []"
                        :key="subtask.id"
                        class="subtask"
                      >
                        <div class="subtask-main">
                          <div class="subtask-title">{{ subtask.title }}</div>
                          <div class="muted subtask-stage">
                            Stage {{ stageLabel(subtask.workflow_stage_id) }}
                          </div>
                        </div>
                        <div class="subtask-meta muted">
                          <span>Progress {{ formatPercent(subtask.progress) }}</span>
                          <span>Updated {{ formatTimestamp(subtask.updated_at) }}</span>
                        </div>
                      </li>
                    </ul>
                  </div>
                </li>
              </ul>
            </section>
          </div>

          <div v-else-if="epics.length > 0" class="stack">
            <section v-for="epic in epics" :key="epic.id" class="epic">
              <div class="epic-header">
                <div>
                  <div class="epic-title">{{ epic.title }}</div>
                  <div class="muted meta-row">
                    <span>Progress {{ formatPercent(epic.progress) }}</span>
                    <span>Updated {{ formatTimestamp(epic.updated_at) }}</span>
                  </div>
                </div>
              </div>

              <ul class="list">
                <li v-for="task in tasksByEpicId[epic.id] ?? []" :key="task.id" class="task">
                  <div class="task-row">
                    <button type="button" class="toggle" @click="toggleTask(task.id)">
                      {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                    </button>
                    <RouterLink class="task-link" :to="`/work/${task.id}`">
                      {{ task.title }}
                    </RouterLink>
                    <span class="muted chip">{{ task.status }}</span>
                    <span class="muted chip">Progress {{ formatPercent(task.progress) }}</span>
                    <span class="muted chip">Updated {{ formatTimestamp(task.updated_at) }}</span>
                  </div>

                  <div v-if="displayFieldsForTask(task).length" class="custom-values">
                    <span v-for="item in displayFieldsForTask(task)" :key="item.id" class="pill">
                      {{ item.label }}
                    </span>
                  </div>

                  <div v-if="expandedTaskIds[task.id]" class="subtasks">
                    <div v-if="subtasksByTaskId[task.id]?.loading" class="muted">
                      Loading subtasks…
                    </div>
                    <div v-else-if="subtasksByTaskId[task.id]?.error" class="error">
                      {{ subtasksByTaskId[task.id]?.error }}
                    </div>
                    <div
                      v-else-if="(subtasksByTaskId[task.id]?.subtasks?.length ?? 0) === 0"
                      class="muted"
                    >
                      No subtasks yet.
                    </div>
                    <ul v-else class="subtask-list">
                      <li
                        v-for="subtask in subtasksByTaskId[task.id]?.subtasks ?? []"
                        :key="subtask.id"
                        class="subtask"
                      >
                        <div class="subtask-main">
                          <div class="subtask-title">{{ subtask.title }}</div>
                          <div class="muted subtask-stage">
                            Stage {{ stageLabel(subtask.workflow_stage_id) }}
                          </div>
                        </div>
                        <div class="subtask-meta muted">
                          <span>Progress {{ formatPercent(subtask.progress) }}</span>
                          <span>Updated {{ formatTimestamp(subtask.updated_at) }}</span>
                        </div>
                      </li>
                    </ul>
                  </div>
                </li>
              </ul>
            </section>

            <section v-if="tasksByEpicId['unknown']?.length" class="epic">
              <div class="epic-header">
                <div>
                  <div class="epic-title">Other tasks</div>
                  <div class="muted meta-row">
                    <span>Tasks not assigned to an epic</span>
                  </div>
                </div>
              </div>

              <ul class="list">
                <li v-for="task in tasksByEpicId['unknown'] ?? []" :key="task.id" class="task">
                  <div class="task-row">
                    <button type="button" class="toggle" @click="toggleTask(task.id)">
                      {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                    </button>
                    <RouterLink class="task-link" :to="`/work/${task.id}`">
                      {{ task.title }}
                    </RouterLink>
                    <span class="muted chip">{{ task.status }}</span>
                    <span class="muted chip">Progress {{ formatPercent(task.progress) }}</span>
                    <span class="muted chip">Updated {{ formatTimestamp(task.updated_at) }}</span>
                  </div>

                  <div v-if="displayFieldsForTask(task).length" class="custom-values">
                    <span v-for="item in displayFieldsForTask(task)" :key="item.id" class="pill">
                      {{ item.label }}
                    </span>
                  </div>
                </li>
              </ul>
            </section>
          </div>

          <ul v-else class="list">
            <li v-for="task in filteredTasks" :key="task.id" class="task">
              <div class="task-row">
                <button type="button" class="toggle" @click="toggleTask(task.id)">
                  {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                </button>
                <RouterLink class="task-link" :to="`/work/${task.id}`">{{ task.title }}</RouterLink>
                <span class="muted chip">{{ task.status }}</span>
                <span class="muted chip">Progress {{ formatPercent(task.progress) }}</span>
                <span class="muted chip">Updated {{ formatTimestamp(task.updated_at) }}</span>
              </div>

              <div v-if="displayFieldsForTask(task).length" class="custom-values">
                <span v-for="item in displayFieldsForTask(task)" :key="item.id" class="pill">
                  {{ item.label }}
                </span>
              </div>

              <div v-if="expandedTaskIds[task.id]" class="subtasks">
                <div v-if="subtasksByTaskId[task.id]?.loading" class="muted">Loading subtasks…</div>
                <div v-else-if="subtasksByTaskId[task.id]?.error" class="error">
                  {{ subtasksByTaskId[task.id]?.error }}
                </div>
                <div
                  v-else-if="(subtasksByTaskId[task.id]?.subtasks?.length ?? 0) === 0"
                  class="muted"
                >
                  No subtasks yet.
                </div>
                <ul v-else class="subtask-list">
                  <li
                    v-for="subtask in subtasksByTaskId[task.id]?.subtasks ?? []"
                    :key="subtask.id"
                    class="subtask"
                  >
                    <div class="subtask-main">
                      <div class="subtask-title">{{ subtask.title }}</div>
                      <div class="muted subtask-stage">Stage {{ stageLabel(subtask.workflow_stage_id) }}</div>
                    </div>
                    <div class="subtask-meta muted">
                      <span>Progress {{ formatPercent(subtask.progress) }}</span>
                      <span>Updated {{ formatTimestamp(subtask.updated_at) }}</span>
                    </div>
                  </li>
                </ul>
              </div>
            </li>
          </ul>
        </div>
      </div>

      <div class="card">
        <h2 class="section-title">Custom fields</h2>
        <p class="muted">Project-scoped fields used on tasks and subtasks.</p>

        <div v-if="loadingCustomFields" class="muted">Loading custom fields…</div>
        <div v-else-if="customFields.length === 0" class="muted">No custom fields yet.</div>
        <ul v-else class="custom-fields">
          <li v-for="field in customFields" :key="field.id" class="custom-field">
            <div class="custom-field-main">
              <div class="custom-field-name">{{ field.name }}</div>
              <div class="muted custom-field-type">{{ field.field_type }}</div>
            </div>
            <label v-if="canManageCustomization" class="custom-field-safe">
              <input v-model="field.client_safe" type="checkbox" @change="toggleClientSafe(field)" />
              Client safe
            </label>
            <button
              v-if="canManageCustomization"
              type="button"
              class="danger"
              @click="requestArchiveCustomField(field)"
            >
              Archive
            </button>
          </li>
        </ul>

        <form v-if="canManageCustomization" class="new-field" @submit.prevent="createCustomField">
          <h3 class="section-title">Add field</h3>
          <div class="new-field-row">
            <label class="toolbar-label">
              Name
              <input v-model="newCustomFieldName" type="text" placeholder="e.g., Priority" />
            </label>

            <label class="toolbar-label">
              Type
              <select v-model="newCustomFieldType">
                <option value="text">Text</option>
                <option value="number">Number</option>
                <option value="date">Date</option>
                <option value="select">Select</option>
                <option value="multi_select">Multi-select</option>
              </select>
            </label>

            <label class="toolbar-label">
              Options
              <input
                v-model="newCustomFieldOptions"
                :disabled="newCustomFieldType !== 'select' && newCustomFieldType !== 'multi_select'"
                type="text"
                placeholder="Comma-separated (select types only)"
              />
            </label>

            <label class="toolbar-label">
              Client safe
              <input v-model="newCustomFieldClientSafe" type="checkbox" />
            </label>

            <button type="submit" :disabled="creatingCustomField">Create</button>
          </div>
        </form>
      </div>
    </div>
    <VlConfirmModal
      v-model:open="deleteSavedViewModalOpen"
      title="Delete saved view"
      body="Delete this saved view?"
      confirm-label="Delete view"
      confirm-variant="danger"
      :loading="deletingSavedView"
      @confirm="deleteSavedView"
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
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1rem;
}

.toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.toolbar-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}

.toolbar-actions {
  display: flex;
  gap: 0.5rem;
}

.status-filters {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
}

.status-filter {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.9rem;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.status-group {
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}

.status-group:first-child {
  border-top: none;
  padding-top: 0;
}

.epic {
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}

.epic:first-child {
  border-top: none;
  padding-top: 0;
}

.epic-title {
  font-weight: 700;
}

.meta-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  font-size: 0.9rem;
}

.group-title {
  margin: 0.5rem 0;
  font-size: 1rem;
}

.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.task {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}

.task:last-child {
  border-bottom: none;
}

.task-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.task-link {
  font-weight: 600;
}

.toggle {
  width: 2rem;
  padding: 0.25rem 0;
  border-radius: 8px;
  line-height: 1;
}

.chip {
  font-size: 0.85rem;
  padding: 0.1rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #f8fafc;
}

.custom-values {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-size: 0.85rem;
  color: var(--muted);
}

.subtasks {
  margin-left: 2.75rem;
  border-left: 2px solid var(--border);
  padding-left: 0.75rem;
}

.subtask-list {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.subtask {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}

.subtask:last-child {
  border-bottom: none;
}

.subtask-title {
  font-weight: 600;
}

.subtask-stage {
  font-size: 0.85rem;
}

.subtask-meta {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
  align-items: flex-end;
}

.section-title {
  margin: 0.5rem 0;
  font-size: 1rem;
}

.custom-fields {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.custom-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}

.custom-field:last-child {
  border-bottom: none;
}

.custom-field-main {
  display: flex;
  flex-direction: column;
}

.custom-field-name {
  font-weight: 600;
}

.custom-field-type {
  font-size: 0.85rem;
}

.custom-field-safe {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.9rem;
}

.new-field {
  margin-top: 1rem;
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}

.new-field-row {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem;
}

.danger {
  border-color: #b42318;
  color: #b42318;
}
</style>
