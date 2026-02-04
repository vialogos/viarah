<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Task } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { computeGanttBar, computeGanttWindow, formatDateRange } from "../utils/schedule";

type ScheduledTask = Task & { start_date: string; end_date: string };

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

function isScheduledTask(task: Task): task is ScheduledTask {
  return typeof task.start_date === "string" && typeof task.end_date === "string";
}

const scheduledTasks = computed(() => tasks.value.filter(isScheduledTask));
const unscheduledTasks = computed(() => tasks.value.filter((t) => !isScheduledTask(t)));
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
</script>

<template>
  <div class="card">
    <h1 class="page-title">Gantt</h1>
    <div class="muted">Last updated: {{ formatTimestamp(lastUpdatedAt) }}</div>

    <div class="section">
      <div v-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!context.orgId || !context.projectId" class="muted">
        Select an org and project to view a schedule.
      </div>
      <div v-else-if="scheduledTasks.length === 0 && unscheduledTasks.length === 0" class="muted">
        No tasks yet.
      </div>

      <div v-else>
        <div v-if="window.windowStart && window.windowEnd" class="muted window">
          Window: {{ window.windowStart }} → {{ window.windowEnd }}
        </div>

        <div v-if="scheduledTasks.length" class="gantt">
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

        <div v-if="unscheduledTasks.length" class="unscheduled">
          <h2 class="subtitle">Unscheduled</h2>
          <ul class="unscheduled-list">
            <li v-for="task in unscheduledTasks" :key="task.id">
              <span class="title">{{ task.title }}</span>
              <span class="muted detail">({{ formatDateRange(task.start_date, task.end_date) }})</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section {
  margin-top: 0.75rem;
}

.window {
  margin: 0.75rem 0;
}

.gantt {
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
  color: var(--muted);
  font-size: 0.9rem;
  margin-top: 0.2rem;
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

.unscheduled {
  margin-top: 1.25rem;
}

.subtitle {
  margin: 0 0 0.5rem 0;
  font-size: 1rem;
}

.unscheduled-list {
  margin: 0;
  padding-left: 1.25rem;
}

.detail {
  margin-left: 0.35rem;
}

@media (max-width: 720px) {
  .gantt-row {
    grid-template-columns: 1fr;
  }
}
</style>
