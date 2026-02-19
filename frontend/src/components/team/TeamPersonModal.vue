<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../../api";
import type {
  ApiKey,
  OrgInvite,
  Person,
  PersonContactEntry,
  PersonContactEntryKind,
  PersonMessage,
  PersonMessageThread,
  PersonPayment,
  PersonProjectMembership,
  PersonRate,
} from "../../api/types";
import VlConfirmModal from "../VlConfirmModal.vue";
import VlLabel from "../VlLabel.vue";
import TeamPersonAvailabilityTab from "./TeamPersonAvailabilityTab.vue";
import type { VlLabelColor } from "../../utils/labels";
import { useContextStore } from "../../stores/context";
import { formatTimestamp } from "../../utils/format";

const props = withDefaults(
  defineProps<{
    open?: boolean;
    orgId?: string;
    person?: Person | null;
    canManage?: boolean;
  }>(),
  {
    open: false,
    orgId: "",
    person: null,
    canManage: false,
  }
);

const emit = defineEmits<{
  (event: "update:open", value: boolean): void;
  (event: "saved", person: Person): void;
  (event: "invite-material", material: { token: string; invite_url: string }): void;
}>();

const router = useRouter();
const route = useRoute();
const context = useContextStore();

const localPerson = ref<Person | null>(null);
const currentPerson = computed(() => props.person ?? localPerson.value);

const activeTabKey = ref<string>("profile");

type PersonDraft = {
  full_name: string;
  preferred_name: string;
  email: string;
  title: string;
  skills: string[];
  bio: string;
  notes: string;
  timezone: string;
  location: string;
  phone: string;
  slack_handle: string;
  linkedin_url: string;
  gitlab_username: string;
};

function blankDraft(): PersonDraft {
  return {
    full_name: "",
    preferred_name: "",
    email: "",
    title: "",
    skills: [],
    bio: "",
    notes: "",
    timezone: "UTC",
    location: "",
    phone: "",
    slack_handle: "",
    linkedin_url: "",
    gitlab_username: "",
  };
}

function draftFromPerson(person: Person): PersonDraft {
  return {
    full_name: person.full_name || "",
    preferred_name: person.preferred_name || "",
    email: person.email || "",
    title: person.title || "",
    skills: Array.isArray(person.skills) ? [...person.skills] : [],
    bio: person.bio || "",
    notes: person.notes || "",
    timezone: person.timezone || "UTC",
    location: person.location || "",
    phone: person.phone || "",
    slack_handle: person.slack_handle || "",
    linkedin_url: person.linkedin_url || "",
    gitlab_username: person.gitlab_username || "",
  };
}

const draft = ref<PersonDraft>(blankDraft());
const saving = ref(false);
const error = ref("");
const savedBanner = ref("");
const skillInput = ref("");
const inviting = ref(false);
const inviteError = ref("");
const revokeInviteConfirmOpen = ref(false);
const apiKeys = ref<ApiKey[]>([]);
const apiKeysLoading = ref(false);
const apiKeysError = ref("");
const actionError = ref("");
const tokenMaterial = ref<null | { token: string; apiKey: ApiKey }>(null);

const projectMemberships = ref<PersonProjectMembership[]>([]);
const projectMembershipsLoading = ref(false);
const projectMembershipsError = ref("");

const modalTitle = computed(() => {
  const person = currentPerson.value;
  if (!person) {
    return "New person";
  }

  const label = (person.preferred_name || person.full_name || person.email || "").trim();
  return label ? `Edit: ${label}` : "Edit person";
});

function close() {
  emit("update:open", false);
}

function resetState() {
  activeTabKey.value = "profile";
  error.value = "";
  savedBanner.value = "";
  skillInput.value = "";
  localPerson.value = null;

  inviteError.value = "";
  inviting.value = false;
  revokeInviteConfirmOpen.value = false;

  tokenMaterial.value = null;
  apiKeys.value = [];
  apiKeysError.value = "";
  apiKeysLoading.value = false;
  actionError.value = "";

  projectMemberships.value = [];
  projectMembershipsLoading.value = false;
  projectMembershipsError.value = "";
}

watch(
  () => [props.open, props.person?.id],
  ([open]) => {
    if (!open) {
      resetState();
      return;
    }

    const person = props.person;
    if (person) {
      localPerson.value = null;
      draft.value = draftFromPerson(person);
    } else {
      localPerson.value = null;
      draft.value = blankDraft();
    }

    // Ensure projects are available for API key scoping.
    if (props.orgId) {
      void context.refreshProjects();
    }
  },
  { immediate: true }
);

function personStatusLabelColor(status: string): VlLabelColor {
  if (status === "active") {
    return "green";
  }
  if (status === "invited") {
    return "orange";
  }
  return "grey";
}

function roleLabelColor(role: string): VlLabelColor {
  if (role === "admin") {
    return "red";
  }
  if (role === "pm") {
    return "purple";
  }
  if (role === "client") {
    return "teal";
  }
  return "blue";
}

function contactKindLabel(kind: PersonContactEntryKind): string {
  if (kind === "call") {
    return "Call";
  }
  if (kind === "email") {
    return "Email";
  }
  if (kind === "meeting") {
    return "Meeting";
  }
  return "Note";
}

function contactKindColor(kind: PersonContactEntryKind): VlLabelColor {
  if (kind === "call") {
    return "teal";
  }
  if (kind === "email") {
    return "purple";
  }
  if (kind === "meeting") {
    return "orange";
  }
  return "blue";
}

const statusLabel = computed(() => {
  const person = currentPerson.value;
  if (!person) {
    return null;
  }

  const status = String(person.status || "candidate").toLowerCase();
  const title = status === "active" ? "Active member" : status === "invited" ? "Invited" : "Candidate";
  return {
    text: title,
    color: personStatusLabelColor(status),
  };
});

const membershipRoleLabel = computed(() => {
  const person = currentPerson.value;
  if (!person || !person.membership_role) {
    return null;
  }
  return {
    text: String(person.membership_role).toUpperCase(),
    color: roleLabelColor(String(person.membership_role)),
  };
});

function normalizeSkills(skills: string[]): string[] {
  const out: string[] = [];
  for (const raw of skills) {
    const trimmed = String(raw || "").trim();
    if (!trimmed) {
      continue;
    }
    if (!out.includes(trimmed)) {
      out.push(trimmed);
    }
  }
  return out;
}

async function handleUnauthorized() {
  close();
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function projectMembersManageUrl(projectId: string): string {
  return `/settings/project?projectId=${encodeURIComponent(projectId)}#project-members`;
}

async function refreshProjectMemberships() {
  projectMembershipsError.value = "";

  if (!props.open || !props.orgId) {
    projectMemberships.value = [];
    return;
  }
  if (activeTabKey.value !== "projects") {
    return;
  }

  const person = currentPerson.value;
  if (!person) {
    projectMemberships.value = [];
    return;
  }

  projectMembershipsLoading.value = true;
  try {
    const res = await api.listPersonProjectMemberships(props.orgId, person.id);
    projectMemberships.value = res.memberships;
  } catch (err) {
    projectMemberships.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      projectMembershipsError.value = "Not permitted.";
      return;
    }
    projectMembershipsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    projectMembershipsLoading.value = false;
  }
}

watch(
  () => [props.open, activeTabKey.value, currentPerson.value?.id],
  () => void refreshProjectMemberships(),
  { immediate: true }
);

async function savePerson() {
  if (!props.canManage) {
    error.value = "Not permitted.";
    return;
  }

  if (!props.orgId) {
    error.value = "Select an org first.";
    return;
  }

  saving.value = true;
  error.value = "";
  savedBanner.value = "";

  const payload = {
    full_name: draft.value.full_name.trim(),
    preferred_name: draft.value.preferred_name.trim(),
    email: draft.value.email.trim() ? draft.value.email.trim().toLowerCase() : null,
    title: draft.value.title.trim(),
    skills: normalizeSkills(draft.value.skills),
    bio: draft.value.bio.trim(),
    notes: draft.value.notes.trim(),
    timezone: (draft.value.timezone || "").trim() || "UTC",
    location: draft.value.location.trim(),
    phone: draft.value.phone.trim(),
    slack_handle: draft.value.slack_handle.trim(),
    linkedin_url: draft.value.linkedin_url.trim(),
    gitlab_username: draft.value.gitlab_username.trim() ? draft.value.gitlab_username.trim().toLowerCase() : null,
  };

  try {
    const person = currentPerson.value;
    if (!person) {
      const res = await api.createOrgPerson(props.orgId, payload);
      localPerson.value = res.person;
      draft.value = draftFromPerson(res.person);
      emit("saved", res.person);
      savedBanner.value = "Saved.";
      return;
    }

    const res = await api.updateOrgPerson(props.orgId, person.id, payload);
    localPerson.value = res.person;
    draft.value = draftFromPerson(res.person);
    emit("saved", res.person);
    savedBanner.value = "Saved.";
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Not permitted.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}

// Skills editing

function addSkill() {
  const raw = skillInput.value.trim();
  if (!raw) {
    return;
  }

  const normalized = raw
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);

  const next = normalizeSkills([...(draft.value.skills || []), ...normalized]);
  draft.value.skills = next;
  skillInput.value = "";
}

