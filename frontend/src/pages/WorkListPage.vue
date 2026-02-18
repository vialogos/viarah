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
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { mapAllSettledWithConcurrency } from "../utils/promisePool";
import { formatPercent, formatTimestamp, progressLabelColor } from "../utils/format";
import type { VlLabelColor } from "../utils/labels";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

type ScopeMeta = { orgId: string; orgName: string; projectId: string; projectName: string };
type ScopedTask = Task & { _scope?: ScopeMeta };
type ScopedEpic = Epic & { _scope?: ScopeMeta };

const tasks = ref<ScopedTask[]>([]);
const epics = ref<ScopedEpic[]>([]);
const stages = ref<WorkflowStage[]>([]);
const savedViews = ref<SavedView[]>([]);
const customFields = ref<CustomFieldDefinition[]>([]);

const hasAnyWorkItems = computed(() => tasks.value.length > 0 || epics.value.length > 0);

const loading = ref(false);
const loadingSavedViews = ref(false);
const loadingCustomFields = ref(false);
const error = ref("");
const epicsError = ref("");
const aggregateFailures = ref<Array<{ scope: ScopeMeta; message: string }>>([]);
const aggregateMetaWarning = ref("");
const readOnlyScopeActive = computed(() => context.isAnyAllScopeActive);

type SubtaskState = { loading: boolean; error: string; subtasks: Subtask[] };
const subtasksByTaskId = ref<Record<string, SubtaskState>>({});
const expandedTaskIds = ref<Record<string, boolean>>({});

const projectWorkflowId = computed(() => {
  const project = context.projects.find((p) => p.id === context.projectId);
  return project?.workflow_id ?? null;
});

