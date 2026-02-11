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

const statusCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const task of tasks.value) {
    counts[task.status] = (counts[task.status] ?? 0) + 1;
  }
  return counts;
});

const lastUpdateAt = computed(() => {
  let maxTs = 0;
  let maxIso = "";
  for (const task of tasks.value) {
    const ts = Date.parse(task.updated_at ?? "");
    if (!Number.isFinite(ts)) {
      continue;
    }
    if (ts > maxTs) {
      maxTs = ts;
      maxIso = task.updated_at ?? "";
    }
  }
  return maxIso;
});

const changedTasks = computed(() => {
  const cutoff = Date.parse(lastSeenAt.value);
  if (!Number.isFinite(cutoff)) {
    return [];
  }

  return [...tasks.value]
    .filter((task) => {
      const ts = Date.parse(task.updated_at ?? "");
      return Number.isFinite(ts) && ts > cutoff;
    })
    .sort((a, b) => Date.parse(b.updated_at ?? "") - Date.parse(a.updated_at ?? ""));
});

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
      <pf-title h="1" size="2xl">Client portal</pf-title>
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
        <pf-spinner size="md" aria-label="Loading client portal overview" />
      </div>
      <pf-alert v-else-if="error" inline variant="danger" :title="error" />
      <div v-else>
        <pf-title h="2" size="lg">{{ projectName || "Project" }}</pf-title>

        <div class="labels">
          <VlLabel color="blue">Last update {{ lastUpdateAt ? formatTimestamp(lastUpdateAt) : "—" }}</VlLabel>
          <VlLabel color="blue">Last seen {{ lastSeenAt ? formatTimestamp(lastSeenAt) : "—" }}</VlLabel>
          <pf-button variant="secondary" small @click="markSeen">Mark as seen</pf-button>
        </div>

        <pf-card class="subcard">
          <pf-card-body>
            <pf-title h="3" size="md">Status summary</pf-title>
            <div class="labels">
              <VlLabel
                v-for="status in ['backlog', 'in_progress', 'qa', 'done']"
                :key="status"
                :color="taskStatusLabelColor(status)"
              >
                {{ statusLabel(status) }}: {{ statusCounts[status] ?? 0 }}
              </VlLabel>
            </div>
          </pf-card-body>
        </pf-card>

        <pf-card class="subcard">
          <pf-card-body>
            <pf-title h="3" size="md">What changed</pf-title>

            <pf-empty-state v-if="!lastSeenAt" variant="small">
              <pf-empty-state-header title="No baseline yet" heading-level="h4" />
              <pf-empty-state-body>Click “Mark as seen” to start tracking changes.</pf-empty-state-body>
            </pf-empty-state>

            <pf-empty-state v-else-if="changedTasks.length === 0" variant="small">
              <pf-empty-state-header title="No changes" heading-level="h4" />
              <pf-empty-state-body>No changes since your last visit.</pf-empty-state-body>
            </pf-empty-state>

            <div v-else class="table-wrap">
              <pf-table aria-label="Changed client tasks">
                <pf-thead>
                  <pf-tr>
                    <pf-th>Task</pf-th>
                    <pf-th>Status</pf-th>
                    <pf-th>Updated</pf-th>
                  </pf-tr>
                </pf-thead>
                <pf-tbody>
                  <pf-tr v-for="task in changedTasks" :key="task.id">
                    <pf-td data-label="Task">
                      <RouterLink class="link" :to="`/client/tasks/${task.id}`">{{ task.title }}</RouterLink>
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
          </pf-card-body>
        </pf-card>

        <div class="actions">
          <pf-button variant="primary" to="/client/tasks">View tasks</pf-button>
        </div>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.subcard {
  margin-top: 1rem;
}

.table-wrap {
  overflow-x: auto;
  margin-top: 0.75rem;
}

.link {
  text-decoration: none;
  color: var(--accent);
}

.actions {
  margin-top: 1rem;
}
</style>
