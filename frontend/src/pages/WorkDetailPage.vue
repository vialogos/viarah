<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import TrustPanel from "../components/TrustPanel.vue";
import { api, ApiError } from "../api";
import type { Attachment, Comment, Epic, Project, Subtask, Task, WorkflowStage } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatPercent, formatTimestamp } from "../utils/format";

const props = defineProps<{ taskId: string }>();
const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const task = ref<Task | null>(null);
const comments = ref<Comment[]>([]);
const attachments = ref<Attachment[]>([]);
const commentDraft = ref("");
const selectedFile = ref<File | null>(null);
const epic = ref<Epic | null>(null);
const project = ref<Project | null>(null);
const subtasks = ref<Subtask[]>([]);
const stages = ref<WorkflowStage[]>([]);

const loading = ref(false);
const error = ref("");
const collabError = ref("");
const stageUpdateErrorBySubtaskId = ref<Record<string, string>>({});
const stageUpdateSavingSubtaskId = ref("");

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canEditStages = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const stageById = computed(() => {
  const map: Record<string, WorkflowStage> = {};
  for (const stage of stages.value) {
    map[stage.id] = stage;
  }
  return map;
});

const workflowId = computed(() => project.value?.workflow_id ?? null);

function stageLabel(stageId: string | null | undefined): string {
  if (!stageId) {
    return "(unassigned)";
  }
  const stage = stageById.value[stageId];
  return stage ? stage.name : stageId;
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  collabError.value = "";
  stageUpdateErrorBySubtaskId.value = {};

  if (!context.orgId) {
    task.value = null;
    epic.value = null;
    project.value = null;
    subtasks.value = [];
    stages.value = [];
    comments.value = [];
    attachments.value = [];
    commentDraft.value = "";
    selectedFile.value = null;
    return;
  }

  loading.value = true;
  try {
    const [taskRes, subtasksRes] = await Promise.all([
      api.getTask(context.orgId, props.taskId),
      api.listSubtasks(context.orgId, props.taskId),
    ]);
    task.value = taskRes.task;
    subtasks.value = subtasksRes.subtasks;

    epic.value = null;
    project.value = null;
    stages.value = [];

    try {
      const epicRes = await api.getEpic(context.orgId, taskRes.task.epic_id);
      epic.value = epicRes.epic;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await handleUnauthorized();
        return;
      }
    }

    const projectId = epic.value?.project_id ?? context.projectId;
    if (projectId) {
      try {
        const projectRes = await api.getProject(context.orgId, projectId);
        project.value = projectRes.project;
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          await handleUnauthorized();
          return;
        }
      }
    }

    if (project.value?.workflow_id) {
      try {
        const stageRes = await api.listWorkflowStages(context.orgId, project.value.workflow_id);
        stages.value = stageRes.stages;
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          await handleUnauthorized();
          return;
        }
        stages.value = [];
      }
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    task.value = null;
    epic.value = null;
    project.value = null;
    subtasks.value = [];
    stages.value = [];
    comments.value = [];
    attachments.value = [];
    error.value = err instanceof Error ? err.message : String(err);
    return;
  } finally {
    loading.value = false;
  }

  try {
    const commentsRes = await api.listTaskComments(context.orgId, props.taskId);
    comments.value = commentsRes.comments;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    comments.value = [];
    collabError.value = err instanceof Error ? err.message : String(err);
  }

  try {
    const attachmentsRes = await api.listTaskAttachments(context.orgId, props.taskId);
    attachments.value = attachmentsRes.attachments;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    attachments.value = [];
    collabError.value = err instanceof Error ? err.message : String(err);
  }
}

async function submitComment() {
  if (!context.orgId) {
    return;
  }

  collabError.value = "";
  const body = commentDraft.value.trim();
  if (!body) {
    return;
  }

  try {
    await api.createTaskComment(context.orgId, props.taskId, body);
    commentDraft.value = "";
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    collabError.value = err instanceof Error ? err.message : String(err);
  }
}

