<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Task } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { taskStatusLabelColor } from "../utils/labels";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const tasks = ref<Task[]>([]);
const loading = ref(false);
const error = ref("");

const orgName = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.org.name ?? "";
});

const projectName = computed(() => {
  if (!context.projectId) {
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

const statusCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const task of tasks.value) {
    counts[task.status] = (counts[task.status] ?? 0) + 1;
  }
  return counts;
});

const todayUtcDate = computed(() => new Date().toISOString().slice(0, 10));

const overdueCount = computed(() => {
  const today = todayUtcDate.value;
  return tasks.value.filter((task) => {
    if (!task.end_date) {
      return false;
    }
    if (task.status === "done") {
      return false;
    }
    return task.end_date < today;
  }).length;
});

const recentUpdates = computed(() => {
  return [...tasks.value]
    .filter((task) => Boolean(task.updated_at))
    .sort((a, b) => Date.parse(b.updated_at ?? "") - Date.parse(a.updated_at ?? ""))
    .slice(0, 10);
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";

  if (!context.hasConcreteScope) {
    tasks.value = [];
    return;
  }

  if (context.isAnyAllScopeActive) {
    tasks.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listTasks(context.orgId, context.projectId, { assignee_user_id: "me" });
    tasks.value = res.tasks;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    tasks.value = [];
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgScope, context.projectScope, context.orgId, context.projectId], () => void refresh(), {
  immediate: true,
});
</script>

<template>
  <pf-card>
    <pf-card-title>
      <pf-title h="1" size="2xl">Dashboard</pf-title>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="context.isAnyAllScopeActive">
        <pf-empty-state-header title="Select a specific org and project" heading-level="h2" />
        <pf-empty-state-body>
          Dashboard v1 does not support “All orgs” / “All projects” aggregation yet. Switch to a single org and
          project to view scoped metrics.
        </pf-empty-state-body>
        <pf-empty-state-actions>
          <pf-button variant="primary" to="/work">Go to Work</pf-button>
        </pf-empty-state-actions>
      </pf-empty-state>

      <pf-empty-state v-else-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to view dashboard metrics.</pf-empty-state-body>
      </pf-empty-state>

      <pf-empty-state v-else-if="!context.projectId">
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

        <pf-title h="3" size="md" class="section-title">Tasks assigned to me</pf-title>
        <div class="metric-grid">
          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('in_progress')">In progress</VlLabel>
              <pf-title h="4" size="3xl">{{ statusCounts["in_progress"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('qa')">QA</VlLabel>
              <pf-title h="4" size="3xl">{{ statusCounts["qa"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('backlog')">Backlog</VlLabel>
              <pf-title h="4" size="3xl">{{ statusCounts["backlog"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel :color="taskStatusLabelColor('done')">Done</VlLabel>
              <pf-title h="4" size="3xl">{{ statusCounts["done"] ?? 0 }}</pf-title>
            </pf-card-body>
          </pf-card>

          <pf-card class="metric-card">
            <pf-card-body class="metric-body">
              <VlLabel color="red" :title="`End date before ${todayUtcDate} (UTC) and not done`">Overdue</VlLabel>
              <pf-title h="4" size="3xl">{{ overdueCount }}</pf-title>
            </pf-card-body>
          </pf-card>
        </div>

        <pf-title h="3" size="md" class="section-title">Recent updates (assigned)</pf-title>

        <pf-empty-state v-if="recentUpdates.length === 0" variant="small">
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
              <pf-tr v-for="task in recentUpdates" :key="task.id">
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
</style>