function removeSkill(value: string) {
  draft.value.skills = (draft.value.skills || []).filter((s) => s !== value);
}

// Invite flow (PM/admin; person must exist)
const inviteRole = ref("member");
const inviteEmail = ref("");
const inviteMessage = ref("");

const activeInvite = computed<OrgInvite | null>(() => {
  const person = currentPerson.value;
  if (!person) {
    return null;
  }
  return person.active_invite || null;
});

watch(
  () => currentPerson.value?.id,
  () => {
    const person = currentPerson.value;
    inviteError.value = "";
    inviteRole.value = person?.membership_role || "member";
    inviteEmail.value = person?.email || "";
    inviteMessage.value = "";
  },
  { immediate: true }
);

function requestRevokeInvite() {
  inviteError.value = "";
  revokeInviteConfirmOpen.value = true;
}

async function revokeInvite() {
  const invite = activeInvite.value;
  if (!invite) {
    inviteError.value = "No active invite to revoke.";
    return;
  }

  inviting.value = true;
  inviteError.value = "";
  try {
    await api.revokeOrgInvite(props.orgId, invite.id);
    revokeInviteConfirmOpen.value = false;

    // Refresh person so status/invite fields are accurate.
    const person = currentPerson.value;
    if (person) {
      const refreshed = await api.getOrgPerson(props.orgId, person.id);
      localPerson.value = refreshed.person;
      draft.value = draftFromPerson(refreshed.person);
      emit("saved", refreshed.person);
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      inviteError.value = "Not permitted.";
      return;
    }
    inviteError.value = err instanceof Error ? err.message : String(err);
  } finally {
    inviting.value = false;
  }
}

async function resendInvite() {
  const invite = activeInvite.value;
  if (!invite) {
    inviteError.value = "No active invite to resend.";
    return;
  }

  inviting.value = true;
  inviteError.value = "";
  try {
    const res = await api.resendOrgInvite(props.orgId, invite.id);
    emit("invite-material", { token: res.token, invite_url: res.invite_url });

    const person = currentPerson.value;
    if (person) {
      const refreshed = await api.getOrgPerson(props.orgId, person.id);
      localPerson.value = refreshed.person;
      draft.value = draftFromPerson(refreshed.person);
      emit("saved", refreshed.person);
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      inviteError.value = "Not permitted.";
      return;
    }
    inviteError.value = err instanceof Error ? err.message : String(err);
  } finally {
    inviting.value = false;
  }
}

async function sendInvite() {
  inviteError.value = "";

  if (!props.canManage) {
    inviteError.value = "Not permitted.";
    return;
  }

  const person = currentPerson.value;
  if (!person) {
    inviteError.value = "Save the person before inviting.";
    return;
  }

  const email = inviteEmail.value.trim().toLowerCase();
  if (!email) {
    inviteError.value = "Email is required.";
    return;
  }

  inviting.value = true;
  try {
    const res = await api.inviteOrgPerson(props.orgId, person.id, {
      role: inviteRole.value,
      email,
      message: inviteMessage.value.trim() ? inviteMessage.value.trim() : undefined,
    });

    emit("invite-material", { token: res.token, invite_url: res.invite_url });

    const refreshed = await api.getOrgPerson(props.orgId, person.id);
    localPerson.value = refreshed.person;
    draft.value = draftFromPerson(refreshed.person);
    emit("saved", refreshed.person);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      inviteError.value = "Not permitted.";
      return;
    }
    inviteError.value = err instanceof Error ? err.message : String(err);
  } finally {
    inviting.value = false;
  }
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function dateToDatetimeLocal(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function datetimeLocalFromIso(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return dateToDatetimeLocal(date);
}

function isoFromDatetimeLocal(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString();
}

function todayUtcDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function amountToCents(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  const cents = Math.round(parsed * 100);
  return cents > 0 ? cents : null;
}

function centsToAmountString(value: number): string {
  return (value / 100).toFixed(2);
}

// Contact tab

type ContactDraft = {
  kind: PersonContactEntryKind;
  occurred_at_local: string;
  summary: string;
  notes: string;
};

function blankContactDraft(): ContactDraft {
  return {
    kind: "note",
    occurred_at_local: dateToDatetimeLocal(new Date()),
    summary: "",
    notes: "",
  };
}

const contactEntries = ref<PersonContactEntry[]>([]);
const contactLoading = ref(false);
const contactError = ref("");
const contactDraft = ref<ContactDraft>(blankContactDraft());
const contactSaving = ref(false);
const contactEditingId = ref("");

const contactDeleteConfirmOpen = ref(false);
const pendingContactDelete = ref<PersonContactEntry | null>(null);
const contactDeleting = ref(false);

async function refreshContactEntries() {
  contactError.value = "";

  if (!props.open || !props.orgId) {
    contactEntries.value = [];
    return;
  }
  if (activeTabKey.value !== "contact") {
    return;
  }

  const person = currentPerson.value;
  if (!person) {
    contactEntries.value = [];
    return;
  }

  contactLoading.value = true;
  try {
    const res = await api.listPersonContactEntries(props.orgId, person.id);
    contactEntries.value = res.entries;
  } catch (err) {
    contactEntries.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      contactError.value = "Not permitted.";
      return;
    }
    contactError.value = err instanceof Error ? err.message : String(err);
  } finally {
    contactLoading.value = false;
  }
}

watch(
  () => [props.open, activeTabKey.value, currentPerson.value?.id],
  () => void refreshContactEntries(),
  { immediate: true }
);

function startEditContact(entry: PersonContactEntry) {
  contactEditingId.value = entry.id;
  contactDraft.value = {
    kind: entry.kind,
    occurred_at_local: datetimeLocalFromIso(entry.occurred_at),
    summary: entry.summary || "",
    notes: entry.notes || "",
  };
}

function cancelEditContact() {
  contactEditingId.value = "";
  contactDraft.value = blankContactDraft();
}

async function saveContactEntry() {
  contactError.value = "";

  if (!props.canManage) {
    contactError.value = "Not permitted.";
    return;
  }
  if (!props.orgId) {
    contactError.value = "Select an org first.";
    return;
  }

  const person = currentPerson.value;
  if (!person) {
    contactError.value = "Save the person before adding entries.";
    return;
  }

  const occurredAt = isoFromDatetimeLocal(contactDraft.value.occurred_at_local);
  if (!occurredAt) {
    contactError.value = "Choose a valid date/time.";
    return;
  }

  const payload = {
    kind: contactDraft.value.kind,
    occurred_at: occurredAt,
    summary: contactDraft.value.summary.trim() ? contactDraft.value.summary.trim() : undefined,
    notes: contactDraft.value.notes.trim() ? contactDraft.value.notes.trim() : undefined,
  };

  contactSaving.value = true;
  try {
    if (contactEditingId.value) {
      await api.patchPersonContactEntry(props.orgId, person.id, contactEditingId.value, payload);
    } else {
      await api.createPersonContactEntry(props.orgId, person.id, payload);
    }

    contactDraft.value = blankContactDraft();
    contactEditingId.value = "";
    await refreshContactEntries();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      contactError.value = "Not permitted.";
      return;
    }
    contactError.value = err instanceof Error ? err.message : String(err);
  } finally {
    contactSaving.value = false;
  }
}

function requestDeleteContact(entry: PersonContactEntry) {
  contactError.value = "";
  pendingContactDelete.value = entry;
  contactDeleteConfirmOpen.value = true;
}

async function deleteContact() {
  contactError.value = "";
  const entry = pendingContactDelete.value;
  const person = currentPerson.value;
  if (!entry || !person) {
    contactError.value = "No contact entry selected.";
    return;
  }

  contactDeleting.value = true;
  try {
    await api.deletePersonContactEntry(props.orgId, person.id, entry.id);
    contactDeleteConfirmOpen.value = false;
    pendingContactDelete.value = null;
    await refreshContactEntries();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      contactError.value = "Not permitted.";
      return;
    }
    contactError.value = err instanceof Error ? err.message : String(err);
  } finally {
    contactDeleting.value = false;
  }
}

// Messages tab

const messageThreads = ref<PersonMessageThread[]>([]);
const messageThreadsLoading = ref(false);
const messageThreadsError = ref("");

const threadDraftTitle = ref("");
const threadEditingId = ref("");
const threadSaving = ref(false);

const threadDeleteConfirmOpen = ref(false);
const pendingThreadDelete = ref<PersonMessageThread | null>(null);
const threadDeleting = ref(false);

const selectedThreadId = ref("");
const selectedThread = computed(() => messageThreads.value.find((t) => t.id === selectedThreadId.value) ?? null);

const threadMessages = ref<PersonMessage[]>([]);
const threadMessagesLoading = ref(false);
const threadMessagesError = ref("");
const messageDraft = ref("");
const messageSending = ref(false);

