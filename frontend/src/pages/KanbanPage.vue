<script setup lang="ts">
		import { computed, onBeforeUnmount, ref, watch } from "vue";
		import { useRoute, useRouter, RouterLink } from "vue-router";
		import Draggable from "vuedraggable";

		import { api, ApiError } from "../api";
	import type { Task, WorkflowStage } from "../api/types";
	import VlLabel from "../components/VlLabel.vue";
	import { useContextStore } from "../stores/context";
	import { useRealtimeStore } from "../stores/realtime";
	import { useSessionStore } from "../stores/session";
	import { formatTimestamp } from "../utils/format";
	import { taskStatusLabelColor } from "../utils/labels";

const router = useRouter();
	const route = useRoute();
	const session = useSessionStore();
	const context = useContextStore();
	const realtime = useRealtimeStore();

	const loading = ref(false);
	const error = ref("");

	const stages = ref<WorkflowStage[]>([]);
	const tasks = ref<Task[]>([]);

	const isDragging = ref(false);
	const movingTaskIds = ref(new Set<string>());

	const orgRole = computed(() => {
	  if (!context.orgId) {
	    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});
const canManage = computed(() => orgRole.value === "admin" || orgRole.value === "pm");

const project = computed(() => {
  if (!context.projectId) {
    return null;
  }
  return context.projects.find((p) => p.id === context.projectId) ?? null;
});

const sortedStages = computed(() => [...stages.value].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)));

const tasksByStageId = computed(() => {
  const map: Record<string, Task[]> = {};
  for (const stage of sortedStages.value) {
    map[stage.id] = [];
  }
  for (const task of tasks.value) {
    const stageId = task.workflow_stage_id;
    if (!stageId) {
      continue;
    }
    (map[stageId] ?? (map[stageId] = [])).push(task);
  }
  // Stable-ish ordering: most recently updated first.
  for (const stageId of Object.keys(map)) {
    map[stageId] = map[stageId]!.sort((a, b) => Date.parse(b.updated_at ?? "") - Date.parse(a.updated_at ?? ""));
  }
  return map;
});