async function uploadAttachment() {
  if (!context.orgId) {
    return;
  }
  if (!selectedFile.value) {
    return;
  }

  collabError.value = "";
  try {
    await api.uploadTaskAttachment(context.orgId, props.taskId, selectedFile.value);
    selectedFile.value = null;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    collabError.value = err instanceof Error ? err.message : String(err);
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.item(0);
  selectedFile.value = file ?? null;
}

watch(() => [context.orgId, props.taskId], () => void refresh(), { immediate: true });

async function onStageChange(subtaskId: string, event: Event) {
  if (!context.orgId) {
    return;
  }

  const value = (event.target as HTMLSelectElement).value;
  const workflowStageId = value ? value : null;

  stageUpdateSavingSubtaskId.value = subtaskId;
  stageUpdateErrorBySubtaskId.value = { ...stageUpdateErrorBySubtaskId.value, [subtaskId]: "" };

  try {
    await api.updateSubtaskStage(context.orgId, subtaskId, workflowStageId);
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    stageUpdateErrorBySubtaskId.value = {
      ...stageUpdateErrorBySubtaskId.value,
      [subtaskId]: err instanceof Error ? err.message : String(err),
    };
  } finally {
    stageUpdateSavingSubtaskId.value = "";
  }
}
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
        <p class="muted">
          <span class="chip">{{ task.status }}</span>
          <span class="chip">Progress {{ formatPercent(task.progress) }}</span>
          <span class="chip">Updated {{ formatTimestamp(task.updated_at) }}</span>
        </p>

        <p v-if="epic" class="muted">
          <span class="muted">Epic:</span> <strong>{{ epic.title }}</strong>
          <span class="chip">Progress {{ formatPercent(epic.progress) }}</span>
        </p>

        <p v-if="task.description">{{ task.description }}</p>

        <div v-if="project && !workflowId" class="card warn">
          This project has no workflow assigned. Stage changes are disabled.
        </div>

        <TrustPanel
          title="Task trust panel (progress transparency)"
          :progress="task.progress"
          :updated-at="task.updated_at ?? null"
          :progress-why="task.progress_why"
        />

        <TrustPanel
          v-if="epic"
          title="Epic trust panel (progress transparency)"
          :progress="epic.progress"
          :updated-at="epic.updated_at"
          :progress-why="epic.progress_why"
        />

        <h2 class="section-title">Subtasks</h2>
        <p v-if="subtasks.length === 0" class="muted">No subtasks yet.</p>
        <ul v-else class="subtask-list">
          <li v-for="subtask in subtasks" :key="subtask.id" class="subtask">
            <div class="subtask-main">
              <div class="subtask-title">{{ subtask.title }}</div>
              <div class="muted subtask-meta">
                <span class="chip">{{ subtask.status }}</span>
                <span class="chip">Progress {{ formatPercent(subtask.progress) }}</span>
                <span class="chip">Updated {{ formatTimestamp(subtask.updated_at) }}</span>
              </div>
            </div>

            <div class="subtask-stage">
              <label class="field">
                <span class="label">Stage</span>

                <select
                  v-if="canEditStages && workflowId && stages.length > 0"
                  :value="subtask.workflow_stage_id ?? ''"
                  :disabled="stageUpdateSavingSubtaskId === subtask.id"
                  @change="onStageChange(subtask.id, $event)"
                >
                  <option value="">(unassigned)</option>
                  <option v-for="stage in stages" :key="stage.id" :value="stage.id">
                    {{ stage.order }}. {{ stage.name }}{{ stage.is_done ? " (Done)" : "" }}
                  </option>
                </select>

                <div v-else class="muted">{{ stageLabel(subtask.workflow_stage_id) }}</div>

                <div v-if="stageUpdateErrorBySubtaskId[subtask.id]" class="error">
                  {{ stageUpdateErrorBySubtaskId[subtask.id] }}
                </div>
              </label>
            </div>
          </li>
        </ul>

        <div class="collaboration">
          <h2 class="section-title">Collaboration</h2>
          <div v-if="collabError" class="error">{{ collabError }}</div>

          <div class="collaboration-grid">
            <div class="card comments">
              <h3>Comments</h3>

              <div v-if="comments.length === 0" class="muted">No comments yet.</div>
              <div v-else class="comment-list">
                <div v-for="comment in comments" :key="comment.id" class="comment">
                  <div class="comment-meta">
                    <span class="comment-author">{{
                      comment.author.display_name || comment.author.id
                    }}</span>
                    <span class="muted">{{ new Date(comment.created_at).toLocaleString() }}</span>
                  </div>
                  <!-- body_html is sanitized server-side -->
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <div class="comment-body" v-html="comment.body_html"></div>
                </div>
              </div>

              <div class="comment-form">
                <textarea
                  v-model="commentDraft"
                  rows="4"
                  placeholder="Write a comment (Markdown supported)…"
                />
                <button class="primary" type="button" @click="submitComment">Post comment</button>
              </div>
            </div>

            <div class="card attachments">
              <h3>Attachments</h3>

              <div v-if="attachments.length === 0" class="muted">No attachments yet.</div>
              <div v-else class="attachment-list">
                <div v-for="attachment in attachments" :key="attachment.id" class="attachment-row">
                  <div class="attachment-name">{{ attachment.filename }}</div>
                  <div class="attachment-meta muted">
                    {{ attachment.size_bytes }} bytes • {{ attachment.content_type }}
                  </div>
                  <a class="attachment-link" :href="attachment.download_url">Download</a>
                </div>
              </div>

              <div class="attachment-form">
                <input type="file" @change="onFileChange" />
                <button
                  type="button"
                  class="primary"
                  :disabled="!selectedFile"
                  @click="uploadAttachment"
                >
                  Upload
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  margin-top: 1rem;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.85rem;
  padding: 0.1rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #f8fafc;
  margin-right: 0.5rem;
  margin-top: 0.25rem;
}

.section-title {
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
  font-size: 1.1rem;
}

.warn {
  margin-top: 1rem;
  border-color: #fde68a;
  background: #fffbeb;
}

.subtask-list {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.subtask {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem;
  display: grid;
  grid-template-columns: 1fr 260px;
  gap: 0.75rem;
}

.subtask-title {
  font-weight: 700;
}

.subtask-meta {
  margin-top: 0.25rem;
}

.subtask-stage {
  display: flex;
  justify-content: flex-end;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 220px;
}

.label {
  font-size: 0.85rem;
  color: var(--muted);
}

@media (max-width: 720px) {
  .subtask {
    grid-template-columns: 1fr;
  }

  .subtask-stage {
    justify-content: flex-start;
  }
}

.collaboration-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-top: 0.75rem;
}

.comment-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.comment-meta {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
}

.comment-author {
  font-weight: 600;
}

.comment-body :deep(p) {
  margin: 0.25rem 0 0;
}

.comment-form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.attachment-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.attachment-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.25rem 0.75rem;
  align-items: center;
}

.attachment-meta {
  grid-column: 1 / -1;
}

.attachment-link {
  justify-self: end;
}

.attachment-form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
