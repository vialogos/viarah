<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { OrgMembershipWithUser } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import type { VlLabelColor } from "../utils/labels";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const memberships = ref<OrgMembershipWithUser[]>([]);
const loading = ref(false);
const error = ref("");

const roleDraftByMembershipId = ref<Record<string, string>>({});
const roleErrorByMembershipId = ref<Record<string, string>>({});
const roleSavingMembershipId = ref("");

const roleConfirmOpen = ref(false);
const roleConfirmMembership = ref<OrgMembershipWithUser | null>(null);
const roleConfirmRole = ref("");
const roleConfirmError = ref("");

type ProfileDraft = {
  display_name: string;
  title: string;
  skills_raw: string;
  bio: string;
  availability_status: string;
  availability_hours_per_week: string;
  availability_next_available_at: string;
  availability_notes: string;
};

const profileModalOpen = ref(false);
const profileMembership = ref<OrgMembershipWithUser | null>(null);
const profileDraft = ref<ProfileDraft>({
  display_name: "",
  title: "",
  skills_raw: "",
  bio: "",
  availability_status: "unknown",
  availability_hours_per_week: "",
  availability_next_available_at: "",
  availability_notes: "",
});
const profileSaving = ref(false);
const profileError = ref("");

const inviteModalOpen = ref(false);
const inviteEmail = ref("");
const inviteRole = ref("member");
const inviting = ref(false);
const inviteError = ref("");

const inviteMaterial = ref<null | { token: string; inviteUrl: string; fullInviteUrl: string }>(null);
const clipboardStatus = ref("");

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManage = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

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

function roleDisplay(role: string): string {
  return role ? role.toUpperCase() : "";
}

function availabilityLabelColor(status: string): VlLabelColor {
  if (status === "available") {
    return "green";
  }
  if (status === "limited") {
    return "orange";
  }
  if (status === "unavailable") {
    return "red";
  }
  return "grey";
}

function availabilityLabel(membership: OrgMembershipWithUser): string {
  const status = String(membership.availability_status || "unknown").toLowerCase();
  const base = status === "available" ? "Available" : status === "limited" ? "Limited" : status === "unavailable" ? "Unavailable" : "Unknown";

  const hours = membership.availability_hours_per_week;
  if (hours == null) {
    return base;
  }
  return `${base} · ${hours}h/w`;
}

function availabilityTooltip(membership: OrgMembershipWithUser): string | undefined {
  const parts: string[] = [];
  if (membership.availability_next_available_at) {
    parts.push(`Next available: ${membership.availability_next_available_at}`);
  }
  if (membership.availability_notes) {
    parts.push(membership.availability_notes);
  }
  return parts.length ? parts.join(" — ") : undefined;
}

