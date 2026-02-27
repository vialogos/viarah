<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Epic, OrgMembershipWithUser, Task, WorkflowStageMeta } from "../api/types";
import { isClientOnlyMemberships } from "../routerGuards";
import GitLabLinksCard from "../components/GitLabLinksCard.vue";
import VlLabel from "../components/VlLabel.vue";
import VlTimelineRoadmap from "../components/VlTimelineRoadmap.vue";
import { useContextStore } from "../stores/context";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import { formatPercent, progressLabelColor } from "../utils/format";
import { taskStatusLabelColor, workItemStatusLabel, type VlLabelColor } from "../utils/labels";
import { formatDateRange, sortTasksForTimeline } from "../utils/schedule";
import {
  buildTimelineGroups,
  buildTimelineItems,
  splitTasksBySchedule,
  type RoadmapGroupBy,
  type RoadmapScalePreset,
} from "../utils/timelineRoadmap";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const realtime = useRealtimeStore();

const tasks = ref<Task[]>([]);
const epics = ref<Epic[]>([]);
const epicsLoading = ref(false);
const epicsError = ref("");
const orgMembers = ref<OrgMembershipWithUser[]>([]);
const orgMembersLoading = ref(false);
const orgMembersError = ref("");
const loading = ref(false);
const error = ref("");

const timelineRef = ref<InstanceType<typeof VlTimelineRoadmap> | null>(null);

const STATUS_OPTIONS = [
  { value: "backlog", label: "Backlog" },
  { value: "in_progress", label: "In progress" },
  { value: "qa", label: "QA" },
  { value: "done", label: "Done" },
] as const;

const INTERNAL_ROLES = new Set(["admin", "pm", "member"]);

function queryParamFirst(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === "string") {
    return value[0];
  }
  return "";
}

const legacyListView = computed(() => queryParamFirst(route.query.view) === "list");

const isClientOnly = computed(() => isClientOnlyMemberships(session.memberships));
const currentRole = computed(() => session.effectiveOrgRole(context.orgId));

const canManageGitLabIntegration = computed(() => currentRole.value === "admin" || currentRole.value === "pm");
const canManageGitLabLinks = computed(
  () =>
    INTERNAL_ROLES.has(currentRole.value) &&
    (canManageGitLabIntegration.value || currentRole.value === "member")
);
const canShowGitLabLinks = computed(() => !isClientOnly.value && INTERNAL_ROLES.has(currentRole.value));

const scalePreset = ref<RoadmapScalePreset>("week");
const groupBy = ref<RoadmapGroupBy>("status");
const search = ref("");
const debouncedSearch = ref("");
const selectedStatuses = ref<string[]>(STATUS_OPTIONS.map((option) => option.value));
const selectedTaskId = ref<string | null>(null);
const hoveredTaskId = ref<string | null>(null);

const scheduleStartDraft = ref("");
const scheduleEndDraft = ref("");
const scheduleSaving = ref(false);
const scheduleError = ref("");
const scheduleModalOpen = ref(false);

const timelineFullscreen = ref(false);

function setTimelineFullscreen(next: boolean) {
  timelineFullscreen.value = next;
  document.body.style.overflow = next ? "hidden" : "";
}

function handleFullscreenKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    setTimelineFullscreen(false);
  }
}

watch(
  timelineFullscreen,
  (next) => {
    window.removeEventListener("keydown", handleFullscreenKeydown);
    if (next) {
      window.addEventListener("keydown", handleFullscreenKeydown);
    }
  },
  { immediate: true }
);

