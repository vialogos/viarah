<script setup lang="ts">
	import { computed, onBeforeUnmount, ref, watch } from "vue";
	import { useRoute, useRouter } from "vue-router";

	import { api, ApiError } from "../api";
	import type { AuditEvent, Client, Person, Task } from "../api/types";
	import VlLabel from "../components/VlLabel.vue";
	import { useContextStore } from "../stores/context";
	import { useRealtimeStore } from "../stores/realtime";
	import { useSessionStore } from "../stores/session";
	import { formatTimestamp } from "../utils/format";
	import { taskStatusLabelColor } from "../utils/labels";
	import { mapAllSettledWithConcurrency } from "../utils/promisePool";

const router = useRouter();
	const route = useRoute();
	const session = useSessionStore();
	const context = useContextStore();
	const realtime = useRealtimeStore();

const projectTasks = ref<Task[]>([]);
const myTasks = ref<Task[]>([]);
const loading = ref(false);
const error = ref("");

const activityEvents = ref<AuditEvent[]>([]);
const activityLoading = ref(false);
const activityError = ref("");

const activityTasksById = ref<Record<string, Task>>({});
const activityClientsById = ref<Record<string, Client>>({});
const activityPeopleById = ref<Record<string, Person>>({});

const orgName = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.org.name ?? "";
});

const projectName = computed(() => {
  if (!context.projectId) {
    if (context.projectScope === "all" && context.orgId) {
      return "All projects";
    }
    return "";
  }
  return context.projects.find((p) => p.id === context.projectId)?.name ?? "";
});

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canAccessOrgAdminRoutes = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

function statusLabel(status: string): string {
  switch (status) {
    case "backlog":
      return "Backlog";
    case "in_progress":
      return "In progress";
    case "qa":
      return "QA";
    case "done":
      return "Done";
    default:
      return status;
  }
}

function countTasksByStatus(rows: Task[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const task of rows) {
    counts[task.status] = (counts[task.status] ?? 0) + 1;
  }
  return counts;
}

const projectStatusCounts = computed(() => countTasksByStatus(projectTasks.value));
const myStatusCounts = computed(() => countTasksByStatus(myTasks.value));

const todayUtcDate = computed(() => new Date().toISOString().slice(0, 10));

function countOverdue(rows: Task[]): number {
  const today = todayUtcDate.value;
  return rows.filter((task) => {
    if (!task.end_date) {
      return false;
    }
    if (task.status === "done") {
      return false;
    }
    return task.end_date < today;
  }).length;
}

const projectOverdueCount = computed(() => countOverdue(projectTasks.value));
const myOverdueCount = computed(() => countOverdue(myTasks.value));

function recentUpdatesFor(rows: Task[]): Task[] {
  return [...rows]
    .filter((task) => Boolean(task.updated_at))
    .sort((a, b) => Date.parse(b.updated_at ?? "") - Date.parse(a.updated_at ?? ""))
    .slice(0, 10);
}

