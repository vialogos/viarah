<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import GitLabLinksCard from "../components/GitLabLinksCard.vue";
import TrustPanel from "../components/TrustPanel.vue";
import VlLabel from "../components/VlLabel.vue";
import VlLabelGroup from "../components/VlLabelGroup.vue";
import type {
  Attachment,
  Comment,
  CustomFieldDefinition,
  Epic,
  Project,
  ProjectMembershipWithUser,
  Subtask,
  Task,
  TaskParticipant,
  WorkflowStage,
} from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatPercent, formatTimestamp, progressLabelColor } from "../utils/format";
import { taskStatusLabelColor, workItemStatusLabel, type VlLabelColor } from "../utils/labels";

const props = defineProps<{ taskId: string }>();
const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

function normalizeQueryParam(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === "string") {
    return value[0];
  }
  return "";
}

const effectiveOrgId = computed(() => context.orgId || normalizeQueryParam(route.query.orgId));
const projectIdFromQuery = computed(() => normalizeQueryParam(route.query.projectId) || null);
const canWrite = computed(() => {
  const orgId = effectiveOrgId.value;
  if (!orgId) {
    return false;
  }
  const role = session.memberships.find((m) => m.org.id === orgId)?.role ?? "";
  return Boolean(role) && role !== "client";
});

const task = ref<Task | null>(null);
const customFields = ref<CustomFieldDefinition[]>([]);
const customFieldDraft = ref<Record<string, string | number | string[] | null>>({});
const initialCustomFieldValues = ref<Record<string, string | number | string[] | null>>({});
const loadingCustomFields = ref(false);
const savingCustomFields = ref(false);
const customFieldError = ref("");

const comments = ref<Comment[]>([]);
const attachments = ref<Attachment[]>([]);
const commentDraft = ref("");
const commentClientSafe = ref(false);
const selectedFile = ref<File | null>(null);
const attachmentUploadKey = ref(0);
const uploadingAttachment = ref(false);
const epic = ref<Epic | null>(null);
const project = ref<Project | null>(null);
const projectMemberships = ref<ProjectMembershipWithUser[]>([]);
const loadingProjectMemberships = ref(false);
const savingAssignee = ref(false);
const assignmentError = ref("");
const assignmentDrawerExpanded = ref(false);

const ASSIGNEE_UNASSIGNED_MENU_ID = "__unassigned__";
const ASSIGNEE_MAX_RESULTS = 50;
const assigneeSelectOpen = ref(false);
const assigneeQuery = ref("");

const taskStartDateDraft = ref("");
const taskEndDateDraft = ref("");
const savingSchedule = ref(false);
const scheduleError = ref("");

const participants = ref<TaskParticipant[]>([]);
const loadingParticipants = ref(false);
const participantError = ref("");
const participantToAddUserId = ref("");
const savingParticipant = ref(false);
const removingParticipantUserId = ref("");
const subtasks = ref<Subtask[]>([]);
const stages = ref<WorkflowStage[]>([]);

const createSubtaskModalOpen = ref(false);
const createSubtaskTitle = ref("");
const createSubtaskDescription = ref("");
const createSubtaskStatus = ref("backlog");
const createSubtaskStartDate = ref("");
const createSubtaskEndDate = ref("");
const creatingSubtask = ref(false);
const createSubtaskError = ref("");

const loading = ref(false);
const error = ref("");
const collabError = ref("");
const clientSafeError = ref("");
const savingClientSafe = ref(false);
const taskStageSaving = ref(false);
const taskStageError = ref("");
const taskProgressSaving = ref(false);
const taskProgressError = ref("");
const epicProgressSaving = ref(false);
const epicProgressError = ref("");
const stageUpdateErrorBySubtaskId = ref<Record<string, string>>({});
const stageUpdateSavingSubtaskId = ref("");

const socket = ref<WebSocket | null>(null);
let socketReconnectAttempt = 0;
let socketReconnectTimeoutId: number | null = null;
let socketDesiredOrgId: string | null = null;

const currentRole = computed(() => {
  const orgId = effectiveOrgId.value;
  if (!orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === orgId)?.role ?? "";
});

const canAuthorWork = computed(() => {
  if (!canWrite.value) {
    return false;
  }
  return currentRole.value === "admin" || currentRole.value === "pm" || currentRole.value === "member";
});

const canEditStages = computed(() => canWrite.value && (currentRole.value === "admin" || currentRole.value === "pm"));
const canEditCustomFields = computed(() => canEditStages.value);
const canEditClientSafe = computed(() => canEditStages.value);
const canManageGitLabIntegration = computed(() => canEditStages.value);
const canManageGitLabLinks = computed(() => {
  if (!canWrite.value) {
    return false;
  }
  return canManageGitLabIntegration.value || currentRole.value === "member";
});

const stageById = computed(() => {
  const map: Record<string, WorkflowStage> = {};
  for (const stage of stages.value) {
    map[stage.id] = stage;
  }
  return map;
});

const workflowId = computed(() => project.value?.workflow_id ?? null);
const projectId = computed(() => project.value?.id ?? context.projectId ?? projectIdFromQuery.value ?? null);

const projectMemberByUserId = computed(() => {
  const map: Record<string, ProjectMembershipWithUser> = {};
  for (const m of projectMemberships.value) {
    map[m.user.id] = m;
  }
  return map;
});

const assignableMembers = computed(() => projectMemberships.value.filter((m) => m.role !== "client"));

function assignableMemberLabel(membership: ProjectMembershipWithUser): string {
  return membership.user.display_name || membership.user.email || membership.user.id;
}

function assignableMemberDescription(membership: ProjectMembershipWithUser): string {
  const name = (membership.user.display_name || "").trim().toLowerCase();
  const email = (membership.user.email || "").trim();
  if (name && email && email.trim().toLowerCase() !== name) {
    return email;
  }
  return "";
}

const sortedAssignableMembers = computed(() =>
  assignableMembers.value
    .slice()
    .sort((a, b) => assignableMemberLabel(a).localeCompare(assignableMemberLabel(b)))
);

const assigneeMenu = computed(() => {
  const q = assigneeQuery.value.trim().toLowerCase();
  const members = sortedAssignableMembers.value;

  if (!q) {
    return {
      results: members.slice(0, ASSIGNEE_MAX_RESULTS),
      truncated: members.length > ASSIGNEE_MAX_RESULTS,
    };
  }

  const results: ProjectMembershipWithUser[] = [];
  let truncated = false;

  for (const membership of members) {
    const label = assignableMemberLabel(membership).toLowerCase();
    const email = (membership.user.email || "").toLowerCase();
    if (!label.includes(q) && !email.includes(q)) {
      continue;
    }

    results.push(membership);
    if (results.length >= ASSIGNEE_MAX_RESULTS) {
      truncated = true;
      break;
    }
  }

  return { results, truncated };
});

const projectMembersSettingsTo = computed(() => {
  if (!projectId.value) {
    return { path: "/settings/project" };
  }
  return {
    path: "/settings/project",
    query: { projectId: projectId.value },
    hash: "#project-members",
  };
});

