<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { GanttChart } from "jordium-gantt-vue3";
import "jordium-gantt-vue3/dist/assets/jordium-gantt-vue3.css";

import { api, ApiError } from "../api";
import type { Epic, GitLabLink, Subtask, Task } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { taskStatusLabelColor } from "../utils/labels";
import {
  buildGanttTooltipDescription,
  formatGitLabReferenceSummary,
  progressFractionToPercent,
  stableGanttId,
  stableGanttNumericId,
  type GanttTimeScale,
} from "../utils/gantt";
import { readGanttPrefs, writeGanttPrefs, type GanttRouteScope } from "../utils/ganttPrefs";
import { mapAllSettledWithConcurrency } from "../utils/promisePool";
import { computeGanttBar, computeGanttWindow, formatDateRange } from "../utils/schedule";

type ScheduledTask = Task & { start_date: string; end_date: string };

type ViaRahGanttNodeKind = "epic" | "task" | "subtask";

type ViaRahGanttTask = import("jordium-gantt-vue3").JordiumGanttTask & {
  vlStableId: string;
  vlKind: ViaRahGanttNodeKind;
  /**
   * The ViaRah task id used for click-through navigation.
   * - For kind=task: the task id
   * - For kind=subtask: the parent task id
   */
  vlTaskId?: string;
  vlEpicId?: string;
  vlSubtaskId?: string;

  vlStatus?: string | null;
  vlStageName?: string | null;
  vlStartDate?: string | null;
  vlEndDate?: string | null;
  vlProgress?: number | null;
};

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const tasks = ref<Task[]>([]);
const epics = ref<Epic[]>([]);
const lastUpdatedAt = ref<string | null>(null);
const loading = ref(false);
const error = ref("");

const ganttTasks = ref<ViaRahGanttTask[]>([]);

const timeScale = ref<GanttTimeScale>("week");
const collapsedByStableId = ref<Record<string, boolean>>({});

const gitLabLinksByTaskId = ref<Record<string, { loading: boolean; error: string; links: GitLabLink[] }>>({});
const subtasksByTaskId = ref<Record<string, { loading: boolean; error: string; subtasks: Subtask[] }>>({});

const scope = computed<GanttRouteScope>(() => (route.path.startsWith("/client/") ? "client" : "internal"));

function queryStringFirst(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === "string") {
    return value[0];
  }
  return "";
}

const useLegacy = computed(() => queryStringFirst(route.query.legacy) === "1");

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function applyPrefsFromLocalStorage() {
  const prefs = readGanttPrefs({
    userId: session.user?.id,
    orgId: context.orgId,
    projectId: context.projectId,
    scope: scope.value,
  });
  timeScale.value = prefs.timeScale;
  collapsedByStableId.value = prefs.collapsedByStableId;
}

function persistPrefs(nextCollapsedByStableId?: Record<string, boolean>) {
  writeGanttPrefs(
    {
      userId: session.user?.id,
      orgId: context.orgId,
      projectId: context.projectId,
      scope: scope.value,
    },
    {
      version: 1,
      timeScale: timeScale.value,
      collapsedByStableId: nextCollapsedByStableId ?? collapsedByStableId.value,
    }
  );
}

watch(() => [session.user?.id, context.orgId, context.projectId, scope.value], () => applyPrefsFromLocalStorage(), {
  immediate: true,
});

watch(
  () => timeScale.value,
  () => persistPrefs(),
  { flush: "post" }
);