function stageTasks(stageId: string): Task[] {
  return tasksByStageId.value[stageId] ?? [];
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

	async function refresh() {
	  error.value = "";

	  if (!context.orgId) {
    stages.value = [];
    tasks.value = [];
    return;
  }
  if (!context.projectId) {
    stages.value = [];
    tasks.value = [];
    return;
  }

  loading.value = true;
	  try {
	    const projectRes = await api.getProject(context.orgId, context.projectId);
	    const workflowId = projectRes.project.workflow_id;
	    if (!workflowId) {
      stages.value = [];
      tasks.value = [];
      return;
    }

    const [stagesRes, tasksRes] = await Promise.all([
      api.listWorkflowStages(context.orgId, workflowId),
      api.listTasks(context.orgId, context.projectId, {}),
    ]);

	    stages.value = stagesRes.stages;
	    tasks.value = tasksRes.tasks;
	  } catch (err) {
	    stages.value = [];
	    tasks.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
	  }
		}

		function isRecord(value: unknown): value is Record<string, unknown> {
		  return Boolean(value) && typeof value === "object";
		}

		async function refreshTask(taskId: string) {
		  if (!context.orgId) {
		    return;
		  }
		  if (!taskId) {
		    return;
		  }
		  try {
		    const res = await api.getTask(context.orgId, taskId);
		    tasks.value = tasks.value.some((t) => t.id === taskId)
		      ? tasks.value.map((t) => (t.id === taskId ? res.task : t))
		      : [...tasks.value, res.task];
		  } catch (err) {
		    if (err instanceof ApiError && err.status === 401) {
		      await handleUnauthorized();
		      return;
		    }
		    if (err instanceof ApiError && err.status === 404) {
		      tasks.value = tasks.value.filter((t) => t.id !== taskId);
		    }
		  }
		}

	async function setTaskStage(task: Task, stageId: string) {
	  if (!context.orgId) {
	    return;
	  }

  movingTaskIds.value.add(task.id);
  try {
    const res = await api.updateTaskStage(context.orgId, task.id, stageId);
    tasks.value = tasks.value.map((t) => (t.id === task.id ? res.task : t));
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
    await refresh();
  } finally {
    movingTaskIds.value.delete(task.id);
  }
	}

	function onStageListChange(stageId: string, event: { added?: { element: Task } }) {
	  if (!event.added) {
    return;
  }
  const task = event.added.element;
  if (!task || task.workflow_stage_id === stageId) {
    return;
  }
  void setTaskStage(task, stageId);
	}

		watch(() => [context.orgId, context.projectId], () => void refresh(), { immediate: true });
		const unsubscribe = realtime.subscribe((event) => {
		  if (event.type !== "work_item.updated") {
		    return;
		  }
		  if (!context.orgId || !context.projectId) {
		    return;
		  }
		  if (event.org_id && event.org_id !== context.orgId) {
		    return;
		  }
		  if (!isRecord(event.data)) {
		    return;
		  }
		  const projectId = typeof event.data.project_id === "string" ? event.data.project_id : "";
		  const taskId = typeof event.data.task_id === "string" ? event.data.task_id : "";
		  if (!projectId || projectId !== context.projectId) {
		    return;
		  }
		  if (!taskId || movingTaskIds.value.has(taskId) || isDragging.value) {
		    return;
		  }
		  void refreshTask(taskId);
		});

		onBeforeUnmount(() => {
		  unsubscribe();
		});
	</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <div>
          <pf-title h="1" size="2xl">Board</pf-title>
          <div class="muted small" v-if="project">
            {{ project.name }}
            <span v-if="project.client"> • {{ project.client.name }}</span>
          </div>
        </div>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to view a board.</pf-empty-state-body>
      </pf-empty-state>

      <pf-empty-state v-else-if="!context.projectId">
        <pf-empty-state-header title="Select a project" heading-level="h2" />
        <pf-empty-state-body>Select a single project to use the board.</pf-empty-state-body>
      </pf-empty-state>

      <pf-alert v-else-if="error" inline variant="danger" :title="error" />

      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading board" />
      </div>

      <pf-empty-state v-else-if="sortedStages.length === 0" variant="small">
        <pf-empty-state-header title="No workflow configured" heading-level="h3" />
        <pf-empty-state-body>Assign a workflow to this project to use the board.</pf-empty-state-body>
        <pf-empty-state-footer>
          <pf-empty-state-actions>
            <pf-button variant="secondary" to="/settings/project">Project settings</pf-button>
          </pf-empty-state-actions>
        </pf-empty-state-footer>
      </pf-empty-state>

      <div
        v-else
        class="board"
        aria-label="Kanban board"
      >
        <pf-card v-for="stage in sortedStages" :key="stage.id" class="column">
          <pf-card-title>
            <div class="column-title">
              <div class="column-name">
                <span>{{ stage.name }}</span>
                <VlLabel :color="taskStatusLabelColor(stage.category)" variant="outline">
                  {{ stage.category.replace('_', ' ').toUpperCase() }}
                </VlLabel>
              </div>
              <VlLabel color="blue" variant="outline">{{ stageTasks(stage.id).length }}</VlLabel>
            </div>
          </pf-card-title>
          <pf-card-body class="column-body">
            <Draggable
              :list="stageTasks(stage.id)"
              item-key="id"
              :group="{ name: 'kanban-tasks' }"
              :disabled="!canManage"
              :sort="false"
              class="dropzone"
              @start="isDragging = true"
              @end="isDragging = false"
              @change="(event: any) => onStageListChange(stage.id, event)"
            >
              <template #item="{ element }">
                <pf-card class="task-card">
                  <pf-card-body class="task-body">
                    <div class="task-title">
                      <RouterLink class="link" :to="`/work/${element.id}`">{{ element.title }}</RouterLink>
                    </div>
                    <div class="muted small">
                      Updated {{ formatTimestamp(element.updated_at ?? '') }}
                    </div>
                  </pf-card-body>
                </pf-card>
              </template>
              <template #footer>
                <pf-empty-state v-if="stageTasks(stage.id).length === 0" variant="small" class="empty-column">
                  <pf-empty-state-header title="Empty" heading-level="h4" />
                  <pf-empty-state-body>Drag tasks here.</pf-empty-state-body>
                </pf-empty-state>
              </template>
            </Draggable>
          </pf-card-body>
        </pf-card>
      </div>

      <pf-alert
        v-if="!canManage && context.orgId && context.projectId"
        inline
        variant="info"
        title="Board is read-only"
        class="readonly-hint"
      >
        Drag-and-drop requires PM/admin org role.
      </pf-alert>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.actions {
  display: flex;
  gap: 0.5rem;
}

.muted {
  color: var(--pf-v6-global--Color--200);
}

.small {
  font-size: 0.85rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 1rem 0;
}

.board {
  display: flex;
  gap: 0.75rem;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: scroll;
  overflow-y: hidden;
  scrollbar-gutter: stable;
  padding-bottom: 1rem;
}

.column {
  min-width: 320px;
  max-width: 340px;
  flex: 0 0 auto;
}

.column-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}

.column-name {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}

.column-body {
  padding-top: 0.5rem;
}

.dropzone {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-height: 180px;
}

.task-card {
  cursor: grab;
}

.task-body {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.task-title {
  font-weight: 600;
}

.empty-column {
  border: 1px dashed var(--pf-v6-global--BorderColor--200);
  border-radius: var(--pf-v6-global--BorderRadius--md);
  padding: 0.5rem;
}

.readonly-hint {
  margin-top: 0.75rem;
}
</style>
