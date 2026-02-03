<script setup lang="ts">
import { ref, watch } from "vue";

import { api } from "../api";
import type { Task } from "../api/types";
import { useContextStore } from "../stores/context";

const props = defineProps<{ taskId: string }>();
const context = useContextStore();

const task = ref<Task | null>(null);
const loading = ref(false);
const error = ref("");

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    task.value = null;
    return;
  }

  loading.value = true;
  try {
    const res = await api.getTask(context.orgId, props.taskId);
    task.value = res.task;
  } catch (err) {
    task.value = null;
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgId, props.taskId], () => void refresh(), { immediate: true });
</script>

<template>
  <div>
    <RouterLink to="/work">← Back to Work</RouterLink>

    <div class="card detail">
      <div v-if="!context.orgId" class="muted">Select an org to view work.</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!task" class="muted">Not found.</div>
      <div v-else>
        <h1 class="page-title">{{ task.title }}</h1>
        <p class="muted">{{ task.status }}</p>
        <p v-if="task.description">{{ task.description }}</p>

        <div class="meta">
          <div><span class="muted">Progress</span> {{ Math.round(task.progress * 100) }}%</div>
          <div><span class="muted">Task ID</span> {{ task.id }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  margin-top: 1rem;
}

.meta {
  margin-top: 1rem;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}
</style>
