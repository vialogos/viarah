<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Task } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { formatDateRange, sortTasksForTimeline } from "../utils/schedule";
import VlLabel from "../components/VlLabel.vue";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const tasks = ref<Task[]>([]);
const lastUpdatedAt = ref<string | null>(null);
const loading = ref(false);
const error = ref("");

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  if (!context.orgId || !context.projectId) {
    tasks.value = [];
    lastUpdatedAt.value = null;
    return;
  }

  loading.value = true;
  try {
    const res = await api.listTasks(context.orgId, context.projectId);
    tasks.value = res.tasks;
    lastUpdatedAt.value = res.last_updated_at ?? null;
  } catch (err) {
    tasks.value = [];
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

const sortedTasks = computed(() => sortTasksForTimeline(tasks.value));

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
</script>

<template>
  <div class="card">
    <h1 class="page-title">Timeline</h1>
    <div class="muted">Last updated: {{ formatTimestamp(lastUpdatedAt) }}</div>

    <div class="section">
      <div v-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!context.orgId || !context.projectId" class="muted">
        Select an org and project to view a schedule.
      </div>
      <div v-else-if="sortedTasks.length === 0" class="muted">No tasks yet.</div>

      <ul v-else class="timeline">
        <li v-for="task in sortedTasks" :key="task.id" class="timeline-item">
          <div class="title">{{ task.title }}</div>
          <div class="meta">
            <VlLabel :title="task.status" :color="statusColor(task.status)" variant="filled">
              {{ statusLabel(task.status) }}
            </VlLabel>
            <span class="sep">•</span>
            <span>{{ formatDateRange(task.start_date, task.end_date) }}</span>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.section {
  margin-top: 0.75rem;
}

.timeline {
  list-style: none;
  padding: 0;
  margin: 0.75rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.timeline-item {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem 0.9rem;
  background: var(--panel);
}

.title {
  font-weight: 600;
}

.meta {
  margin-top: 0.25rem;
  display: flex;
  gap: 0.5rem;
  align-items: center;
  color: var(--muted);
  font-size: 0.9rem;
}

.sep {
  opacity: 0.6;
}
</style>