watch(
  timelineFullscreen,
  async (next) => {
    if (!next) {
      await nextTick();
      document.body.style.overflow = "";
      return;
    }
    await nextTick();
    window.dispatchEvent(new Event("resize"));
    window.setTimeout(() => timelineRef.value?.fit(), 0);
  },
  { flush: "post" }
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleFullscreenKeydown);
  document.body.style.overflow = "";
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  if (!context.orgId || !context.projectId) {
    tasks.value = [];
    epics.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listTasks(context.orgId, context.projectId);
    tasks.value = res.tasks;
    if (selectedTaskId.value && !tasks.value.some((task) => task.id === selectedTaskId.value)) {
      selectedTaskId.value = null;
    }
    if (!legacyListView.value) {
      window.setTimeout(() => timelineRef.value?.fit(), 0);
    }
  } catch (err) {
    tasks.value = [];
    epics.value = [];
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

let refreshTimeoutId: number | null = null;
function scheduleRefreshTasks() {
  if (refreshTimeoutId != null) {
    return;
  }
  refreshTimeoutId = window.setTimeout(() => {
    refreshTimeoutId = null;
    if (loading.value) {
      return;
    }
    void refresh();
  }, 250);
}

let refreshEpicsTimeoutId: number | null = null;
function scheduleRefreshEpics() {
  if (refreshEpicsTimeoutId != null) {
    return;
  }
  refreshEpicsTimeoutId = window.setTimeout(() => {
    refreshEpicsTimeoutId = null;
    if (epicsLoading.value) {
      return;
    }
    void refreshEpics();
  }, 250);
}

let refreshOrgMembersTimeoutId: number | null = null;
function scheduleRefreshOrgMembers() {
  if (refreshOrgMembersTimeoutId != null) {
    return;
  }
  refreshOrgMembersTimeoutId = window.setTimeout(() => {
    refreshOrgMembersTimeoutId = null;
    if (orgMembersLoading.value) {
      return;
    }
    void refreshOrgMembers();
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

  if (auditEventType.startsWith("task.") || auditEventType.startsWith("subtask.")) {
    scheduleRefreshTasks();
    return;
  }

  if (auditEventType.startsWith("epic.")) {
    scheduleRefreshEpics();
    return;
  }

  if (auditEventType.startsWith("org_membership.")) {
    scheduleRefreshOrgMembers();
  }
});

onBeforeUnmount(() => {
  unsubscribeRealtime();
  if (refreshTimeoutId != null) {
    window.clearTimeout(refreshTimeoutId);
    refreshTimeoutId = null;
  }
  if (refreshEpicsTimeoutId != null) {
    window.clearTimeout(refreshEpicsTimeoutId);
    refreshEpicsTimeoutId = null;
  }
  if (refreshOrgMembersTimeoutId != null) {
    window.clearTimeout(refreshOrgMembersTimeoutId);
    refreshOrgMembersTimeoutId = null;
  }
});

let searchDebounceHandle: number | null = null;
watch(
  search,
  (next) => {
    if (searchDebounceHandle != null) {
      window.clearTimeout(searchDebounceHandle);
    }

    const value = next.trim();
    if (!value) {
      debouncedSearch.value = "";
      return;
    }

    searchDebounceHandle = window.setTimeout(() => {
      debouncedSearch.value = value;
    }, 175);
  },
  { immediate: true }
);

watch(
  isClientOnly,
  (clientOnly) => {
    if (clientOnly && groupBy.value === "epic") {
      groupBy.value = "status";
    }
  },
  { immediate: true }
);

function statusEnabled(status: string): boolean {
  return selectedStatuses.value.includes(status);
}

function setStatusEnabled(status: string, enabled: boolean): void {
  if (enabled) {
    if (!selectedStatuses.value.includes(status)) {
      selectedStatuses.value = [...selectedStatuses.value, status];
    }
    return;
  }
  selectedStatuses.value = selectedStatuses.value.filter((value) => value !== status);
}

const filteredTasks = computed(() => {
  const searchValue = debouncedSearch.value.trim().toLowerCase();
  const allowedStatuses = new Set(selectedStatuses.value);
  return tasks.value.filter((task) => {
    if (allowedStatuses.size > 0 && !allowedStatuses.has(task.status)) {
      return false;
    }
    if (searchValue) {
      return task.title.toLowerCase().includes(searchValue);
    }
    return true;
  });
});

const sortedTasks = computed(() => sortTasksForTimeline(filteredTasks.value));

const split = computed(() => splitTasksBySchedule(filteredTasks.value));
const scheduledTasks = computed(() => split.value.scheduled);
const unscheduledTasks = computed(() => split.value.unscheduled);

type OrgMemberByUserId = Record<string, OrgMembershipWithUser>;
const orgMemberByUserId = computed<OrgMemberByUserId>(() => {
  const map: OrgMemberByUserId = {};
  for (const membership of orgMembers.value) {
    map[membership.user.id] = membership;
  }
  return map;
});

const epicTitleById = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const epic of epics.value) {
    map[epic.id] = epic.title;
  }
  return map;
});