function truncate(text: string, maxChars: number): string {
  const normalized = (text || "").trim();
  if (!normalized) {
    return "";
  }
  if (normalized.length <= maxChars) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, maxChars - 1))}…`;
}

function skillsRawFromList(skills: string[]): string {
  return (skills || []).join(", ");
}

function parseSkillsRaw(raw: string): string[] {
  const parts = raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return Array.from(new Set(parts));
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refreshMemberships() {
  error.value = "";
  roleErrorByMembershipId.value = {};

  if (!context.orgId) {
    memberships.value = [];
    roleDraftByMembershipId.value = {};
    return;
  }

  loading.value = true;
  try {
    const res = await api.listOrgMemberships(context.orgId);
    memberships.value = res.memberships;
    roleDraftByMembershipId.value = Object.fromEntries(res.memberships.map((m) => [m.id, m.role]));
  } catch (err) {
    memberships.value = [];
    roleDraftByMembershipId.value = {};

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
    loading.value = false;
  }
}

function openInviteModal() {
  inviteError.value = "";
  inviteModalOpen.value = true;
}

function dismissInviteMaterial() {
  inviteMaterial.value = null;
  clipboardStatus.value = "";
}

function fullUrlFromInviteUrl(inviteUrl: string): string {
  if (inviteUrl.startsWith("http://") || inviteUrl.startsWith("https://")) {
    return inviteUrl;
  }
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  if (!origin) {
    return inviteUrl;
  }
  return `${origin}${inviteUrl}`;
}

async function createInvite() {
  inviteError.value = "";
  if (!context.orgId) {
    inviteError.value = "Select an org first.";
    return;
  }
  if (!canManage.value) {
    inviteError.value = "Not permitted.";
    return;
  }

  const email = inviteEmail.value.trim().toLowerCase();
  if (!email) {
    inviteError.value = "Email is required.";
    return;
  }

  inviting.value = true;
  try {
    const res = await api.createOrgInvite(context.orgId, { email, role: inviteRole.value });
    inviteMaterial.value = {
      token: res.token,
      inviteUrl: res.invite_url,
      fullInviteUrl: fullUrlFromInviteUrl(res.invite_url),
    };
    clipboardStatus.value = "";

    inviteEmail.value = "";
    inviteRole.value = "member";
    inviteModalOpen.value = false;
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

function requestRoleChange(membership: OrgMembershipWithUser) {
  roleConfirmError.value = "";
  roleConfirmMembership.value = membership;
  roleConfirmRole.value = roleDraftByMembershipId.value[membership.id] ?? membership.role;
  roleConfirmOpen.value = true;
}

async function applyRoleChange() {
  roleConfirmError.value = "";
  const membership = roleConfirmMembership.value;
  const nextRole = roleConfirmRole.value;

  if (!context.orgId) {
    roleConfirmError.value = "Select an org first.";
    return;
  }
  if (!membership) {
    roleConfirmError.value = "No membership selected.";
    return;
  }
  if (!nextRole || nextRole === membership.role) {
    roleConfirmOpen.value = false;
    return;
  }

  roleSavingMembershipId.value = membership.id;
  roleErrorByMembershipId.value = { ...roleErrorByMembershipId.value, [membership.id]: "" };
  try {
    await api.updateOrgMembership(context.orgId, membership.id, { role: nextRole });
    roleConfirmOpen.value = false;
    roleConfirmMembership.value = null;
    await refreshMemberships();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }

    const message = err instanceof Error ? err.message : String(err);
    if (err instanceof ApiError && err.status === 403) {
      roleErrorByMembershipId.value = { ...roleErrorByMembershipId.value, [membership.id]: "Not permitted." };
    } else {
      roleErrorByMembershipId.value = { ...roleErrorByMembershipId.value, [membership.id]: message };
    }
    roleConfirmError.value = roleErrorByMembershipId.value[membership.id] ?? message;
  } finally {
    roleSavingMembershipId.value = "";
  }
}


function openProfileModal(membership: OrgMembershipWithUser) {
  profileError.value = "";
  profileMembership.value = membership;
  profileDraft.value = {
    display_name: membership.user.display_name ?? "",
    title: membership.title ?? "",
    skills_raw: skillsRawFromList(membership.skills ?? []),
    bio: membership.bio ?? "",
    availability_status: membership.availability_status ?? "unknown",
    availability_hours_per_week:
      membership.availability_hours_per_week != null ? String(membership.availability_hours_per_week) : "",
    availability_next_available_at: membership.availability_next_available_at ?? "",
    availability_notes: membership.availability_notes ?? "",
  };
  profileModalOpen.value = true;
}

async function saveProfile() {
  profileError.value = "";
  const membership = profileMembership.value;

  if (!context.orgId) {
    profileError.value = "Select an org first.";
    return;
  }
  if (!canManage.value) {
    profileError.value = "Not permitted.";
    return;
  }
  if (!membership) {
    profileError.value = "No membership selected.";
    return;
  }

  const hoursRaw = profileDraft.value.availability_hours_per_week.trim();
  let hours: number | null = null;
  if (hoursRaw) {
    const parsed = Number.parseInt(hoursRaw, 10);
    if (!Number.isFinite(parsed) || Number.isNaN(parsed)) {
      profileError.value = "Hours/week must be an integer.";
      return;
    }
    if (parsed < 0 || parsed > 168) {
      profileError.value = "Hours/week must be between 0 and 168.";
      return;
    }
    hours = parsed;
  }

  const nextAvailableRaw = profileDraft.value.availability_next_available_at.trim();
  const nextAvailableAt = nextAvailableRaw ? nextAvailableRaw : null;

  profileSaving.value = true;
  try {
    await api.updateOrgMembership(context.orgId, membership.id, {
      display_name: profileDraft.value.display_name,
      title: profileDraft.value.title,
      skills: parseSkillsRaw(profileDraft.value.skills_raw),
      bio: profileDraft.value.bio,
      availability_status: profileDraft.value.availability_status,
      availability_hours_per_week: hours,
      availability_next_available_at: nextAvailableAt,
      availability_notes: profileDraft.value.availability_notes,
    });

    profileModalOpen.value = false;
    profileMembership.value = null;
    await refreshMemberships();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      profileError.value = "Not permitted.";
      return;
    }
    profileError.value = err instanceof Error ? err.message : String(err);
  } finally {
    profileSaving.value = false;
  }
}

watch(() => context.orgId, refreshMemberships, { immediate: true });
</script>

<template>
  <div class="stack">
    <pf-card v-if="inviteMaterial" class="token-card">
      <pf-card-body>
        <div class="token-header">
          <div>
            <pf-title h="2" size="lg">Invite material (shown once)</pf-title>
            <pf-content>
              <p class="muted small">Copy the token and accept URL now. For security, it will not be shown again.</p>
            </pf-content>
          </div>
          <pf-close-button aria-label="Close invite material panel" @click="dismissInviteMaterial" />
        </div>

        <pf-form class="token-form">
          <pf-form-group label="Accept URL" field-id="team-invite-url">
            <div class="token-row">
              <pf-text-input-group class="token-input-group">
                <pf-text-input-group-main
                  :model-value="inviteMaterial.fullInviteUrl"
                  readonly
                  aria-label="Invite accept URL"
                />
              </pf-text-input-group>
              <pf-button variant="secondary" @click="copyText(inviteMaterial.fullInviteUrl)">Copy</pf-button>
            </div>
          </pf-form-group>

          <pf-form-group label="Token" field-id="team-invite-token">
            <div class="token-row">
              <pf-text-input-group class="token-input-group">
                <pf-text-input-group-main :model-value="inviteMaterial.token" readonly aria-label="Invite token" />
              </pf-text-input-group>
              <pf-button variant="secondary" @click="copyText(inviteMaterial.token)">Copy</pf-button>
            </div>
          </pf-form-group>

          <div v-if="clipboardStatus" class="muted small">{{ clipboardStatus }}</div>
        </pf-form>
      </pf-card-body>
    </pf-card>

    <pf-card>
      <pf-card-title>
        <div class="header">
          <div>
            <pf-title h="1" size="2xl">Team</pf-title>
            <pf-content>
              <p class="muted">Invite users, manage org roles, and maintain member profiles/availability for attribution (PM/admin only).</p>
            </pf-content>
          </div>

          <div class="controls">
            <pf-button variant="secondary" :disabled="!context.orgId || loading" @click="refreshMemberships">
              Refresh
            </pf-button>
            <pf-button variant="secondary" :disabled="!context.orgId" @click="router.push('/team/roles')">
              Roles
            </pf-button>
            <pf-button variant="secondary" :disabled="!context.orgId" @click="router.push('/team/api-keys')">
              API keys
            </pf-button>
            <pf-button v-if="canManage" variant="primary" :disabled="!context.orgId" @click="openInviteModal">
              Invite user
            </pf-button>
          </div>
        </div>
      </pf-card-title>

      <pf-card-body>
        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to view memberships and manage invites.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading memberships" />
        </div>

        <div v-else>
          <pf-alert v-if="error" inline variant="danger" :title="error" />

          <pf-empty-state v-else-if="memberships.length === 0">
            <pf-empty-state-header title="No members" heading-level="h2" />
            <pf-empty-state-body>This org has no memberships.</pf-empty-state-body>
          </pf-empty-state>

          <pf-table v-else aria-label="Org memberships">
            <pf-thead>
              <pf-tr>
                <pf-th>User</pf-th>
                <pf-th>Role</pf-th>
                <pf-th />
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="m in memberships" :key="m.id">
                <pf-td data-label="User">
                  <div class="title-row">
                    <span class="name">{{ m.user.display_name || "—" }}</span>
                    <VlLabel :color="roleLabelColor(m.role)">{{ roleDisplay(m.role) }}</VlLabel>
                    <VlLabel :color="availabilityLabelColor(m.availability_status)" :title="availabilityTooltip(m)">
                      {{ availabilityLabel(m) }}
                    </VlLabel>
                  </div>
                  <div class="muted small">{{ m.user.email }}</div>
                  <div v-if="m.title" class="muted small">{{ m.title }}</div>
                  <div v-if="m.skills && m.skills.length" class="skills">
                    <VlLabel
                      v-for="skill in m.skills.slice(0, 6)"
                      :key="`${m.id}-skill-${skill}`"
                      variant="outline"
                      color="teal"
                    >
                      {{ skill }}
                    </VlLabel>
                    <VlLabel v-if="m.skills.length > 6" variant="outline" color="grey">
                      +{{ m.skills.length - 6 }}
                    </VlLabel>
                  </div>
                  <div v-if="m.bio" class="muted small bio">{{ truncate(m.bio, 140) }}</div>
                </pf-td>

                <pf-td data-label="Role">
                  <pf-form-select
                    :id="`team-role-${m.id}`"
                    v-model="roleDraftByMembershipId[m.id]"
                    :disabled="!canManage || roleSavingMembershipId === m.id"
                  >
                    <pf-form-select-option value="admin">admin</pf-form-select-option>
                    <pf-form-select-option value="pm">pm</pf-form-select-option>
                    <pf-form-select-option value="member">member</pf-form-select-option>
                    <pf-form-select-option value="client">client</pf-form-select-option>
                  </pf-form-select>
                  <pf-helper-text v-if="roleErrorByMembershipId[m.id]" class="small">
                    <pf-helper-text-item variant="warning">{{ roleErrorByMembershipId[m.id] }}</pf-helper-text-item>
                  </pf-helper-text>
                </pf-td>

                <pf-td data-label="Actions">
                  <div class="actions">
                    <pf-button
                      variant="secondary"
                      :disabled="!canManage || profileSaving"
                      @click="openProfileModal(m)"
                    >
                      Edit profile
                    </pf-button>
                    <pf-button
                      variant="secondary"
                      :disabled="
                        !canManage ||
                          roleSavingMembershipId === m.id ||
                          !roleDraftByMembershipId[m.id] ||
                          roleDraftByMembershipId[m.id] === m.role
                      "
                      @click="requestRoleChange(m)"
                    >
                      Change role
                    </pf-button>
                  </div>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>

          <pf-helper-text v-if="!canManage" class="note">
            <pf-helper-text-item>Only PM/admin can invite users, edit profiles, or change roles.</pf-helper-text-item>
          </pf-helper-text>
        </div>
      </pf-card-body>
    </pf-card>
  </div>

  <pf-modal v-model:open="inviteModalOpen" title="Invite user">
    <pf-form class="modal-form" @submit.prevent="createInvite">
      <pf-form-group label="Email" field-id="team-invite-email">
        <pf-text-input
          id="team-invite-email"
          v-model="inviteEmail"
          type="email"
          autocomplete="email"
          inputmode="email"
          required
        />
      </pf-form-group>

      <pf-form-group label="Role" field-id="team-invite-role">
        <pf-form-select id="team-invite-role" v-model="inviteRole">
          <pf-form-select-option value="admin">admin</pf-form-select-option>
          <pf-form-select-option value="pm">pm</pf-form-select-option>
          <pf-form-select-option value="member">member</pf-form-select-option>
          <pf-form-select-option value="client">client</pf-form-select-option>
        </pf-form-select>
      </pf-form-group>

      <pf-alert v-if="inviteError" inline variant="danger" :title="inviteError" />
    </pf-form>

    <template #footer>
      <pf-button variant="primary" :disabled="inviting || !canManage" @click="createInvite">
        {{ inviting ? "Inviting…" : "Create invite" }}
      </pf-button>
      <pf-button variant="link" :disabled="inviting" @click="inviteModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>

  <pf-modal v-model:open="profileModalOpen" title="Edit profile">
    <pf-form class="modal-form" @submit.prevent="saveProfile">
      <pf-content>
        <p v-if="profileMembership">
          Editing <strong>{{ profileMembership.user.email }}</strong> ({{ profileMembership.role }}). Role changes are
          separate; use “Change role” from the members table.
        </p>
        <p v-else>No membership selected.</p>
      </pf-content>

      <pf-form-group label="Display name" field-id="team-profile-display-name">
        <pf-text-input id="team-profile-display-name" v-model="profileDraft.display_name" type="text" />
      </pf-form-group>

      <pf-form-group label="Title / role title" field-id="team-profile-title">
        <pf-text-input
          id="team-profile-title"
          v-model="profileDraft.title"
          type="text"
          placeholder="e.g., Project Manager"
        />
      </pf-form-group>

      <pf-form-group label="Skills / tags" field-id="team-profile-skills">
        <pf-text-input
          id="team-profile-skills"
          v-model="profileDraft.skills_raw"
          type="text"
          placeholder="Comma-separated (e.g., React, PM, QA)"
        />
      </pf-form-group>

      <pf-form-group label="Bio / notes" field-id="team-profile-bio">
        <pf-textarea id="team-profile-bio" v-model="profileDraft.bio" rows="4" />
      </pf-form-group>

      <pf-title h="3" size="md">Availability</pf-title>

      <pf-form-group label="Status" field-id="team-profile-availability-status">
        <pf-form-select id="team-profile-availability-status" v-model="profileDraft.availability_status">
          <pf-form-select-option value="unknown">unknown</pf-form-select-option>
          <pf-form-select-option value="available">available</pf-form-select-option>
          <pf-form-select-option value="limited">limited</pf-form-select-option>
          <pf-form-select-option value="unavailable">unavailable</pf-form-select-option>
        </pf-form-select>
      </pf-form-group>

      <pf-form-group label="Hours/week" field-id="team-profile-availability-hours">
        <pf-text-input
          id="team-profile-availability-hours"
          v-model="profileDraft.availability_hours_per_week"
          type="number"
          min="0"
          max="168"
        />
      </pf-form-group>

      <pf-form-group label="Next available" field-id="team-profile-availability-next">
        <pf-text-input
          id="team-profile-availability-next"
          v-model="profileDraft.availability_next_available_at"
          type="date"
        />
      </pf-form-group>

      <pf-form-group label="Availability notes" field-id="team-profile-availability-notes">
        <pf-textarea id="team-profile-availability-notes" v-model="profileDraft.availability_notes" rows="3" />
      </pf-form-group>

      <pf-alert v-if="profileError" inline variant="danger" :title="profileError" />
    </pf-form>

    <template #footer>
      <pf-button variant="primary" :disabled="profileSaving || !canManage" @click="saveProfile">
        {{ profileSaving ? "Saving…" : "Save" }}
      </pf-button>
      <pf-button variant="link" :disabled="profileSaving" @click="profileModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>

  <pf-modal v-model:open="roleConfirmOpen" title="Change role">
    <pf-content>
      <p v-if="roleConfirmMembership">
        Change role for <strong>{{ roleConfirmMembership.user.email }}</strong> from
        <strong>{{ roleConfirmMembership.role }}</strong> to <strong>{{ roleConfirmRole }}</strong>?
      </p>
      <p v-else>No membership selected.</p>
    </pf-content>

    <pf-alert v-if="roleConfirmError" inline variant="danger" :title="roleConfirmError" />

    <template #footer>
      <pf-button
        variant="primary"
        :disabled="!canManage || roleSavingMembershipId === (roleConfirmMembership?.id ?? '')"
        @click="applyRoleChange"
      >
        {{ roleSavingMembershipId ? "Saving…" : "Confirm" }}
      </pf-button>
      <pf-button
        variant="link"
        :disabled="roleSavingMembershipId === (roleConfirmMembership?.id ?? '')"
        @click="roleConfirmOpen = false"
      >
        Cancel
      </pf-button>
    </template>
  </pf-modal>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.name {
  font-weight: 600;
}

.skills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.35rem;
}

.bio {
  margin-top: 0.35rem;
}


.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.note {
  margin-top: 0.75rem;
}

.token-card {
  border: 1px solid var(--pf-t--global--border--color--default);
}

.token-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.token-form {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.token-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.token-input-group {
  flex: 1;
  min-width: 320px;
}
</style>
