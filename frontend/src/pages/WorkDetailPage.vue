<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import GitLabLinksCard from "../components/GitLabLinksCard.vue";
import TrustPanel from "../components/TrustPanel.vue";
import VlLabel from "../components/VlLabel.vue";
import type {
  Attachment,
  Comment,
  CustomFieldDefinition,
  Epic,
  Project,
  Subtask,
  Task,
  WorkflowStage,
} from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatPercent, formatTimestamp, progressLabelColor } from "../utils/format";
import { taskStatusLabelColor } from "../utils/labels";

const props = defineProps<{ taskId: string }>();
const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const task = ref<Task | null>(null);
const customFields = ref<CustomFieldDefinition[]>([]);
const customFieldDraft = ref<Record<string, unknown>>({});
const initialCustomFieldValues = ref<Record<string, unknown | null>>({});
const loadingCustomFields = ref(false);
const savingCustomFields = ref(false);
const customFieldError = ref("");

const comments = ref<Comment[]>([]);
const attachments = ref<Attachment[]>([]);
const commentDraft = ref("");
const commentClientSafe = ref(false);
const selectedFile = ref<File | null>(null);
const epic = ref<Epic | null>(null);
const project = ref<Project | null>(null);
const subtasks = ref<Subtask[]>([]);
const stages = ref<WorkflowStage[]>([]);

const loading = ref(false);
const error = ref("");
const collabError = ref("");
const clientSafeError = ref("");
const savingClientSafe = ref(false);
const stageUpdateErrorBySubtaskId = ref<Record<string, string>>({});
const stageUpdateSavingSubtaskId = ref("");

const socket = ref<WebSocket | null>(null);
let socketReconnectAttempt = 0;
let socketReconnectTimeoutId: number | null = null;
let socketDesiredOrgId: string | null = null;

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canEditStages = computed(() => currentRole.value === "admin" || currentRole.value === "pm");
const canEditCustomFields = computed(() => canEditStages.value);
const canEditClientSafe = computed(() => canEditStages.value);
const canManageGitLabIntegration = computed(() => canEditStages.value);
const canManageGitLabLinks = computed(
  () => canManageGitLabIntegration.value || currentRole.value === "member"
);

const stageById = computed(() => {
  const map: Record<string, WorkflowStage> = {};
  for (const stage of stages.value) {
    map[stage.id] = stage;
  }
  return map;
});

const workflowId = computed(() => project.value?.workflow_id ?? null);
const projectId = computed(() => project.value?.id ?? context.projectId ?? null);

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
  clientSafeError.value = "";
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
    commentClientSafe.value = false;
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

    const nextProjectId = epic.value?.project_id ?? context.projectId;
    if (nextProjectId) {
      try {
        const projectRes = await api.getProject(context.orgId, nextProjectId);
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

async function refreshCustomFields() {
  customFieldError.value = "";

  if (!context.orgId || !projectId.value) {
    customFields.value = [];
    return;
  }

  loadingCustomFields.value = true;
  try {
    const res = await api.listCustomFields(context.orgId, projectId.value);
    customFields.value = res.custom_fields;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    customFields.value = [];
    customFieldError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingCustomFields.value = false;
  }
}

function formatCustomFieldValue(field: CustomFieldDefinition, value: unknown): string {
  if (value == null) {
    return "";
  }
  if (field.field_type === "multi_select") {
    return Array.isArray(value) ? value.join(", ") : String(value);
  }
  return String(value);
}

function initCustomFieldDraft() {
  if (!task.value) {
    customFieldDraft.value = {};
    initialCustomFieldValues.value = {};
    return;
  }

  const valueMap = new Map((task.value.custom_field_values ?? []).map((v) => [v.field_id, v.value]));
  const nextDraft: Record<string, unknown> = {};
  const nextInitial: Record<string, unknown | null> = {};

  for (const field of customFields.value) {
    const current = valueMap.get(field.id);
    if (current == null) {
      if (field.field_type === "multi_select") {
        nextDraft[field.id] = [];
      } else {
        nextDraft[field.id] = "";
      }
      nextInitial[field.id] = null;
    } else {
      nextDraft[field.id] = current;
      nextInitial[field.id] = current as unknown;
    }
  }

  customFieldDraft.value = nextDraft;
  initialCustomFieldValues.value = nextInitial;
}

function valuesEqual(a: unknown | null, b: unknown | null): boolean {
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b)) {
      return false;
    }
    return JSON.stringify(a) === JSON.stringify(b);
  }
  return a === b;
}

function normalizeDraftValue(field: CustomFieldDefinition, raw: unknown): unknown | null {
  if (field.field_type === "multi_select") {
    const values = Array.isArray(raw) ? raw.filter((v) => typeof v === "string") : [];
    return values.length ? values : null;
  }

  if (field.field_type === "number") {
    if (raw == null || raw === "") {
      return null;
    }
    const n = typeof raw === "number" ? raw : Number(raw);
    if (Number.isNaN(n)) {
      throw new Error(`"${field.name}" must be a number`);
    }
    return n;
  }

  const text = String(raw ?? "").trim();
  return text ? text : null;
}