const activeEpicLabel = computed(() => {
  const task = activeTask.value;
  if (!task) {
    return "—";
  }
  const title = epicTitleById.value[task.epic_id] ?? "";
  if (title) {
    return title;
  }
  if (epicsLoading.value) {
    return "Loading…";
  }
  return "—";
});

const effectiveGroupBy = computed<RoadmapGroupBy>(() => {
  if (isClientOnly.value && groupBy.value === "epic") {
    return "status";
  }
  return groupBy.value;
});

const timelineGroups = computed(() =>
  buildTimelineGroups(scheduledTasks.value, effectiveGroupBy.value, { epicTitlesById: epicTitleById.value })
);
const timelineItems = computed(() => buildTimelineItems(scheduledTasks.value, effectiveGroupBy.value));

const selectedTask = computed(() => tasks.value.find((task) => task.id === selectedTaskId.value) ?? null);
const hoveredTask = computed(() => tasks.value.find((task) => task.id === hoveredTaskId.value) ?? null);
const activeTask = computed(() => selectedTask.value ?? hoveredTask.value);

const canEditSchedule = computed(() => !isClientOnly.value && INTERNAL_ROLES.has(currentRole.value));

watch(
  activeTask,
  (next) => {
    scheduleError.value = "";
    scheduleStartDraft.value = next?.start_date ?? "";
    scheduleEndDraft.value = next?.end_date ?? "";
  },
  { immediate: true }
);

async function saveSchedule() {
  scheduleError.value = "";
  if (!context.orgId) {
    scheduleError.value = "Select an org to continue.";
    return;
  }
  if (!context.projectId) {
    scheduleError.value = "Select a project to continue.";
    return;
  }
  const task = activeTask.value;
  if (!task) {
    return;
  }
  if (!canEditSchedule.value) {
    scheduleError.value = "Not permitted.";
    return;
  }

  const startDate = scheduleStartDraft.value.trim();
  const endDate = scheduleEndDraft.value.trim();
  if (startDate && endDate && startDate > endDate) {
    scheduleError.value = "Start date must be on or before end date.";
    return;
  }

  scheduleSaving.value = true;
  try {
    await api.patchTask(context.orgId, task.id, {
      start_date: startDate || null,
      end_date: endDate || null,
    });
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    scheduleError.value = err instanceof Error ? err.message : String(err);
  } finally {
    scheduleSaving.value = false;
  }
}

async function clearSchedule() {
  scheduleStartDraft.value = "";
  scheduleEndDraft.value = "";
  await saveSchedule();
}

function openScheduleModal(task: Task) {
  selectedTaskId.value = task.id;
  scheduleModalOpen.value = true;
}

async function saveScheduleFromModal() {
  await saveSchedule();
  if (!scheduleError.value) {
    scheduleModalOpen.value = false;
  }
}

