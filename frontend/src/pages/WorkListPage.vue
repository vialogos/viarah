<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Epic, Subtask, Task, WorkflowStage } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatPercent, formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const tasks = ref<Task[]>([]);
const epics = ref<Epic[]>([]);
const stages = ref<WorkflowStage[]>([]);

const loading = ref(false);
const error = ref("");
const epicsError = ref("");

type SubtaskState = { loading: boolean; error: string; subtasks: Subtask[] };
const subtasksByTaskId = ref<Record<string, SubtaskState>>({});
const expandedTaskIds = ref<Record<string, boolean>>({});

const projectWorkflowId = computed(() => {
  const project = context.projects.find((p) => p.id === context.projectId);
  return project?.workflow_id ?? null;
});

const tasksByEpicId = computed(() => {
  const map: Record<string, Task[]> = {};
  for (const task of tasks.value) {
    const key = task.epic_id || "unknown";
    if (!map[key]) {
      map[key] = [];
    }
    map[key].push(task);
  }
  return map;
});

const stageNameById = computed(() => {
  const map: Record<string, string> = {};
  for (const stage of stages.value) {
    map[stage.id] = stage.name;
  }
  return map;
});

function stageLabel(stageId: string | null | undefined): string {
  if (!stageId) {
    return "(unassigned)";
  }
  return stageNameById.value[stageId] ?? stageId;
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  epicsError.value = "";

  if (!context.orgId || !context.projectId) {
    tasks.value = [];
    epics.value = [];
    expandedTaskIds.value = {};
    subtasksByTaskId.value = {};
    return;
  }

  loading.value = true;
  expandedTaskIds.value = {};
  subtasksByTaskId.value = {};
  try {
    const [tasksResult, epicsResult] = await Promise.allSettled([
      api.listTasks(context.orgId, context.projectId),
      api.listEpics(context.orgId, context.projectId),
    ]);

    if (tasksResult.status === "fulfilled") {
      tasks.value = tasksResult.value.tasks;
    } else {
      tasks.value = [];
      const reason = tasksResult.reason;
      if (reason instanceof ApiError && reason.status === 401) {
        await handleUnauthorized();
        return;
      }
      error.value = reason instanceof Error ? reason.message : String(reason);
    }

    if (epicsResult.status === "fulfilled") {
      epics.value = epicsResult.value.epics;
    } else {
      epics.value = [];
      const reason = epicsResult.reason;
      if (reason instanceof ApiError && reason.status === 401) {
        await handleUnauthorized();
        return;
      }
      if (reason instanceof ApiError && reason.status === 403) {
        epicsError.value = "Epics are not available for your role; showing tasks only.";
      } else {
        epicsError.value = reason instanceof Error ? reason.message : String(reason);
      }
    }
  } finally {
    loading.value = false;
  }
}

async function refreshStages() {
  if (!context.orgId || !projectWorkflowId.value) {
    stages.value = [];
    return;
  }

  try {
    const res = await api.listWorkflowStages(context.orgId, projectWorkflowId.value);
    stages.value = res.stages;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    stages.value = [];
  }
}

