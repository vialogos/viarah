<script setup lang="ts">
	import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
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
				const boardShellEl = ref<HTMLDivElement | null>(null);
				const boardScrollEl = ref<HTMLDivElement | null>(null);
				const boardScrollbarTrackEl = ref<HTMLDivElement | null>(null);
				const boardShellHeightPx = ref<number | null>(null);
				const showBoardScrollbar = ref(false);
				const scrollbarThumbWidthPx = ref(0);
				const scrollbarThumbLeftPx = ref(0);
				let isComputingBoardShellHeight = false;
				let boardResizeObserver: ResizeObserver | null = null;
				let observedBoardScrollEl: Element | null = null;
				let scrollbarPointerId: number | null = null;
				let scrollbarDragStartX = 0;
				let scrollbarDragStartThumbLeft = 0;

				function clamp(value: number, min: number, max: number): number {
				  return Math.min(max, Math.max(min, value));
				}

				function syncScrollbarThumb() {
				  const scroller = boardScrollEl.value;
				  if (!scroller) {
				    showBoardScrollbar.value = false;
				    scrollbarThumbWidthPx.value = 0;
				    scrollbarThumbLeftPx.value = 0;
				    return;
				  }

				  const hasOverflow = scroller.scrollWidth > scroller.clientWidth + 1;
				  showBoardScrollbar.value = hasOverflow;
				  if (!hasOverflow) {
				    scrollbarThumbWidthPx.value = 0;
				    scrollbarThumbLeftPx.value = 0;
				    return;
				  }

				  const track = boardScrollbarTrackEl.value;
				  if (!track) {
				    return;
				  }

				  const trackWidth = track.clientWidth;
				  const scrollRange = scroller.scrollWidth - scroller.clientWidth;
				  if (trackWidth <= 0 || scrollRange <= 0) {
				    scrollbarThumbWidthPx.value = trackWidth;
				    scrollbarThumbLeftPx.value = 0;
				    return;
				  }

				  const nextThumbWidth = Math.max(56, Math.floor((trackWidth * scroller.clientWidth) / scroller.scrollWidth));
				  const maxThumbLeft = Math.max(0, trackWidth - nextThumbWidth);
				  const nextThumbLeft = Math.round((scroller.scrollLeft / scrollRange) * maxThumbLeft);
				  scrollbarThumbWidthPx.value = Math.min(trackWidth, nextThumbWidth);
				  scrollbarThumbLeftPx.value = clamp(nextThumbLeft, 0, maxThumbLeft);
				}

				async function recomputeBoardShellHeight() {
				  if (isComputingBoardShellHeight) {
				    return;
				  }
			  isComputingBoardShellHeight = true;
			  try {
			    await nextTick();
			    const shell = boardShellEl.value;
			    if (!shell) {
			      boardShellHeightPx.value = null;
			      return;
			    }

	    const rect = shell.getBoundingClientRect();
	    const bottomInset = 16;
	    const available = Math.floor(window.innerHeight - rect.top - bottomInset);
	    boardShellHeightPx.value = Math.max(260, available);
	  } finally {
	    isComputingBoardShellHeight = false;
	  }
			}

			async function recomputeBoardScrollbar() {
			  await nextTick();
			  syncScrollbarThumb();
			  if (showBoardScrollbar.value && !boardScrollbarTrackEl.value) {
			    await nextTick();
			    syncScrollbarThumb();
			  }
			}

			function onBoardScroll() {
			  syncScrollbarThumb();
			}

			function scrollBoardToThumbLeft(nextThumbLeft: number) {
			  const scroller = boardScrollEl.value;
			  const track = boardScrollbarTrackEl.value;
			  if (!scroller || !track) {
			    return;
			  }
			  const trackWidth = track.clientWidth;
			  const scrollRange = scroller.scrollWidth - scroller.clientWidth;
			  const maxThumbLeft = Math.max(0, trackWidth - scrollbarThumbWidthPx.value);
			  if (scrollRange <= 0 || maxThumbLeft <= 0) {
			    scroller.scrollLeft = 0;
			    syncScrollbarThumb();
			    return;
			  }
			  const pct = clamp(nextThumbLeft / maxThumbLeft, 0, 1);
			  scroller.scrollLeft = pct * scrollRange;
			}

			function onScrollbarTrackPointerDown(event: PointerEvent) {
			  if (event.button !== 0) {
			    return;
			  }
			  const track = boardScrollbarTrackEl.value;
			  if (!track) {
			    return;
			  }
			  const rect = track.getBoundingClientRect();
			  const clickX = event.clientX - rect.left;
			  const targetThumbLeft = clickX - scrollbarThumbWidthPx.value / 2;
			  scrollBoardToThumbLeft(targetThumbLeft);
			}

			function onScrollbarThumbPointerDown(event: PointerEvent) {
			  if (event.button !== 0) {
			    return;
			  }
			  scrollbarPointerId = event.pointerId;
			  scrollbarDragStartX = event.clientX;
			  scrollbarDragStartThumbLeft = scrollbarThumbLeftPx.value;
			  (event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId);
			}

			function onScrollbarThumbPointerMove(event: PointerEvent) {
			  if (scrollbarPointerId == null || event.pointerId !== scrollbarPointerId) {
			    return;
			  }
			  const track = boardScrollbarTrackEl.value;
			  if (!track) {
			    return;
			  }
			  const trackWidth = track.clientWidth;
			  const maxThumbLeft = Math.max(0, trackWidth - scrollbarThumbWidthPx.value);
			  const deltaX = event.clientX - scrollbarDragStartX;
			  const nextThumbLeft = clamp(scrollbarDragStartThumbLeft + deltaX, 0, maxThumbLeft);
			  scrollbarThumbLeftPx.value = nextThumbLeft;
			  scrollBoardToThumbLeft(nextThumbLeft);
			}

			function onScrollbarThumbPointerUp(event: PointerEvent) {
			  if (scrollbarPointerId == null || event.pointerId !== scrollbarPointerId) {
			    return;
			  }
			  scrollbarPointerId = null;
			  syncScrollbarThumb();
			}

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

		onMounted(() => {
		  void recomputeBoardShellHeight();
		  void recomputeBoardScrollbar();
		  window.addEventListener("resize", recomputeBoardShellHeight, { passive: true });
		  window.addEventListener("resize", recomputeBoardScrollbar, { passive: true });

		  if (typeof ResizeObserver !== "undefined") {
		    boardResizeObserver = new ResizeObserver(() => void recomputeBoardScrollbar());
		  }
		});

		watch(
		  () => [loading.value, error.value, sortedStages.value.length],
		  () => void recomputeBoardShellHeight(),
		  { flush: "post" }
		);

		watch(
		  () => boardScrollEl.value,
		  (nextEl) => {
		    if (!boardResizeObserver) {
		      return;
		    }
		    if (observedBoardScrollEl) {
		      boardResizeObserver.unobserve(observedBoardScrollEl);
		      observedBoardScrollEl = null;
		    }
		    if (nextEl) {
		      boardResizeObserver.observe(nextEl);
		      observedBoardScrollEl = nextEl;
		      void recomputeBoardScrollbar();
		    }
		  },
		  { flush: "post", immediate: true }
		);

		watch(
		  () => [loading.value, error.value, sortedStages.value.length, tasks.value.length],
		  () => void recomputeBoardScrollbar(),
		  { flush: "post" }
		);
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
					  window.removeEventListener("resize", recomputeBoardShellHeight);
					  window.removeEventListener("resize", recomputeBoardScrollbar);
					  if (boardResizeObserver) {
					    boardResizeObserver.disconnect();
					    boardResizeObserver = null;
					  }
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
	        class="board-shell"
	        ref="boardShellEl"
	        :style="boardShellHeightPx ? { height: `${boardShellHeightPx}px` } : undefined"
		      >
				      <div
				        class="board-scroll"
				        ref="boardScrollEl"
				        aria-label="Kanban board"
				        @scroll="onBoardScroll"
				      >
				        <div class="board">
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
			      </div>

					      <div
					        v-if="showBoardScrollbar"
					        class="board-scrollbar"
					        aria-label="Kanban horizontal scrollbar"
				      >
				        <div
				          class="board-scrollbar-track"
				          ref="boardScrollbarTrackEl"
				          aria-hidden="true"
				          @pointerdown="onScrollbarTrackPointerDown"
				        >
				          <div
				            class="board-scrollbar-thumb"
				            :style="{ width: `${scrollbarThumbWidthPx}px`, transform: `translateX(${scrollbarThumbLeftPx}px)` }"
				            @pointerdown.stop="onScrollbarThumbPointerDown"
				            @pointermove="onScrollbarThumbPointerMove"
				            @pointerup="onScrollbarThumbPointerUp"
				            @pointercancel="onScrollbarThumbPointerUp"
				          ></div>
				        </div>
				      </div>
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

		.board-shell {
		  display: flex;
		  flex-direction: column;
		  min-height: 0;
		}

				.board-scroll {
				  flex: 1;
				  overflow-x: auto;
				  overflow-y: hidden;
				  min-height: 0;
				  scrollbar-gutter: stable both-edges;
				}

				.board-scroll::-webkit-scrollbar {
				  height: 0;
				}

				.board-scroll {
				  scrollbar-width: none;
				}

					.board-scrollbar {
					  position: sticky;
					  bottom: 0;
					  padding: 0.35rem 0;
					  background: var(--pf-v6-global--BackgroundColor--100);
					  border-top: 1px solid var(--pf-v6-global--BorderColor--100);
					}

					.board-scrollbar-track {
					  height: 10px;
					  background: var(--pf-v6-global--BorderColor--100);
					  border-radius: 999px;
					  position: relative;
					  user-select: none;
					}

					.board-scrollbar-thumb {
					  position: absolute;
					  top: 0;
					  left: 0;
					  height: 100%;
					  border-radius: 999px;
					  background: var(--pf-v6-global--Color--200);
					  cursor: grab;
					  touch-action: none;
					}

				.board {
				  display: flex;
				  gap: 0.75rem;
				  width: max-content;
		  min-width: 100%;
		  height: 100%;
		  align-items: stretch;
		}

		.column {
		  min-width: 320px;
		  max-width: 340px;
	  flex: 0 0 auto;
	  height: 100%;
	  display: flex;
	  flex-direction: column;
	  min-height: 0;
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
	  flex: 1;
	  min-height: 0;
	  display: flex;
	  flex-direction: column;
	}

	.dropzone {
	  display: flex;
	  flex-direction: column;
	  gap: 0.5rem;
	  flex: 1;
	  overflow-y: auto;
	  min-height: 0;
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
