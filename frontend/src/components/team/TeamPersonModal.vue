<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../../api";
import type { ApiKey, OrgInvite, Person } from "../../api/types";
import VlConfirmModal from "../VlConfirmModal.vue";
import VlLabel from "../VlLabel.vue";
import TeamPersonAvailabilityTab from "./TeamPersonAvailabilityTab.vue";
import type { VlLabelColor } from "../../utils/labels";
import { useContextStore } from "../../stores/context";

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
  };
}

const draft = ref<PersonDraft>(blankDraft());
const saving = ref(false);
const error = ref("");
const savedBanner = ref("");

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
const skillInput = ref("");

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
const inviting = ref(false);
const inviteError = ref("");

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

const revokeInviteConfirmOpen = ref(false);

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

// API keys tab
const apiKeys = ref<ApiKey[]>([]);
const apiKeysLoading = ref(false);
const apiKeysError = ref("");
const actionError = ref("");

const newKeyName = ref("viarah-cli");
const newProjectId = ref("");
const scopeRead = ref(true);
const scopeWrite = ref(false);
const creating = ref(false);

const tokenMaterial = ref<null | { token: string; apiKey: ApiKey }>(null);
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
          <pf-empty-state>
            <pf-empty-state-header title="Contact history" heading-level="h3" />
            <pf-empty-state-body>
              Contact log entries (calls/emails/notes) will live here.
            </pf-empty-state-body>
          </pf-empty-state>
        </div>
      </pf-tab>

      <pf-tab :key="'messages'" title="Messages">
        <div class="tab-stack">
          <pf-empty-state>
            <pf-empty-state-header title="Message threads" heading-level="h3" />
            <pf-empty-state-body>
              Internal message threads per person will live here.
            </pf-empty-state-body>
          </pf-empty-state>
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

          <pf-empty-state>
            <pf-empty-state-header title="Project roster" heading-level="h3" />
            <pf-empty-state-body>
              This view will show project memberships for the selected person and provide links to manage membership.
            </pf-empty-state-body>
          </pf-empty-state>
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
          <pf-empty-state>
            <pf-empty-state-header title="Payments" heading-level="h3" />
            <pf-empty-state-body>
              Rates + payments ledger per person will live here.
            </pf-empty-state-body>
          </pf-empty-state>
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
}
</style>