const participantsDisplay = computed(() => {
  const names = participants.value
    .map((p) => (p.user.display_name || p.user.email || "").trim())
    .filter((name) => Boolean(name));
  const unique = Array.from(new Set(names));
  if (!unique.length) {
    return "";
  }
  const shown = unique.slice(0, 3);
  const remaining = unique.length - shown.length;
  if (remaining > 0) {
    return `${shown.join(", ")} +${remaining}`;
  }
  return shown.join(", ");
});

function shortUserId(userId: string): string {
  const trimmed = (userId || "").trim();
  if (trimmed.length <= 12) {
    return trimmed;
  }
  return `${trimmed.slice(0, 8)}…${trimmed.slice(-4)}`;
}

const assigneeDisplay = computed(() => {
  const assigneeUserId = task.value?.assignee_user_id ?? null;
  if (!assigneeUserId) {
    return "";
  }
  const member = projectMemberByUserId.value[assigneeUserId];
  if (member) {
    return member.user.display_name || member.user.email;
  }
  return shortUserId(assigneeUserId);
});

function stageLabel(stageId: string | null | undefined): string {
  if (!stageId) {
    return "(unassigned)";
  }
  const stage = stageById.value[stageId];
  return stage ? stage.name : "(unknown stage)";
}

function stageLabelColor(stageId: string | null | undefined): VlLabelColor {
  if (!stageId) {
    return "blue";
  }

  const stage = stageById.value[stageId];
  if (!stage) {
    return "teal";
  }
  if (stage.is_done) {
    return "green";
  }
  if (stage.is_qa) {
    return "purple";
  }
  if (stage.counts_as_wip) {
    return "orange";
  }
  return "teal";
}

function participantSourceLabel(source: string): string {
  if (source === "manual") {
    return "Manual";
  }
  if (source === "assignee") {
    return "Assignee";
  }
  if (source === "comment") {
    return "Commented";
  }
  if (source === "gitlab") {
    return "GitLab";
  }
  return source;
}

function participantSourceColor(source: string): VlLabelColor {
  if (source === "manual") {
    return "grey";
  }
  if (source === "assignee") {
    return "teal";
  }
  if (source === "comment") {
    return "blue";
  }
  if (source === "gitlab") {
    return "purple";
  }
  return "blue";
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

const STATUS_OPTIONS = [
  { value: "backlog", label: "Backlog" },
  { value: "in_progress", label: "In progress" },
  { value: "qa", label: "QA" },
  { value: "done", label: "Done" },
] as const;

async function refresh() {
  error.value = "";
  collabError.value = "";
  clientSafeError.value = "";
  stageUpdateErrorBySubtaskId.value = {};

  const orgId = effectiveOrgId.value;
  if (!orgId) {
    task.value = null;
    epic.value = null;
    project.value = null;
    subtasks.value = [];
    stages.value = [];
    comments.value = [];
    attachments.value = [];
    participants.value = [];
    participantError.value = "";
    participantToAddUserId.value = "";
    assignmentDrawerExpanded.value = false;
    taskStartDateDraft.value = "";
    taskEndDateDraft.value = "";
    scheduleError.value = "";
    commentDraft.value = "";
    commentClientSafe.value = false;
    selectedFile.value = null;
    return;
  }

  loading.value = true;
  try {
    const [taskRes, subtasksRes] = await Promise.all([
      api.getTask(orgId, props.taskId),
      api.listSubtasks(orgId, props.taskId),
    ]);
    task.value = taskRes.task;
    taskStartDateDraft.value = taskRes.task.start_date ?? "";
    taskEndDateDraft.value = taskRes.task.end_date ?? "";
    subtasks.value = subtasksRes.subtasks;

    epic.value = null;
    project.value = null;
    stages.value = [];

    try {
      const epicRes = await api.getEpic(orgId, taskRes.task.epic_id);
      epic.value = epicRes.epic;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await handleUnauthorized();
        return;
      }
    }

    const nextProjectId = epic.value?.project_id ?? context.projectId ?? projectIdFromQuery.value;
    if (nextProjectId) {
      try {
        const projectRes = await api.getProject(orgId, nextProjectId);
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
        const stageRes = await api.listWorkflowStages(orgId, project.value.workflow_id);
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
    participants.value = [];
    participantError.value = "";
    error.value = err instanceof Error ? err.message : String(err);
    taskStartDateDraft.value = "";
    taskEndDateDraft.value = "";
    scheduleError.value = "";
    return;
  } finally {
    loading.value = false;
  }

  try {
    const commentsRes = await api.listTaskComments(orgId, props.taskId);
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
    const attachmentsRes = await api.listTaskAttachments(orgId, props.taskId);
    attachments.value = attachmentsRes.attachments;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    attachments.value = [];
    collabError.value = err instanceof Error ? err.message : String(err);
  }

  loadingParticipants.value = true;
  try {
    participantError.value = "";
    const participantsRes = await api.listTaskParticipants(orgId, props.taskId);
    participants.value = participantsRes.participants;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    participants.value = [];
    participantError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingParticipants.value = false;
  }
}

async function refreshCustomFields() {
  customFieldError.value = "";

  const orgId = effectiveOrgId.value;
  if (!canWrite.value || !orgId || !projectId.value) {
    customFields.value = [];
    return;
  }

  loadingCustomFields.value = true;
  try {
    const res = await api.listCustomFields(orgId, projectId.value);
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

function updateCustomFieldDraft(fieldId: string, value: string | number | string[] | null) {
  customFieldDraft.value[fieldId] = value;
}

async function refreshProjectMemberships() {
  assignmentError.value = "";

  const orgId = effectiveOrgId.value;
  if (!orgId || !projectId.value) {
    projectMemberships.value = [];
    return;
  }

  if (!canEditStages.value) {
    projectMemberships.value = [];
    return;
  }

  loadingProjectMemberships.value = true;
  try {
    const res = await api.listProjectMemberships(orgId, projectId.value);
    projectMemberships.value = res.memberships;
  } catch (err) {
    projectMemberships.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      assignmentError.value = "Not permitted.";
      return;
    }
    assignmentError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingProjectMemberships.value = false;
  }
}

async function onAssigneeChange(value: unknown) {
  const orgId = effectiveOrgId.value;
  if (!orgId || !task.value) {
    return;
  }
  if (!canEditStages.value) {
    return;
  }

  const raw = Array.isArray(value) ? value[0] ?? "" : String(value ?? "");
  const nextAssigneeUserId = raw ? raw : null;

  assignmentError.value = "";
  savingAssignee.value = true;
  try {
    const res = await api.patchTask(orgId, task.value.id, { assignee_user_id: nextAssigneeUserId });
    task.value = res.task;
    try {
      const participantsRes = await api.listTaskParticipants(orgId, task.value.id);
      participants.value = participantsRes.participants;
    } catch {
      // Best-effort refresh; websocket events will also trigger `refresh()`.
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      assignmentError.value = "Not permitted.";
      return;
    }
    assignmentError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingAssignee.value = false;
  }
}

async function onAssigneeSelected(value: unknown) {
  const raw = Array.isArray(value) ? value[0] ?? "" : String(value ?? "");

  assigneeSelectOpen.value = false;
  assigneeQuery.value = "";

  if (!raw || raw === ASSIGNEE_UNASSIGNED_MENU_ID) {
    await onAssigneeChange("");
    return;
  }
  await onAssigneeChange(raw);
}

async function assignToMe() {
  if (!session.user?.id) {
    return;
  }
  await onAssigneeChange(session.user.id);
}

async function unassign() {
  await onAssigneeChange("");
}

async function saveSchedule() {
  const orgId = effectiveOrgId.value;
  if (!orgId || !task.value) {
    return;
  }
  if (!canEditStages.value) {
    return;
  }

  const startDate = taskStartDateDraft.value.trim();
  const endDate = taskEndDateDraft.value.trim();
  const payload = {
    start_date: startDate ? startDate : null,
    end_date: endDate ? endDate : null,
  };

  scheduleError.value = "";
  savingSchedule.value = true;
  try {
    const res = await api.patchTask(orgId, task.value.id, payload);
    task.value = res.task;
    taskStartDateDraft.value = res.task.start_date ?? "";
    taskEndDateDraft.value = res.task.end_date ?? "";
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      scheduleError.value = "Not permitted.";
      return;
    }
    scheduleError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingSchedule.value = false;
  }
}

async function clearSchedule() {
  taskStartDateDraft.value = "";
  taskEndDateDraft.value = "";
  await saveSchedule();
}

function onParticipantToAddChange(value: unknown) {
  const raw = Array.isArray(value) ? value[0] ?? "" : String(value ?? "");
  participantToAddUserId.value = raw;
}

async function addManualParticipant() {
  const orgId = effectiveOrgId.value;
  if (!orgId || !task.value) {
    return;
  }
  if (!canEditStages.value) {
    return;
  }

  const userId = participantToAddUserId.value.trim();
  if (!userId) {
    return;
  }

  participantError.value = "";
  savingParticipant.value = true;
  try {
    await api.createTaskParticipant(orgId, task.value.id, userId);
    participantToAddUserId.value = "";
    const participantsRes = await api.listTaskParticipants(orgId, task.value.id);
    participants.value = participantsRes.participants;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      participantError.value = "Not permitted.";
      return;
    }
    participantError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingParticipant.value = false;
  }
}

async function removeManualParticipant(userId: string) {
  const orgId = effectiveOrgId.value;
  if (!orgId || !task.value) {
    return;
  }
  if (!canEditStages.value) {
    return;
  }

  participantError.value = "";
  removingParticipantUserId.value = userId;
  try {
    await api.deleteTaskParticipant(orgId, task.value.id, userId);
    const participantsRes = await api.listTaskParticipants(orgId, task.value.id);
    participants.value = participantsRes.participants;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      participantError.value = "Not permitted.";
      return;
    }
    participantError.value = err instanceof Error ? err.message : String(err);
  } finally {
    removingParticipantUserId.value = "";
  }
}