function stageLabelColor(stage: WorkflowStageMeta | null): VlLabelColor {
  if (!stage) {
    return "blue";
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

function stageLabel(stage: WorkflowStageMeta | null): string {
  if (!stage) {
    return "(unassigned)";
  }
  return stage.name || "(unknown stage)";
}

const assigneeDisplay = computed(() => {
  const task = activeTask.value;
  if (!task) {
    return "—";
  }
  if (!task.assignee_user_id) {
    return "Unassigned";
  }
  if (task.assignee_user?.id && task.assignee_user.id === session.user?.id) {
    return session.user.display_name || session.user.email || "You";
  }
  if (task.assignee_user) {
    return task.assignee_user.display_name || task.assignee_user.email || task.assignee_user.id;
  }
  if (task.assignee_user_id === session.user?.id) {
    return session.user.display_name || session.user.email || "You";
  }
  const member = orgMemberByUserId.value[task.assignee_user_id];
  if (!member) {
    return task.assignee_user_id;
  }
  return member.user.display_name || member.user.email || member.user.id;
});

async function refreshEpics() {
  epicsError.value = "";

  if (
    !context.orgId ||
    !context.projectId ||
    isClientOnly.value
  ) {
    epics.value = [];
    return;
  }

  epicsLoading.value = true;
  try {
    const res = await api.listEpics(context.orgId, context.projectId);
    epics.value = res.epics;
  } catch (err) {
    epics.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      epicsError.value = "Epics are not available for your role; falling back to status grouping.";
      groupBy.value = "status";
      return;
    }
    epicsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    epicsLoading.value = false;
  }
}

watch(() => [context.orgId, context.projectId, effectiveGroupBy.value, isClientOnly.value], () => void refreshEpics(), {
  immediate: true,
});

async function refreshOrgMembers() {
  orgMembersError.value = "";
  if (!context.orgId || isClientOnly.value) {
    orgMembers.value = [];
    return;
  }

  orgMembersLoading.value = true;
  try {
    const res = await api.listOrgMemberships(context.orgId);
    orgMembers.value = res.memberships;
  } catch (err) {
    orgMembers.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      orgMembersError.value = "Not permitted.";
      return;
    }
    orgMembersError.value = err instanceof Error ? err.message : String(err);
  } finally {
    orgMembersLoading.value = false;
  }
}

watch(
  () => selectedTask.value?.assignee_user_id,
  (nextAssignee) => {
    if (!nextAssignee || orgMembers.value.length || orgMembersLoading.value) {
      return;
    }
    void refreshOrgMembers();
  }
);

function taskDetailPath(taskId: string): string {
  return isClientOnly.value ? `/client/tasks/${taskId}` : `/work/${taskId}`;
}

async function openTask(taskId: string) {
  await router.push({ path: taskDetailPath(taskId) });
}

function fitTimeline() {
  timelineRef.value?.fit();
}

function zoomInTimeline() {
  timelineRef.value?.zoomIn();
}

function zoomOutTimeline() {
  timelineRef.value?.zoomOut();
}
</script>

