<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Task } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { readClientLastSeenAt, writeClientLastSeenAt } from "../utils/clientPortal";
import { formatTimestamp } from "../utils/format";
import { taskStatusLabelColor } from "../utils/labels";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const tasks = ref<Task[]>([]);
const loading = ref(false);
const error = ref("");
const lastSeenAt = ref("");

const projectName = computed(() => {
  if (!context.projectId) {
    return "";
  }
  return context.projects.find((p) => p.id === context.projectId)?.name ?? "";
});

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

function isUpdatedSinceLastSeen(task: Task): boolean {
  const cutoff = Date.parse(lastSeenAt.value);
  if (!Number.isFinite(cutoff)) {
    return false;
  }
  const ts = Date.parse(task.updated_at ?? "");
  return Number.isFinite(ts) && ts > cutoff;
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";

  if (!context.orgId || !context.projectId) {
    tasks.value = [];
    lastSeenAt.value = "";
    return;
  }

  lastSeenAt.value = readClientLastSeenAt(context.projectId);

  loading.value = true;
  try {
    const res = await api.listTasks(context.orgId, context.projectId);
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

function markSeen() {
  if (!context.projectId) {
    return;
  }
  const next = new Date().toISOString();
  writeClientLastSeenAt(context.projectId, next);
  lastSeenAt.value = next;
}

watch(() => [context.orgId, context.projectId], () => void refresh(), { immediate: true });
</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <div>
          <pf-title h="1" size="2xl">Tasks</pf-title>
          <pf-content>
            <p class="muted">{{ projectName || "Select a project" }}</p>
          </pf-content>
        </div>
        <pf-button variant="secondary" small @click="markSeen">Mark as seen</pf-button>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
      </pf-empty-state>
      <pf-empty-state v-else-if="!context.projectId">
        <pf-empty-state-header title="Select a project" heading-level="h2" />
        <pf-empty-state-body>Select a project to continue.</pf-empty-state-body>
      </pf-empty-state>
      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading client tasks" />
      </div>
      <pf-alert v-else-if="error" inline variant="danger" :title="error" />
      <pf-empty-state v-else-if="tasks.length === 0">
        <pf-empty-state-header title="No tasks yet" heading-level="h2" />
        <pf-empty-state-body>No client-visible tasks were found for this project.</pf-empty-state-body>
      </pf-empty-state>
      <div v-else class="table-wrap">
        <pf-table aria-label="Client tasks">
          <pf-thead>
            <pf-tr>
              <pf-th>Task</pf-th>
              <pf-th>Status</pf-th>
              <pf-th>Dates</pf-th>
              <pf-th>Updated</pf-th>
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="task in tasks" :key="task.id">
              <pf-td data-label="Task">
                <div class="title">
                  <RouterLink class="link" :to="`/client/tasks/${task.id}`">{{ task.title }}</RouterLink>
                  <VlLabel v-if="isUpdatedSinceLastSeen(task)" color="orange" variant="filled">Changed</VlLabel>
                </div>
              </pf-td>
              <pf-td data-label="Status">
                <VlLabel :color="taskStatusLabelColor(task.status)">{{ statusLabel(task.status) }}</VlLabel>
              </pf-td>
              <pf-td class="muted" data-label="Dates">
                {{ task.start_date || "—" }} → {{ task.end_date || "—" }}
              </pf-td>
              <pf-td data-label="Updated">
                <VlLabel v-if="task.updated_at" color="blue">{{ formatTimestamp(task.updated_at) }}</VlLabel>
                <span v-else class="muted">—</span>
              </pf-td>
            </pf-tr>
          </pf-tbody>
        </pf-table>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.table-wrap {
  overflow-x: auto;
}

.title {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.link {
  text-decoration: none;
  color: var(--accent);
}
</style>