async function loadSubtasks(taskId: string) {
  if (!context.orgId) {
    return;
  }

  const prior = subtasksByTaskId.value[taskId];
  subtasksByTaskId.value = {
    ...subtasksByTaskId.value,
    [taskId]: { loading: true, error: "", subtasks: prior?.subtasks ?? [] },
  };

  try {
    const res = await api.listSubtasks(context.orgId, taskId);
    subtasksByTaskId.value = {
      ...subtasksByTaskId.value,
      [taskId]: { loading: false, error: "", subtasks: res.subtasks },
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    subtasksByTaskId.value = {
      ...subtasksByTaskId.value,
      [taskId]: {
        loading: false,
        error: err instanceof Error ? err.message : String(err),
        subtasks: [],
      },
    };
  }
}

async function toggleTask(taskId: string) {
  const next = { ...expandedTaskIds.value, [taskId]: !expandedTaskIds.value[taskId] };
  expandedTaskIds.value = next;

  if (next[taskId] && !subtasksByTaskId.value[taskId]) {
    await loadSubtasks(taskId);
  }
}

watch(() => [context.orgId, context.projectId], () => void refresh(), { immediate: true });
watch(() => [context.orgId, projectWorkflowId.value], () => void refreshStages(), { immediate: true });
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
      <div v-else>
        <p v-if="epicsError" class="muted">{{ epicsError }}</p>

        <div v-if="epics.length > 0" class="stack">
          <section v-for="epic in epics" :key="epic.id" class="epic">
            <div class="epic-header">
              <div>
                <div class="epic-title">{{ epic.title }}</div>
                <div class="muted meta-row">
                  <span>Progress {{ formatPercent(epic.progress) }}</span>
                  <span>Updated {{ formatTimestamp(epic.updated_at) }}</span>
                </div>
              </div>
            </div>

            <ul class="list">
              <li
                v-for="task in tasksByEpicId[epic.id] ?? []"
                :key="task.id"
                class="task"
              >
                <div class="task-row">
                  <button type="button" class="toggle" @click="toggleTask(task.id)">
                    {{ expandedTaskIds[task.id] ? "▾" : "▸" }}
                  </button>
                  <RouterLink class="task-link" :to="`/work/${task.id}`">
                    {{ task.title }}
                  </RouterLink>
                  <span class="muted chip">{{ task.status }}</span>
                  <span class="muted chip">Progress {{ formatPercent(task.progress) }}</span>
                  <span class="muted chip">Updated {{ formatTimestamp(task.updated_at) }}</span>
                </div>

                <div v-if="expandedTaskIds[task.id]" class="subtasks">
                  <div v-if="subtasksByTaskId[task.id]?.loading" class="muted">
                    Loading subtasks…
                  </div>
                  <div v-else-if="subtasksByTaskId[task.id]?.error" class="error">
                    {{ subtasksByTaskId[task.id]?.error }}
                  </div>
                  <div
                    v-else-if="(subtasksByTaskId[task.id]?.subtasks?.length ?? 0) === 0"
                    class="muted"
                  >
                    No subtasks yet.
                  </div>
                  <ul v-else class="subtask-list">
                    <li
                      v-for="subtask in subtasksByTaskId[task.id]?.subtasks ?? []"
                      :key="subtask.id"
                      class="subtask"
                    >
                      <div class="subtask-main">
                        <div class="subtask-title">{{ subtask.title }}</div>
                        <div class="muted subtask-stage">
                          Stage {{ stageLabel(subtask.workflow_stage_id) }}
                        </div>
                      </div>
                      <div class="subtask-meta muted">
                        <span>Progress {{ formatPercent(subtask.progress) }}</span>
                        <span>Updated {{ formatTimestamp(subtask.updated_at) }}</span>
                      </div>
                    </li>
                  </ul>
                </div>
              </li>
            </ul>
          </section>
        </div>

        <ul v-else class="list">
          <li v-for="task in tasks" :key="task.id" class="task">
            <div class="task-row">
              <RouterLink class="task-link" :to="`/work/${task.id}`">{{ task.title }}</RouterLink>
              <span class="muted chip">{{ task.status }}</span>
              <span class="muted chip">Progress {{ formatPercent(task.progress) }}</span>
              <span class="muted chip">Updated {{ formatTimestamp(task.updated_at) }}</span>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.epic {
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}

.epic:first-child {
  border-top: none;
  padding-top: 0;
}

.epic-title {
  font-weight: 700;
}

.meta-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  font-size: 0.9rem;
}

.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.task {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}

.task:last-child {
  border-bottom: none;
}

.task-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.task-link {
  font-weight: 600;
}

.toggle {
  width: 2rem;
  padding: 0.25rem 0;
  border-radius: 8px;
  line-height: 1;
}

.chip {
  font-size: 0.85rem;
  padding: 0.1rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #f8fafc;
}

.subtasks {
  margin-left: 2.75rem;
  border-left: 2px solid var(--border);
  padding-left: 0.75rem;
}

.subtask-list {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.subtask {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}

.subtask:last-child {
  border-bottom: none;
}

.subtask-title {
  font-weight: 600;
}

.subtask-stage {
  font-size: 0.85rem;
}

.subtask-meta {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
  align-items: flex-end;
}
</style>