function initCustomFieldDraft() {
  if (!task.value) {
    customFieldDraft.value = {};
    initialCustomFieldValues.value = {};
    return;
  }

  const valueMap = new Map((task.value.custom_field_values ?? []).map((v) => [v.field_id, v.value]));
  const nextDraft: Record<string, string | number | string[] | null> = {};
  const nextInitial: Record<string, string | number | string[] | null> = {};

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
      nextDraft[field.id] = current as string | number | string[] | null;
      nextInitial[field.id] = current as string | number | string[] | null;
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
  if (!canEditCustomFields.value) {
    return;
  }
  const orgId = effectiveOrgId.value;
  if (!orgId || !task.value) {
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

    await api.patchTaskCustomFieldValues(orgId, task.value.id, values);
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
  if (!canAuthorWork.value) {
    return;
  }
  const orgId = effectiveOrgId.value;
  if (!orgId) {
    return;
  }

  collabError.value = "";
  const body = commentDraft.value.trim();
  if (!body) {
    return;
  }

  try {
    await api.createTaskComment(orgId, props.taskId, body, {
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

async function onClientSafeToggle(nextClientSafe: boolean) {
  const orgId = effectiveOrgId.value;
  if (!orgId || !task.value) {
    return;
  }
  if (!canEditClientSafe.value) {
    return;
  }

  clientSafeError.value = "";
  savingClientSafe.value = true;
  try {
    const res = await api.patchTask(orgId, task.value.id, { client_safe: nextClientSafe });
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
  if (!canAuthorWork.value) {
    return;
  }
  const orgId = effectiveOrgId.value;
  if (!orgId) {
    return;
  }
  if (!selectedFile.value) {
    return;
  }

  collabError.value = "";
  uploadingAttachment.value = true;
  try {
    await api.uploadTaskAttachment(orgId, props.taskId, selectedFile.value);
    selectedFile.value = null;
    attachmentUploadKey.value += 1;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    collabError.value = err instanceof Error ? err.message : String(err);
  } finally {
    uploadingAttachment.value = false;
  }
}

function onSelectedFileChange(file: File | null) {
  selectedFile.value = file ?? null;
}

async function onStageChange(subtaskId: string, value: string | string[] | null | undefined) {
  if (!canEditStages.value) {
    return;
  }
  const orgId = effectiveOrgId.value;
  if (!orgId) {
    return;
  }

  const raw = Array.isArray(value) ? value[0] ?? "" : value ?? "";
  const workflowStageId = raw ? raw : null;

  stageUpdateSavingSubtaskId.value = subtaskId;
  stageUpdateErrorBySubtaskId.value = { ...stageUpdateErrorBySubtaskId.value, [subtaskId]: "" };

  try {
    await api.updateSubtaskStage(orgId, subtaskId, workflowStageId);
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

async function onTaskStageChange(value: string | string[] | null | undefined) {
  const orgId = effectiveOrgId.value;
  if (!canEditStages.value || !orgId || !task.value) {
    return;
  }

  const raw = Array.isArray(value) ? value[0] ?? "" : value ?? "";
  const workflowStageId = raw ? raw : null;

  taskStageSaving.value = true;
  taskStageError.value = "";
  try {
    await api.updateTaskStage(orgId, task.value.id, workflowStageId);
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    taskStageError.value = err instanceof Error ? err.message : String(err);
  } finally {
    taskStageSaving.value = false;
  }
}

async function patchTaskProgress(payload: { progress_policy?: string | null }) {
  const orgId = effectiveOrgId.value;
  if (!canEditStages.value || !orgId || !task.value) {
    return;
  }
  taskProgressSaving.value = true;
  taskProgressError.value = "";
  try {
    await api.patchTask(orgId, task.value.id, payload);
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    taskProgressError.value = err instanceof Error ? err.message : String(err);
  } finally {
    taskProgressSaving.value = false;
  }
}

async function patchEpicProgress(payload: { progress_policy?: string | null }) {
  const orgId = effectiveOrgId.value;
  if (!canEditStages.value || !orgId || !epic.value) {
    return;
  }
  epicProgressSaving.value = true;
  epicProgressError.value = "";
  try {
    await api.patchEpic(orgId, epic.value.id, payload);
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    epicProgressError.value = err instanceof Error ? err.message : String(err);
  } finally {
    epicProgressSaving.value = false;
  }
}

function openCreateSubtaskModal() {
  createSubtaskTitle.value = "";
  createSubtaskDescription.value = "";
  createSubtaskStatus.value = "backlog";
  createSubtaskStartDate.value = "";
  createSubtaskEndDate.value = "";
  createSubtaskError.value = "";
  createSubtaskModalOpen.value = true;
}

async function createSubtask() {
  const orgId = effectiveOrgId.value;
  if (!orgId || !task.value) {
    createSubtaskError.value = "Select an org to continue.";
    return;
  }
  if (!canAuthorWork.value) {
    createSubtaskError.value = "Only admin/pm/member can create work items.";
    return;
  }

  const title = createSubtaskTitle.value.trim();
  if (!title) {
    createSubtaskError.value = "Title is required.";
    return;
  }

  createSubtaskError.value = "";
  creatingSubtask.value = true;
  try {
    const payload: {
      title: string;
      description?: string;
      status?: string;
      start_date?: string | null;
      end_date?: string | null;
    } = { title };

    const description = createSubtaskDescription.value.trim();
    if (description) {
      payload.description = description;
    }
    if (createSubtaskStatus.value) {
      payload.status = createSubtaskStatus.value;
    }
    if (createSubtaskStartDate.value) {
      payload.start_date = createSubtaskStartDate.value;
    }
    if (createSubtaskEndDate.value) {
      payload.end_date = createSubtaskEndDate.value;
    }

    await api.createSubtask(orgId, task.value.id, payload);
    createSubtaskModalOpen.value = false;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    createSubtaskError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingSubtask.value = false;
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
    if (!canWrite.value || effectiveOrgId.value !== orgId || socketDesiredOrgId !== orgId) {
      return;
    }
    startRealtime();
  }, delayMs);
}

function startRealtime() {
  stopRealtime();

  const orgId = effectiveOrgId.value;
  if (!canWrite.value || !orgId) {
    return;
  }
  if (typeof WebSocket === "undefined") {
    return;
  }

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

    if (!canWrite.value || socketDesiredOrgId !== orgId || effectiveOrgId.value !== orgId) {
      return;
    }
    if (event.code === 4400 || event.code === 4401 || event.code === 4403) {
      return;
    }

    scheduleRealtimeReconnect(orgId);
  };
}

watch(() => [effectiveOrgId.value, props.taskId], () => void refresh(), { immediate: true });
watch(() => [canWrite.value, effectiveOrgId.value, projectId.value], () => void refreshCustomFields(), { immediate: true });
watch(
  () => [effectiveOrgId.value, projectId.value, canEditStages.value],
  () => void refreshProjectMemberships(),
  { immediate: true }
);
watch(() => [canWrite.value, effectiveOrgId.value], () => startRealtime(), { immediate: true });
watch(assigneeSelectOpen, (open) => {
  if (!open) {
    assigneeQuery.value = "";
  }
});

watch(
  () => [task.value, customFields.value],
  () => {
    initCustomFieldDraft();
  }
);

onBeforeUnmount(() => stopRealtime());
</script>

<template>
  <div class="work-detail-layout">
    <div class="work-detail-main stack">
      <pf-card>
        <pf-card-title>
          <div class="top">
            <div>
              <pf-title h="1" size="2xl">{{ task?.title || "Work item" }}</pf-title>
              <div v-if="task" class="labels">
                <VlLabel
                  v-if="task.workflow_stage_id"
                  :color="stageLabelColor(task.workflow_stage_id)"
                  :title="task.workflow_stage_id ?? undefined"
                >
                  Stage {{ stageLabel(task.workflow_stage_id) }}
                </VlLabel>
                <VlLabel v-else :color="taskStatusLabelColor(task.status)">{{ workItemStatusLabel(task.status) }}</VlLabel>
                <VlLabel :color="task.client_safe ? 'green' : 'orange'">
                  Client {{ task.client_safe ? "visible" : "hidden" }}
                </VlLabel>
                <VlLabel :color="progressLabelColor(task.progress)">
                  Task progress {{ formatPercent(task.progress) }}
                </VlLabel>
                <VlLabel color="grey">Updated {{ formatTimestamp(task.updated_at ?? "") }}</VlLabel>
              </div>
              <pf-alert
                v-if="!canWrite"
                inline
                variant="info"
                title="Read-only view. Select a specific org + project to make changes."
              />
            </div>

            <pf-button variant="link" to="/work">Back</pf-button>
          </div>
        </pf-card-title>

        <pf-card-body>
          <pf-empty-state v-if="!effectiveOrgId">
            <pf-empty-state-header title="Select an org" heading-level="h2" />
            <pf-empty-state-body>Select an org to view this work item.</pf-empty-state-body>
          </pf-empty-state>

          <div v-else-if="loading" class="loading-row">
            <pf-spinner size="md" aria-label="Loading work item" />
          </div>

          <pf-alert v-else-if="error" inline variant="danger" :title="error" />

          <pf-empty-state v-else-if="!task">
            <pf-empty-state-header title="Not found" heading-level="h2" />
            <pf-empty-state-body>This work item does not exist or is not accessible.</pf-empty-state-body>
          </pf-empty-state>

          <div v-else class="overview">
            <span
              id="vl-work-detail-ready"
              data-testid="vl-work-detail-ready"
              aria-hidden="true"
              style="display: none"
            />
            <pf-content v-if="epic">
              <p>
                <span class="muted">Epic:</span> <strong>{{ epic.title }}</strong>
                <VlLabel :color="progressLabelColor(epic.progress)">
                  Epic progress {{ formatPercent(epic.progress) }}
                </VlLabel>
              </p>
            </pf-content>

            <pf-alert v-if="canAuthorWork && !projectId" inline variant="info" title="Select a project to create subtasks." />

            <pf-content v-if="task.description_html || task.description">
              <!-- description_html is sanitized server-side -->
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div v-if="task.description_html" class="description-markdown" v-html="task.description_html"></div>
              <div v-else class="description">{{ task.description }}</div>
            </pf-content>

            <pf-drawer :expanded="assignmentDrawerExpanded" inline position="end" class="assignment-drawer">
              <pf-drawer-content-body :padding="false">
                <pf-content class="assignment-summary">
                  <p>
                    <span class="muted">Assignee:</span>
                    <strong v-if="assigneeDisplay">{{ assigneeDisplay }}</strong>
                    <span v-else class="muted">Unassigned</span>
                  </p>
                  <p>
                    <span class="muted">Participants:</span>
                    <strong v-if="participantsDisplay">{{ participantsDisplay }}</strong>
                    <span v-else class="muted">None yet</span>
                  </p>
                </pf-content>

                <pf-alert v-if="assignmentError" inline variant="danger" :title="assignmentError" />
                <pf-alert v-if="participantError" inline variant="danger" :title="participantError" />

                <div v-if="canEditStages" class="actions">
                  <pf-button
                    variant="secondary"
                    :aria-expanded="assignmentDrawerExpanded"
                    @click="assignmentDrawerExpanded = true"
                  >
                    Manage participants
                  </pf-button>
                </div>
              </pf-drawer-content-body>

              <template v-if="canEditStages" #content>
                <pf-drawer-panel-content default-size="380px" min-size="260px" resizable>
                  <pf-drawer-head>
                    <pf-title h="3" size="md">Participants</pf-title>

                    <pf-drawer-actions>
                      <pf-drawer-close-button @click="assignmentDrawerExpanded = false" />
                    </pf-drawer-actions>
                  </pf-drawer-head>

                  <pf-drawer-panel-body>
                    <pf-form class="drawer-form">
                      <pf-title h="4" size="md">Participants</pf-title>

                      <div v-if="loadingParticipants" class="loading-row">
                        <pf-spinner size="md" aria-label="Loading participants" />
                      </div>

                      <pf-empty-state v-else-if="participants.length === 0" variant="small">
                        <pf-empty-state-header title="No participants yet" heading-level="h4" />
                        <pf-empty-state-body>
                          Participants are populated from assignee + comments + GitLab issue links + manual participants.
                        </pf-empty-state-body>
                      </pf-empty-state>

                      <pf-data-list v-else compact aria-label="Task participants">
                        <pf-data-list-item v-for="p in participants" :key="p.user.id" class="participant-item">
                          <pf-data-list-cell>
                            <div class="participant-row">
                              <div class="participant-main">
                                <div class="participant-name">
                                  {{ p.user.display_name || p.user.email || shortUserId(p.user.id) }}
                                  <span v-if="p.org_role" class="muted small">({{ p.org_role }})</span>
                                </div>
                                <VlLabelGroup class="participant-sources" :num-labels="5">
                                  <VlLabel
                                    v-for="source in p.sources"
                                    :key="source"
                                    :color="participantSourceColor(source)"
                                    variant="filled"
                                  >
                                    {{ participantSourceLabel(source) }}
                                  </VlLabel>
                                </VlLabelGroup>
                              </div>

                              <pf-button
                                v-if="p.sources.includes('manual')"
                                variant="link"
                                :disabled="removingParticipantUserId === p.user.id"
                                @click="removeManualParticipant(p.user.id)"
                              >
                                Remove manual
                              </pf-button>
                            </div>
                          </pf-data-list-cell>
                        </pf-data-list-item>
                      </pf-data-list>

                      <pf-form-group label="Add participant" field-id="task-participant-add" class="grow">
                        <pf-form-select
                          id="task-participant-add"
                          :model-value="participantToAddUserId"
                          :disabled="savingParticipant || !projectMemberships.length"
                          @update:model-value="onParticipantToAddChange($event)"
                        >
                          <pf-form-select-option value="">(select a project member)</pf-form-select-option>
                          <pf-form-select-option v-for="m in projectMemberships" :key="m.user.id" :value="m.user.id">
                            {{ m.user.display_name || m.user.email }} ({{ m.role }})
                          </pf-form-select-option>
                        </pf-form-select>
                      </pf-form-group>

                      <pf-button
                        variant="primary"
                        :disabled="savingParticipant || !participantToAddUserId.trim()"
                        @click="addManualParticipant"
                      >
                        Add
                      </pf-button>

                      <pf-helper-text class="note">
                        <pf-helper-text-item v-if="!projectMemberships.length">
                          No project members yet.
                          <pf-button variant="link" :to="projectMembersSettingsTo">Add members</pf-button>
                        </pf-helper-text-item>
                        <pf-helper-text-item v-else>
                          Manual participants complement auto participants derived from assignee + comments + GitLab links.
                        </pf-helper-text-item>
                      </pf-helper-text>
                    </pf-form>
                  </pf-drawer-panel-body>
                </pf-drawer-panel-content>
              </template>
            </pf-drawer>
          </div>
        </pf-card-body>
      </pf-card>

      <GitLabLinksCard
        v-if="task && effectiveOrgId"
        :org-id="effectiveOrgId"
        :task-id="props.taskId"
        :can-manage-integration="canManageGitLabIntegration"
        :can-manage-links="canManageGitLabLinks"
      />

      <pf-card v-if="task">
        <pf-card-title>
          <pf-title h="2" size="lg">Custom fields</pf-title>
        </pf-card-title>

        <pf-card-body>
          <div v-if="loadingCustomFields" class="loading-row">
            <pf-spinner size="md" aria-label="Loading custom fields" />
          </div>

          <pf-alert v-else-if="customFieldError" inline variant="danger" :title="customFieldError" />

          <pf-empty-state v-else-if="customFields.length === 0" variant="small">
            <pf-empty-state-header title="No custom fields yet" heading-level="h3" />
            <pf-empty-state-body>No custom fields were defined for this project.</pf-empty-state-body>
          </pf-empty-state>

          <div v-else>
            <pf-form v-if="canEditCustomFields">
              <pf-form-group
                v-for="field in customFields"
                :key="field.id"
                :label="field.name"
                :field-id="`custom-field-${field.id}`"
              >
                <pf-text-input
                  v-if="field.field_type === 'text'"
                  :id="`custom-field-${field.id}`"
                  :model-value="String(customFieldDraft[field.id] ?? '')"
                  type="text"
                  @update:model-value="(value) => updateCustomFieldDraft(field.id, value)"
                />
                <pf-text-input
                  v-else-if="field.field_type === 'number'"
                  :id="`custom-field-${field.id}`"
                  :model-value="(customFieldDraft[field.id] as string | number | null) ?? ''"
                  type="number"
                  step="any"
                  @update:model-value="(value) => updateCustomFieldDraft(field.id, value)"
                />
                <pf-text-input
                  v-else-if="field.field_type === 'date'"
                  :id="`custom-field-${field.id}`"
                  :model-value="String(customFieldDraft[field.id] ?? '')"
                  type="date"
                  @update:model-value="(value) => updateCustomFieldDraft(field.id, value)"
                />
                <pf-form-select
                  v-else-if="field.field_type === 'select'"
                  :id="`custom-field-${field.id}`"
                  :model-value="String(customFieldDraft[field.id] ?? '')"
                  @update:model-value="
                    (value) => updateCustomFieldDraft(field.id, typeof value === 'string' ? value : '')
                  "
                >
                  <pf-form-select-option value="">(none)</pf-form-select-option>
                  <pf-form-select-option v-for="opt in field.options" :key="opt" :value="opt">
                    {{ opt }}
                  </pf-form-select-option>
                </pf-form-select>
                <pf-form-select
                  v-else-if="field.field_type === 'multi_select'"
                  :id="`custom-field-${field.id}`"
                  :model-value="Array.isArray(customFieldDraft[field.id]) ? (customFieldDraft[field.id] as string[]) : []"
                  multiple
                  @update:model-value="
                    (value) => updateCustomFieldDraft(field.id, Array.isArray(value) ? value : [])
                  "
                >
                  <pf-form-select-option v-for="opt in field.options" :key="opt" :value="opt">
                    {{ opt }}
                  </pf-form-select-option>
                </pf-form-select>
                <div v-else class="muted">Unsupported field type: {{ field.field_type }}</div>
              </pf-form-group>

              <div class="actions">
                <pf-button
                  v-if="canEditCustomFields"
                  type="button"
                  variant="primary"
                  :disabled="savingCustomFields"
                  @click="saveCustomFieldValues"
                >
                  Save custom fields
                </pf-button>
              </div>
            </pf-form>

            <pf-description-list v-else horizontal compact>
              <pf-description-list-group v-for="field in customFields" :key="field.id">
                <pf-description-list-term>{{ field.name }}</pf-description-list-term>
                <pf-description-list-description>
                  {{
                    formatCustomFieldValue(
                      field,
                      task.custom_field_values.find((v) => v.field_id === field.id)?.value
                    ) || "—"
                  }}
                </pf-description-list-description>
              </pf-description-list-group>
            </pf-description-list>
          </div>
        </pf-card-body>
      </pf-card>

      <pf-card v-if="task">
        <pf-card-title>
          <div class="subtasks-header">
            <pf-title h="2" size="lg">Subtasks</pf-title>
            <pf-button
              v-if="canAuthorWork"
              type="button"
              variant="secondary"
              small
              :disabled="!context.projectId"
              @click="openCreateSubtaskModal"
            >
              Create subtask
            </pf-button>
          </div>
        </pf-card-title>

        <pf-card-body>
          <pf-empty-state v-if="subtasks.length === 0" variant="small">
            <pf-empty-state-header title="No subtasks yet" heading-level="h3" />
            <pf-empty-state-body>No subtasks were found for this task.</pf-empty-state-body>
            <pf-button
              v-if="canAuthorWork"
              type="button"
              variant="primary"
              :disabled="!context.projectId"
              @click="openCreateSubtaskModal"
            >
              Create subtask
            </pf-button>
          </pf-empty-state>

          <div v-else class="table-wrap">
            <pf-table aria-label="Subtasks">
              <pf-thead>
                <pf-tr>
                  <pf-th>Subtask</pf-th>
                  <pf-th>Status</pf-th>
                  <pf-th>Progress</pf-th>
                  <pf-th>Updated</pf-th>
                  <pf-th>Stage</pf-th>
                </pf-tr>
              </pf-thead>
              <pf-tbody>
                <pf-tr v-for="subtask in subtasks" :key="subtask.id">
                  <pf-td data-label="Subtask">
                    <div class="subtask-title">{{ subtask.title }}</div>
                  </pf-td>
                  <pf-td data-label="Status">
                    <VlLabel :color="taskStatusLabelColor(subtask.status)">{{ workItemStatusLabel(subtask.status) }}</VlLabel>
                  </pf-td>
                  <pf-td data-label="Progress">
                    <VlLabel :color="progressLabelColor(subtask.progress)">
                      {{ formatPercent(subtask.progress) }}
                    </VlLabel>
                  </pf-td>
                  <pf-td data-label="Updated">
                    <VlLabel color="grey">{{ formatTimestamp(subtask.updated_at ?? "") }}</VlLabel>
                  </pf-td>
                  <pf-td data-label="Stage">
                    <div v-if="canEditStages && workflowId && stages.length > 0">
                      <pf-form-select
                        :id="`subtask-stage-${subtask.id}`"
                        :model-value="subtask.workflow_stage_id ?? ''"
                        :disabled="stageUpdateSavingSubtaskId === subtask.id"
                        :aria-label="`Stage for ${subtask.title}`"
                        @update:model-value="onStageChange(subtask.id, $event)"
                      >
                        <pf-form-select-option value="">(unassigned)</pf-form-select-option>
                        <pf-form-select-option v-for="stage in stages" :key="stage.id" :value="stage.id">
                          {{ stage.order }}. {{ stage.name }}{{ stage.is_done ? " (Done)" : "" }}
                        </pf-form-select-option>
                      </pf-form-select>
                    </div>
                    <VlLabel
                      v-else
                      :color="stageLabelColor(subtask.workflow_stage_id)"
                      :title="subtask.workflow_stage_id ?? undefined"
                    >
                      {{ stageLabel(subtask.workflow_stage_id) }}
                    </VlLabel>

                    <pf-helper-text v-if="stageUpdateErrorBySubtaskId[subtask.id]" class="small">
                      <pf-helper-text-item variant="error">
                        {{ stageUpdateErrorBySubtaskId[subtask.id] }}
                      </pf-helper-text-item>
                    </pf-helper-text>
                  </pf-td>
                </pf-tr>
              </pf-tbody>
            </pf-table>
          </div>
        </pf-card-body>
      </pf-card>

      <pf-card v-if="task">
        <pf-card-title>
          <pf-title h="2" size="lg">Collaboration</pf-title>
        </pf-card-title>

        <pf-card-body>
          <pf-alert v-if="collabError" inline variant="danger" :title="collabError" />

          <div class="collaboration-grid">
            <pf-card>
              <pf-card-title>
                <pf-title h="3" size="md">Comments</pf-title>
              </pf-card-title>
              <pf-card-body>
                <pf-empty-state v-if="comments.length === 0" variant="small">
                  <pf-empty-state-header title="No comments yet" heading-level="h4" />
                  <pf-empty-state-body>Write the first comment on this work item.</pf-empty-state-body>
                </pf-empty-state>

                <pf-data-list v-else compact aria-label="Task comments">
                  <pf-data-list-item v-for="comment in comments" :key="comment.id">
                    <pf-data-list-cell>
                      <div class="comment-meta">
                        <span class="comment-author">{{ comment.author.display_name || comment.author.id }}</span>
                        <div class="comment-labels">
                          <VlLabel :color="comment.client_safe ? 'teal' : 'orange'">
                            {{ comment.client_safe ? "Client" : "Internal" }}
                          </VlLabel>
                          <VlLabel color="blue">{{ formatTimestamp(comment.created_at) }}</VlLabel>
                        </div>
                      </div>

                      <pf-content class="comment-body">
                        <!-- body_html is sanitized server-side -->
                        <!-- eslint-disable-next-line vue/no-v-html -->
                        <div v-html="comment.body_html"></div>
                      </pf-content>
                    </pf-data-list-cell>
                  </pf-data-list-item>
                </pf-data-list>

                <pf-form v-if="canAuthorWork" class="comment-form">
                  <pf-form-group label="Add a comment" field-id="task-comment-body">
                    <pf-textarea
                      id="task-comment-body"
                      v-model="commentDraft"
                      rows="4"
                      placeholder="Write a comment (Markdown supported)…"
                    />
                  </pf-form-group>
                  <pf-checkbox id="task-comment-client-safe" v-model="commentClientSafe" label="Visible to client" />
                  <pf-button type="button" variant="primary" :disabled="!commentDraft.trim()" @click="submitComment">
                    Post comment
                  </pf-button>
                </pf-form>
              </pf-card-body>
            </pf-card>

            <pf-card>
              <pf-card-title>
                <pf-title h="3" size="md">Attachments</pf-title>
              </pf-card-title>
              <pf-card-body>
                <pf-empty-state v-if="attachments.length === 0" variant="small">
                  <pf-empty-state-header title="No attachments yet" heading-level="h4" />
                  <pf-empty-state-body>Upload the first attachment for this work item.</pf-empty-state-body>
                </pf-empty-state>

                <pf-data-list v-else compact aria-label="Task attachments">
                  <pf-data-list-item v-for="attachment in attachments" :key="attachment.id">
                    <pf-data-list-cell>
                      <div class="attachment-row">
                        <div>
                          <div class="attachment-name">{{ attachment.filename }}</div>
                          <div class="muted small">
                            {{ attachment.size_bytes }} bytes • {{ attachment.content_type }}
                          </div>
                        </div>
                        <pf-button variant="link" :href="attachment.download_url" target="_blank" rel="noopener">
                          Download
                        </pf-button>
                      </div>
                    </pf-data-list-cell>
                  </pf-data-list-item>
                </pf-data-list>

                <div v-if="canAuthorWork" class="attachment-form">
                  <pf-file-upload
                    :key="attachmentUploadKey"
                    browse-button-text="Choose file"
                    hide-default-preview
                    :disabled="uploadingAttachment"
                    @file-input-change="onSelectedFileChange"
                  >
                    <div class="muted small">
                      {{
                        selectedFile
                          ? `${selectedFile.name} (${selectedFile.size} bytes)`
                          : "No file selected."
                      }}
                    </div>
                  </pf-file-upload>

                  <pf-button type="button" variant="primary" :disabled="!selectedFile || uploadingAttachment" @click="uploadAttachment">
                    {{ uploadingAttachment ? "Uploading…" : "Upload" }}
                  </pf-button>
                </div>
              </pf-card-body>
            </pf-card>
          </div>
        </pf-card-body>
      </pf-card>
    </div>

    <aside v-if="task" class="work-detail-aside stack" aria-label="Work detail sidebar">
      <pf-card>
        <pf-card-title>
          <pf-title h="2" size="lg">Ownership</pf-title>
        </pf-card-title>
        <pf-card-body>
          <pf-form>
            <pf-form-group label="Assignee" field-id="task-assignee">
              <pf-select
                v-model:open="assigneeSelectOpen"
                :selected="task.assignee_user_id ?? ASSIGNEE_UNASSIGNED_MENU_ID"
                :disabled="!canEditStages || savingAssignee || loadingProjectMemberships"
                full-width
                @update:selected="onAssigneeSelected"
              >
                <template #label>
                  <span v-if="assigneeDisplay">{{ assigneeDisplay }}</span>
                  <span v-else class="muted">Unassigned</span>
                </template>

                <pf-menu-input>
                  <div @click.stop>
                    <pf-search-input
                      v-model="assigneeQuery"
                      aria-label="Search assignees"
                      placeholder="Search members…"
                      @clear="assigneeQuery = ''"
                    />
                  </div>
                </pf-menu-input>

                <pf-divider />

                  <pf-menu-list>
                    <pf-menu-item :value="ASSIGNEE_UNASSIGNED_MENU_ID">Unassigned</pf-menu-item>
                    <pf-menu-item
                      v-for="m in assigneeMenu.results"
                      :key="m.user.id"
                      :value="m.user.id"
                      :description="assignableMemberDescription(m) || undefined"
                    >
                      {{ assignableMemberLabel(m) }}
                      <span v-if="m.role" class="muted small">({{ m.role }})</span>
                    </pf-menu-item>
                  </pf-menu-list>
                </pf-select>

              <pf-helper-text v-if="canEditStages && (assignmentError || assigneeMenu.truncated || (!projectMemberships.length && !loadingProjectMemberships))" class="small">
                <pf-helper-text-item v-if="assignmentError" variant="error">{{ assignmentError }}</pf-helper-text-item>
                <pf-helper-text-item v-else-if="!projectMemberships.length && !loadingProjectMemberships">
                  No project members yet.
                  <pf-button variant="link" :to="projectMembersSettingsTo">Add members</pf-button>
                </pf-helper-text-item>
                <pf-helper-text-item v-if="assigneeMenu.truncated">
                  Showing first {{ ASSIGNEE_MAX_RESULTS }} results. Search to narrow.
                </pf-helper-text-item>
              </pf-helper-text>
            </pf-form-group>

            <div class="assignment-actions">
              <pf-button variant="secondary" :disabled="!canEditStages || savingAssignee || !session.user?.id" @click="assignToMe">
                Assign to me
              </pf-button>
              <pf-button variant="link" :disabled="!canEditStages || savingAssignee" @click="unassign">
                Unassign
              </pf-button>
            </div>
          </pf-form>
        </pf-card-body>
      </pf-card>

      <pf-card>
        <pf-card-title>
          <pf-title h="2" size="lg">Workflow</pf-title>
        </pf-card-title>
        <pf-card-body>
          <pf-form>
            <pf-form-group label="Task stage" field-id="sidebar-task-stage">
              <div v-if="canEditStages && workflowId && stages.length > 0">
                <pf-form-select
                  id="sidebar-task-stage"
                  :model-value="task.workflow_stage_id ?? ''"
                  :disabled="taskStageSaving"
                  @update:model-value="onTaskStageChange"
                >
                  <pf-form-select-option value="">(unassigned)</pf-form-select-option>
                  <pf-form-select-option v-for="stage in stages" :key="stage.id" :value="stage.id">
                    {{ stage.order }}. {{ stage.name }}{{ stage.is_done ? " (Done)" : "" }}
                  </pf-form-select-option>
                </pf-form-select>
              </div>
              <VlLabel
                v-else
                :color="stageLabelColor(task.workflow_stage_id)"
                :title="task.workflow_stage_id ?? undefined"
              >
                {{ stageLabel(task.workflow_stage_id) }}
              </VlLabel>
              <pf-helper-text v-if="taskStageError" class="small">
                <pf-helper-text-item variant="error">{{ taskStageError }}</pf-helper-text-item>
              </pf-helper-text>
            </pf-form-group>

            <pf-form-group v-if="canEditStages" label="Task progress policy" field-id="sidebar-task-progress-policy">
              <pf-form-select
                id="sidebar-task-progress-policy"
                :model-value="task.progress_policy ?? ''"
                :disabled="taskProgressSaving"
                @update:model-value="
                  (value) =>
                    patchTaskProgress({
                      progress_policy: String(Array.isArray(value) ? value[0] : value ?? '') || null,
                    })
                "
              >
                <pf-form-select-option value="">(inherit project/epic)</pf-form-select-option>
                <pf-form-select-option value="subtasks_rollup">Subtasks rollup</pf-form-select-option>
                <pf-form-select-option value="workflow_stage">Workflow stage</pf-form-select-option>
              </pf-form-select>
            </pf-form-group>

            <pf-form-group v-if="canEditStages && epic" label="Epic progress policy" field-id="sidebar-epic-progress-policy">
              <pf-form-select
                id="sidebar-epic-progress-policy"
                :model-value="epic.progress_policy ?? ''"
                :disabled="epicProgressSaving"
                @update:model-value="
                  (value) =>
                    patchEpicProgress({
                      progress_policy: String(Array.isArray(value) ? value[0] : value ?? '') || null,
                    })
                "
              >
                <pf-form-select-option value="">(inherit project)</pf-form-select-option>
                <pf-form-select-option value="subtasks_rollup">Subtasks rollup</pf-form-select-option>
                <pf-form-select-option value="workflow_stage">Workflow stage</pf-form-select-option>
              </pf-form-select>
            </pf-form-group>
          </pf-form>

          <pf-alert v-if="taskProgressError" inline variant="danger" :title="taskProgressError" />
          <pf-alert v-if="epicProgressError" inline variant="danger" :title="epicProgressError" />

          <pf-alert
            v-if="project && !workflowId"
            inline
            variant="warning"
            title="This project has no workflow assigned. Stage changes are disabled."
          />
        </pf-card-body>
      </pf-card>

      <pf-card>
        <pf-card-title>
          <pf-title h="2" size="lg">Planning</pf-title>
        </pf-card-title>
        <pf-card-body>
          <pf-form>
            <pf-form-group label="Start date" field-id="task-start-date">
              <pf-text-input
                id="task-start-date"
                v-model="taskStartDateDraft"
                type="date"
                :disabled="!canEditStages || savingSchedule"
                @change="saveSchedule"
              />
            </pf-form-group>

            <pf-form-group label="End date" field-id="task-end-date">
              <pf-text-input
                id="task-end-date"
                v-model="taskEndDateDraft"
                type="date"
                :disabled="!canEditStages || savingSchedule"
                @change="saveSchedule"
              />
            </pf-form-group>

            <div class="planning-actions">
              <pf-button variant="secondary" :disabled="!canEditStages || savingSchedule" @click="saveSchedule">
                {{ savingSchedule ? "Saving…" : "Save" }}
              </pf-button>
              <pf-button variant="link" :disabled="!canEditStages || savingSchedule" @click="clearSchedule">
                Clear
              </pf-button>
            </div>
          </pf-form>

          <pf-alert v-if="scheduleError" inline variant="danger" :title="scheduleError" />
        </pf-card-body>
      </pf-card>

      <pf-card>
        <pf-card-title>
          <pf-title h="2" size="lg">Client portal</pf-title>
        </pf-card-title>
        <pf-card-body>
          <pf-form>
            <pf-form-group field-id="task-client-safe">
              <pf-checkbox
                id="task-client-safe"
                :model-value="Boolean(task.client_safe)"
                :disabled="!canEditClientSafe || savingClientSafe"
                label="Visible to client (enables client portal list/detail + comments)"
                @update:model-value="onClientSafeToggle(Boolean($event))"
              />
            </pf-form-group>
          </pf-form>

          <pf-alert v-if="clientSafeError" inline variant="danger" :title="clientSafeError" />
        </pf-card-body>
      </pf-card>

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
    </aside>
  </div>

  <pf-modal v-model:open="createSubtaskModalOpen" title="Create subtask" variant="medium">
    <pf-form class="modal-form" @submit.prevent="createSubtask">
      <pf-form-group label="Title" field-id="subtask-create-title">
        <pf-text-input
          id="subtask-create-title"
          v-model="createSubtaskTitle"
          type="text"
          placeholder="Subtask title"
        />
      </pf-form-group>

      <pf-form-group label="Description (optional)" field-id="subtask-create-description">
        <pf-textarea id="subtask-create-description" v-model="createSubtaskDescription" rows="4" />
      </pf-form-group>

      <pf-form-group label="Status" field-id="subtask-create-status">
        <pf-form-select id="subtask-create-status" v-model="createSubtaskStatus">
          <pf-form-select-option v-for="option in STATUS_OPTIONS" :key="option.value" :value="option.value">
            {{ option.label }}
          </pf-form-select-option>
        </pf-form-select>
      </pf-form-group>

      <pf-form-group label="Start date (optional)" field-id="subtask-create-start-date">
        <pf-text-input id="subtask-create-start-date" v-model="createSubtaskStartDate" type="date" />
      </pf-form-group>

      <pf-form-group label="End date (optional)" field-id="subtask-create-end-date">
        <pf-text-input id="subtask-create-end-date" v-model="createSubtaskEndDate" type="date" />
      </pf-form-group>

      <pf-alert v-if="createSubtaskError" inline variant="danger" :title="createSubtaskError" />
    </pf-form>

    <template #footer>
      <pf-button
        variant="primary"
        :disabled="creatingSubtask || !canAuthorWork || !context.projectId || !createSubtaskTitle.trim()"
        @click="createSubtask"
      >
        {{ creatingSubtask ? "Creating…" : "Create" }}
      </pf-button>
      <pf-button variant="link" :disabled="creatingSubtask" @click="createSubtaskModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>
</template>

<style scoped>
.work-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1rem;
}

.work-detail-main,
.work-detail-aside {
  min-width: 0;
}

@media (min-width: 992px) {
  .work-detail-layout {
    grid-template-columns: minmax(0, 1fr) 320px;
    align-items: start;
  }
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.overview {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.description {
  white-space: pre-wrap;
}

.description-markdown :deep(p) {
  margin: 0.5rem 0;
}

.assignment-summary {
  margin-top: 0.25rem;
}

.drawer-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.grow {
  flex: 1;
  min-width: 260px;
}

.participant-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.participant-main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.participant-name {
  font-weight: 600;
}

.participant-sources {
  margin-top: 0.25rem;
}

.note {
  margin-top: 0.5rem;
}

.policy-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem;
}

@media (min-width: 992px) {
  .policy-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.ownership {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.ownership-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.subtasks-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.actions {
  margin-top: 0.75rem;
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.table-wrap {
  overflow-x: auto;
}

.subtask-title {
  font-weight: 600;
}

.collaboration-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 720px) {
  .collaboration-grid {
    grid-template-columns: 1fr;
  }
}

.comment-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.comment-author {
  font-weight: 600;
}

.comment-labels {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.comment-body {
  margin-top: 0.25rem;
}

.comment-form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.attachment-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.attachment-name {
  font-weight: 600;
}

.small {
  font-size: 0.9rem;
}

.attachment-form {
  margin-top: 1rem;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.75rem;
}
</style>
