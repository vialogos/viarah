<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Task } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { readClientLastSeenAt, writeClientLastSeenAt } from "../utils/clientPortal";
import { formatTimestamp } from "../utils/format";
import VlLabel from "../components/VlLabel.vue";

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

function statusColor(status: string): "blue" | "purple" | "orange" | "success" | null {
  if (status === "backlog") {
    return "blue";
  }
  if (status === "in_progress") {
    return "purple";
  }
  if (status === "qa") {
    return "orange";
  }
  if (status === "done") {
    return "success";
  }
  return null;
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
  <div class="card">
    <h1 class="page-title">Client portal</h1>

    <div v-if="!context.orgId" class="muted">Select an org to continue.</div>
    <div v-else-if="!context.projectId" class="muted">Select a project to continue.</div>
    <div v-else-if="loading" class="muted">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <h2 class="section-title">{{ projectName || "Project" }}</h2>

      <div class="overview-meta">
        <VlLabel>Last update {{ lastUpdateAt ? formatTimestamp(lastUpdateAt) : "—" }}</VlLabel>
        <VlLabel>Last seen {{ lastSeenAt ? formatTimestamp(lastSeenAt) : "—" }}</VlLabel>
        <button type="button" class="pf-v6-c-button pf-m-secondary pf-m-small" @click="markSeen">
          Mark as seen
        </button>
      </div>

      <div class="card subtle">
        <h3>Status summary</h3>
        <div class="chips">
          <VlLabel
            v-for="status in ['backlog', 'in_progress', 'qa', 'done']"
            :key="status"
            :color="statusColor(status)"
            variant="outline"
          >
            {{ statusLabel(status) }}: {{ statusCounts[status] ?? 0 }}
          </VlLabel>
        </div>
      </div>

      <div class="card subtle">
        <h3>What changed</h3>

        <div v-if="!lastSeenAt" class="muted">
          No baseline yet. Click “Mark as seen” to start tracking changes.
        </div>

        <div v-else-if="changedTasks.length === 0" class="muted">No changes since your last visit.</div>

        <ul v-else class="changes">
          <li v-for="task in changedTasks" :key="task.id" class="change-row">
            <RouterLink class="link" :to="`/client/tasks/${task.id}`">{{ task.title }}</RouterLink>
            <VlLabel :title="task.status" :color="statusColor(task.status)" variant="filled">
              {{ statusLabel(task.status) }}
            </VlLabel>
            <span class="muted">{{ formatTimestamp(task.updated_at ?? '') }}</span>
          </li>
        </ul>
      </div>

      <div class="actions">
        <RouterLink class="pf-v6-c-button pf-m-primary pf-m-small" to="/client/tasks">View tasks</RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title {
  margin: 0 0 0.5rem 0;
}

.section-title {
  margin: 0.75rem 0 0.25rem 0;
  font-size: 1.1rem;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--pf-t--global--spacer--xs);
}

.card.subtle {
  margin-top: 1rem;
  border-color: var(--pf-t--global--border--color--default);
  background: var(--pf-t--global--background--color--secondary--default);
}

.changes {
  margin: 0.75rem 0 0 0;
  padding-left: 1rem;
}

.change-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 0.75rem;
  align-items: baseline;
  padding: 0.25rem 0;
}

.link {
  text-decoration: none;
  color: var(--pf-t--global--text--color--link--default);
}

.actions {
  margin-top: 1rem;
}

.overview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--pf-t--global--spacer--xs);
  align-items: center;
}
</style>