async function saveCustomFieldValues() {
  if (!context.orgId || !task.value) {
    return;
  }

  savingCustomFields.value = true;
  customFieldError.value = "";
  try {
    const values: Record<string, unknown | null> = {};
    for (const field of customFields.value) {
      const nextNormalized = normalizeDraftValue(field, customFieldDraft.value[field.id]);
      const prior = initialCustomFieldValues.value[field.id] ?? null;
      if (valuesEqual(nextNormalized, prior)) {
        continue;
      }
      values[field.id] = nextNormalized;
    }

    if (!Object.keys(values).length) {
      return;
    }

    await api.patchTaskCustomFieldValues(context.orgId, task.value.id, values);
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    customFieldError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingCustomFields.value = false;
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
    await api.createTaskComment(context.orgId, props.taskId, body, {
      client_safe: commentClientSafe.value,
    });
    commentDraft.value = "";
    commentClientSafe.value = false;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    collabError.value = err instanceof Error ? err.message : String(err);
  }
}

async function onClientSafeToggle(event: Event) {
  if (!context.orgId || !task.value) {
    return;
  }
  if (!canEditClientSafe.value) {
    return;
  }

  clientSafeError.value = "";
  const nextClientSafe = (event.target as HTMLInputElement).checked;

  savingClientSafe.value = true;
  try {
    const res = await api.patchTask(context.orgId, task.value.id, { client_safe: nextClientSafe });
    task.value = res.task;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    clientSafeError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingClientSafe.value = false;
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

function realtimeUrl(orgId: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/orgs/${orgId}/events`;
}

function stopRealtime() {
  socketDesiredOrgId = null;

  if (socketReconnectTimeoutId != null) {
    window.clearTimeout(socketReconnectTimeoutId);
    socketReconnectTimeoutId = null;
  }

  if (socket.value) {
    socket.value.close();
    socket.value = null;
  }
}

function scheduleRealtimeReconnect(orgId: string) {
  if (socketReconnectTimeoutId != null) {
    return;
  }

  const delayMs = Math.min(10_000, 1_000 * 2 ** socketReconnectAttempt);
  socketReconnectAttempt = Math.min(socketReconnectAttempt + 1, 10);

  socketReconnectTimeoutId = window.setTimeout(() => {
    socketReconnectTimeoutId = null;
    if (context.orgId !== orgId || socketDesiredOrgId !== orgId) {
      return;
    }
    startRealtime();
  }, delayMs);
}

function startRealtime() {
  stopRealtime();

  if (!context.orgId) {
    return;
  }
  if (typeof WebSocket === "undefined") {
    return;
  }

  const orgId = context.orgId;
  socketDesiredOrgId = orgId;

  const ws = new WebSocket(realtimeUrl(orgId));
  socket.value = ws;

  ws.onopen = () => {
    socketReconnectAttempt = 0;
  };

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(String(event.data)) as unknown;
      if (!payload || typeof payload !== "object") {
        return;
      }

      const typed = payload as Record<string, unknown>;
      const type = String(typed.type ?? "");
      const data = typed.data;

      if (!data || typeof data !== "object") {
        return;
      }

      const dataObj = data as Record<string, unknown>;

      if (type === "work_item.updated") {
        if (String(dataObj.task_id ?? "") === props.taskId) {
          void refresh();
        }
        return;
      }

      if (type === "comment.created") {
        if (String(dataObj.work_item_type ?? "") !== "task") {
          return;
        }
        if (String(dataObj.work_item_id ?? "") === props.taskId) {
          void refresh();
        }
      }
    } catch {
      return;
    }
  };

  ws.onclose = (event) => {
    socket.value = null;

    if (socketDesiredOrgId !== orgId || context.orgId !== orgId) {
      return;
    }
    if (event.code === 4400 || event.code === 4401 || event.code === 4403) {
      return;
    }

    scheduleRealtimeReconnect(orgId);
  };
}

watch(() => [context.orgId, props.taskId], () => void refresh(), { immediate: true });
watch(() => [context.orgId, projectId.value], () => void refreshCustomFields(), { immediate: true });
watch(() => context.orgId, () => startRealtime(), { immediate: true });

watch(
  () => [task.value, customFields.value],
  () => {
    initCustomFieldDraft();
  }
);

onBeforeUnmount(() => stopRealtime());
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
        <div class="labels">
          <VlLabel :color="taskStatusLabelColor(task.status)">{{ task.status }}</VlLabel>
          <VlLabel :color="task.client_safe ? 'green' : 'orange'">
            Client {{ task.client_safe ? "visible" : "hidden" }}
          </VlLabel>
          <VlLabel :color="progressLabelColor(task.progress)">Progress {{ formatPercent(task.progress) }}</VlLabel>
          <VlLabel color="blue">Updated {{ formatTimestamp(task.updated_at ?? "") }}</VlLabel>
        </div>

        <p v-if="epic">
          <span class="muted">Epic:</span> <strong>{{ epic.title }}</strong>
          <VlLabel :color="progressLabelColor(epic.progress)">Progress {{ formatPercent(epic.progress) }}</VlLabel>
        </p>

        <p v-if="task.description">{{ task.description }}</p>

        <div class="card client-visibility">
          <h2 class="section-title">Client portal</h2>

          <label v-if="canEditClientSafe" class="field-inline">
            <input
              type="checkbox"
              :checked="Boolean(task.client_safe)"
              :disabled="savingClientSafe"
              @change="onClientSafeToggle"
            />
            <span>Visible to client (enables client portal list/detail + comments)</span>
          </label>

          <div v-else class="muted">Visible to client: {{ task.client_safe ? "Yes" : "No" }}</div>

          <div v-if="clientSafeError" class="error">{{ clientSafeError }}</div>
        </div>

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

        <GitLabLinksCard
          :org-id="context.orgId"
          :task-id="props.taskId"
          :can-manage-integration="canManageGitLabIntegration"
          :can-manage-links="canManageGitLabLinks"
        />

        <div class="custom-fields">
          <h2 class="section-title">Custom fields</h2>

          <div v-if="loadingCustomFields" class="muted">Loading custom fields…</div>
          <div v-else-if="customFieldError" class="error">{{ customFieldError }}</div>
          <div v-else-if="customFields.length === 0" class="muted">No custom fields yet.</div>
          <div v-else class="custom-field-grid">
            <div v-for="field in customFields" :key="field.id" class="custom-field-row">
              <div class="custom-field-label">{{ field.name }}</div>

              <div v-if="canEditCustomFields" class="custom-field-input">
                <input v-if="field.field_type === 'text'" v-model="customFieldDraft[field.id]" type="text" />
                <input
                  v-else-if="field.field_type === 'number'"
                  v-model="customFieldDraft[field.id]"
                  type="number"
                  step="any"
                />
                <input v-else-if="field.field_type === 'date'" v-model="customFieldDraft[field.id]" type="date" />
                <select v-else-if="field.field_type === 'select'" v-model="customFieldDraft[field.id]">
                  <option value="">(none)</option>
                  <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>
                <select v-else-if="field.field_type === 'multi_select'" v-model="customFieldDraft[field.id]" multiple>
                  <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>
              </div>

              <div v-else class="muted">
                {{
                  formatCustomFieldValue(
                    field,
                    task.custom_field_values.find((v) => v.field_id === field.id)?.value
                  ) || "—"
                }}
              </div>
            </div>

            <button
              v-if="canEditCustomFields"
              type="button"
              class="primary save-custom-fields"
              :disabled="savingCustomFields"
              @click="saveCustomFieldValues"
            >
              Save custom fields
            </button>
          </div>
        </div>

        <h2 class="section-title">Subtasks</h2>
        <p v-if="subtasks.length === 0" class="muted">No subtasks yet.</p>
        <ul v-else class="subtask-list">
          <li v-for="subtask in subtasks" :key="subtask.id" class="subtask">
            <div class="subtask-main">
              <div class="subtask-title">{{ subtask.title }}</div>
              <div class="subtask-meta labels">
                <VlLabel :color="taskStatusLabelColor(subtask.status)">{{ subtask.status }}</VlLabel>
                <VlLabel :color="progressLabelColor(subtask.progress)">
                  Progress {{ formatPercent(subtask.progress) }}
                </VlLabel>
                <VlLabel color="blue">Updated {{ formatTimestamp(subtask.updated_at ?? '') }}</VlLabel>
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
                    <span class="comment-author">{{ comment.author.display_name || comment.author.id }}</span>
                    <VlLabel :color="comment.client_safe ? 'teal' : 'orange'">
                      {{ comment.client_safe ? "Client" : "Internal" }}
                    </VlLabel>
                    <span class="muted">{{ new Date(comment.created_at).toLocaleString() }}</span>
                  </div>
                  <!-- body_html is sanitized server-side -->
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <div class="comment-body" v-html="comment.body_html"></div>
                </div>
              </div>

              <div class="comment-form">
                <textarea v-model="commentDraft" rows="4" placeholder="Write a comment (Markdown supported)…" />
                <label class="field-inline">
                  <input v-model="commentClientSafe" type="checkbox" />
                  <span>Visible to client</span>
                </label>
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
                <button type="button" class="primary" :disabled="!selectedFile" @click="uploadAttachment">
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

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
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

.custom-fields {
  margin-top: 1.5rem;
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}

.custom-field-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.custom-field-row {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 0.75rem;
  align-items: center;
}

.custom-field-label {
  font-weight: 600;
}

.custom-field-input input,
.custom-field-input select {
  width: 100%;
}

.save-custom-fields {
  align-self: start;
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

.field-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.label {
  font-size: 0.85rem;
  color: var(--muted);
}

.client-visibility {
  margin-top: 1rem;
  border-color: #e5e7eb;
  background: #fafafa;
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