async function refreshMessageThreads() {
  messageThreadsError.value = "";

  if (!props.open || !props.orgId) {
    messageThreads.value = [];
    return;
  }
  if (activeTabKey.value !== "messages") {
    return;
  }

  const person = currentPerson.value;
  if (!person) {
    messageThreads.value = [];
    return;
  }

  messageThreadsLoading.value = true;
  try {
    const res = await api.listPersonMessageThreads(props.orgId, person.id);
    messageThreads.value = res.threads;

    if (selectedThreadId.value && res.threads.some((t) => t.id === selectedThreadId.value)) {
      return;
    }
    selectedThreadId.value = res.threads[0]?.id ?? "";
  } catch (err) {
    messageThreads.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      messageThreadsError.value = "Not permitted.";
      return;
    }
    messageThreadsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    messageThreadsLoading.value = false;
  }
}

async function refreshThreadMessages() {
  threadMessagesError.value = "";

  if (!props.open || !props.orgId) {
    threadMessages.value = [];
    return;
  }
  if (activeTabKey.value !== "messages") {
    return;
  }

  const person = currentPerson.value;
  if (!person || !selectedThreadId.value) {
    threadMessages.value = [];
    return;
  }

  threadMessagesLoading.value = true;
  try {
    const res = await api.listPersonThreadMessages(props.orgId, person.id, selectedThreadId.value);
    threadMessages.value = res.messages;
  } catch (err) {
    threadMessages.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      threadMessagesError.value = "Not permitted.";
      return;
    }
    threadMessagesError.value = err instanceof Error ? err.message : String(err);
  } finally {
    threadMessagesLoading.value = false;
  }
}

watch(
  () => [props.open, activeTabKey.value, currentPerson.value?.id],
  () => void refreshMessageThreads(),
  { immediate: true }
);

watch(
  () => [props.open, activeTabKey.value, currentPerson.value?.id, selectedThreadId.value],
  () => void refreshThreadMessages(),
  { immediate: true }
);

function startEditThread(thread: PersonMessageThread) {
  threadEditingId.value = thread.id;
  threadDraftTitle.value = thread.title || "";
}

function cancelEditThread() {
  threadEditingId.value = "";
  threadDraftTitle.value = "";
}

async function saveThread() {
  messageThreadsError.value = "";

  if (!props.canManage) {
    messageThreadsError.value = "Not permitted.";
    return;
  }

  const person = currentPerson.value;
  if (!props.orgId || !person) {
    messageThreadsError.value = "Save the person first.";
    return;
  }

  const title = threadDraftTitle.value.trim();
  if (!title) {
    messageThreadsError.value = "Title is required.";
    return;
  }

  threadSaving.value = true;
  try {
    if (threadEditingId.value) {
      await api.patchPersonMessageThread(props.orgId, person.id, threadEditingId.value, { title });
    } else {
      const res = await api.createPersonMessageThread(props.orgId, person.id, { title });
      selectedThreadId.value = res.thread.id;
    }

    cancelEditThread();
    await refreshMessageThreads();
    await refreshThreadMessages();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      messageThreadsError.value = "Not permitted.";
      return;
    }
    messageThreadsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    threadSaving.value = false;
  }
}

function requestDeleteThread(thread: PersonMessageThread) {
  messageThreadsError.value = "";
  pendingThreadDelete.value = thread;
  threadDeleteConfirmOpen.value = true;
}

async function deleteThread() {
  messageThreadsError.value = "";
  const person = currentPerson.value;
  const thread = pendingThreadDelete.value;
  if (!props.orgId || !person || !thread) {
    messageThreadsError.value = "No thread selected.";
    return;
  }

  threadDeleting.value = true;
  try {
    await api.deletePersonMessageThread(props.orgId, person.id, thread.id);
    threadDeleteConfirmOpen.value = false;
    pendingThreadDelete.value = null;
    if (selectedThreadId.value === thread.id) {
      selectedThreadId.value = "";
      threadMessages.value = [];
    }
    await refreshMessageThreads();
    await refreshThreadMessages();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      messageThreadsError.value = "Not permitted.";
      return;
    }
    messageThreadsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    threadDeleting.value = false;
  }
}

async function sendMessage() {
  threadMessagesError.value = "";

  if (!props.canManage) {
    threadMessagesError.value = "Not permitted.";
    return;
  }

  const person = currentPerson.value;
  const threadId = selectedThreadId.value;
  if (!props.orgId || !person || !threadId) {
    threadMessagesError.value = "Select a thread first.";
    return;
  }

  const body_markdown = messageDraft.value.trim();
  if (!body_markdown) {
    threadMessagesError.value = "Message body is required.";
    return;
  }

  messageSending.value = true;
  try {
    await api.createPersonThreadMessage(props.orgId, person.id, threadId, { body_markdown });
    messageDraft.value = "";
    await refreshMessageThreads();
    await refreshThreadMessages();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      threadMessagesError.value = "Not permitted.";
      return;
    }
    threadMessagesError.value = err instanceof Error ? err.message : String(err);
  } finally {
    messageSending.value = false;
  }
}

// Payments tab

type RateDraft = {
  currency: string;
  amount: string;
  effective_date: string;
  notes: string;
};

function blankRateDraft(): RateDraft {
  return {
    currency: "USD",
    amount: "",
    effective_date: todayUtcDate(),
    notes: "",
  };
}

const rates = ref<PersonRate[]>([]);
const ratesLoading = ref(false);
const ratesError = ref("");
const rateDraft = ref<RateDraft>(blankRateDraft());
const rateSaving = ref(false);
const rateEditingId = ref("");

const rateDeleteConfirmOpen = ref(false);
const pendingRateDelete = ref<PersonRate | null>(null);
const rateDeleting = ref(false);

async function refreshRates() {
  ratesError.value = "";

  if (!props.open || !props.orgId) {
    rates.value = [];
    return;
  }
  if (activeTabKey.value !== "payments") {
    return;
  }

  const person = currentPerson.value;
  if (!person) {
    rates.value = [];
    return;
  }

  ratesLoading.value = true;
  try {
    const res = await api.listPersonRates(props.orgId, person.id);
    rates.value = res.rates;
  } catch (err) {
    rates.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      ratesError.value = "Not permitted.";
      return;
    }
    ratesError.value = err instanceof Error ? err.message : String(err);
  } finally {
    ratesLoading.value = false;
  }
}

function startEditRate(rate: PersonRate) {
  rateEditingId.value = rate.id;
  rateDraft.value = {
    currency: rate.currency || "USD",
    amount: centsToAmountString(rate.amount_cents),
    effective_date: rate.effective_date,
    notes: rate.notes || "",
  };
}

function cancelEditRate() {
  rateEditingId.value = "";
  rateDraft.value = blankRateDraft();
}

async function saveRate() {
  ratesError.value = "";

  if (!props.canManage) {
    ratesError.value = "Not permitted.";
    return;
  }

  const person = currentPerson.value;
  if (!props.orgId || !person) {
    ratesError.value = "Save the person first.";
    return;
  }

  const amount_cents = amountToCents(rateDraft.value.amount);
  if (!amount_cents) {
    ratesError.value = "Amount must be a positive number.";
    return;
  }

  const payload = {
    currency: rateDraft.value.currency.trim() || "USD",
    amount_cents,
    effective_date: rateDraft.value.effective_date,
    notes: rateDraft.value.notes.trim() ? rateDraft.value.notes.trim() : undefined,
  };

  rateSaving.value = true;
  try {
    if (rateEditingId.value) {
      await api.patchPersonRate(props.orgId, person.id, rateEditingId.value, payload);
    } else {
      await api.createPersonRate(props.orgId, person.id, payload);
    }
    cancelEditRate();
    await refreshRates();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      ratesError.value = "Not permitted.";
      return;
    }
    ratesError.value = err instanceof Error ? err.message : String(err);
  } finally {
    rateSaving.value = false;
  }
}

function requestDeleteRate(rate: PersonRate) {
  ratesError.value = "";
  pendingRateDelete.value = rate;
  rateDeleteConfirmOpen.value = true;
}

async function deleteRate() {
  ratesError.value = "";
  const person = currentPerson.value;
  const rate = pendingRateDelete.value;
  if (!props.orgId || !person || !rate) {
    ratesError.value = "No rate selected.";
    return;
  }

  rateDeleting.value = true;
  try {
    await api.deletePersonRate(props.orgId, person.id, rate.id);
    rateDeleteConfirmOpen.value = false;
    pendingRateDelete.value = null;
    await refreshRates();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      ratesError.value = "Not permitted.";
      return;
    }
    ratesError.value = err instanceof Error ? err.message : String(err);
  } finally {
    rateDeleting.value = false;
  }
}

type PaymentDraft = {
  currency: string;
  amount: string;
  paid_date: string;
  notes: string;
};

function blankPaymentDraft(): PaymentDraft {
  return {
    currency: "USD",
    amount: "",
    paid_date: todayUtcDate(),
    notes: "",
  };
}

const payments = ref<PersonPayment[]>([]);
const paymentsLoading = ref(false);
const paymentsError = ref("");
const paymentDraft = ref<PaymentDraft>(blankPaymentDraft());
const paymentSaving = ref(false);
const paymentEditingId = ref("");

