<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Task } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { readClientLastSeenAt, writeClientLastSeenAt } from "../utils/clientPortal";
import { formatTimestamp } from "../utils/format";

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
  <div class="card">
    <div class="header">
      <div>
        <h1 class="page-title">Tasks</h1>
        <div class="muted">{{ projectName || "Select a project" }}</div>
      </div>
      <button type="button" class="small" @click="markSeen">Mark as seen</button>
    </div>

    <div v-if="!context.orgId" class="muted">Select an org to continue.</div>
    <div v-else-if="!context.projectId" class="muted">Select a project to continue.</div>
    <div v-else-if="loading" class="muted">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="tasks.length === 0" class="muted">No client-visible tasks yet.</div>
    <div v-else class="table">
      <div class="row head">
        <div>Task</div>
        <div>Status</div>
        <div>Dates</div>
        <div>Updated</div>
      </div>

      <div v-for="task in tasks" :key="task.id" class="row">
        <div class="title">
          <RouterLink class="link" :to="`/client/tasks/${task.id}`">{{ task.title }}</RouterLink>
          <span v-if="isUpdatedSinceLastSeen(task)" class="badge">Changed</span>
        </div>
        <div class="muted">{{ statusLabel(task.status) }}</div>
        <div class="muted">
          {{ task.start_date || "—" }} → {{ task.end_date || "—" }}
        </div>
        <div class="muted">{{ task.updated_at ? formatTimestamp(task.updated_at) : "—" }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.table {
  display: grid;
  gap: 0.25rem;
}

.row {
  display: grid;
  grid-template-columns: 1fr 140px 220px 180px;
  gap: 0.75rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fafafa;
}

.row.head {
  background: transparent;
  border: none;
  padding: 0;
  font-size: 0.85rem;
  color: var(--muted);
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

.badge {
  font-size: 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  padding: 0.05rem 0.45rem;
  background: #eef2ff;
  color: #3730a3;
}

.small {
  padding: 0.25rem 0.5rem;
  font-size: 0.85rem;
}
</style>