<template>
  <Teleport to="body" :disabled="!timelineFullscreen">
    <div :class="{ 'fullscreen-shell': timelineFullscreen }">
      <pf-card :class="{ 'fullscreen-card': timelineFullscreen }">
        <pf-card-title>
          <div class="header">
            <div>
              <pf-title h="1" size="2xl">Timeline</pf-title>
              <pf-content>
                <p class="muted">Interactive roadmap view (Day/Week/Month scale, grouping, filters, details).</p>
              </pf-content>
            </div>
            <div class="header-actions">
              <pf-button type="button" variant="secondary" small @click="setTimelineFullscreen(!timelineFullscreen)">
                {{ timelineFullscreen ? "Exit full screen" : "Full screen" }}
              </pf-button>
            </div>
          </div>
        </pf-card-title>

        <pf-card-body>
          <div v-if="loading" class="loading-row">
            <pf-spinner size="md" aria-label="Loading timeline" />
          </div>

          <pf-alert v-else-if="error" inline variant="danger" :title="error" />

          <pf-empty-state v-else-if="!context.orgId || !context.projectId">
            <pf-empty-state-header title="Timeline is project-scoped" heading-level="h2" />
            <pf-empty-state-body>Select a single org and project to view a schedule.</pf-empty-state-body>
          </pf-empty-state>

          <pf-empty-state v-else-if="tasks.length === 0">
            <pf-empty-state-header title="No tasks yet" heading-level="h2" />
            <pf-empty-state-body>No tasks were found for the selected project.</pf-empty-state-body>
          </pf-empty-state>

          <div v-else>
            <pf-toolbar class="toolbar">
              <pf-toolbar-content>
                <pf-toolbar-group>
                  <pf-toolbar-item>
                    <pf-form-group label="Scale" field-id="timeline-scale" class="filter-field">
                      <pf-form-select id="timeline-scale" v-model="scalePreset">
                        <pf-form-select-option value="day">Day</pf-form-select-option>
                        <pf-form-select-option value="week">Week</pf-form-select-option>
                        <pf-form-select-option value="month">Month</pf-form-select-option>
                      </pf-form-select>
                    </pf-form-group>
                  </pf-toolbar-item>

                  <pf-toolbar-item>
                    <pf-form-group label="Group by" field-id="timeline-group-by" class="filter-field">
                      <pf-form-select id="timeline-group-by" v-model="groupBy">
                        <pf-form-select-option value="status">Status</pf-form-select-option>
                        <pf-form-select-option v-if="!isClientOnly" value="epic">Epic</pf-form-select-option>
                      </pf-form-select>
                    </pf-form-group>
                  </pf-toolbar-item>

                  <pf-toolbar-item>
                    <pf-form-group label="Search" field-id="timeline-search" class="filter-field">
                      <pf-search-input
                        id="timeline-search"
                        v-model="search"
                        placeholder="Filter by title…"
                        @clear="search = ''"
                      />
                    </pf-form-group>
                  </pf-toolbar-item>
                </pf-toolbar-group>

                <pf-toolbar-group>
                  <pf-toolbar-item>
                    <pf-form-group label="Status filters">
                      <div class="status-filters">
                        <pf-checkbox
                          v-for="option in STATUS_OPTIONS"
                          :id="`timeline-status-filter-${option.value}`"
                          :key="option.value"
                          :label="option.label"
                          :model-value="statusEnabled(option.value)"
                          @update:model-value="setStatusEnabled(option.value, Boolean($event))"
                        />
                      </div>
                    </pf-form-group>
                  </pf-toolbar-item>
                </pf-toolbar-group>

                <pf-toolbar-group variant="action-group-plain" align="end">
                  <pf-toolbar-item>
                    <pf-button
                      type="button"
                      variant="secondary"
                      small
                      :disabled="scheduledTasks.length === 0"
                      @click="fitTimeline"
                    >
                      Fit
                    </pf-button>
                  </pf-toolbar-item>
                  <pf-toolbar-item>
                    <pf-button
                      type="button"
                      variant="secondary"
                      small
                      :disabled="scheduledTasks.length === 0"
                      @click="zoomOutTimeline"
                    >
                      Zoom out
                    </pf-button>
                  </pf-toolbar-item>
                  <pf-toolbar-item>
                    <pf-button
                      type="button"
                      variant="secondary"
                      small
                      :disabled="scheduledTasks.length === 0"
                      @click="zoomInTimeline"
                    >
                      Zoom in
                    </pf-button>
                  </pf-toolbar-item>
                </pf-toolbar-group>
              </pf-toolbar-content>
            </pf-toolbar>

            <pf-alert v-if="legacyListView" inline variant="warning" title="Legacy list mode enabled">
              <p class="muted">This view is enabled via <code>?view=list</code> for one release-cycle rollback safety.</p>
            </pf-alert>

            <pf-alert v-if="epicsError" inline variant="warning" :title="epicsError" />
            <div v-if="epicsLoading" class="inline-loading">
              <pf-spinner size="sm" aria-label="Loading epics" />
              <span class="muted">Loading epics…</span>
            </div>

            <pf-empty-state v-if="sortedTasks.length === 0">
              <pf-empty-state-header title="No tasks match the current filters" heading-level="h2" />
              <pf-empty-state-body>Adjust status filters or search to see tasks.</pf-empty-state-body>
            </pf-empty-state>

            <div v-else-if="legacyListView">
              <pf-data-list compact aria-label="Timeline tasks (legacy list)">
                <pf-data-list-item v-for="task in sortedTasks" :key="task.id">
                  <pf-data-list-cell>
                    <div class="title">{{ task.title }}</div>
                    <div class="meta">
                      <VlLabel :color="taskStatusLabelColor(task.status)">{{ workItemStatusLabel(task.status) }}</VlLabel>
                      <span class="muted">{{ formatDateRange(task.start_date, task.end_date) }}</span>
                    </div>
                  </pf-data-list-cell>
                  <pf-data-list-cell align-right>
                    <pf-button variant="link" :to="taskDetailPath(task.id)">Open</pf-button>
                  </pf-data-list-cell>
                </pf-data-list-item>
              </pf-data-list>
            </div>

            <div v-else class="layout">
              <div class="roadmap">
                <pf-empty-state v-if="scheduledTasks.length === 0" variant="small">
                  <pf-empty-state-header title="No scheduled tasks" heading-level="h2" />
                  <pf-empty-state-body>
                    Tasks with both start and end dates will appear on the roadmap. Unscheduled tasks are listed below.
                  </pf-empty-state-body>
                </pf-empty-state>

                <VlTimelineRoadmap
                  v-else
                  ref="timelineRef"
                  :items="timelineItems"
                  :groups="timelineGroups"
                  :time-axis-scale="scalePreset"
                  @hover="hoveredTaskId = $event"
                  @select="selectedTaskId = $event"
                  @open="openTask($event)"
                />

                <pf-helper-text class="note">
                  <pf-helper-text-item>Tip: click to select; double-click to open.</pf-helper-text-item>
                </pf-helper-text>

                <div v-if="unscheduledTasks.length" class="unscheduled">
                  <pf-title h="2" size="lg">Unscheduled ({{ unscheduledTasks.length }})</pf-title>
                  <pf-content>
                    <p class="muted">Tasks missing a start and/or end date are surfaced here and are not dropped.</p>
                  </pf-content>

                  <pf-data-list compact aria-label="Unscheduled tasks">
                    <pf-data-list-item v-for="task in unscheduledTasks" :key="task.id">
                      <pf-data-list-cell>
                        <pf-button variant="link" class="task-link" @click="selectedTaskId = task.id">
                          {{ task.title }}
                        </pf-button>
                        <div class="meta">
                          <VlLabel :color="taskStatusLabelColor(task.status)">{{ workItemStatusLabel(task.status) }}</VlLabel>
                          <span class="muted">{{ formatDateRange(task.start_date, task.end_date) }}</span>
                        </div>
                      </pf-data-list-cell>
                      <pf-data-list-cell align-right>
                        <pf-button v-if="canEditSchedule" variant="secondary" small @click="openScheduleModal(task)">
                          Schedule
                        </pf-button>
                        <pf-button variant="link" :to="taskDetailPath(task.id)">Open</pf-button>
                      </pf-data-list-cell>
                    </pf-data-list-item>
                  </pf-data-list>
                </div>
              </div>

              <div class="details">
                <pf-card>
                  <pf-card-title>
                    <pf-title h="2" size="lg">Details</pf-title>
                  </pf-card-title>
                  <pf-card-body>
                    <pf-empty-state v-if="!activeTask" variant="small">
                      <pf-empty-state-header title="Select a task" heading-level="h3" />
                      <pf-empty-state-body>Click a scheduled bar or an unscheduled row to view details.</pf-empty-state-body>
                    </pf-empty-state>

                    <div v-else>
                      <div class="detail-header">
                        <pf-title h="3" size="lg">{{ activeTask.title }}</pf-title>
                        <div class="detail-actions">
                          <pf-button variant="primary" small :to="taskDetailPath(activeTask.id)">Open task</pf-button>
                          <pf-button v-if="selectedTaskId" variant="secondary" small @click="selectedTaskId = null">
                            Clear
                          </pf-button>
                        </div>
                      </div>

                      <div class="detail-meta">
                        <VlLabel v-if="activeTask.workflow_stage" :color="stageLabelColor(activeTask.workflow_stage)">
                          Stage {{ stageLabel(activeTask.workflow_stage) }}
                        </VlLabel>
                        <VlLabel v-else :color="taskStatusLabelColor(activeTask.status)">{{ workItemStatusLabel(activeTask.status) }}</VlLabel>

                        <VlLabel color="blue">{{ formatDateRange(activeTask.start_date, activeTask.end_date) }}</VlLabel>

                        <VlLabel :color="progressLabelColor(activeTask.progress)">
                          Progress {{ formatPercent(activeTask.progress) }}
                        </VlLabel>

                        <VlLabel v-if="!isClientOnly" color="grey">Assignee {{ assigneeDisplay }}</VlLabel>

                        <VlLabel v-if="!isClientOnly" color="purple">
                          Epic {{ activeEpicLabel }}
                        </VlLabel>
                      </div>

                      <pf-progress
                        class="task-progress"
                        size="sm"
                        :value="Math.round((activeTask.progress ?? 0) * 100)"
                        :label="formatPercent(activeTask.progress)"
                      />

                      <pf-form v-if="canEditSchedule" class="schedule-form" @submit.prevent="saveSchedule">
                        <pf-title h="4" size="md">Schedule</pf-title>
                        <div class="schedule-grid">
                          <pf-form-group label="Start date" field-id="timeline-start-date">
                            <pf-text-input id="timeline-start-date" v-model="scheduleStartDraft" type="date" />
                          </pf-form-group>
                          <pf-form-group label="End date" field-id="timeline-end-date">
                            <pf-text-input id="timeline-end-date" v-model="scheduleEndDraft" type="date" />
                          </pf-form-group>
                        </div>
                        <div class="schedule-actions">
                          <pf-button variant="primary" :disabled="scheduleSaving" type="submit">
                            {{ scheduleSaving ? "Saving…" : "Save" }}
                          </pf-button>
                          <pf-button variant="secondary" :disabled="scheduleSaving" type="button" @click="clearSchedule">
                            Clear
                          </pf-button>
                        </div>
                        <pf-alert v-if="scheduleError" inline variant="danger" :title="scheduleError" />
                      </pf-form>

                      <div v-if="selectedTask && canShowGitLabLinks" class="gitlab-links-wrap">
                        <GitLabLinksCard
                          :org-id="context.orgId"
                          :task-id="selectedTask.id"
                          :can-manage-integration="canManageGitLabIntegration"
                          :can-manage-links="canManageGitLabLinks"
                        />
                      </div>

                      <pf-alert v-if="orgMembersError" inline variant="warning" :title="orgMembersError" />
                      <div v-if="orgMembersLoading" class="inline-loading">
                        <pf-spinner size="sm" aria-label="Loading org members" />
                        <span class="muted">Loading org members…</span>
                      </div>
                    </div>
                  </pf-card-body>
                </pf-card>
              </div>
            </div>
          </div>
        </pf-card-body>
      </pf-card>
    </div>
  </Teleport>

  <pf-modal v-model:open="scheduleModalOpen" title="Schedule task" variant="small">
    <pf-form class="modal-form" @submit.prevent="saveScheduleFromModal">
      <pf-form-group label="Start date" field-id="timeline-modal-start-date">
        <pf-text-input id="timeline-modal-start-date" v-model="scheduleStartDraft" type="date" />
      </pf-form-group>
      <pf-form-group label="End date" field-id="timeline-modal-end-date">
        <pf-text-input id="timeline-modal-end-date" v-model="scheduleEndDraft" type="date" />
      </pf-form-group>
      <pf-alert v-if="scheduleError" inline variant="danger" :title="scheduleError" />
    </pf-form>

    <template #footer>
      <pf-button variant="primary" :disabled="scheduleSaving" @click="saveScheduleFromModal">
        {{ scheduleSaving ? "Saving…" : "Save" }}
      </pf-button>
      <pf-button variant="secondary" :disabled="scheduleSaving" @click="clearSchedule">Clear</pf-button>
      <pf-button variant="link" :disabled="scheduleSaving" @click="scheduleModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>
</template>

<style scoped>
.fullscreen-shell {
  position: fixed;
  inset: 0;
  z-index: 1000;
  padding: 1rem;
  background: var(--pf-v6-global--BackgroundColor--100, #fff);
  overflow: auto;
}

.fullscreen-card {
  min-height: calc(100vh - 2rem);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  justify-content: end;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.5rem 0;
}

.toolbar {
  margin-bottom: 0.75rem;
}

.filter-field {
  min-width: 200px;
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

.status-filters {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}

.inline-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
}

.layout {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 1rem;
  align-items: start;
}

.details {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.note {
  margin-top: 0.5rem;
}

.unscheduled {
  margin-top: 1.25rem;
}

.task-link {
  font-weight: 700;
}

.detail-header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.detail-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.detail-meta {
  margin-top: 0.75rem;
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}

.task-progress {
  margin-top: 0.75rem;
}

.schedule-form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.schedule-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.schedule-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
}

.gitlab-links-wrap {
  margin-top: 1rem;
}

@media (max-width: 980px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .schedule-grid {
    grid-template-columns: 1fr;
  }
}
</style>
