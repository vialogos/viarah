<script setup lang="ts">
	import { computed, onBeforeUnmount, ref, watch } from "vue";
	import { useRoute, useRouter } from "vue-router";

			import { api, ApiError } from "../api";
			import type { Task } from "../api/types";
			import ActivityStream from "../components/ActivityStream.vue";
			import VlLabel from "../components/VlLabel.vue";
			import { useContextStore } from "../stores/context";
			import { useRealtimeStore } from "../stores/realtime";
			import { useSessionStore } from "../stores/session";
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

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
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

		let refreshTimeoutId: number | null = null;

		function scheduleRefresh() {
		  if (refreshTimeoutId != null) {
		    return;
		  }
		  refreshTimeoutId = window.setTimeout(() => {
		    refreshTimeoutId = null;
		    void refresh();
		  }, 250);
		}

		const unsubscribeRealtime = realtime.subscribe((event) => {
		  if (!context.orgId || (event.org_id && event.org_id !== context.orgId)) {
		    return;
		  }
		  if (event.type === "work_item.updated" || event.type === "comment.created" || event.type === "gitlab_link.updated") {
		    scheduleRefresh();
		  }
		});

		onBeforeUnmount(() => {
		  unsubscribeRealtime();
		  if (refreshTimeoutId != null) {
		    window.clearTimeout(refreshTimeoutId);
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

	        <pf-title h="3" size="md" class="section-title">Recent activity</pf-title>
	        <div class="activity-grid">
	          <ActivityStream
	            class="activity-stream"
	            :org-id="context.orgId"
	            :title="context.projectScope === 'single' ? 'Recent activity (project)' : 'Recent activity (projects)'"
	            :project-id="context.projectScope === 'single' ? context.projectId : undefined"
	            :limit="20"
	          />
	          <ActivityStream
	            class="activity-stream"
	            :org-id="context.orgId"
	            title="Recent activity (assigned to me)"
	            :task-ids="myTasks.map((task) => task.id)"
	            :limit="20"
	          />
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

	.activity-grid {
	  display: grid;
	  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
	  gap: 0.75rem;
	  margin-top: 0.75rem;
	}

	.activity-stream {
	  margin-top: 0;
	}
</style>