const paymentDeleteConfirmOpen = ref(false);
const pendingPaymentDelete = ref<PersonPayment | null>(null);
const paymentDeleting = ref(false);

async function refreshPayments() {
  paymentsError.value = "";

  if (!props.open || !props.orgId) {
    payments.value = [];
    return;
  }
  if (activeTabKey.value !== "payments") {
    return;
  }

  const person = currentPerson.value;
  if (!person) {
    payments.value = [];
    return;
  }

  paymentsLoading.value = true;
  try {
    const res = await api.listPersonPayments(props.orgId, person.id);
    payments.value = res.payments;
  } catch (err) {
    payments.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      paymentsError.value = "Not permitted.";
      return;
    }
    paymentsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    paymentsLoading.value = false;
  }
}

watch(
  () => [props.open, activeTabKey.value, currentPerson.value?.id],
  () => {
    void refreshRates();
    void refreshPayments();
  },
  { immediate: true }
);

function startEditPayment(payment: PersonPayment) {
  paymentEditingId.value = payment.id;
  paymentDraft.value = {
    currency: payment.currency || "USD",
    amount: centsToAmountString(payment.amount_cents),
    paid_date: payment.paid_date,
    notes: payment.notes || "",
  };
}

function cancelEditPayment() {
  paymentEditingId.value = "";
  paymentDraft.value = blankPaymentDraft();
}

async function savePayment() {
  paymentsError.value = "";

  if (!props.canManage) {
    paymentsError.value = "Not permitted.";
    return;
  }

  const person = currentPerson.value;
  if (!props.orgId || !person) {
    paymentsError.value = "Save the person first.";
    return;
  }

  const amount_cents = amountToCents(paymentDraft.value.amount);
  if (!amount_cents) {
    paymentsError.value = "Amount must be a positive number.";
    return;
  }

  const payload = {
    currency: paymentDraft.value.currency.trim() || "USD",
    amount_cents,
    paid_date: paymentDraft.value.paid_date,
    notes: paymentDraft.value.notes.trim() ? paymentDraft.value.notes.trim() : undefined,
  };

  paymentSaving.value = true;
  try {
    if (paymentEditingId.value) {
      await api.patchPersonPayment(props.orgId, person.id, paymentEditingId.value, payload);
    } else {
      await api.createPersonPayment(props.orgId, person.id, payload);
    }
    cancelEditPayment();
    await refreshPayments();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      paymentsError.value = "Not permitted.";
      return;
    }
    paymentsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    paymentSaving.value = false;
  }
}

function requestDeletePayment(payment: PersonPayment) {
  paymentsError.value = "";
  pendingPaymentDelete.value = payment;
  paymentDeleteConfirmOpen.value = true;
}

async function deletePayment() {
  paymentsError.value = "";
  const person = currentPerson.value;
  const payment = pendingPaymentDelete.value;
  if (!props.orgId || !person || !payment) {
    paymentsError.value = "No payment selected.";
    return;
  }

  paymentDeleting.value = true;
  try {
    await api.deletePersonPayment(props.orgId, person.id, payment.id);
    paymentDeleteConfirmOpen.value = false;
    pendingPaymentDelete.value = null;
    await refreshPayments();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      paymentsError.value = "Not permitted.";
      return;
    }
    paymentsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    paymentDeleting.value = false;
  }
}

// API keys tab

const newKeyName = ref("viarah-cli");
const newProjectId = ref("");
const scopeRead = ref(true);
const scopeWrite = ref(false);
const creating = ref(false);

const clipboardStatus = ref("");

const rotateModalOpen = ref(false);
const pendingRotateKey = ref<ApiKey | null>(null);
const rotating = ref(false);

const revokeModalOpen = ref(false);
const pendingRevokeKey = ref<ApiKey | null>(null);
const revoking = ref(false);

const projectNameById = computed(() => {
  const map: Record<string, string> = {};
  for (const p of context.projects) {
    map[p.id] = p.name;
  }
  return map;
});

function dismissTokenMaterial() {
  tokenMaterial.value = null;
  clipboardStatus.value = "";
}

async function copyText(value: string) {
  clipboardStatus.value = "";
  if (!value) {
    return;
  }

  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      clipboardStatus.value = "Copied.";
      return;
    }
    throw new Error("Clipboard API unavailable");
  } catch {
    clipboardStatus.value = "Copy failed; select and copy manually.";
  }
}

function scopesForDraft(): string[] {
  const scopes: string[] = [];
  if (scopeRead.value) {
    scopes.push("read");
  }
  if (scopeWrite.value) {
    scopes.push("write");
  }
  if (!scopes.length) {
    scopes.push("read");
  }
  return scopes;
}

async function refreshApiKeys() {
  apiKeysError.value = "";
  actionError.value = "";

  const person = currentPerson.value;
  if (!props.orgId || !person?.user?.id) {
    apiKeys.value = [];
    return;
  }

  apiKeysLoading.value = true;
  try {
    const res = await api.listApiKeys(props.orgId, { owner_user_id: person.user.id });
    apiKeys.value = res.api_keys;
  } catch (err) {
    apiKeys.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      apiKeysError.value = "Not permitted.";
      return;
    }
    apiKeysError.value = err instanceof Error ? err.message : String(err);
  } finally {
    apiKeysLoading.value = false;
  }
}

watch(
  () => [props.open, activeTabKey.value, currentPerson.value?.user?.id],
  ([open, tab]) => {
    if (!open) {
      return;
    }
    if (tab !== "api_keys") {
      return;
    }
    void refreshApiKeys();
  }
);

async function createKey() {
  actionError.value = "";

  if (!props.orgId) {
    actionError.value = "Select an org first.";
    return;
  }

  const person = currentPerson.value;
  if (!person?.user?.id) {
    actionError.value = "API keys are available after invite acceptance.";
    return;
  }

  if (!props.canManage) {
    actionError.value = "Not permitted.";
    return;
  }

  const name = newKeyName.value.trim();
  if (!name) {
    actionError.value = "Name is required.";
    return;
  }

  creating.value = true;
  try {
    const res = await api.createApiKey(props.orgId, {
      name,
      project_id: newProjectId.value ? newProjectId.value : null,
      scopes: scopesForDraft(),
      owner_user_id: person.user.id,
    });

    tokenMaterial.value = { token: res.token, apiKey: res.api_key };
    clipboardStatus.value = "";

    newKeyName.value = "viarah-cli";
    newProjectId.value = "";
    scopeRead.value = true;
    scopeWrite.value = false;

    await refreshApiKeys();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      actionError.value = "Not permitted.";
      return;
    }
    actionError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creating.value = false;
  }
}

function requestRotateKey(key: ApiKey) {
  actionError.value = "";
  pendingRotateKey.value = key;
  rotateModalOpen.value = true;
}

async function rotateKey() {
  actionError.value = "";
  const key = pendingRotateKey.value;
  if (!key) {
    actionError.value = "No API key selected.";
    return;
  }

  rotating.value = true;
  try {
    const res = await api.rotateApiKey(key.id);
    tokenMaterial.value = { token: res.token, apiKey: res.api_key };
    clipboardStatus.value = "";
    rotateModalOpen.value = false;
    pendingRotateKey.value = null;
    await refreshApiKeys();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      actionError.value = "Not permitted.";
      return;
    }
    actionError.value = err instanceof Error ? err.message : String(err);
  } finally {
    rotating.value = false;
  }
}

function requestRevokeKey(key: ApiKey) {
  actionError.value = "";
  pendingRevokeKey.value = key;
  revokeModalOpen.value = true;
}

async function revokeKey() {
  actionError.value = "";
  const key = pendingRevokeKey.value;
  if (!key) {
    actionError.value = "No API key selected.";
    return;
  }

  revoking.value = true;
  try {
    await api.revokeApiKey(key.id);
    revokeModalOpen.value = false;
    pendingRevokeKey.value = null;
    await refreshApiKeys();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      actionError.value = "Not permitted.";
      return;
    }
    actionError.value = err instanceof Error ? err.message : String(err);
  } finally {
    revoking.value = false;
  }
}
</script>

