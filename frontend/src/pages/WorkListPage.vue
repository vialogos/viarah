<script setup lang="ts">
import { ref, watch } from "vue";

import { api } from "../api";
import type { Task } from "../api/types";
import { useContextStore } from "../stores/context";

const context = useContextStore();

const tasks = ref<Task[]>([]);
const loading = ref(false);
const error = ref("");

async function refresh() {
  error.value = "";

  if (!context.orgId || !context.projectId) {
    tasks.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listTasks(context.orgId, context.projectId);
    tasks.value = res.tasks;
  } catch (err) {
    tasks.value = [];
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgId, context.projectId], () => void refresh(), { immediate: true });
</script>

<template>
  <div>
    <h1 class="page-title">Work</h1>
    <p class="muted">Tasks scoped to the selected org + project.</p>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>
    <p v-else-if="!context.projectId" class="card">Select a project to continue.</p>

    <div v-else class="card">
      <div v-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="tasks.length === 0" class="muted">No tasks yet.</div>
      <ul v-else class="list">
        <li v-for="task in tasks" :key="task.id" class="item">
          <RouterLink :to="`/work/${task.id}`">{{ task.title }}</RouterLink>
          <span class="muted status">{{ task.status }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}

.item:last-child {
  border-bottom: none;
}

.status {
  font-size: 0.85rem;
}
</style>