async function refresh() {
  error.value = "";
  if (!context.orgId || !context.projectId) {
    tasks.value = [];
    epics.value = [];
    ganttTasks.value = [];
    gitLabLinksByTaskId.value = {};
    subtasksByTaskId.value = {};
    lastUpdatedAt.value = null;
    return;
  }

  loading.value = true;
  try {
    const res = await api.listTasks(context.orgId, context.projectId);
    tasks.value = res.tasks;
    lastUpdatedAt.value = res.last_updated_at ?? null;

    if (scope.value === "internal") {
      const epicRes = await api.listEpics(context.orgId, context.projectId);
      epics.value = epicRes.epics;
    } else {
      epics.value = [];
    }

    rebuildGanttTasks();
    if (scope.value === "internal") {
      void prefetchGitLabLinks();
    }
  } catch (err) {
    tasks.value = [];
    epics.value = [];
    ganttTasks.value = [];
    gitLabLinksByTaskId.value = {};
    subtasksByTaskId.value = {};
    lastUpdatedAt.value = null;
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

function isScheduledTask(task: Task): task is ScheduledTask {
  return typeof task.start_date === "string" && typeof task.end_date === "string";
}

const scheduledTasks = computed(() => tasks.value.filter(isScheduledTask));
const window = computed(() => computeGanttWindow(tasks.value));

function barStyle(task: ScheduledTask): Record<string, string> {
  if (!window.value.windowStart || !window.value.windowEnd) {
    return {};
  }

  const bar = computeGanttBar(task, window.value.windowStart, window.value.windowEnd);
  return {
    left: `${bar.leftPct}%`,
    width: `${bar.widthPct}%`,
  };
}

function flattenNodes(nodes: ViaRahGanttTask[]): ViaRahGanttTask[] {
  const out: ViaRahGanttTask[] = [];
  const stack = [...nodes];
  while (stack.length) {
    const current = stack.pop();
    if (!current) {
      continue;
    }
    out.push(current);
    if (Array.isArray(current.children) && current.children.length) {
      stack.push(...(current.children as ViaRahGanttTask[]));
    }
  }
  return out;
}

function extractCollapsedMap(nodes: ViaRahGanttTask[]): Record<string, boolean> {
  const map: Record<string, boolean> = {};
  for (const node of flattenNodes(nodes)) {
    if (node.vlKind !== "epic" && node.vlKind !== "task") {
      continue;
    }
    if (typeof node.collapsed !== "boolean") {
      continue;
    }
    map[node.vlStableId] = node.collapsed;
  }
  return map;
}

function sameCollapsedMap(a: Record<string, boolean>, b: Record<string, boolean>): boolean {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  for (const key of aKeys) {
    if (a[key] !== b[key]) {
      return false;
    }
  }
  return true;
}

function gitLabLinksSummaryForTask(taskId: string): string | null {
  if (scope.value !== "internal") {
    return null;
  }

  const state = gitLabLinksByTaskId.value[taskId];
  if (state?.loading) {
    return "(loading…)";
  }
  if (state?.error) {
    return state.error;
  }
  if (state?.links) {
    return formatGitLabReferenceSummary(state.links);
  }
  return "(loading…)";
}

function updateDescriptionsForTask(taskId: string) {
  const nodes = flattenNodes(ganttTasks.value).filter((n) => n.vlTaskId === taskId);
  if (!nodes.length) {
    return;
  }

  const gitLabSummary = gitLabLinksSummaryForTask(taskId);
  for (const node of nodes) {
    node.description = buildGanttTooltipDescription({
      title: node.name,
      status: node.vlStatus ?? null,
      stageName: node.vlStageName ?? null,
      startDate: node.vlStartDate ?? null,
      endDate: node.vlEndDate ?? null,
      progress: node.vlProgress ?? null,
      gitLabLinksSummary: gitLabSummary,
    });
  }
}

async function loadSubtasks(taskId: string) {
  if (scope.value !== "internal") {
    return;
  }
  if (!context.orgId) {
    return;
  }
  if (subtasksByTaskId.value[taskId]) {
    return;
  }

  subtasksByTaskId.value = {
    ...subtasksByTaskId.value,
    [taskId]: { loading: true, error: "", subtasks: [] },
  };

  try {
    const res = await api.listSubtasks(context.orgId, taskId);
    subtasksByTaskId.value = {
      ...subtasksByTaskId.value,
      [taskId]: { loading: false, error: "", subtasks: res.subtasks },
    };

    const parent = flattenNodes(ganttTasks.value).find((n) => n.vlKind === "task" && n.vlTaskId === taskId);
    const rawTask = tasks.value.find((t) => t.id === taskId);
    if (parent && rawTask) {
      parent.children = res.subtasks.map((subtask) => buildSubtaskNode(rawTask, subtask));
      updateDescriptionsForTask(taskId);
    }
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

async function fetchGitLabLinks(taskId: string) {
  if (scope.value !== "internal") {
    return;
  }
  if (!context.orgId) {
    return;
  }

  const prior = gitLabLinksByTaskId.value[taskId];
  if (prior) {
    return;
  }

  gitLabLinksByTaskId.value = {
    ...gitLabLinksByTaskId.value,
    [taskId]: { loading: true, error: "", links: [] },
  };
  updateDescriptionsForTask(taskId);

  try {
    const res = await api.listTaskGitLabLinks(context.orgId, taskId);
    gitLabLinksByTaskId.value = {
      ...gitLabLinksByTaskId.value,
      [taskId]: { loading: false, error: "", links: res.links },
    };
    updateDescriptionsForTask(taskId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    const forbidden = err instanceof ApiError && err.status === 403;
    gitLabLinksByTaskId.value = {
      ...gitLabLinksByTaskId.value,
      [taskId]: {
        loading: false,
        error: forbidden ? "not permitted" : err instanceof Error ? err.message : String(err),
        links: [],
      },
    };
    updateDescriptionsForTask(taskId);
  }
}

async function prefetchGitLabLinks() {
  if (scope.value !== "internal") {
    return;
  }

  const taskIds = tasks.value.map((t) => t.id).filter(Boolean);
  const missing = taskIds.filter((taskId) => !gitLabLinksByTaskId.value[taskId]);
  if (!missing.length) {
    return;
  }

  await mapAllSettledWithConcurrency(missing, 4, async (taskId) => {
    await fetchGitLabLinks(taskId);
  });
}

function buildTaskNode(task: Task): ViaRahGanttTask {
  const stableId = stableGanttId("task", task.id);
  const collapsedDefault = scope.value === "internal";
  const collapsed = collapsedByStableId.value[stableId] ?? collapsedDefault;

  const gitLabSummary = gitLabLinksSummaryForTask(task.id);

  const description = buildGanttTooltipDescription({
    title: task.title,
    status: task.status,
    stageName: task.workflow_stage?.name ?? null,
    startDate: task.start_date,
    endDate: task.end_date,
    progress: task.progress,
    gitLabLinksSummary: gitLabSummary,
  });

  const children =
    scope.value === "internal" && subtasksByTaskId.value[task.id]?.subtasks
      ? subtasksByTaskId.value[task.id]!.subtasks.map((subtask) => buildSubtaskNode(task, subtask))
      : [];

  return {
    id: stableGanttNumericId(stableId),
    name: task.title,
    startDate: task.start_date ?? undefined,
    endDate: task.end_date ?? undefined,
    progress: progressFractionToPercent(task.progress),
    collapsed: scope.value === "internal" ? collapsed : undefined,
    isParent: scope.value === "internal",
    children,
    description,
    vlStableId: stableId,
    vlKind: "task",
    vlTaskId: task.id,
    vlStatus: task.status,
    vlStageName: task.workflow_stage?.name ?? null,
    vlStartDate: task.start_date,
    vlEndDate: task.end_date,
    vlProgress: task.progress,
  };
}

function buildSubtaskNode(parentTask: Task, subtask: Subtask): ViaRahGanttTask {
  const stableId = stableGanttId("subtask", subtask.id);
  const gitLabSummary = gitLabLinksSummaryForTask(parentTask.id);

  return {
    id: stableGanttNumericId(stableId),
    name: subtask.title,
    startDate: subtask.start_date ?? undefined,
    endDate: subtask.end_date ?? undefined,
    progress: progressFractionToPercent(subtask.progress),
    description: buildGanttTooltipDescription({
      title: subtask.title,
      status: subtask.status,
      stageName: null,
      startDate: subtask.start_date,
      endDate: subtask.end_date,
      progress: subtask.progress,
      gitLabLinksSummary: gitLabSummary,
    }),
    vlStableId: stableId,
    vlKind: "subtask",
    vlTaskId: parentTask.id,
    vlSubtaskId: subtask.id,
    vlStatus: subtask.status,
    vlStageName: null,
    vlStartDate: subtask.start_date,
    vlEndDate: subtask.end_date,
    vlProgress: subtask.progress,
  };
}

function buildEpicNode(epicId: string, title: string, children: ViaRahGanttTask[]): ViaRahGanttTask {
  const stableId = stableGanttId("epic", epicId || "none");
  const collapsed = collapsedByStableId.value[stableId] ?? false;

  const scheduledChildren = children.filter((c) => typeof c.startDate === "string" && typeof c.endDate === "string");
  const startDate = scheduledChildren.map((c) => c.startDate!).sort()[0];
  const endDate = [...scheduledChildren]
    .map((c) => c.endDate!)
    .sort()
    .slice(-1)[0];

  const epic = epics.value.find((e) => e.id === epicId);
  const progress = epic ? progressFractionToPercent(epic.progress) : undefined;

  const description = buildGanttTooltipDescription({
    title,
    status: epic?.status ?? null,
    stageName: null,
    startDate: startDate ?? null,
    endDate: endDate ?? null,
    progress: epic?.progress ?? null,
  });

  return {
    id: stableGanttNumericId(stableId),
    name: title,
    startDate,
    endDate,
    progress,
    collapsed,
    isParent: true,
    children,
    description,
    vlStableId: stableId,
    vlKind: "epic",
    vlEpicId: epicId,
    vlStatus: epic?.status ?? null,
    vlStageName: null,
    vlStartDate: startDate ?? null,
    vlEndDate: endDate ?? null,
    vlProgress: epic?.progress ?? null,
  };
}

function rebuildGanttTasks() {
  if (!context.orgId || !context.projectId) {
    ganttTasks.value = [];
    return;
  }

  if (scope.value === "client") {
    ganttTasks.value = tasks.value.map((task) => buildTaskNode(task));
    return;
  }

  const epicsById = new Map(epics.value.map((e) => [e.id, e]));
  const tasksByEpicId = new Map<string, Task[]>();
  for (const task of tasks.value) {
    const key = task.epic_id || "none";
    const group = tasksByEpicId.get(key) ?? [];
    group.push(task);
    tasksByEpicId.set(key, group);
  }

  const epicRows: ViaRahGanttTask[] = [];

  for (const epic of epics.value) {
    const groupTasks = tasksByEpicId.get(epic.id) ?? [];
    if (!groupTasks.length) {
      continue;
    }
    epicRows.push(buildEpicNode(epic.id, epic.title, groupTasks.map((t) => buildTaskNode(t))));
    tasksByEpicId.delete(epic.id);
  }

  for (const [epicId, groupTasks] of tasksByEpicId) {
    const title = epicId === "none" ? "No epic" : epicsById.get(epicId)?.title ?? "Unknown epic";
    epicRows.push(buildEpicNode(epicId, title, groupTasks.map((t) => buildTaskNode(t))));
  }

  ganttTasks.value = epicRows;
}

watch(
  () => ganttTasks.value,
  () => {
    const nextCollapsed = extractCollapsedMap(ganttTasks.value);
    if (!sameCollapsedMap(nextCollapsed, collapsedByStableId.value)) {
      collapsedByStableId.value = nextCollapsed;
      persistPrefs(nextCollapsed);
    }

    if (scope.value !== "internal") {
      return;
    }

    const expanded = flattenNodes(ganttTasks.value).filter((n) => n.vlKind === "task" && n.collapsed === false);
    for (const node of expanded) {
      const taskId = node.vlTaskId;
      if (!taskId) {
        continue;
      }
      if (!subtasksByTaskId.value[taskId]) {
        void loadSubtasks(taskId);
      }
    }
  },
  { deep: true }
);

const unscheduledItems = computed(() => {
  const items: Array<{
    kind: "task" | "subtask";
    id: string;
    taskId: string;
    title: string;
    status: string;
    startDate: string | null;
    endDate: string | null;
  }> = [];

  for (const task of tasks.value) {
    if (isScheduledTask(task)) {
      continue;
    }
    items.push({
      kind: "task",
      id: task.id,
      taskId: task.id,
      title: task.title,
      status: task.status,
      startDate: task.start_date,
      endDate: task.end_date,
    });

    if (scope.value === "internal") {
      const subtasks = subtasksByTaskId.value[task.id]?.subtasks ?? [];
      for (const subtask of subtasks) {
        if (typeof subtask.start_date === "string" && typeof subtask.end_date === "string") {
          continue;
        }
        items.push({
          kind: "subtask",
          id: subtask.id,
          taskId: task.id,
          title: `${task.title} → ${subtask.title}`,
          status: subtask.status,
          startDate: subtask.start_date,
          endDate: subtask.end_date,
        });
      }
    }
  }

  return items;
});

function taskDetailHref(taskId: string): string {
  return scope.value === "client" ? `/client/tasks/${taskId}` : `/work/${taskId}`;
}

async function handleGanttTaskClick(node: unknown) {
  const task = node as ViaRahGanttTask;
  if (task.vlKind === "epic") {
    return;
  }
  if (!task.vlTaskId) {
    return;
  }
  await router.push(taskDetailHref(task.vlTaskId));
}

const parentNodes = computed(() => flattenNodes(ganttTasks.value).filter((n) => n.vlKind === "epic" || n.vlKind === "task"));
const allExpanded = computed(() => parentNodes.value.length > 0 && parentNodes.value.every((n) => n.collapsed === false));

function toggleExpandAll() {
  const nextCollapsed = allExpanded.value;
  for (const node of parentNodes.value) {
    node.collapsed = nextCollapsed;
  }
}
</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <pf-title h="1" size="2xl">Gantt</pf-title>
        <VlLabel color="blue">Last updated: {{ formatTimestamp(lastUpdatedAt) }}</VlLabel>
      </div>
    </pf-card-title>

    <pf-card-body>
      <div v-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading schedule gantt" />
      </div>
      <pf-alert v-else-if="error" inline variant="danger" :title="error" />
      <pf-empty-state v-else-if="!context.orgId || !context.projectId">
        <pf-empty-state-header title="Select an org and project" heading-level="h2" />
        <pf-empty-state-body>Select an org and project to view a schedule.</pf-empty-state-body>
      </pf-empty-state>
      <pf-empty-state v-else-if="tasks.length === 0">
        <pf-empty-state-header title="No tasks yet" heading-level="h2" />
        <pf-empty-state-body>No tasks were found for the selected project.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else>
        <VlLabel v-if="window.windowStart && window.windowEnd" color="blue">
          Window: {{ window.windowStart }} → {{ window.windowEnd }}
        </VlLabel>

        <div v-if="useLegacy">
          <div v-if="scheduledTasks.length" class="gantt legacy">
            <div v-for="task in scheduledTasks" :key="task.id" class="gantt-row">
              <div class="label">
                <div class="title">{{ task.title }}</div>
                <div class="meta">{{ formatDateRange(task.start_date, task.end_date) }}</div>
              </div>
              <div class="track" :title="formatDateRange(task.start_date, task.end_date)">
                <div class="bar" :style="barStyle(task)" />
              </div>
            </div>
          </div>
          <pf-empty-state v-else>
            <pf-empty-state-header title="No scheduled tasks" heading-level="h2" />
            <pf-empty-state-body>Only unscheduled tasks were found for the selected project.</pf-empty-state-body>
          </pf-empty-state>
        </div>

        <div v-else-if="ganttTasks.length" class="gantt-v2">
          <pf-toolbar class="toolbar">
            <pf-toolbar-content>
              <pf-toolbar-group>
                <pf-toolbar-item>
                  <pf-form-group label="Scale" field-id="gantt-scale" class="filter-field">
                    <pf-form-select id="gantt-scale" v-model="timeScale">
                      <pf-form-select-option value="day">Day</pf-form-select-option>
                      <pf-form-select-option value="week">Week</pf-form-select-option>
                      <pf-form-select-option value="month">Month</pf-form-select-option>
                    </pf-form-select>
                  </pf-form-group>
                </pf-toolbar-item>
                <pf-toolbar-item v-if="scope === 'internal'">
                  <pf-button variant="secondary" @click="toggleExpandAll">
                    {{ allExpanded ? "Collapse all" : "Expand all" }}
                  </pf-button>
                </pf-toolbar-item>
                <pf-toolbar-item>
                  <pf-button variant="secondary" @click="refresh">Refresh</pf-button>
                </pf-toolbar-item>
              </pf-toolbar-group>
            </pf-toolbar-content>
          </pf-toolbar>

          <div class="chart-container">
            <GanttChart
              :tasks="ganttTasks"
              locale="en-US"
              theme="light"
              :time-scale="timeScale"
              :show-toolbar="false"
              :use-default-drawer="false"
              :use-default-milestone-dialog="false"
              :allow-drag-and-resize="false"
              :enable-task-row-move="false"
              :enable-task-list-context-menu="false"
              :enable-task-bar-context-menu="false"
              :enable-taskbar-tooltip="true"
              @task-click="handleGanttTaskClick"
            />
          </div>
        </div>

        <div v-if="unscheduledItems.length" class="unscheduled">
          <pf-title h="2" size="lg">Unscheduled</pf-title>
          <pf-data-list compact aria-label="Unscheduled items" class="unscheduled-list">
            <pf-data-list-item v-for="item in unscheduledItems" :key="`${item.kind}:${item.id}`">
              <pf-data-list-cell>
                <RouterLink class="title" :to="taskDetailHref(item.taskId)">{{ item.title }}</RouterLink>
                <div class="meta">
                  <VlLabel :color="taskStatusLabelColor(item.status)">{{ item.status }}</VlLabel>
                  <span class="muted">{{ formatDateRange(item.startDate, item.endDate) }}</span>
                </div>
              </pf-data-list-cell>
            </pf-data-list-item>
          </pf-data-list>
        </div>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.5rem 0;
}

.gantt.legacy {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.gantt-row {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 0.75rem;
  align-items: center;
}

.label {
  min-width: 0;
}

.title {
  font-weight: 600;
}

.meta {
  margin-top: 0.25rem;
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}

.track {
  position: relative;
  height: 18px;
  background: #eef2ff;
  border: 1px solid var(--border);
  border-radius: 999px;
  overflow: hidden;
}

.bar {
  position: absolute;
  top: 0;
  bottom: 0;
  background: var(--accent);
  border-radius: 999px;
  min-width: 6px;
}

.gantt-v2 {
  margin-top: 1rem;
}

.toolbar {
  margin-bottom: 0.75rem;
}

.filter-field {
  margin-bottom: 0;
}

.chart-container {
  height: 70vh;
  min-height: 420px;
}

.unscheduled {
  margin-top: 1.25rem;
}

.unscheduled-list {
  margin-top: 0.5rem;
}

@media (max-width: 720px) {
  .gantt-row {
    grid-template-columns: 1fr;
  }
}
</style>
