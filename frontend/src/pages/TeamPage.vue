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
              <p class="muted">Invite users and manage org roles (PM/admin only).</p>
            </pf-content>
          </div>

          <div class="controls">
            <pf-button variant="secondary" :disabled="!context.orgId || loading" @click="refreshMemberships">
              Refresh
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
                  </div>
                  <div class="muted small">{{ m.user.email }}</div>
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
            <pf-helper-text-item>Only PM/admin can invite users or change roles.</pf-helper-text-item>
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
}

.name {
  font-weight: 600;
}

.actions {
  display: flex;
  justify-content: flex-end;
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