<template>
  <pf-modal
    :open="props.open"
    :title="modalTitle"
    variant="large"
    @update:open="emit('update:open', $event)"
  >
    <div class="header-row">
      <div class="labels">
        <VlLabel v-if="statusLabel" :color="statusLabel.color">{{ statusLabel.text }}</VlLabel>
        <VlLabel v-if="membershipRoleLabel" :color="membershipRoleLabel.color" variant="outline">
          {{ membershipRoleLabel.text }}
        </VlLabel>
      </div>

      <pf-alert v-if="savedBanner" inline variant="success" :title="savedBanner" />
      <pf-alert v-if="error" inline variant="danger" :title="error" />
    </div>

    <pf-tabs v-model:active-key="activeTabKey">
      <pf-tab :key="'profile'" title="Profile">
        <div class="tab-stack">
          <pf-form class="form">
            <div class="profile-grid">
              <pf-form-group label="Full name" field-id="person-full-name">
                <pf-text-input id="person-full-name" v-model="draft.full_name" type="text" autocomplete="name" />
              </pf-form-group>

              <pf-form-group label="Preferred name" field-id="person-preferred-name">
                <pf-text-input
                  id="person-preferred-name"
                  v-model="draft.preferred_name"
                  type="text"
                  autocomplete="nickname"
                />
              </pf-form-group>

              <pf-form-group label="Email" field-id="person-email">
                <pf-text-input
                  id="person-email"
                  v-model="draft.email"
                  type="email"
                  autocomplete="email"
                  placeholder="Optional until inviting"
                />
              </pf-form-group>

              <pf-form-group label="Title" field-id="person-title">
                <pf-text-input id="person-title" v-model="draft.title" type="text" autocomplete="organization-title" />
              </pf-form-group>

              <pf-form-group label="Timezone" field-id="person-timezone">
                <pf-text-input id="person-timezone" v-model="draft.timezone" type="text" placeholder="UTC" />
              </pf-form-group>

              <pf-form-group label="Location" field-id="person-location">
                <pf-text-input id="person-location" v-model="draft.location" type="text" />
              </pf-form-group>

              <pf-form-group label="Phone" field-id="person-phone">
                <pf-text-input id="person-phone" v-model="draft.phone" type="tel" autocomplete="tel" />
              </pf-form-group>

              <pf-form-group label="Slack" field-id="person-slack">
                <pf-text-input id="person-slack" v-model="draft.slack_handle" type="text" placeholder="@handle" />
              </pf-form-group>

              <pf-form-group class="full" label="LinkedIn" field-id="person-linkedin">
                <pf-text-input id="person-linkedin" v-model="draft.linkedin_url" type="url" placeholder="https://…" />
              </pf-form-group>

              <pf-form-group class="full" label="GitLab username" field-id="person-gitlab-username">
                <pf-text-input
                  id="person-gitlab-username"
                  v-model="draft.gitlab_username"
                  type="text"
                  placeholder="e.g. alice"
                />
                <pf-helper-text>
                  <pf-helper-text-item>
                    Used to map GitLab issue participants + work history (must match the org GitLab integration username).
                  </pf-helper-text-item>
                </pf-helper-text>
              </pf-form-group>

              <pf-form-group class="full" label="Bio" field-id="person-bio">
                <pf-textarea id="person-bio" v-model="draft.bio" rows="3" />
              </pf-form-group>

              <pf-form-group class="full" label="Notes" field-id="person-notes">
                <pf-textarea id="person-notes" v-model="draft.notes" rows="3" />
              </pf-form-group>
            </div>
          </pf-form>

          <pf-card v-if="props.canManage" class="invite-card">
            <pf-card-title>
              <div class="invite-title">Invite</div>
            </pf-card-title>
            <pf-card-body>
              <pf-content>
                <p class="muted">
                  Invites are separate from People records. Inviting creates or links a User and org membership.
                </p>
              </pf-content>

              <pf-alert v-if="inviteError" inline variant="danger" :title="inviteError" />

              <pf-form class="invite-form">
                <pf-form-group label="Role" field-id="person-invite-role">
                  <pf-form-select id="person-invite-role" v-model="inviteRole">
                    <pf-form-select-option value="member">Member</pf-form-select-option>
                    <pf-form-select-option value="client">Client</pf-form-select-option>
                    <pf-form-select-option value="pm">PM</pf-form-select-option>
                    <pf-form-select-option value="admin">Admin</pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>

                <pf-form-group label="Email" field-id="person-invite-email">
                  <pf-text-input id="person-invite-email" v-model="inviteEmail" type="email" autocomplete="email" />
                </pf-form-group>

                <pf-form-group label="Message (optional)" field-id="person-invite-message">
                  <pf-textarea id="person-invite-message" v-model="inviteMessage" rows="2" />
                </pf-form-group>

                <div v-if="activeInvite" class="invite-meta">
                  <VlLabel :color="activeInvite.status === 'active' ? 'orange' : 'grey'" variant="outline">
                    {{ activeInvite.status.toUpperCase() }}
                  </VlLabel>
                  <span class="muted">Expires: {{ activeInvite.expires_at }}</span>
                </div>

                <div class="invite-actions">
                  <pf-button
                    v-if="!activeInvite"
                    type="button"
                    :disabled="inviting || !currentPerson"
                    @click="sendInvite"
                  >
                    {{ inviting ? "Inviting…" : "Send invite" }}
                  </pf-button>

                  <pf-button v-else type="button" variant="secondary" :disabled="inviting" @click="resendInvite">
                    {{ inviting ? "Working…" : "Resend link" }}
                  </pf-button>

                  <pf-button v-if="activeInvite" type="button" variant="danger" :disabled="inviting" @click="requestRevokeInvite">
                    Revoke
                  </pf-button>
                </div>

                <pf-alert
                  v-if="!currentPerson"
                  inline
                  variant="info"
                  title="Save this person before sending an invite."
                />
              </pf-form>
            </pf-card-body>
          </pf-card>
        </div>
      </pf-tab>

      <pf-tab :key="'skills'" title="Skills">
        <div class="tab-stack">
          <pf-content>
            <p class="muted">Use skills to support staffing and availability search.</p>
          </pf-content>

          <pf-form class="form">
            <pf-form-group label="Add skill" field-id="person-skill-add">
              <pf-input-group>
                <pf-text-input
                  id="person-skill-add"
                  v-model="skillInput"
                  type="text"
                  placeholder="e.g., React, Django, UX"
                  @keydown.enter.prevent="addSkill"
                />
                <pf-button type="button" variant="secondary" :disabled="!skillInput.trim()" @click="addSkill">
                  Add
                </pf-button>
              </pf-input-group>
              <pf-helper-text>
                <pf-helper-text-item>Comma or newline separated. Duplicate skills are ignored.</pf-helper-text-item>
              </pf-helper-text>
            </pf-form-group>

            <pf-form-group label="Current skills">
              <pf-label-group v-if="draft.skills.length" :num-labels="12">
                <pf-label
                  v-for="skill in draft.skills"
                  :key="skill"
                  color="blue"
                  variant="outline"
                  close-btn-aria-label="Remove skill"
                  :on-close="() => removeSkill(skill)"
                >
                  {{ skill }}
                </pf-label>
              </pf-label-group>
              <pf-empty-state v-else>
                <pf-empty-state-header title="No skills yet" heading-level="h3" />
                <pf-empty-state-body>Add a few skills to make staffing/search work well.</pf-empty-state-body>
              </pf-empty-state>
            </pf-form-group>
          </pf-form>
        </div>
      </pf-tab>

      <pf-tab :key="'availability'" title="Availability">
        <TeamPersonAvailabilityTab :person="currentPerson" :can-manage="props.canManage" />
      </pf-tab>

      <pf-tab :key="'contact'" title="Contact">
        <div class="tab-stack">
          <pf-content>
            <p class="muted">Internal contact history (PM/admin only).</p>
          </pf-content>

          <pf-alert v-if="contactError" inline variant="danger" :title="contactError" />

          <div v-if="contactLoading" class="inline-loading">
            <pf-spinner size="sm" aria-label="Loading contact entries" />
            <span class="muted">Loading contact entries…</span>
          </div>

          <pf-empty-state v-else-if="!currentPerson">
            <pf-empty-state-header title="Save first" heading-level="h3" />
            <pf-empty-state-body>Save the person before managing contact history.</pf-empty-state-body>
          </pf-empty-state>

          <pf-empty-state v-else-if="!props.canManage">
            <pf-empty-state-header title="Not permitted" heading-level="h3" />
            <pf-empty-state-body>Contact history is available to PM/admin users.</pf-empty-state-body>
          </pf-empty-state>

          <template v-else>
            <pf-card>
              <pf-card-title>{{ contactEditingId ? "Edit entry" : "Add entry" }}</pf-card-title>
              <pf-card-body>
                <pf-form class="stack-form" @submit.prevent="saveContactEntry">
                  <pf-form-group label="Kind" field-id="contact-kind">
                    <pf-form-select id="contact-kind" v-model="contactDraft.kind">
                      <pf-form-select-option value="note">Note</pf-form-select-option>
                      <pf-form-select-option value="call">Call</pf-form-select-option>
                      <pf-form-select-option value="email">Email</pf-form-select-option>
                      <pf-form-select-option value="meeting">Meeting</pf-form-select-option>
                    </pf-form-select>
                  </pf-form-group>

                  <pf-form-group label="Occurred at" field-id="contact-occurred-at">
                    <pf-text-input
                      id="contact-occurred-at"
                      v-model="contactDraft.occurred_at_local"
                      type="datetime-local"
                      required
                    />
                  </pf-form-group>

                  <pf-form-group label="Summary" field-id="contact-summary">
                    <pf-text-input
                      id="contact-summary"
                      v-model="contactDraft.summary"
                      type="text"
                      placeholder="Short summary (optional)"
                    />
                  </pf-form-group>

                  <pf-form-group label="Notes" field-id="contact-notes">
                    <pf-textarea id="contact-notes" v-model="contactDraft.notes" rows="4" />
                  </pf-form-group>

                  <div class="row-actions">
                    <pf-button type="submit" :disabled="contactSaving || contactDeleting">
                      {{ contactSaving ? "Saving…" : contactEditingId ? "Save changes" : "Add entry" }}
                    </pf-button>
                    <pf-button
                      v-if="contactEditingId"
                      type="button"
                      variant="secondary"
                      :disabled="contactSaving"
                      @click="cancelEditContact"
                    >
                      Cancel
                    </pf-button>
                  </div>
                </pf-form>
              </pf-card-body>
            </pf-card>

            <pf-card>
              <pf-card-title>Entries</pf-card-title>
              <pf-card-body>
                <pf-empty-state v-if="contactEntries.length === 0" variant="small">
                  <pf-empty-state-header title="No contact entries yet" heading-level="h4" />
                  <pf-empty-state-body>Add a note, call, email, or meeting entry.</pf-empty-state-body>
                </pf-empty-state>

                <div v-else class="table-wrap">
                  <pf-table aria-label="Contact entries">
                    <pf-thead>
                      <pf-tr>
                        <pf-th>When</pf-th>
                        <pf-th>Kind</pf-th>
                        <pf-th>Summary</pf-th>
                        <pf-th>Notes</pf-th>
                        <pf-th align-right>Actions</pf-th>
                      </pf-tr>
                    </pf-thead>
                    <pf-tbody>
                      <pf-tr v-for="entry in contactEntries" :key="entry.id">
                        <pf-td data-label="When">
                          <VlLabel color="blue">{{ formatTimestamp(entry.occurred_at) }}</VlLabel>
                        </pf-td>
                        <pf-td data-label="Kind">
                          <VlLabel :color="contactKindColor(entry.kind)" variant="outline">
                            {{ contactKindLabel(entry.kind) }}
                          </VlLabel>
                        </pf-td>
                        <pf-td data-label="Summary">{{ entry.summary || "—" }}</pf-td>
                        <pf-td data-label="Notes">{{ entry.notes || "—" }}</pf-td>
                        <pf-td data-label="Actions" align-right>
                          <div class="row-actions right">
                            <pf-button type="button" variant="secondary" small @click="startEditContact(entry)">
                              Edit
                            </pf-button>
                            <pf-button
                              type="button"
                              variant="danger"
                              small
                              :disabled="contactDeleting"
                              @click="requestDeleteContact(entry)"
                            >
                              Delete
                            </pf-button>
                          </div>
                        </pf-td>
                      </pf-tr>
                    </pf-tbody>
                  </pf-table>
                </div>
              </pf-card-body>
            </pf-card>
          </template>
        </div>
      </pf-tab>

      <pf-tab :key="'messages'" title="Messages">
        <div class="tab-stack">
          <pf-content>
            <p class="muted">Internal message threads per person (PM/admin only).</p>
          </pf-content>

          <pf-alert v-if="messageThreadsError" inline variant="danger" :title="messageThreadsError" />
          <pf-alert v-if="threadMessagesError" inline variant="danger" :title="threadMessagesError" />

          <div v-if="messageThreadsLoading" class="inline-loading">
            <pf-spinner size="sm" aria-label="Loading message threads" />
            <span class="muted">Loading message threads…</span>
          </div>

          <pf-empty-state v-else-if="!currentPerson">
            <pf-empty-state-header title="Save first" heading-level="h3" />
            <pf-empty-state-body>Save the person before managing message threads.</pf-empty-state-body>
          </pf-empty-state>

          <pf-empty-state v-else-if="!props.canManage">
            <pf-empty-state-header title="Not permitted" heading-level="h3" />
            <pf-empty-state-body>Message threads are available to PM/admin users.</pf-empty-state-body>
          </pf-empty-state>

          <template v-else>
            <pf-card>
              <pf-card-title>{{ threadEditingId ? "Edit thread" : "New thread" }}</pf-card-title>
              <pf-card-body>
                <pf-form class="stack-form" @submit.prevent="saveThread">
                  <pf-form-group label="Title" field-id="thread-title">
                    <pf-text-input
                      id="thread-title"
                      v-model="threadDraftTitle"
                      type="text"
                      placeholder="e.g., Recruiting follow-up"
                      required
                    />
                  </pf-form-group>

                  <div class="row-actions">
                    <pf-button type="submit" :disabled="threadSaving || threadDeleting">
                      {{ threadSaving ? "Saving…" : threadEditingId ? "Save changes" : "Create thread" }}
                    </pf-button>
                    <pf-button
                      v-if="threadEditingId"
                      type="button"
                      variant="secondary"
                      :disabled="threadSaving"
                      @click="cancelEditThread"
                    >
                      Cancel
                    </pf-button>
                  </div>
                </pf-form>

                <pf-empty-state v-if="messageThreads.length === 0" variant="small">
                  <pf-empty-state-header title="No threads yet" heading-level="h4" />
                  <pf-empty-state-body>Create a thread to start tracking conversations.</pf-empty-state-body>
                </pf-empty-state>

                <div v-else class="table-wrap">
                  <pf-table aria-label="Message threads">
                    <pf-thead>
                      <pf-tr>
                        <pf-th>Thread</pf-th>
                        <pf-th>Updated</pf-th>
                        <pf-th>Messages</pf-th>
                        <pf-th align-right>Actions</pf-th>
                      </pf-tr>
                    </pf-thead>
                    <pf-tbody>
                      <pf-tr v-for="thread in messageThreads" :key="thread.id">
                        <pf-td data-label="Thread">
                          <pf-button type="button" variant="link" small @click="selectedThreadId = thread.id">
                            <strong v-if="selectedThreadId === thread.id">{{ thread.title }}</strong>
                            <span v-else>{{ thread.title }}</span>
                          </pf-button>
                        </pf-td>
                        <pf-td data-label="Updated">
                          <VlLabel color="blue">{{ formatTimestamp(thread.updated_at) }}</VlLabel>
                        </pf-td>
                        <pf-td data-label="Messages">{{ thread.message_count }}</pf-td>
                        <pf-td data-label="Actions" align-right>
                          <div class="row-actions right">
                            <pf-button type="button" variant="secondary" small @click="startEditThread(thread)">
                              Edit
                            </pf-button>
                            <pf-button
                              type="button"
                              variant="danger"
                              small
                              :disabled="threadDeleting"
                              @click="requestDeleteThread(thread)"
                            >
                              Delete
                            </pf-button>
                          </div>
                        </pf-td>
                      </pf-tr>
                    </pf-tbody>
                  </pf-table>
                </div>
              </pf-card-body>
            </pf-card>

            <pf-card>
              <pf-card-title>Messages</pf-card-title>
              <pf-card-body>
                <div v-if="threadMessagesLoading" class="inline-loading">
                  <pf-spinner size="sm" aria-label="Loading messages" />
                  <span class="muted">Loading messages…</span>
                </div>

                <pf-empty-state v-else-if="!selectedThread">
                  <pf-empty-state-header title="Select a thread" heading-level="h3" />
                  <pf-empty-state-body>Select a thread to view and send messages.</pf-empty-state-body>
                </pf-empty-state>

                <template v-else>
                  <pf-title h="3" size="md">{{ selectedThread.title }}</pf-title>

                  <pf-empty-state v-if="threadMessages.length === 0" variant="small">
                    <pf-empty-state-header title="No messages yet" heading-level="h4" />
                    <pf-empty-state-body>Send the first message.</pf-empty-state-body>
                  </pf-empty-state>

                  <pf-data-list v-else aria-label="Thread messages">
                    <pf-data-list-item v-for="msg in threadMessages" :key="msg.id" aria-label="Message">
                      <pf-data-list-item-row>
                        <pf-data-list-item-cells>
                          <pf-data-list-cell>
                            <div class="message-meta">
                              <VlLabel color="blue">{{ formatTimestamp(msg.created_at) }}</VlLabel>
                            </div>
                            <div class="message-body">{{ msg.body_markdown }}</div>
                          </pf-data-list-cell>
                        </pf-data-list-item-cells>
                      </pf-data-list-item-row>
                    </pf-data-list-item>
                  </pf-data-list>

                  <pf-form class="stack-form" @submit.prevent="sendMessage">
                    <pf-form-group label="New message" field-id="message-body">
                      <pf-textarea
                        id="message-body"
                        v-model="messageDraft"
                        rows="4"
                        placeholder="Write a message…"
                      />
                    </pf-form-group>

                    <div class="row-actions">
                      <pf-button type="submit" :disabled="messageSending || !messageDraft.trim()">
                        {{ messageSending ? "Sending…" : "Send message" }}
                      </pf-button>
                    </div>
                  </pf-form>
                </template>
              </pf-card-body>
            </pf-card>
          </template>
        </div>
      </pf-tab>

      <pf-tab :key="'projects'" title="Projects">
        <div class="tab-stack">
          <pf-content>
            <p class="muted">
              Project membership is only available for active members (invite accepted + org membership exists). Candidates cannot be
              added to projects.
            </p>
          </pf-content>

          <pf-alert v-if="projectMembershipsError" inline variant="danger" :title="projectMembershipsError" />

          <div v-if="projectMembershipsLoading" class="inline-loading">
            <pf-spinner size="sm" aria-label="Loading project memberships" />
            <span class="muted">Loading project memberships…</span>
          </div>

          <pf-empty-state v-else-if="!currentPerson">
            <pf-empty-state-header title="Save first" heading-level="h3" />
            <pf-empty-state-body>Save the person before managing project staffing.</pf-empty-state-body>
          </pf-empty-state>

          <pf-empty-state v-else-if="!currentPerson.user?.id">
            <pf-empty-state-header title="Not active yet" heading-level="h3" />
            <pf-empty-state-body>
              Candidates can be created and invited, but cannot be staffed on projects until they accept the invite and become an active
              org member.
            </pf-empty-state-body>
          </pf-empty-state>

          <pf-empty-state v-else-if="projectMemberships.length === 0">
            <pf-empty-state-header title="No project memberships" heading-level="h3" />
            <pf-empty-state-body>
              Add this person to a project from <RouterLink to="/settings/project#project-members">Project settings</RouterLink>.
            </pf-empty-state-body>
          </pf-empty-state>

          <pf-table v-else aria-label="Person project memberships">
            <pf-thead>
              <pf-tr>
                <pf-th>Project</pf-th>
                <pf-th>Added</pf-th>
                <pf-th align-right>Actions</pf-th>
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="m in projectMemberships" :key="m.id">
                <pf-td data-label="Project">
                  <strong>{{ m.project.name }}</strong>
                </pf-td>
                <pf-td data-label="Added">{{ formatTimestamp(m.created_at) }}</pf-td>
                <pf-td data-label="Actions" align-right>
                  <pf-button
                    variant="secondary"
                    small
                    :to="projectMembersManageUrl(m.project.id)"
                  >
                    Manage members
                  </pf-button>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>
        </div>
      </pf-tab>

      <pf-tab :key="'api_keys'" title="API keys">
        <div class="tab-stack">
          <pf-content>
            <p class="muted">
              Per-member API keys are intended for <strong>viarah-cli</strong>. Tokens are shown once at creation/rotation.
            </p>
          </pf-content>

          <pf-alert
            v-if="!currentPerson?.user?.id"
            inline
            variant="info"
            title="API keys are available after invite acceptance."
          />

          <pf-alert v-if="apiKeysError" inline variant="danger" :title="apiKeysError" />
          <pf-alert v-if="actionError" inline variant="danger" :title="actionError" />

          <pf-card v-if="tokenMaterial" class="token-card">
            <pf-card-title>
              <div class="token-header">
                <div>
                  <pf-title h="3" size="lg">API key token (shown once)</pf-title>
                  <p class="muted">Copy this now and store it securely. It cannot be retrieved later.</p>
                </div>
                <pf-button type="button" variant="plain" aria-label="Dismiss token" @click="dismissTokenMaterial">
                  ×
                </pf-button>
              </div>
            </pf-card-title>
            <pf-card-body>
              <pf-form>
                <pf-form-group label="Token" field-id="api-key-token">
                  <pf-textarea id="api-key-token" :model-value="tokenMaterial.token" rows="2" readonly />
                </pf-form-group>
                <pf-form-group label="Actions" field-id="api-key-actions">
                  <pf-button type="button" variant="secondary" @click="copyText(tokenMaterial.token)">Copy token</pf-button>
                  <span class="muted">{{ clipboardStatus }}</span>
                </pf-form-group>
              </pf-form>
            </pf-card-body>
          </pf-card>

          <pf-card class="create-card">
            <pf-card-title>Create key</pf-card-title>
            <pf-card-body>
              <pf-form class="key-form">
                <pf-form-group label="Name" field-id="api-key-name">
                  <pf-text-input id="api-key-name" v-model="newKeyName" type="text" />
                </pf-form-group>

                <pf-form-group label="Project restriction (optional)" field-id="api-key-project">
                  <pf-form-select id="api-key-project" v-model="newProjectId">
                    <pf-form-select-option value="">(none)</pf-form-select-option>
                    <pf-form-select-option v-for="p in context.projects" :key="p.id" :value="p.id">
                      {{ p.name }}
                    </pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>

                <pf-form-group label="Scopes">
                  <div class="scope-row">
                    <pf-checkbox id="api-key-scope-read" label="Read" :model-value="scopeRead" @update:model-value="scopeRead = Boolean($event)" />
                    <pf-checkbox id="api-key-scope-write" label="Write" :model-value="scopeWrite" @update:model-value="scopeWrite = Boolean($event)" />
                  </div>
                </pf-form-group>

                <pf-button type="button" :disabled="creating || !currentPerson?.user?.id" @click="createKey">
                  {{ creating ? "Creating…" : "Create key" }}
                </pf-button>
              </pf-form>
            </pf-card-body>
          </pf-card>

          <pf-card>
            <pf-card-title>Existing keys</pf-card-title>
            <pf-card-body>
              <div v-if="apiKeysLoading" class="inline-loading">
                <pf-spinner size="sm" aria-label="Loading API keys" />
                <span class="muted">Loading keys…</span>
              </div>

              <pf-empty-state v-else-if="!apiKeys.length">
                <pf-empty-state-header title="No API keys" heading-level="h3" />
                <pf-empty-state-body>Create a key to enable viarah-cli usage.</pf-empty-state-body>
              </pf-empty-state>

              <pf-data-list v-else aria-label="API keys">
                <pf-data-list-item v-for="key in apiKeys" :key="key.id" aria-label="API key">
                  <pf-data-list-item-row>
                    <pf-data-list-item-cells>
                      <pf-data-list-cell>
                        <div class="key-title">
                          <strong>{{ key.name }}</strong>
                          <span class="muted">{{ key.prefix }}</span>
                        </div>
                        <div class="muted">
                          Scopes: {{ key.scopes.join(", ") }}
                          <span v-if="key.project_id"> · Project: {{ projectNameById[key.project_id] || key.project_id }}</span>
                        </div>
                        <div v-if="key.last_used_at" class="muted">Last used: {{ key.last_used_at }}</div>
                        <div v-if="key.expires_at" class="muted">Expires: {{ key.expires_at }}</div>
                      </pf-data-list-cell>
                      <pf-data-list-cell class="key-actions" align-right>
                        <pf-button type="button" variant="secondary" small :disabled="rotating" @click="requestRotateKey(key)">Rotate</pf-button>
                        <pf-button type="button" variant="danger" small :disabled="revoking" @click="requestRevokeKey(key)">Revoke</pf-button>
                      </pf-data-list-cell>
                    </pf-data-list-item-cells>
                  </pf-data-list-item-row>
                </pf-data-list-item>
              </pf-data-list>
            </pf-card-body>
          </pf-card>
        </div>
      </pf-tab>

      <pf-tab :key="'payments'" title="Payments">
        <div class="tab-stack">
          <pf-content>
            <p class="muted">Rates + payments ledger (PM/admin only).</p>
          </pf-content>

          <pf-alert v-if="ratesError" inline variant="danger" :title="ratesError" />
          <pf-alert v-if="paymentsError" inline variant="danger" :title="paymentsError" />

          <div v-if="ratesLoading || paymentsLoading" class="inline-loading">
            <pf-spinner size="sm" aria-label="Loading rates and payments" />
            <span class="muted">Loading…</span>
          </div>

          <pf-empty-state v-else-if="!currentPerson">
            <pf-empty-state-header title="Save first" heading-level="h3" />
            <pf-empty-state-body>Save the person before managing rates and payments.</pf-empty-state-body>
          </pf-empty-state>

          <pf-empty-state v-else-if="!props.canManage">
            <pf-empty-state-header title="Not permitted" heading-level="h3" />
            <pf-empty-state-body>Rates and payments are available to PM/admin users.</pf-empty-state-body>
          </pf-empty-state>

          <template v-else>
            <pf-card>
              <pf-card-title>{{ rateEditingId ? "Edit rate" : "Add rate" }}</pf-card-title>
              <pf-card-body>
                <pf-form class="stack-form" @submit.prevent="saveRate">
                  <div class="grid-3">
                    <pf-form-group label="Currency" field-id="rate-currency">
                      <pf-text-input id="rate-currency" v-model="rateDraft.currency" type="text" maxlength="3" />
                    </pf-form-group>

                    <pf-form-group label="Amount" field-id="rate-amount">
                      <pf-text-input
                        id="rate-amount"
                        v-model="rateDraft.amount"
                        type="number"
                        inputmode="decimal"
                        step="0.01"
                        min="0"
                        placeholder="0.00"
                      />
                    </pf-form-group>

                    <pf-form-group label="Effective date" field-id="rate-effective-date">
                      <pf-text-input
                        id="rate-effective-date"
                        v-model="rateDraft.effective_date"
                        type="date"
                        required
                      />
                    </pf-form-group>
                  </div>

                  <pf-form-group label="Notes" field-id="rate-notes">
                    <pf-textarea id="rate-notes" v-model="rateDraft.notes" rows="2" />
                  </pf-form-group>

                  <div class="row-actions">
                    <pf-button type="submit" :disabled="rateSaving || rateDeleting">
                      {{ rateSaving ? "Saving…" : rateEditingId ? "Save changes" : "Add rate" }}
                    </pf-button>
                    <pf-button
                      v-if="rateEditingId"
                      type="button"
                      variant="secondary"
                      :disabled="rateSaving"
                      @click="cancelEditRate"
                    >
                      Cancel
                    </pf-button>
                  </div>
                </pf-form>

                <pf-empty-state v-if="rates.length === 0" variant="small">
                  <pf-empty-state-header title="No rates yet" heading-level="h4" />
                  <pf-empty-state-body>Add a rate to start tracking payments.</pf-empty-state-body>
                </pf-empty-state>

                <div v-else class="table-wrap">
                  <pf-table aria-label="Rates">
                    <pf-thead>
                      <pf-tr>
                        <pf-th>Effective</pf-th>
                        <pf-th>Amount</pf-th>
                        <pf-th>Currency</pf-th>
                        <pf-th>Notes</pf-th>
                        <pf-th align-right>Actions</pf-th>
                      </pf-tr>
                    </pf-thead>
                    <pf-tbody>
                      <pf-tr v-for="rate in rates" :key="rate.id">
                        <pf-td data-label="Effective">{{ rate.effective_date }}</pf-td>
                        <pf-td data-label="Amount">{{ centsToAmountString(rate.amount_cents) }}</pf-td>
                        <pf-td data-label="Currency">{{ rate.currency }}</pf-td>
                        <pf-td data-label="Notes">{{ rate.notes || "—" }}</pf-td>
                        <pf-td data-label="Actions" align-right>
                          <div class="row-actions right">
                            <pf-button type="button" variant="secondary" small @click="startEditRate(rate)">
                              Edit
                            </pf-button>
                            <pf-button
                              type="button"
                              variant="danger"
                              small
                              :disabled="rateDeleting"
                              @click="requestDeleteRate(rate)"
                            >
                              Delete
                            </pf-button>
                          </div>
                        </pf-td>
                      </pf-tr>
                    </pf-tbody>
                  </pf-table>
                </div>
              </pf-card-body>
            </pf-card>

            <pf-card>
              <pf-card-title>{{ paymentEditingId ? "Edit payment" : "Add payment" }}</pf-card-title>
              <pf-card-body>
                <pf-form class="stack-form" @submit.prevent="savePayment">
                  <div class="grid-3">
                    <pf-form-group label="Currency" field-id="payment-currency">
                      <pf-text-input
                        id="payment-currency"
                        v-model="paymentDraft.currency"
                        type="text"
                        maxlength="3"
                      />
                    </pf-form-group>

                    <pf-form-group label="Amount" field-id="payment-amount">
                      <pf-text-input
                        id="payment-amount"
                        v-model="paymentDraft.amount"
                        type="number"
                        inputmode="decimal"
                        step="0.01"
                        min="0"
                        placeholder="0.00"
                      />
                    </pf-form-group>

                    <pf-form-group label="Paid date" field-id="payment-paid-date">
                      <pf-text-input
                        id="payment-paid-date"
                        v-model="paymentDraft.paid_date"
                        type="date"
                        required
                      />
                    </pf-form-group>
                  </div>

                  <pf-form-group label="Notes" field-id="payment-notes">
                    <pf-textarea id="payment-notes" v-model="paymentDraft.notes" rows="2" />
                  </pf-form-group>

                  <div class="row-actions">
                    <pf-button type="submit" :disabled="paymentSaving || paymentDeleting">
                      {{ paymentSaving ? "Saving…" : paymentEditingId ? "Save changes" : "Add payment" }}
                    </pf-button>
                    <pf-button
                      v-if="paymentEditingId"
                      type="button"
                      variant="secondary"
                      :disabled="paymentSaving"
                      @click="cancelEditPayment"
                    >
                      Cancel
                    </pf-button>
                  </div>
                </pf-form>

                <pf-empty-state v-if="payments.length === 0" variant="small">
                  <pf-empty-state-header title="No payments yet" heading-level="h4" />
                  <pf-empty-state-body>Log a payment to build the ledger.</pf-empty-state-body>
                </pf-empty-state>

                <div v-else class="table-wrap">
                  <pf-table aria-label="Payments ledger">
                    <pf-thead>
                      <pf-tr>
                        <pf-th>Paid date</pf-th>
                        <pf-th>Amount</pf-th>
                        <pf-th>Currency</pf-th>
                        <pf-th>Notes</pf-th>
                        <pf-th align-right>Actions</pf-th>
                      </pf-tr>
                    </pf-thead>
                    <pf-tbody>
                      <pf-tr v-for="payment in payments" :key="payment.id">
                        <pf-td data-label="Paid date">{{ payment.paid_date }}</pf-td>
                        <pf-td data-label="Amount">{{ centsToAmountString(payment.amount_cents) }}</pf-td>
                        <pf-td data-label="Currency">{{ payment.currency }}</pf-td>
                        <pf-td data-label="Notes">{{ payment.notes || "—" }}</pf-td>
                        <pf-td data-label="Actions" align-right>
                          <div class="row-actions right">
                            <pf-button type="button" variant="secondary" small @click="startEditPayment(payment)">
                              Edit
                            </pf-button>
                            <pf-button
                              type="button"
                              variant="danger"
                              small
                              :disabled="paymentDeleting"
                              @click="requestDeletePayment(payment)"
                            >
                              Delete
                            </pf-button>
                          </div>
                        </pf-td>
                      </pf-tr>
                    </pf-tbody>
                  </pf-table>
                </div>
              </pf-card-body>
            </pf-card>
          </template>
        </div>
      </pf-tab>
    </pf-tabs>

    <template #footer>
      <pf-button type="button" :disabled="saving || !props.canManage" @click="savePerson">
        {{ saving ? "Saving…" : "Save" }}
      </pf-button>
      <pf-button type="button" variant="link" :disabled="saving" @click="close">Close</pf-button>
    </template>

    <VlConfirmModal
      v-model:open="revokeInviteConfirmOpen"
      title="Revoke invite?"
      body="This will revoke the active invite. The person will remain in the directory as a candidate until re-invited."
      confirm-label="Revoke invite"
      confirm-variant="danger"
      :loading="inviting"
      @confirm="revokeInvite"
    />

    <VlConfirmModal
      v-model:open="contactDeleteConfirmOpen"
      title="Delete contact entry?"
      :body="
        pendingContactDelete
          ? 'This will permanently delete the selected contact entry.'
          : 'No contact entry selected.'
      "
      confirm-label="Delete"
      confirm-variant="danger"
      :loading="contactDeleting"
      @confirm="deleteContact"
    />

    <VlConfirmModal
      v-model:open="threadDeleteConfirmOpen"
      title="Delete message thread?"
      :body="
        pendingThreadDelete
          ? 'This will permanently delete the selected thread and its messages.'
          : 'No thread selected.'
      "
      confirm-label="Delete"
      confirm-variant="danger"
      :loading="threadDeleting"
      @confirm="deleteThread"
    />

    <VlConfirmModal
      v-model:open="rateDeleteConfirmOpen"
      title="Delete rate?"
      :body="pendingRateDelete ? 'This will permanently delete the selected rate record.' : 'No rate selected.'"
      confirm-label="Delete"
      confirm-variant="danger"
      :loading="rateDeleting"
      @confirm="deleteRate"
    />

    <VlConfirmModal
      v-model:open="paymentDeleteConfirmOpen"
      title="Delete payment?"
      :body="
        pendingPaymentDelete
          ? 'This will permanently delete the selected payment ledger entry.'
          : 'No payment selected.'
      "
      confirm-label="Delete"
      confirm-variant="danger"
      :loading="paymentDeleting"
      @confirm="deletePayment"
    />

    <VlConfirmModal
      v-model:open="rotateModalOpen"
      title="Rotate API key?"
      body="This will revoke the current token and generate a new one (shown once). Update viarah-cli immediately."
      confirm-label="Rotate"
      confirm-variant="warning"
      :loading="rotating"
      @confirm="rotateKey"
    />

    <VlConfirmModal
      v-model:open="revokeModalOpen"
      title="Revoke API key?"
      body="This key will stop working immediately. This action cannot be undone."
      confirm-label="Revoke"
      confirm-variant="danger"
      :loading="revoking"
      @confirm="revokeKey"
    />
  </pf-modal>
</template>

<style scoped>
.header-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tab-stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.profile-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.full {
  grid-column: 1 / -1;
}

.invite-card {
  height: fit-content;
}

.invite-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.invite-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.invite-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.invite-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.scope-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.inline-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.stack-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.row-actions.right {
  justify-content: flex-end;
}

.table-wrap {
  overflow-x: auto;
}

.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.message-meta {
  margin-bottom: 0.25rem;
}

.message-body {
  white-space: pre-wrap;
}

.key-title {
  display: flex;
  gap: 0.75rem;
  align-items: baseline;
}

.key-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.token-card {
  border-left: 4px solid var(--pf-v6-global--success-color--100);
}

.token-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

@media (max-width: 768px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }

  .grid-3 {
    grid-template-columns: 1fr;
  }
}
</style>
