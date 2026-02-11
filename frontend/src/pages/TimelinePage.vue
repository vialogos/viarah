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
import { formatDateRange, sortTasksForTimeline } from "../utils/schedule";

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
</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <pf-title h="1" size="2xl">Timeline</pf-title>
        <VlLabel color="blue">Last updated: {{ formatTimestamp(lastUpdatedAt) }}</VlLabel>
      </div>
    </pf-card-title>

    <pf-card-body>
      <div v-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading timeline" />
      </div>

      <pf-alert v-else-if="error" inline variant="danger" :title="error" />

      <pf-empty-state v-else-if="!context.orgId || !context.projectId">
        <pf-empty-state-header title="Select an org and project" heading-level="h2" />
        <pf-empty-state-body>Select an org and project to view a schedule.</pf-empty-state-body>
      </pf-empty-state>

      <pf-empty-state v-else-if="sortedTasks.length === 0">
        <pf-empty-state-header title="No tasks yet" heading-level="h2" />
        <pf-empty-state-body>No scheduled tasks were found for this project.</pf-empty-state-body>
      </pf-empty-state>

      <pf-data-list v-else compact aria-label="Timeline tasks">
        <pf-data-list-item v-for="task in sortedTasks" :key="task.id">
          <pf-data-list-cell>
            <div class="title">{{ task.title }}</div>
            <div class="meta">
              <VlLabel :color="taskStatusLabelColor(task.status)">{{ task.status }}</VlLabel>
              <span class="muted">{{ formatDateRange(task.start_date, task.end_date) }}</span>
            </div>
          </pf-data-list-cell>
        </pf-data-list-item>
      </pf-data-list>
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

.title {
  font-weight: 600;
}

.meta {
  margin-top: 0.25rem;
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}
</style>