const epicById = computed(() => {
  const map: Record<string, ScopedEpic> = {};
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
  return stageNameById.value[stageId] ?? "(unknown stage)";
}

function stageLabelColor(stageId: string | null | undefined): VlLabelColor {
  if (!stageId) {
    return "blue";
  }

  const stage = stages.value.find((item) => item.id === stageId);
  if (!stage) {
    return "teal";
  }
  if (stage.is_done) {
    return "green";
  }
  if (stage.is_qa) {
    return "purple";
  }
  if (stage.counts_as_wip) {
    return "orange";
  }
  return "teal";
}

function statusLabelColor(status: string): "blue" | "orange" | "green" | "purple" {
  if (status === "done") {
    return "green";
  }
  if (status === "qa") {
    return "purple";
  }
  if (status === "in_progress") {
    return "orange";
  }
  return "blue";
}

function statusEnabled(value: string): boolean {
  return selectedStatuses.value.includes(value);
}

function setStatusEnabled(value: string, enabled: boolean) {
  if (enabled) {
    selectedStatuses.value = Array.from(new Set([...selectedStatuses.value, value]));
    return;
  }
  selectedStatuses.value = selectedStatuses.value.filter((item) => item !== value);
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

const canManageCustomization = computed(() => {
  if (!context.hasConcreteScope) {
    return false;
  }
  return currentRole.value === "admin" || currentRole.value === "pm";
});

const canAuthorWork = computed(() => {
  if (!context.hasConcreteScope) {
    return false;
  }
  return currentRole.value === "admin" || currentRole.value === "pm" || currentRole.value === "member";
});

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

const createEpicModalOpen = ref(false);
const createEpicTitle = ref("");
const createEpicDescription = ref("");
const createEpicStatus = ref("");
const createEpicError = ref("");
const creatingEpic = ref(false);

const createTaskModalOpen = ref(false);
const createTaskEpicId = ref("");
const createTaskEpicTitle = ref("");
const createTaskTitle = ref("");
const createTaskDescription = ref("");
const createTaskStatus = ref("backlog");
const createTaskStartDate = ref("");
const createTaskEndDate = ref("");
const createTaskError = ref("");
const creatingTask = ref(false);

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
  aggregateFailures.value = [];
  aggregateMetaWarning.value = "";

  if (context.hasConcreteScope) {
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
    return;
  }

  if (!readOnlyScopeActive.value) {
    tasks.value = [];
    epics.value = [];
    expandedTaskIds.value = {};
    subtasksByTaskId.value = {};
    return;
  }

  await refreshWorkAggregate();
}

const INTERNAL_ROLES = new Set(["admin", "pm", "member"]);
const PROJECT_FETCH_CONCURRENCY = 4;
const ORG_PROJECTS_FETCH_CONCURRENCY = 3;

function taskLink(task: ScopedTask) {
  const scope = task._scope;
  if (scope && !context.hasConcreteScope) {
    return { path: `/work/${task.id}`, query: { orgId: scope.orgId, projectId: scope.projectId } };
  }
  return `/work/${task.id}`;
}

async function refreshWorkAggregate() {
  loading.value = true;
  expandedTaskIds.value = {};
  subtasksByTaskId.value = {};
  tasks.value = [];
  epics.value = [];

  const failures: Array<{ scope: ScopeMeta; message: string }> = [];
  let sawEpicsForbidden = false;

  try {
    const orgTargets: Array<{ id: string; name: string }> = [];

    if (context.orgScope === "all") {
      const seen = new Set<string>();
      for (const membership of session.memberships) {
        if (!INTERNAL_ROLES.has(membership.role)) {
          continue;
        }
        if (seen.has(membership.org.id)) {
          continue;
        }
        seen.add(membership.org.id);
        orgTargets.push({ id: membership.org.id, name: membership.org.name });
      }
    } else if (context.orgId) {
      const orgName = session.memberships.find((m) => m.org.id === context.orgId)?.org.name ?? context.orgId;
      orgTargets.push({ id: context.orgId, name: orgName });
    }

    if (orgTargets.length === 0) {
      aggregateFailures.value = [];
      aggregateMetaWarning.value = "";
      return;
    }

    const orgProjectsResults = await mapAllSettledWithConcurrency(
      orgTargets,
      ORG_PROJECTS_FETCH_CONCURRENCY,
      async (org) => {
        const res = await api.listProjects(org.id);
        return { org, projects: res.projects };
      }
    );

    const projectTargets: Array<{ org: { id: string; name: string }; project: { id: string; name: string } }> = [];
    for (let i = 0; i < orgProjectsResults.length; i += 1) {
      const result = orgProjectsResults[i];
      const org = orgTargets[i];
      if (!result || !org) {
        continue;
      }
      if (result.status === "rejected") {
        failures.push({
          scope: { orgId: org.id, orgName: org.name, projectId: "", projectName: "(projects)" },
          message: result.reason instanceof Error ? result.reason.message : String(result.reason),
        });
        continue;
      }
      for (const project of result.value.projects) {
        projectTargets.push({ org: result.value.org, project: { id: project.id, name: project.name } });
      }
    }

    const projectWorkResults = await mapAllSettledWithConcurrency(
      projectTargets,
      PROJECT_FETCH_CONCURRENCY,
      async (target) => {
        const [tasksRes, epicsRes] = await Promise.allSettled([
          api.listTasks(target.org.id, target.project.id),
          api.listEpics(target.org.id, target.project.id),
        ]);
        return { target, tasksRes, epicsRes };
      }
    );

    const nextTasks: ScopedTask[] = [];
    const nextEpics: ScopedEpic[] = [];

    for (let i = 0; i < projectWorkResults.length; i += 1) {
      const item = projectWorkResults[i];
      const target = projectTargets[i];
      if (!item || !target) {
        continue;
      }
      const scope: ScopeMeta = {
        orgId: target.org.id,
        orgName: target.org.name,
        projectId: target.project.id,
        projectName: target.project.name,
      };

      if (item.status === "rejected") {
        failures.push({
          scope,
          message: item.reason instanceof Error ? item.reason.message : String(item.reason),
        });
        continue;
      }

      const tasksRes = item.value.tasksRes;
      if (tasksRes.status === "fulfilled") {
        for (const task of tasksRes.value.tasks) {
          nextTasks.push({ ...(task as Task), _scope: scope });
        }
      } else {
        const reason = tasksRes.reason;
        if (reason instanceof ApiError && reason.status === 401) {
          await handleUnauthorized();
          return;
        }
        failures.push({ scope, message: reason instanceof Error ? reason.message : String(reason) });
      }

      const epicsRes = item.value.epicsRes;
      if (epicsRes.status === "fulfilled") {
        for (const epic of epicsRes.value.epics) {
          nextEpics.push({ ...(epic as Epic), _scope: scope });
        }
      } else {
        const reason = epicsRes.reason;
        if (reason instanceof ApiError && reason.status === 401) {
          await handleUnauthorized();
          return;
        }
        if (reason instanceof ApiError && reason.status === 403) {
          sawEpicsForbidden = true;
        } else {
          failures.push({ scope, message: reason instanceof Error ? reason.message : String(reason) });
        }
      }
    }

    tasks.value = nextTasks;
    epics.value = nextEpics;
    aggregateFailures.value = failures;
    aggregateMetaWarning.value = sawEpicsForbidden
      ? "Some projects do not allow epics for your role; showing tasks where available."
      : "";
  } finally {
    loading.value = false;
  }
}

function openCreateEpicModal() {
  createEpicTitle.value = "";
  createEpicDescription.value = "";
  createEpicStatus.value = "";
  createEpicError.value = "";
  createEpicModalOpen.value = true;
}

async function createEpic() {
  if (!context.orgId || !context.projectId) {
    createEpicError.value = "Select an org and project to continue.";
    return;
  }
  if (!canAuthorWork.value) {
    createEpicError.value = "Only admin/pm/member can create work items.";
    return;
  }

  const title = createEpicTitle.value.trim();
  if (!title) {
    createEpicError.value = "Title is required.";
    return;
  }

  createEpicError.value = "";
  creatingEpic.value = true;
  try {
    const payload: { title: string; description?: string; status?: string } = { title };

    const description = createEpicDescription.value.trim();
    if (description) {
      payload.description = description;
    }
    if (createEpicStatus.value) {
      payload.status = createEpicStatus.value;
    }

    await api.createEpic(context.orgId, context.projectId, payload);
    createEpicModalOpen.value = false;
    await refreshWork();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    createEpicError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingEpic.value = false;
  }
}

function openCreateTaskModal(epic: Epic) {
  createTaskEpicId.value = epic.id;
  createTaskEpicTitle.value = epic.title;
  createTaskTitle.value = "";
  createTaskDescription.value = "";
  createTaskStatus.value = "backlog";
  createTaskStartDate.value = "";
  createTaskEndDate.value = "";
  createTaskError.value = "";
  createTaskModalOpen.value = true;
}

async function createTask() {
  if (!context.orgId || !context.projectId) {
    createTaskError.value = "Select an org and project to continue.";
    return;
  }
  if (!canAuthorWork.value) {
    createTaskError.value = "Only admin/pm/member can create work items.";
    return;
  }

  const epicId = createTaskEpicId.value;
  if (!epicId) {
    createTaskError.value = "Select an epic to continue.";
    return;
  }

  const title = createTaskTitle.value.trim();
  if (!title) {
    createTaskError.value = "Title is required.";
    return;
  }

  createTaskError.value = "";
  creatingTask.value = true;
  try {
    const payload: {
      title: string;
      description?: string;
      status?: string;
      start_date?: string | null;
      end_date?: string | null;
    } = { title };

    const description = createTaskDescription.value.trim();
    if (description) {
      payload.description = description;
    }
    if (createTaskStatus.value) {
      payload.status = createTaskStatus.value;
    }
    if (createTaskStartDate.value) {
      payload.start_date = createTaskStartDate.value;
    }
    if (createTaskEndDate.value) {
      payload.end_date = createTaskEndDate.value;
    }

    const res = await api.createTask(context.orgId, epicId, payload);
    createTaskModalOpen.value = false;
    await refreshWork();
    await router.push(`/work/${res.task.id}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    createTaskError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingTask.value = false;
  }
}

async function refreshStages() {
  if (!context.hasConcreteScope || !context.orgId || !projectWorkflowId.value) {
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

watch(
  projectWorkflowId,
  () => {
    void refreshStages();
  },
  { immediate: true }
);

async function refreshSavedViews() {
  if (!context.hasConcreteScope || !context.orgId || !context.projectId) {
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
  if (!context.hasConcreteScope || !context.orgId || !context.projectId) {
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
  if (context.hasConcreteScope) {
    await Promise.all([refreshWork(), refreshSavedViews(), refreshCustomFields(), refreshStages()]);
    return;
  }

  savedViews.value = [];
  customFields.value = [];
  stages.value = [];
  selectedSavedViewId.value = "";
  await refreshWork();
}

watch(
  () => [context.orgScope, context.projectScope, context.orgId, context.projectId],
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

const filtersActive = computed(() => Boolean(search.value.trim()) || selectedStatuses.value.length > 0);

const noTasksMatchFilters = computed(() => {
  if (!filtersActive.value) {
    return false;
  }
  if (filteredTasks.value.length > 0) {
    return false;
  }
  return tasks.value.length > 0;
});

const tasksByEpicId = computed(() => {
  const map: Record<string, ScopedTask[]> = {};
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

  const groups: Array<{ key: string; label: string; tasks: ScopedTask[] }> = [];
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
  if (!context.hasConcreteScope || !context.orgId) {
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
  if (!context.hasConcreteScope) {
    return;
  }

  const next = { ...expandedTaskIds.value, [taskId]: !expandedTaskIds.value[taskId] };
  expandedTaskIds.value = next;

  if (next[taskId] && !subtasksByTaskId.value[taskId]) {
    await loadSubtasks(taskId);
  }
}

async function createSavedView() {
  if (!context.hasConcreteScope || !context.orgId || !context.projectId) {
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
  if (!context.hasConcreteScope || !context.orgId || !selectedSavedViewId.value) {
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
  if (!context.hasConcreteScope || !context.orgId || !selectedSavedViewId.value) {
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
  if (!context.hasConcreteScope || !context.orgId || !context.projectId) {
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
  if (!context.hasConcreteScope || !context.orgId) {
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
  if (!context.hasConcreteScope || !context.orgId) {
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
  <div class="work-page">
    <pf-title h="1" size="2xl">Work</pf-title>
    <pf-content>
      <p v-if="readOnlyScopeActive" class="muted">
        Global scope (read-only). Select a specific org + project to create or edit work items.
      </p>
      <p v-else class="muted">Tasks scoped to the selected org + project.</p>
    </pf-content>

    <pf-empty-state v-if="context.orgScope === 'single' && !context.orgId">
      <pf-empty-state-header title="Select an org" heading-level="h2" />
      <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
    </pf-empty-state>
    <pf-empty-state
      v-else-if="context.orgScope === 'single' && context.projectScope === 'single' && !context.projectId"
    >
      <pf-empty-state-header title="Select a project" heading-level="h2" />
      <pf-empty-state-body>Select a project to continue.</pf-empty-state-body>
    </pf-empty-state>

    <div v-else class="stack">
      <pf-card>
        <pf-card-body>
          <pf-form class="toolbar">
            <div class="toolbar-row">
              <pf-form-group v-if="context.hasConcreteScope" label="Saved view" field-id="work-saved-view">
                <pf-form-select id="work-saved-view" v-model="selectedSavedViewId">
                  <pf-form-select-option value="">(none)</pf-form-select-option>
                  <pf-form-select-option v-for="view in savedViews" :key="view.id" :value="view.id">
                    {{ view.name }}
                  </pf-form-select-option>
                </pf-form-select>
              </pf-form-group>

              <div v-if="context.hasConcreteScope && loadingSavedViews" class="inline-loading">
                <pf-spinner size="sm" aria-label="Loading saved views" />
                <span class="muted">Loading views…</span>
              </div>

              <div v-if="canAuthorWork || canManageCustomization" class="toolbar-actions">
                <pf-button v-if="canAuthorWork" type="button" variant="primary" small @click="openCreateEpicModal">
                  Create epic
                </pf-button>

                <template v-if="canManageCustomization">
                  <pf-button type="button" variant="secondary" small @click="createSavedView">Save new</pf-button>
                  <pf-button type="button" variant="secondary" small :disabled="!selectedSavedViewId" @click="updateSavedView">
                    Update
                  </pf-button>
                  <pf-button type="button" variant="danger" small :disabled="!selectedSavedViewId" @click="requestDeleteSavedView">
                    Delete
                  </pf-button>
                </template>
              </div>
            </div>

            <div class="toolbar-row">
              <pf-form-group label="Search" field-id="work-search">
                <pf-search-input
                  id="work-search"
                  v-model="search"
                  placeholder="Filter by title…"
                  @clear="search = ''"
                />
              </pf-form-group>

              <pf-form-group label="Status filters">
                <div class="status-filters">
                  <pf-checkbox
                    v-for="option in STATUS_OPTIONS"
                    :id="`status-filter-${option.value}`"
                    :key="option.value"
                    :label="option.label"
                    :model-value="statusEnabled(option.value)"
                    @update:model-value="setStatusEnabled(option.value, Boolean($event))"
                  />
                </div>
              </pf-form-group>

              <pf-form-group label="Sort" field-id="work-sort-field">
                <pf-form-select id="work-sort-field" v-model="sortField">
                  <pf-form-select-option value="created_at">Created</pf-form-select-option>
                  <pf-form-select-option value="updated_at">Updated</pf-form-select-option>
                  <pf-form-select-option value="title">Title</pf-form-select-option>
                </pf-form-select>
              </pf-form-group>

              <pf-form-group label="Direction" field-id="work-sort-direction">
                <pf-form-select id="work-sort-direction" v-model="sortDirection">
                  <pf-form-select-option value="asc">Asc</pf-form-select-option>
                  <pf-form-select-option value="desc">Desc</pf-form-select-option>
                </pf-form-select>
              </pf-form-group>

              <pf-form-group label="Group" field-id="work-group-by">
                <pf-form-select id="work-group-by" v-model="groupBy">
                  <pf-form-select-option value="none">None</pf-form-select-option>
                  <pf-form-select-option value="status">Status</pf-form-select-option>
                </pf-form-select>
              </pf-form-group>
            </div>
          </pf-form>

          <div v-if="loading" class="loading-panel">
            <pf-spinner size="md" aria-label="Loading work items" />
            <pf-skeleton width="100%" height="1.2rem" />
            <pf-skeleton width="100%" height="1.2rem" />
            <pf-skeleton width="80%" height="1.2rem" />
          </div>
          <pf-alert v-else-if="error" inline variant="danger" :title="error" />
          <pf-empty-state v-else-if="!hasAnyWorkItems">
            <pf-empty-state-header title="No work items yet" heading-level="h2" />
            <pf-empty-state-body v-if="canAuthorWork">
              Create an epic to start organizing tasks and subtasks for this project.
            </pf-empty-state-body>
            <pf-empty-state-body v-else>Nothing to show yet for the current scope.</pf-empty-state-body>
            <pf-button v-if="canAuthorWork" type="button" variant="primary" @click="openCreateEpicModal">
              Create epic
            </pf-button>
          </pf-empty-state>
          <div v-else>
            <span
              v-if="context.hasConcreteScope"
              id="vl-work-list-ready"
              data-testid="vl-work-list-ready"
              aria-hidden="true"
              style="display: none"
            />
            <pf-alert
              v-if="readOnlyScopeActive"
              inline
              variant="info"
              title="Global scope is read-only. Select a specific org + project to make changes."
            />
            <pf-alert v-if="aggregateMetaWarning" inline variant="warning" :title="aggregateMetaWarning" />
            <pf-alert
              v-if="aggregateFailures.length > 0"
              inline
              variant="warning"
              :title="`Some projects failed to load (${aggregateFailures.length}).`"
            />
            <pf-data-list v-if="aggregateFailures.length > 0" compact>
              <pf-data-list-item v-for="(item, idx) in aggregateFailures.slice(0, 10)" :key="idx">
                <pf-data-list-cell>
                  <div class="task-row">
                    <VlLabel color="teal">{{ item.scope.orgName }}</VlLabel>
                    <VlLabel color="blue">{{ item.scope.projectName }}</VlLabel>
                    <span class="muted">{{ item.message }}</span>
                  </div>
                </pf-data-list-cell>
              </pf-data-list-item>
            </pf-data-list>
            <pf-content v-if="aggregateFailures.length > 10">
              <p class="muted">Showing the first 10 failures.</p>
            </pf-content>

            <pf-alert v-if="epicsError" inline variant="warning" :title="epicsError" />
            <pf-alert
              v-if="noTasksMatchFilters"
              inline
              variant="info"
              title="No tasks match the current filters."
            />

            <pf-empty-state v-if="filteredTasks.length === 0 && epics.length === 0">
              <pf-empty-state-header title="No tasks match the current filters" heading-level="h2" />
              <pf-empty-state-body>Try clearing search or status filters.</pf-empty-state-body>
            </pf-empty-state>

            <div v-else-if="groupBy === 'status' && filteredTasks.length > 0" class="stack">
              <section v-for="group in taskGroups" :key="group.key" class="status-group">
                <pf-title h="2" size="lg">{{ group.label }}</pf-title>

                <pf-data-list compact>
                  <pf-data-list-item v-for="task in group.tasks" :key="task.id" class="task-item">
                    <pf-data-list-cell>
                      <div class="task-row">
                        <pf-button
                          type="button"
                          variant="plain"
                          class="toggle"
                          no-padding
                          :disabled="!context.hasConcreteScope"
                          :aria-label="expandedTaskIds[task.id] ? 'Collapse task' : 'Expand task'"
                          @click="toggleTask(task.id)"
                        >
                          {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                        </pf-button>
                        <RouterLink class="task-link" :to="taskLink(task)">
                          {{ task.title }}
                        </RouterLink>
                        <VlLabel v-if="task._scope" color="teal">{{ task._scope.orgName }}</VlLabel>
                        <VlLabel v-if="task._scope" color="blue">{{ task._scope.projectName }}</VlLabel>
                        <VlLabel v-if="task.epic_id" color="purple">
                          {{ epicById[task.epic_id]?.title ?? task.epic_id }}
                        </VlLabel>
                        <VlLabel
                          v-if="task.workflow_stage_id"
                          :color="stageLabelColor(task.workflow_stage_id)"
                          :title="task.workflow_stage_id ?? undefined"
                        >
                          Stage {{ stageLabel(task.workflow_stage_id) }}
                        </VlLabel>
                        <VlLabel v-else :color="statusLabelColor(task.status)">{{ task.status }}</VlLabel>
                        <VlLabel :color="progressLabelColor(task.progress)">
                          Progress {{ formatPercent(task.progress) }}
                        </VlLabel>
                        <VlLabel color="grey">Updated {{ formatTimestamp(task.updated_at) }}</VlLabel>
                      </div>

                      <pf-progress
                        class="task-progress"
                        size="sm"
                        :value="Math.round((task.progress ?? 0) * 100)"
                        :label="formatPercent(task.progress)"
                      />

                      <div v-if="context.hasConcreteScope && displayFieldsForTask(task).length" class="custom-values">
                        <VlLabel v-for="item in displayFieldsForTask(task)" :key="item.id">
                          {{ item.label }}
                        </VlLabel>
                      </div>

                      <div v-if="context.hasConcreteScope && expandedTaskIds[task.id]" class="subtasks">
                        <div v-if="!subtasksByTaskId[task.id] || subtasksByTaskId[task.id]?.loading" class="inline-loading">
                          <pf-spinner size="sm" aria-label="Loading subtasks" />
                          <span class="muted">Loading subtasks…</span>
                        </div>
                        <pf-alert
                          v-else-if="subtasksByTaskId[task.id]?.error"
                          inline
                          variant="danger"
                          :title="subtasksByTaskId[task.id]?.error"
                        />
                        <p v-else-if="(subtasksByTaskId[task.id]?.subtasks?.length ?? 0) === 0" class="muted">
                          No subtasks yet.
                        </p>
                        <pf-list v-else class="subtask-list">
                          <pf-list-item
                            v-for="subtask in subtasksByTaskId[task.id]?.subtasks ?? []"
                            :key="subtask.id"
                            class="subtask"
                          >
                            <div class="subtask-main">
                              <div class="subtask-title">{{ subtask.title }}</div>
                              <VlLabel :color="stageLabelColor(subtask.workflow_stage_id)" :title="subtask.workflow_stage_id ?? undefined">
                                Stage {{ stageLabel(subtask.workflow_stage_id) }}
                              </VlLabel>
                            </div>
                            <div class="subtask-meta">
                              <pf-progress
                                class="subtask-progress"
                                size="sm"
                                :value="Math.round((subtask.progress ?? 0) * 100)"
                                :label="formatPercent(subtask.progress)"
                              />
                              <VlLabel color="grey">Updated {{ formatTimestamp(subtask.updated_at) }}</VlLabel>
                            </div>
                          </pf-list-item>
                        </pf-list>
                      </div>
                    </pf-data-list-cell>
                  </pf-data-list-item>
                </pf-data-list>
              </section>
            </div>

            <div v-else-if="epics.length > 0" class="stack">
              <section v-for="epic in epics" :key="epic.id" class="epic">
                <div class="epic-header">
                  <div>
                    <pf-title h="2" size="lg">{{ epic.title }}</pf-title>
                    <div class="meta-row">
                      <template v-if="epic._scope">
                        <VlLabel color="teal">{{ epic._scope.orgName }}</VlLabel>
                        <VlLabel color="blue">{{ epic._scope.projectName }}</VlLabel>
                      </template>
                      <VlLabel :color="progressLabelColor(epic.progress)">
                        Progress {{ formatPercent(epic.progress) }}
                      </VlLabel>
                      <VlLabel color="grey">Updated {{ formatTimestamp(epic.updated_at) }}</VlLabel>
                    </div>
                  </div>

                  <div v-if="canAuthorWork" class="epic-actions">
                    <pf-button
                      type="button"
                      variant="secondary"
                      small
                      :disabled="creatingTask"
                      @click="openCreateTaskModal(epic)"
                    >
                      Add task
                    </pf-button>
                  </div>
                </div>

                <pf-empty-state v-if="(tasksByEpicId[epic.id] ?? []).length === 0" variant="small">
                  <pf-empty-state-header
                    :title="filtersActive ? 'No tasks match the current filters' : 'No tasks yet'"
                    heading-level="h3"
                  />
                  <pf-empty-state-body>
                    <template v-if="filtersActive">
                      Try clearing search or status filters, or use “Add task” to create a new task for this epic.
                    </template>
                    <template v-else>Use “Add task” to create the first task for this epic.</template>
                  </pf-empty-state-body>
                </pf-empty-state>

                <pf-data-list v-else compact>
                  <pf-data-list-item v-for="task in tasksByEpicId[epic.id] ?? []" :key="task.id" class="task-item">
                    <pf-data-list-cell>
                      <div class="task-row">
                        <pf-button
                          type="button"
                          variant="plain"
                          class="toggle"
                          no-padding
                          :disabled="!context.hasConcreteScope"
                          :aria-label="expandedTaskIds[task.id] ? 'Collapse task' : 'Expand task'"
                          @click="toggleTask(task.id)"
                        >
                          {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                        </pf-button>
                        <RouterLink class="task-link" :to="taskLink(task)">
                          {{ task.title }}
                        </RouterLink>
                        <VlLabel v-if="task._scope" color="teal">{{ task._scope.orgName }}</VlLabel>
                        <VlLabel v-if="task._scope" color="blue">{{ task._scope.projectName }}</VlLabel>
                        <VlLabel
                          v-if="task.workflow_stage_id"
                          :color="stageLabelColor(task.workflow_stage_id)"
                          :title="task.workflow_stage_id ?? undefined"
                        >
                          Stage {{ stageLabel(task.workflow_stage_id) }}
                        </VlLabel>
                        <VlLabel v-else :color="statusLabelColor(task.status)">{{ task.status }}</VlLabel>
                        <VlLabel :color="progressLabelColor(task.progress)">
                          Progress {{ formatPercent(task.progress) }}
                        </VlLabel>
                        <VlLabel color="grey">Updated {{ formatTimestamp(task.updated_at) }}</VlLabel>
                      </div>

                      <pf-progress
                        class="task-progress"
                        size="sm"
                        :value="Math.round((task.progress ?? 0) * 100)"
                        :label="formatPercent(task.progress)"
                      />

                      <div v-if="context.hasConcreteScope && displayFieldsForTask(task).length" class="custom-values">
                        <VlLabel v-for="item in displayFieldsForTask(task)" :key="item.id">
                          {{ item.label }}
                        </VlLabel>
                      </div>

                      <div v-if="context.hasConcreteScope && expandedTaskIds[task.id]" class="subtasks">
                        <div v-if="!subtasksByTaskId[task.id] || subtasksByTaskId[task.id]?.loading" class="inline-loading">
                          <pf-spinner size="sm" aria-label="Loading subtasks" />
                          <span class="muted">Loading subtasks…</span>
                        </div>
                        <pf-alert
                          v-else-if="subtasksByTaskId[task.id]?.error"
                          inline
                          variant="danger"
                          :title="subtasksByTaskId[task.id]?.error"
                        />
                        <p v-else-if="(subtasksByTaskId[task.id]?.subtasks?.length ?? 0) === 0" class="muted">
                          No subtasks yet.
                        </p>
                        <pf-list v-else class="subtask-list">
                          <pf-list-item
                            v-for="subtask in subtasksByTaskId[task.id]?.subtasks ?? []"
                            :key="subtask.id"
                            class="subtask"
                          >
                            <div class="subtask-main">
                              <div class="subtask-title">{{ subtask.title }}</div>
                              <VlLabel :color="stageLabelColor(subtask.workflow_stage_id)" :title="subtask.workflow_stage_id ?? undefined">
                                Stage {{ stageLabel(subtask.workflow_stage_id) }}
                              </VlLabel>
                            </div>
                            <div class="subtask-meta">
                              <pf-progress
                                class="subtask-progress"
                                size="sm"
                                :value="Math.round((subtask.progress ?? 0) * 100)"
                                :label="formatPercent(subtask.progress)"
                              />
                              <VlLabel color="grey">Updated {{ formatTimestamp(subtask.updated_at) }}</VlLabel>
                            </div>
                          </pf-list-item>
                        </pf-list>
                      </div>
                    </pf-data-list-cell>
                  </pf-data-list-item>
                </pf-data-list>
              </section>

              <section v-if="tasksByEpicId['unknown']?.length" class="epic">
                <pf-title h="2" size="lg">Other tasks</pf-title>
                <pf-content>
                  <p class="muted">Tasks not assigned to an epic.</p>
                </pf-content>

                <pf-data-list compact>
                  <pf-data-list-item v-for="task in tasksByEpicId['unknown'] ?? []" :key="task.id" class="task-item">
                    <pf-data-list-cell>
                      <div class="task-row">
                        <pf-button
                          type="button"
                          variant="plain"
                          class="toggle"
                          no-padding
                          :disabled="!context.hasConcreteScope"
                          :aria-label="expandedTaskIds[task.id] ? 'Collapse task' : 'Expand task'"
                          @click="toggleTask(task.id)"
                        >
                          {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                        </pf-button>
                        <RouterLink class="task-link" :to="taskLink(task)">
                          {{ task.title }}
                        </RouterLink>
                        <VlLabel v-if="task._scope" color="teal">{{ task._scope.orgName }}</VlLabel>
                        <VlLabel v-if="task._scope" color="blue">{{ task._scope.projectName }}</VlLabel>
                        <VlLabel
                          v-if="task.workflow_stage_id"
                          :color="stageLabelColor(task.workflow_stage_id)"
                          :title="task.workflow_stage_id ?? undefined"
                        >
                          Stage {{ stageLabel(task.workflow_stage_id) }}
                        </VlLabel>
                        <VlLabel v-else :color="statusLabelColor(task.status)">{{ task.status }}</VlLabel>
                        <VlLabel :color="progressLabelColor(task.progress)">
                          Progress {{ formatPercent(task.progress) }}
                        </VlLabel>
                        <VlLabel color="grey">Updated {{ formatTimestamp(task.updated_at) }}</VlLabel>
                      </div>

                      <pf-progress
                        class="task-progress"
                        size="sm"
                        :value="Math.round((task.progress ?? 0) * 100)"
                        :label="formatPercent(task.progress)"
                      />

                      <div v-if="context.hasConcreteScope && displayFieldsForTask(task).length" class="custom-values">
                        <VlLabel v-for="item in displayFieldsForTask(task)" :key="item.id">
                          {{ item.label }}
                        </VlLabel>
                      </div>

                      <div v-if="context.hasConcreteScope && expandedTaskIds[task.id]" class="subtasks">
                        <div v-if="!subtasksByTaskId[task.id] || subtasksByTaskId[task.id]?.loading" class="inline-loading">
                          <pf-spinner size="sm" aria-label="Loading subtasks" />
                          <span class="muted">Loading subtasks…</span>
                        </div>
                        <pf-alert
                          v-else-if="subtasksByTaskId[task.id]?.error"
                          inline
                          variant="danger"
                          :title="subtasksByTaskId[task.id]?.error"
                        />
                        <p v-else-if="(subtasksByTaskId[task.id]?.subtasks?.length ?? 0) === 0" class="muted">
                          No subtasks yet.
                        </p>
                        <pf-list v-else class="subtask-list">
                          <pf-list-item
                            v-for="subtask in subtasksByTaskId[task.id]?.subtasks ?? []"
                            :key="subtask.id"
                            class="subtask"
                          >
                            <div class="subtask-main">
                              <div class="subtask-title">{{ subtask.title }}</div>
                              <VlLabel :color="stageLabelColor(subtask.workflow_stage_id)" :title="subtask.workflow_stage_id ?? undefined">
                                Stage {{ stageLabel(subtask.workflow_stage_id) }}
                              </VlLabel>
                            </div>
                            <div class="subtask-meta">
                              <pf-progress
                                class="subtask-progress"
                                size="sm"
                                :value="Math.round((subtask.progress ?? 0) * 100)"
                                :label="formatPercent(subtask.progress)"
                              />
                              <VlLabel color="grey">Updated {{ formatTimestamp(subtask.updated_at) }}</VlLabel>
                            </div>
                          </pf-list-item>
                        </pf-list>
                      </div>
                    </pf-data-list-cell>
                  </pf-data-list-item>
                </pf-data-list>
              </section>
            </div>

            <pf-data-list v-else compact>
              <pf-data-list-item v-for="task in filteredTasks" :key="task.id" class="task-item">
                <pf-data-list-cell>
                  <div class="task-row">
                    <pf-button
                      type="button"
                      variant="plain"
                      class="toggle"
                      no-padding
                      :disabled="!context.hasConcreteScope"
                      :aria-label="expandedTaskIds[task.id] ? 'Collapse task' : 'Expand task'"
                      @click="toggleTask(task.id)"
                    >
                      {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                    </pf-button>
                    <RouterLink class="task-link" :to="taskLink(task)">{{ task.title }}</RouterLink>
                    <VlLabel v-if="task._scope" color="teal">{{ task._scope.orgName }}</VlLabel>
                    <VlLabel v-if="task._scope" color="blue">{{ task._scope.projectName }}</VlLabel>
                    <VlLabel
                      v-if="task.workflow_stage_id"
                      :color="stageLabelColor(task.workflow_stage_id)"
                      :title="task.workflow_stage_id ?? undefined"
                    >
                      Stage {{ stageLabel(task.workflow_stage_id) }}
                    </VlLabel>
                    <VlLabel v-else :color="statusLabelColor(task.status)">{{ task.status }}</VlLabel>
                    <VlLabel :color="progressLabelColor(task.progress)">
                      Progress {{ formatPercent(task.progress) }}
                    </VlLabel>
                    <VlLabel color="grey">Updated {{ formatTimestamp(task.updated_at) }}</VlLabel>
                  </div>

                  <pf-progress
                    class="task-progress"
                    size="sm"
                    :value="Math.round((task.progress ?? 0) * 100)"
                    :label="formatPercent(task.progress)"
                  />

                  <div v-if="context.hasConcreteScope && expandedTaskIds[task.id]" class="subtasks">
                    <div v-if="!subtasksByTaskId[task.id] || subtasksByTaskId[task.id]?.loading" class="inline-loading">
                      <pf-spinner size="sm" aria-label="Loading subtasks" />
                      <span class="muted">Loading subtasks…</span>
                    </div>
                    <pf-alert
                      v-else-if="subtasksByTaskId[task.id]?.error"
                      inline
                      variant="danger"
                      :title="subtasksByTaskId[task.id]?.error"
                    />
                    <p v-else-if="(subtasksByTaskId[task.id]?.subtasks?.length ?? 0) === 0" class="muted">
                      No subtasks yet.
                    </p>
                    <pf-list v-else class="subtask-list">
                      <pf-list-item
                        v-for="subtask in subtasksByTaskId[task.id]?.subtasks ?? []"
                        :key="subtask.id"
                        class="subtask"
                      >
                        <div class="subtask-main">
                          <div class="subtask-title">{{ subtask.title }}</div>
                          <VlLabel :color="stageLabelColor(subtask.workflow_stage_id)" :title="subtask.workflow_stage_id ?? undefined">
                            Stage {{ stageLabel(subtask.workflow_stage_id) }}
                          </VlLabel>
                        </div>
                        <div class="subtask-meta">
                          <pf-progress
                            class="subtask-progress"
                            size="sm"
                            :value="Math.round((subtask.progress ?? 0) * 100)"
                            :label="formatPercent(subtask.progress)"
                          />
                          <VlLabel color="grey">Updated {{ formatTimestamp(subtask.updated_at) }}</VlLabel>
                        </div>
                      </pf-list-item>
                    </pf-list>
                  </div>
                </pf-data-list-cell>
              </pf-data-list-item>
            </pf-data-list>
          </div>
        </pf-card-body>
      </pf-card>

      <pf-card v-if="context.hasConcreteScope">
        <pf-card-body>
          <pf-title h="2" size="lg">Custom fields</pf-title>
          <pf-content>
            <p class="muted">Project-scoped fields used on tasks and subtasks.</p>
          </pf-content>

          <div v-if="loadingCustomFields" class="inline-loading">
            <pf-spinner size="sm" aria-label="Loading custom fields" />
            <span class="muted">Loading custom fields…</span>
          </div>
          <pf-empty-state v-else-if="customFields.length === 0">
            <pf-empty-state-header title="No custom fields yet" heading-level="h3" />
            <pf-empty-state-body>Create one to capture project-specific metadata.</pf-empty-state-body>
          </pf-empty-state>
          <pf-data-list v-else compact>
            <pf-data-list-item v-for="field in customFields" :key="field.id" class="custom-field">
              <pf-data-list-cell>
                <div class="custom-field-main">
                  <div class="custom-field-name">{{ field.name }}</div>
                  <VlLabel color="teal">{{ field.field_type }}</VlLabel>
                </div>
              </pf-data-list-cell>
              <pf-data-list-cell v-if="canManageCustomization" align-right>
                <div class="custom-field-actions">
                  <pf-checkbox
                    :id="`field-safe-${field.id}`"
                    v-model="field.client_safe"
                    label="Client safe"
                    @change="toggleClientSafe(field)"
                  />
                  <pf-button type="button" variant="danger" small @click="requestArchiveCustomField(field)">
                    Archive
                  </pf-button>
                </div>
              </pf-data-list-cell>
            </pf-data-list-item>
          </pf-data-list>

          <pf-form v-if="canManageCustomization" class="new-field" @submit.prevent="createCustomField">
            <pf-title h="3" size="md">Add field</pf-title>
            <div class="new-field-row">
              <pf-form-group label="Name" field-id="new-field-name">
                <pf-text-input id="new-field-name" v-model="newCustomFieldName" type="text" placeholder="e.g., Priority" />
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
        </pf-card-body>
      </pf-card>
    </div>

    <pf-modal v-model:open="createEpicModalOpen" title="Create epic">
      <pf-form class="modal-form" @submit.prevent="createEpic">
        <pf-form-group label="Title" field-id="epic-create-title">
          <pf-text-input id="epic-create-title" v-model="createEpicTitle" type="text" placeholder="Epic title" />
        </pf-form-group>

        <pf-form-group label="Description (optional)" field-id="epic-create-description">
          <pf-textarea id="epic-create-description" v-model="createEpicDescription" rows="4" />
        </pf-form-group>

        <pf-form-group label="Status (optional)" field-id="epic-create-status">
          <pf-form-select id="epic-create-status" v-model="createEpicStatus">
            <pf-form-select-option value="">(none)</pf-form-select-option>
            <pf-form-select-option v-for="option in STATUS_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </pf-form-select-option>
          </pf-form-select>
        </pf-form-group>

        <pf-alert v-if="createEpicError" inline variant="danger" :title="createEpicError" />
      </pf-form>

      <template #footer>
        <pf-button
          variant="primary"
          :disabled="creatingEpic || !canAuthorWork || !createEpicTitle.trim()"
          @click="createEpic"
        >
          {{ creatingEpic ? "Creating…" : "Create" }}
        </pf-button>
        <pf-button variant="link" :disabled="creatingEpic" @click="createEpicModalOpen = false">Cancel</pf-button>
      </template>
    </pf-modal>

    <pf-modal v-model:open="createTaskModalOpen" title="Add task">
      <pf-form class="modal-form" @submit.prevent="createTask">
        <pf-content v-if="createTaskEpicTitle">
          <p class="muted">Epic: <strong>{{ createTaskEpicTitle }}</strong></p>
        </pf-content>

        <pf-form-group label="Title" field-id="task-create-title">
          <pf-text-input id="task-create-title" v-model="createTaskTitle" type="text" placeholder="Task title" />
        </pf-form-group>

        <pf-form-group label="Description (optional)" field-id="task-create-description">
          <pf-textarea id="task-create-description" v-model="createTaskDescription" rows="4" />
        </pf-form-group>

        <pf-form-group label="Status" field-id="task-create-status">
          <pf-form-select id="task-create-status" v-model="createTaskStatus">
            <pf-form-select-option v-for="option in STATUS_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </pf-form-select-option>
          </pf-form-select>
        </pf-form-group>

        <pf-form-group label="Start date (optional)" field-id="task-create-start-date">
          <pf-text-input id="task-create-start-date" v-model="createTaskStartDate" type="date" />
        </pf-form-group>

        <pf-form-group label="End date (optional)" field-id="task-create-end-date">
          <pf-text-input id="task-create-end-date" v-model="createTaskEndDate" type="date" />
        </pf-form-group>

        <pf-alert v-if="createTaskError" inline variant="danger" :title="createTaskError" />
      </pf-form>

      <template #footer>
        <pf-button
          variant="primary"
          :disabled="creatingTask || !canAuthorWork || !createTaskTitle.trim()"
          @click="createTask"
        >
          {{ creatingTask ? "Creating…" : "Create" }}
        </pf-button>
        <pf-button variant="link" :disabled="creatingTask" @click="createTaskModalOpen = false">Cancel</pf-button>
      </template>
    </pf-modal>

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
.work-page {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.toolbar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.inline-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.loading-panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.status-group {
  border-top: 1px solid var(--border);
  padding-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.status-group:first-child {
  border-top: none;
  padding-top: 0.75rem;
}

.epic {
  border-top: 1px solid var(--border);
  padding-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.epic:first-child {
  border-top: none;
  padding-top: 0.75rem;
}

.epic-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.epic-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.meta-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: 0.75rem;
}

.task-item {
  border-bottom: 1px solid var(--border);
}

.task-item:last-child {
  border-bottom: 0;
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
  min-width: 2rem;
  min-height: 2rem;
  border-radius: 8px;
  line-height: 1;
}

.task-progress {
  margin-top: 0.45rem;
}

.custom-values {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.45rem;
}

.subtasks {
  margin-left: 2.75rem;
  border-left: 2px solid var(--border);
  padding-left: 0.75rem;
  margin-top: 0.55rem;
}

.subtask-list {
  margin-top: 0.5rem;
}

.subtask {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
}

.subtask-main {
  flex: 1 1 320px;
  min-width: 240px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.subtask-title {
  font-weight: 600;
}

.subtask-meta {
  flex: 0 0 auto;
  display: flex;
  flex-direction: row;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}

.subtask-progress {
  min-width: 160px;
}

.custom-field {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.custom-field-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.custom-field-name {
  font-weight: 600;
}

.custom-field-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
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
  margin-top: 0.5rem;
}

.danger {
  border-color: #b42318;
  color: #b42318;
}
</style>