const projectRecentUpdates = computed(() => recentUpdatesFor(projectTasks.value));
const myRecentUpdates = computed(() => recentUpdatesFor(myTasks.value));

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function shortId(value: string): string {
  if (!value) {
    return "";
  }
  if (value.length <= 12) {
    return value;
  }
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function metadataString(event: AuditEvent, key: string): string | null {
  const value = event.metadata?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function actorLabel(event: AuditEvent): string {
  return event.actor_user?.display_name || event.actor_user?.email || "System";
}

function activityTarget(event: AuditEvent): { label: string; to?: string } {
  const taskId = metadataString(event, "task_id");
  if (taskId) {
    const task = activityTasksById.value[taskId];
    return { label: task?.title || `Task ${shortId(taskId)}`, to: `/work/${taskId}` };
  }

  const clientId = metadataString(event, "client_id");
  if (clientId) {
    const client = activityClientsById.value[clientId];
    return { label: client?.name || `Client ${shortId(clientId)}`, to: `/clients/${clientId}` };
  }

  const personId = metadataString(event, "person_id");
  if (personId) {
    const person = activityPeopleById.value[personId];
    const label = (person?.preferred_name || person?.full_name || person?.email || "").trim();
    return { label: label || `Person ${shortId(personId)}`, to: `/people/${personId}` };
  }

  return { label: event.event_type };
}

function activitySummary(event: AuditEvent): string {
  switch (event.event_type) {
    case "task.workflow_stage_changed":
      return "moved";
    case "subtask.workflow_stage_changed":
      return "moved";
    case "comment.created":
      return "commented on";
    case "attachment.created":
      return "attached a file to";
    case "client.created":
      return "created";
    case "client.updated":
      return "updated";
    case "person_message.created":
      return "messaged";
    default:
      return event.event_type.split("_").join(" ").split(".").join(" ");
  }
}

async function refreshActivity() {
  activityError.value = "";

  if (!context.orgId) {
    activityEvents.value = [];
    activityTasksById.value = {};
    activityClientsById.value = {};
    activityPeopleById.value = {};
    return;
  }

  activityLoading.value = true;
  try {
    const res = await api.listAuditEvents(context.orgId);
    const raw = res.events || [];
    const projectFiltered =
      context.projectScope === "single" && context.projectId
        ? raw.filter((event) => metadataString(event, "project_id") === context.projectId)
        : raw;

    const events = projectFiltered.slice(0, 25);
    activityEvents.value = events;

    const taskIds = Array.from(
      new Set(events.map((event) => metadataString(event, "task_id")).filter(Boolean) as string[])
    );
    const clientIds = Array.from(
      new Set(events.map((event) => metadataString(event, "client_id")).filter(Boolean) as string[])
    );
    const personIds = Array.from(
      new Set(events.map((event) => metadataString(event, "person_id")).filter(Boolean) as string[])
    );

    const TASK_FETCH_CONCURRENCY = 6;
    const [taskResults, clientResults, personResults] = await Promise.all([
      mapAllSettledWithConcurrency(taskIds, TASK_FETCH_CONCURRENCY, async (taskId) =>
        api.getTask(context.orgId!, taskId)
      ),
      mapAllSettledWithConcurrency(clientIds, TASK_FETCH_CONCURRENCY, async (clientId) =>
        api.getClient(context.orgId!, clientId)
      ),
      mapAllSettledWithConcurrency(personIds, TASK_FETCH_CONCURRENCY, async (personId) =>
        api.getOrgPerson(context.orgId!, personId)
      ),
    ]);

    const nextTasks: Record<string, Task> = {};
    for (let i = 0; i < taskIds.length; i += 1) {
      const id = taskIds[i];
      const result = taskResults[i];
      if (!id || !result || result.status !== "fulfilled") {
        continue;
      }
      nextTasks[id] = result.value.task;
    }
    activityTasksById.value = nextTasks;

    const nextClients: Record<string, Client> = {};
    for (let i = 0; i < clientIds.length; i += 1) {
      const id = clientIds[i];
      const result = clientResults[i];
      if (!id || !result || result.status !== "fulfilled") {
        continue;
      }
      nextClients[id] = result.value.client;
    }
    activityClientsById.value = nextClients;

    const nextPeople: Record<string, Person> = {};
    for (let i = 0; i < personIds.length; i += 1) {
      const id = personIds[i];
      const result = personResults[i];
      if (!id || !result || result.status !== "fulfilled") {
        continue;
      }
      nextPeople[id] = result.value.person;
    }
    activityPeopleById.value = nextPeople;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    activityEvents.value = [];
    activityTasksById.value = {};
    activityClientsById.value = {};
    activityPeopleById.value = {};
    activityError.value = err instanceof Error ? err.message : String(err);
  } finally {
    activityLoading.value = false;
  }
}

async function refresh() {
  error.value = "";

  if (!context.hasOrgScope) {
    projectTasks.value = [];
    myTasks.value = [];
    return;
  }

  loading.value = true;
  try {
    const orgId = context.orgId;
    const projectIds =
      context.projectScope === "single" && context.projectId
        ? [context.projectId]
        : context.projects.map((p) => p.id);

    if (projectIds.length === 0) {
      projectTasks.value = [];
      myTasks.value = [];
      return;
    }

    const PROJECT_FETCH_CONCURRENCY = 4;
    const allTasksResults = await mapAllSettledWithConcurrency(
      projectIds,
      PROJECT_FETCH_CONCURRENCY,
      async (projectId) => api.listTasks(orgId, projectId, {})
    );
    const myTasksResults = await mapAllSettledWithConcurrency(
      projectIds,
      PROJECT_FETCH_CONCURRENCY,
      async (projectId) => api.listTasks(orgId, projectId, { assignee_user_id: "me" })
    );

    const nextProjectTasks: Task[] = [];
    for (const res of allTasksResults) {
      if (res.status === "fulfilled") {
        nextProjectTasks.push(...res.value.tasks);
      }
    }

    const nextMyTasks: Task[] = [];
    for (const res of myTasksResults) {
      if (res.status === "fulfilled") {
        nextMyTasks.push(...res.value.tasks);
      }
    }

    const firstFailure =
      allTasksResults.find((r) => r.status === "rejected") ??
      myTasksResults.find((r) => r.status === "rejected");

    if (firstFailure && firstFailure.status === "rejected") {
      throw firstFailure.reason;
    }

    projectTasks.value = nextProjectTasks;
    myTasks.value = nextMyTasks;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    projectTasks.value = [];
    myTasks.value = [];
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgScope, context.projectScope, context.orgId, context.projectId], () => void refresh(), {
  immediate: true,
});

	watch(() => [context.orgScope, context.projectScope, context.orgId, context.projectId], () => void refreshActivity(), {
	  immediate: true,
	});

	let refreshTimeoutId: number | null = null;
	let refreshActivityTimeoutId: number | null = null;

	function scheduleRefresh() {
	  if (refreshTimeoutId != null) {
	    return;
	  }
	  refreshTimeoutId = window.setTimeout(() => {
	    refreshTimeoutId = null;
	    void refresh();
	  }, 250);
	}

	function scheduleRefreshActivity() {
	  if (refreshActivityTimeoutId != null) {
	    return;
	  }
	  refreshActivityTimeoutId = window.setTimeout(() => {
	    refreshActivityTimeoutId = null;
	    void refreshActivity();
	  }, 250);
	}

	const unsubscribeRealtime = realtime.subscribe((event) => {
	  if (!context.orgId || (event.org_id && event.org_id !== context.orgId)) {
	    return;
	  }
	  if (event.type === "work_item.updated" || event.type === "comment.created" || event.type === "gitlab_link.updated") {
	    scheduleRefresh();
	    scheduleRefreshActivity();
	  }
	});

	onBeforeUnmount(() => {
	  unsubscribeRealtime();
	  if (refreshTimeoutId != null) {
	    window.clearTimeout(refreshTimeoutId);
	  }
	  if (refreshActivityTimeoutId != null) {
	    window.clearTimeout(refreshActivityTimeoutId);
	  }
	});
</script>

<template>
  <pf-card>
    <pf-card-title>
      <pf-title h="1" size="2xl">Dashboard</pf-title>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to view dashboard metrics.</pf-empty-state-body>
      </pf-empty-state>

      <pf-empty-state v-else-if="context.projectScope === 'single' && !context.projectId">
        <pf-empty-state-header title="Select a project" heading-level="h2" />
        <pf-empty-state-body>Select a project to view dashboard metrics.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading dashboard metrics" />
      </div>

      <pf-alert v-else-if="error" inline variant="danger" :title="error" />

      <div v-else>
        <pf-title h="2" size="lg">{{ orgName || "Org" }} / {{ projectName || "Project" }}</pf-title>

        <pf-title h="3" size="md" class="section-title">Quick links</pf-title>
        <div class="actions">
          <pf-button variant="primary" to="/work">Work</pf-button>
          <pf-button
            variant="secondary"
            :to="canAccessOrgAdminRoutes ? '/projects?create=1' : undefined"
            :disabled="!canAccessOrgAdminRoutes"
            :title="!canAccessOrgAdminRoutes ? 'Requires PM/admin org role' : undefined"
          >
            New project
          </pf-button>
          <pf-button
            variant="secondary"
            :to="canAccessOrgAdminRoutes ? '/team' : undefined"
            :disabled="!canAccessOrgAdminRoutes"
            :title="!canAccessOrgAdminRoutes ? 'Requires PM/admin org role' : undefined"
          >
            Team
          </pf-button>
          <pf-button variant="secondary" to="/notifications/settings">Notification settings</pf-button>
        </div>

        <pf-title h="3" size="md" class="section-title">Project tasks</pf-title>
        <div class="metric-grid">
          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('in_progress')">In progress</VlLabel>
              <pf-title h="4" size="3xl">{{ projectStatusCounts["in_progress"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('qa')">QA</VlLabel>
              <pf-title h="4" size="3xl">{{ projectStatusCounts["qa"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('backlog')">Backlog</VlLabel>
              <pf-title h="4" size="3xl">{{ projectStatusCounts["backlog"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('done')">Done</VlLabel>
              <pf-title h="4" size="3xl">{{ projectStatusCounts["done"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel color="red" :title="`End date before ${todayUtcDate} (UTC) and not done`">Overdue</VlLabel>
              <pf-title h="4" size="3xl">{{ projectOverdueCount }}</pf-title>
            </pf-card-body>
          </pf-card>
        </div>

        <pf-title h="3" size="md" class="section-title">Tasks assigned to me</pf-title>
        <div class="metric-grid">
          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('in_progress')">In progress</VlLabel>
              <pf-title h="4" size="3xl">{{ myStatusCounts["in_progress"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('qa')">QA</VlLabel>
              <pf-title h="4" size="3xl">{{ myStatusCounts["qa"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('backlog')">Backlog</VlLabel>
              <pf-title h="4" size="3xl">{{ myStatusCounts["backlog"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('done')">Done</VlLabel>
              <pf-title h="4" size="3xl">{{ myStatusCounts["done"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel color="red" :title="`End date before ${todayUtcDate} (UTC) and not done`">Overdue</VlLabel>
              <pf-title h="4" size="3xl">{{ myOverdueCount }}</pf-title>
            </pf-card-body>
          </pf-card>
        </div>

        <pf-title h="3" size="md" class="section-title">Activity</pf-title>

        <pf-alert v-if="activityError" inline variant="danger" :title="activityError" />

        <div v-else-if="activityLoading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading activity" />
        </div>

        <pf-empty-state v-else-if="activityEvents.length === 0" variant="small">
          <pf-empty-state-header title="No recent activity" heading-level="h4" />
          <pf-empty-state-body>No audit events found for this scope.</pf-empty-state-body>
        </pf-empty-state>

        <pf-card v-else class="activity-card">
          <pf-card-body>
            <pf-data-list aria-label="Activity feed">
              <pf-data-list-item v-for="event in activityEvents" :key="event.id" aria-label="Activity item">
                <pf-data-list-item-row>
                  <pf-data-list-item-cells>
                    <pf-data-list-cell>
                      <div class="activity-row">
                        <div class="activity-main">
                          <span class="activity-actor">{{ actorLabel(event) }}</span>
                          <span class="activity-action">{{ activitySummary(event) }}</span>
                          <RouterLink v-if="activityTarget(event).to" class="link" :to="activityTarget(event).to!">
                            {{ activityTarget(event).label }}
                          </RouterLink>
                          <span v-else class="activity-target">{{ activityTarget(event).label }}</span>
                        </div>
                        <div class="activity-meta muted small">{{ formatTimestamp(event.created_at) }}</div>
                      </div>
                    </pf-data-list-cell>
                  </pf-data-list-item-cells>
                </pf-data-list-item-row>
              </pf-data-list-item>
            </pf-data-list>
          </pf-card-body>
        </pf-card>

        <pf-title h="3" size="md" class="section-title">Recent updates (project)</pf-title>

        <pf-empty-state v-if="projectRecentUpdates.length === 0" variant="small">
          <pf-empty-state-header title="No recent updates" heading-level="h4" />
          <pf-empty-state-body>No tasks found for this project.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else class="table-wrap">
          <pf-table aria-label="Recent project task updates">
            <pf-thead>
              <pf-tr>
                <pf-th>Task</pf-th>
                <pf-th>Status</pf-th>
                <pf-th>Updated</pf-th>
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="task in projectRecentUpdates" :key="task.id">
                <pf-td data-label="Task">
                  <RouterLink class="link" :to="`/work/${task.id}`">{{ task.title }}</RouterLink>
                </pf-td>
                <pf-td data-label="Status">
                  <VlLabel :color="taskStatusLabelColor(task.status)">{{ statusLabel(task.status) }}</VlLabel>
                </pf-td>
                <pf-td data-label="Updated">
                  <VlLabel color="blue">{{ formatTimestamp(task.updated_at ?? '') }}</VlLabel>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>
        </div>

        <pf-title h="3" size="md" class="section-title">Recent updates (assigned)</pf-title>

        <pf-empty-state v-if="myRecentUpdates.length === 0" variant="small">
          <pf-empty-state-header title="No recent updates" heading-level="h4" />
          <pf-empty-state-body>No assigned tasks yet for this project.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else class="table-wrap">
          <pf-table aria-label="Recent task updates">
            <pf-thead>
              <pf-tr>
                <pf-th>Task</pf-th>
                <pf-th>Status</pf-th>
                <pf-th>Updated</pf-th>
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="task in myRecentUpdates" :key="task.id">
                <pf-td data-label="Task">
                  <RouterLink class="link" :to="`/work/${task.id}`">{{ task.title }}</RouterLink>
                </pf-td>
                <pf-td data-label="Status">
                  <VlLabel :color="taskStatusLabelColor(task.status)">{{ statusLabel(task.status) }}</VlLabel>
                </pf-td>
                <pf-td data-label="Updated">
                  <VlLabel color="blue">{{ formatTimestamp(task.updated_at ?? '') }}</VlLabel>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>
        </div>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.section-title {
  margin-top: 1.25rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.metric-card {
  height: 100%;
}

.metric-body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.table-wrap {
  overflow-x: auto;
  margin-top: 0.75rem;
}

.activity-card {
  margin-top: 0.75rem;
}

.activity-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: baseline;
}

.activity-main {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: baseline;
}

.activity-actor {
  font-weight: 600;
}

.activity-action {
  color: var(--pf-v6-global--Color--200);
}

.activity-target {
  color: var(--pf-v6-global--Color--100);
}
</style>
