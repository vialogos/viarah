<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Task } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
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
  <pf-card>
    <pf-card-title>
      <div class="header">
        <pf-title h="1" size="2xl">Gantt</pf-title>
        <VlLabel color="blue">Last updated: {{ formatTimestamp(lastUpdatedAt) }}</VlLabel>
      </div>
    </pf-card-title>

    <pf-card-body>
      <div v-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading schedule gantt" />
      </div>
      <pf-alert v-else-if="error" inline variant="danger" :title="error" />
      <pf-empty-state v-else-if="!context.orgId || !context.projectId">
        <pf-empty-state-header title="Select an org and project" heading-level="h2" />
        <pf-empty-state-body>Select an org and project to view a schedule.</pf-empty-state-body>
      </pf-empty-state>
      <pf-empty-state v-else-if="scheduledTasks.length === 0 && unscheduledTasks.length === 0">
        <pf-empty-state-header title="No tasks yet" heading-level="h2" />
        <pf-empty-state-body>No tasks were found for the selected project.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else>
        <VlLabel v-if="window.windowStart && window.windowEnd" color="blue">
          Window: {{ window.windowStart }} → {{ window.windowEnd }}
        </VlLabel>

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
          <pf-title h="2" size="lg">Unscheduled</pf-title>
          <pf-list class="unscheduled-list">
            <pf-list-item v-for="task in unscheduledTasks" :key="task.id">
              <span class="title">{{ task.title }}</span>
              <span class="muted detail">({{ formatDateRange(task.start_date, task.end_date) }})</span>
            </pf-list-item>
          </pf-list>
        </div>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.5rem 0;
}

.gantt {
  margin-top: 1rem;
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

.unscheduled-list {
  margin-top: 0.5rem;
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
