<script setup lang="ts">
	import { computed, onBeforeUnmount, ref, watch } from "vue";
	import { useRoute, useRouter } from "vue-router";

	import { api, ApiError } from "../api";
	import type { OrgInvite, Person, PersonStatus } from "../api/types";
	import TeamPersonModal from "../components/team/TeamPersonModal.vue";
	import VlConfirmModal from "../components/VlConfirmModal.vue";
	import VlInitialsAvatar from "../components/VlInitialsAvatar.vue";
	import VlLabel from "../components/VlLabel.vue";
	import type { VlLabelColor } from "../utils/labels";
	import { formatTimestampInTimeZone } from "../utils/format";
	import { useContextStore } from "../stores/context";
	import { useRealtimeStore } from "../stores/realtime";
	import { useSessionStore } from "../stores/session";

const router = useRouter();
	const route = useRoute();
	const session = useSessionStore();
	const context = useContextStore();
	const realtime = useRealtimeStore();

const people = ref<Person[]>([]);
const invites = ref<OrgInvite[]>([]);
const loading = ref(false);
const error = ref("");

const search = ref("");
const statusFilter = ref<"all" | PersonStatus>("all");
const roleFilter = ref<"all" | "admin" | "pm" | "member">("all");


const availabilityFilter = ref<"any" | "available_next_14_days">("any");
const availabilityLoading = ref(false);
const availabilityError = ref("");
const availabilityByPersonId = ref<
  Record<string, { has_availability: boolean; next_available_at: string | null; minutes_available: number }>
>({});

const personModalOpen = ref(false);
const selectedPerson = ref<Person | null>(null);
const personModalInitialSection = ref<"profile" | "invite">("profile");

const inviteMaterial = ref<
  null | { token: string; invite_url: string; full_invite_url: string; email_sent?: boolean }
>(null);
const inviteClipboardStatus = ref("");

const pendingRevokeInvite = ref<OrgInvite | null>(null);
const revokeInviteConfirmOpen = ref(false);
const inviteActionError = ref("");

const currentRole = computed(() => {
  return session.effectiveOrgRole(context.orgId);
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

function statusLabelColor(status: string): VlLabelColor {
  if (status === "active") {
    return "green";
  }
  if (status === "invited") {
    return "orange";
  }
  return "grey";
}

function inviteStatusLabelColor(status: string): VlLabelColor {
  if (status === "active") {
    return "orange";
  }
  if (status === "accepted") {
    return "green";
  }
  return "grey";
}


function personDisplay(person: Person): string {
  const label = (person.preferred_name || person.full_name || person.email || "").trim();
  return label || "Unnamed";
}

function personSubtitle(person: Person): string {
  const parts: string[] = [];
  if (person.title) {
    parts.push(person.title);
  }
  if (person.timezone) {
    parts.push(person.timezone);
  }
  return parts.join(" · ");
}


function availabilityHoursLabel(minutes: number): string {
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours}h`;
}

function availabilitySummary(person: Person): {
  has_availability: boolean;
  next_available_at: string | null;
  minutes_available: number;
} | null {
  return availabilityByPersonId.value[person.id] ?? null;
}

function absoluteInviteUrl(inviteUrl: string): string {
  try {
    if (typeof window === "undefined") {
      return inviteUrl;
    }
    return new URL(inviteUrl, window.location.origin).toString();
  } catch {
    return inviteUrl;
  }
}

async function copyText(value: string) {
  inviteClipboardStatus.value = "";
  if (!value) {
    return;
  }

  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      inviteClipboardStatus.value = "Copied.";
      return;
    }
    throw new Error("Clipboard API unavailable");
  } catch {
    inviteClipboardStatus.value = "Copy failed; select and copy manually.";
  }
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refreshAll(options?: { q?: string }) {
  error.value = "";
  inviteActionError.value = "";

  if (!context.orgId) {
    people.value = [];
    invites.value = [];
    return;
  }

  loading.value = true;
  try {
    const [peopleRes, invitesRes] = await Promise.all([
      api.listOrgPeople(context.orgId, { q: options?.q }),
      api.listOrgInvites(context.orgId, { status: "active" }),
    ]);

    people.value = peopleRes.people;
    invites.value = invitesRes.invites;
  } catch (err) {
    people.value = [];
    invites.value = [];

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

function availabilityWindowNext14Days(): { start_at: string; end_at: string } {
  const start = new Date();
  const end = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000);
  return { start_at: start.toISOString(), end_at: end.toISOString() };
}

async function refreshAvailability() {
  availabilityError.value = "";

  if (!context.orgId) {
    availabilityByPersonId.value = {};
    return;
  }

  if (availabilityFilter.value === "any") {
    availabilityByPersonId.value = {};
    return;
  }

  availabilityLoading.value = true;
  try {
    const window = availabilityWindowNext14Days();
    const res = await api.searchPeopleAvailability(context.orgId, window);

    const map: Record<
      string,
      { has_availability: boolean; next_available_at: string | null; minutes_available: number }
    > = {};

    for (const row of res.matches) {
      map[row.person_id] = {
        has_availability: Boolean(row.has_availability),
        next_available_at: row.next_available_at ?? null,
        minutes_available: Number(row.minutes_available ?? 0),
      };
    }

    availabilityByPersonId.value = map;
  } catch (err) {
    availabilityByPersonId.value = {};

    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      availabilityError.value = "Not permitted.";
      return;
    }

    availabilityError.value = err instanceof Error ? err.message : String(err);
  } finally {
    availabilityLoading.value = false;
  }
}

let searchTimer: number | null = null;
	async function refreshDirectory() {
	  await refreshAll({ q: search.value.trim() ? search.value.trim() : undefined });
	  await refreshAvailability();
	}

	function isRecord(value: unknown): value is Record<string, unknown> {
	  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
	}

	let refreshTimeoutId: number | null = null;
	function scheduleRefreshDirectory() {
	  if (refreshTimeoutId != null) {
	    return;
	  }
	  refreshTimeoutId = window.setTimeout(() => {
	    refreshTimeoutId = null;
	    if (loading.value || availabilityLoading.value) {
	      return;
	    }
	    void refreshDirectory();
	  }, 250);
	}

	function shouldRefreshDirectoryForAuditEventType(eventType: string): boolean {
	  const t = String(eventType || "").trim();
	  return t.startsWith("person.") || t.startsWith("org_invite.") || t.startsWith("person_availability.");
	}

	const unsubscribeRealtime = realtime.subscribe((event) => {
	  if (event.type !== "audit_event.created") {
	    return;
	  }
	  if (!context.orgId) {
	    return;
	  }
	  if (event.org_id && event.org_id !== context.orgId) {
	    return;
	  }
	  if (!isRecord(event.data)) {
	    return;
	  }
	  const auditEventType = typeof event.data.event_type === "string" ? event.data.event_type : "";
	  if (!shouldRefreshDirectoryForAuditEventType(auditEventType)) {
	    return;
	  }
	  scheduleRefreshDirectory();
	});

	onBeforeUnmount(() => {
	  unsubscribeRealtime();
	  if (refreshTimeoutId != null) {
	    window.clearTimeout(refreshTimeoutId);
	    refreshTimeoutId = null;
	  }
	});

watch(() => [context.orgId, availabilityFilter.value], () => void refreshAvailability(), { immediate: true });

watch(
  () => [context.orgId, search.value],
  ([orgId, q]) => {
    if (!orgId) {
      void refreshAll();
      return;
    }

    if (searchTimer != null) {
      window.clearTimeout(searchTimer);
    }

    const trimmed = String(q || "").trim();
    searchTimer = window.setTimeout(() => {
      void refreshAll({ q: trimmed || undefined });
    }, 250);
  },
  { immediate: true }
);

const filteredPeople = computed(() => {
  const needle = search.value.trim().toLowerCase();

  const statusPriority: Record<string, number> = { active: 0, invited: 1, candidate: 2 };

  const out = people.value
    .filter((person) => {
      if (person.membership_role === "client") {
        return false;
      }
      if (statusFilter.value !== "all" && person.status !== statusFilter.value) {
        return false;
      }
      if (roleFilter.value !== "all" && person.membership_role !== roleFilter.value) {
        return false;
      }


      if (availabilityFilter.value !== "any") {
        const summary = availabilitySummary(person);
        if (!summary?.has_availability) {
          return false;
        }
      }

      if (!needle) {
        return true;
      }

      const haystack = [
        person.full_name,
        person.preferred_name,
        person.email,
        person.title,
        person.location,
        person.timezone,
        ...(person.skills || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return haystack.includes(needle);
    })
    .sort((a, b) => {
      const pa = statusPriority[a.status] ?? 99;
      const pb = statusPriority[b.status] ?? 99;
      if (pa !== pb) {
        return pa - pb;
      }
      return personDisplay(a).localeCompare(personDisplay(b));
    });

  return out;
});

function openCreate() {
  selectedPerson.value = null;
  personModalInitialSection.value = "profile";
  personModalOpen.value = true;
}

function openInvite() {
  selectedPerson.value = null;
  personModalInitialSection.value = "invite";
  personModalOpen.value = true;
}

function openEdit(person: Person) {
  selectedPerson.value = person;
  personModalInitialSection.value = "profile";
  personModalOpen.value = true;
}

function dismissInviteMaterial() {
  inviteMaterial.value = null;
  inviteClipboardStatus.value = "";
}

function showInviteMaterial(material: {
  token: string;
  invite_url: string;
  full_invite_url?: string;
  email_sent?: boolean;
}) {
  const full = material.full_invite_url || absoluteInviteUrl(material.invite_url);
  inviteMaterial.value = {
    token: material.token,
    invite_url: material.invite_url,
    full_invite_url: full,
    email_sent: material.email_sent,
  };
  inviteClipboardStatus.value = "";
}

async function resendInvite(invite: OrgInvite) {
  inviteActionError.value = "";

  if (!context.orgId) {
    inviteActionError.value = "Select an org first.";
    return;
  }

  try {
    const res = await api.resendOrgInvite(context.orgId, invite.id);
    showInviteMaterial({
      token: res.token,
      invite_url: res.invite_url,
      full_invite_url: res.full_invite_url,
      email_sent: res.email_sent,
    });
    await refreshAll({ q: search.value.trim() ? search.value.trim() : undefined });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      inviteActionError.value = "Not permitted.";
      return;
    }
    inviteActionError.value = err instanceof Error ? err.message : String(err);
  }
}

function requestRevokeInvite(invite: OrgInvite) {
  inviteActionError.value = "";
  pendingRevokeInvite.value = invite;
  revokeInviteConfirmOpen.value = true;
}

async function revokeInvite() {
  const invite = pendingRevokeInvite.value;
  if (!invite || !context.orgId) {
    inviteActionError.value = "No invite selected.";
    return;
  }

  inviteActionError.value = "";
  try {
    await api.revokeOrgInvite(context.orgId, invite.id);
    revokeInviteConfirmOpen.value = false;
    pendingRevokeInvite.value = null;
    await refreshAll({ q: search.value.trim() ? search.value.trim() : undefined });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      inviteActionError.value = "Not permitted.";
      return;
    }
    inviteActionError.value = err instanceof Error ? err.message : String(err);
  }
}

function quickInviteLabel(person: Person): string {
  if (person.status === "active") {
    return "Edit";
  }
  if (person.status === "invited") {
    return "Manage invite";
  }
  return "Invite";
}
</script>

<template>
  <pf-empty-state v-if="!context.orgId">
    <pf-empty-state-header title="Select an org" heading-level="h2" />
    <pf-empty-state-body>Select an org to manage People and invites.</pf-empty-state-body>
  </pf-empty-state>

  <div v-else class="stack">
    <pf-card>
      <pf-card-body>
        <div class="page-header">
          <div>
            <pf-title h="1" size="2xl">Team</pf-title>
            <p class="muted">People records exist before invites; inviting links or creates a user + membership.</p>
          </div>
          <div class="header-actions">
            <pf-button type="button" :disabled="!canManage" @click="openCreate">New person</pf-button>
            <pf-button type="button" variant="secondary" :disabled="!canManage" @click="openInvite">Invite member</pf-button>
          </div>
        </div>

        <pf-form class="toolbar">
          <div class="toolbar-row">
            <pf-form-group label="Search" field-id="team-search">
              <pf-search-input
                id="team-search"
                v-model="search"
                placeholder="Name, email, skills…"
                @clear="search = ''"
              />
            </pf-form-group>

            <pf-form-group label="Status" field-id="team-status">
              <pf-form-select id="team-status" v-model="statusFilter">
                <pf-form-select-option value="all">All</pf-form-select-option>
                <pf-form-select-option value="active">Active</pf-form-select-option>
                <pf-form-select-option value="invited">Invited</pf-form-select-option>
                <pf-form-select-option value="candidate">Candidate</pf-form-select-option>
              </pf-form-select>
            </pf-form-group>

            <pf-form-group label="Role" field-id="team-role">
              <pf-form-select id="team-role" v-model="roleFilter">
                <pf-form-select-option value="all">Any</pf-form-select-option>
                <pf-form-select-option value="admin">Admin</pf-form-select-option>
                <pf-form-select-option value="pm">PM</pf-form-select-option>
                <pf-form-select-option value="member">Member</pf-form-select-option>
              </pf-form-select>
            </pf-form-group>


            <pf-form-group label="Availability" field-id="team-availability">
              <pf-form-select id="team-availability" v-model="availabilityFilter">
                <pf-form-select-option value="any">Any</pf-form-select-option>
                <pf-form-select-option value="available_next_14_days">Available (next 14d)</pf-form-select-option>
              </pf-form-select>
            </pf-form-group>

            <div v-if="loading" class="inline-loading">
              <pf-spinner size="sm" aria-label="Loading people" />
              <span class="muted">Loading…</span>
            </div>


            <div v-if="availabilityLoading" class="inline-loading">
              <pf-spinner size="sm" aria-label="Searching availability" />
              <span class="muted">Availability…</span>
            </div>
          </div>
        </pf-form>

        <pf-alert v-if="error" inline variant="danger" :title="error" />

        <pf-alert v-if="availabilityError" inline variant="danger" :title="availabilityError" />
      </pf-card-body>
    </pf-card>

    <pf-empty-state v-if="!filteredPeople.length && !loading">
      <pf-empty-state-header title="No people" heading-level="h2" />
      <pf-empty-state-body>
        Create a Person record to start building your team directory. Inviting is a separate action.
      </pf-empty-state-body>
      <pf-empty-state-footer>
        <pf-empty-state-actions>
          <pf-button type="button" :disabled="!canManage" @click="openCreate">New person</pf-button>
          <pf-button type="button" variant="secondary" :disabled="!canManage" @click="openInvite">Invite member</pf-button>
        </pf-empty-state-actions>
      </pf-empty-state-footer>
    </pf-empty-state>

    <pf-gallery v-else gutter min-width="280px">
      <pf-gallery-item v-for="person in filteredPeople" :key="person.id">
        <pf-card class="person-card">
          <pf-card-body>
            <div class="person-header">
              <RouterLink
                class="person-link"
                :to="`/people/${person.id}`"
                :aria-label="`Open ${personDisplay(person)} profile`"
              >
                <VlInitialsAvatar :label="personDisplay(person)" :src="person.avatar_url" size="lg" bordered />
              </RouterLink>
              <div class="person-header-text">
                <div class="name-row">
                  <RouterLink class="person-link" :to="`/people/${person.id}`">
                    <pf-title h="2" size="lg">{{ personDisplay(person) }}</pf-title>
                  </RouterLink>
                  <VlLabel :color="statusLabelColor(person.status)" variant="outline">
                    {{ person.status.toUpperCase() }}
                  </VlLabel>
                  <VlLabel
                    v-if="person.membership_role"
                    :color="roleLabelColor(person.membership_role)"
                    variant="outline"
                  >
                    {{ person.membership_role.toUpperCase() }}
                  </VlLabel>
                </div>
                <div v-if="personSubtitle(person)" class="muted">{{ personSubtitle(person) }}</div>
                <div v-if="person.email" class="muted">{{ person.email }}</div>
                <div v-if="availabilitySummary(person)" class="muted small">
                  Next available:
                  {{
                    availabilitySummary(person)?.next_available_at
                      ? formatTimestampInTimeZone(availabilitySummary(person)?.next_available_at, person.timezone)
                      : "—"
                  }}
                  · {{ availabilityHoursLabel(availabilitySummary(person)!.minutes_available) }} in range
                </div>
              </div>
            </div>

            <pf-label-group v-if="person.skills?.length" :num-labels="4" class="skills">
              <VlLabel v-for="skill in person.skills" :key="skill" color="blue" variant="outline">{{ skill }}</VlLabel>
            </pf-label-group>

            <div class="card-actions">
              <pf-button type="button" variant="secondary" small :disabled="!canManage" @click="openEdit(person)">
                {{ quickInviteLabel(person) }}
              </pf-button>

              <pf-button
                v-if="person.active_invite"
                type="button"
                variant="secondary"
                small
                :disabled="!canManage"
                @click="resendInvite(person.active_invite)"
              >
                Resend link
              </pf-button>

              <pf-button
                v-if="person.active_invite"
                type="button"
                variant="danger"
                small
                :disabled="!canManage"
                @click="requestRevokeInvite(person.active_invite)"
              >
                Revoke
              </pf-button>
            </div>
          </pf-card-body>
        </pf-card>
      </pf-gallery-item>
    </pf-gallery>

    <pf-card>
      <pf-card-title>
        <div class="invites-title">
          <div class="invites-title-left">
            <span>Pending invites</span>
            <VlLabel v-if="invites.length" color="blue" variant="outline">{{ invites.length }}</VlLabel>
          </div>
          <pf-button type="button" variant="secondary" small :disabled="!canManage" @click="openInvite">
            Invite member
          </pf-button>
        </div>
      </pf-card-title>
      <pf-card-body>
        <pf-content>
          <p class="muted">Resend generates a new token/link (shown once) and revokes the prior invite.</p>
        </pf-content>

        <pf-alert v-if="inviteActionError" inline variant="danger" :title="inviteActionError" />

        <pf-empty-state v-if="!invites.length">
          <pf-empty-state-header title="No pending invites" heading-level="h3" />
          <pf-empty-state-body>Create a person, then invite them when ready.</pf-empty-state-body>
          <pf-empty-state-footer>
            <pf-empty-state-actions>
              <pf-button type="button" :disabled="!canManage" @click="openCreate">New person</pf-button>
              <pf-button type="button" variant="secondary" :disabled="!canManage" @click="openInvite">
                Invite member
              </pf-button>
            </pf-empty-state-actions>
          </pf-empty-state-footer>
        </pf-empty-state>

        <pf-data-list v-else aria-label="Pending invites">
          <pf-data-list-item v-for="invite in invites" :key="invite.id" aria-label="Invite">
            <pf-data-list-item-row>
              <pf-data-list-item-cells>
                <pf-data-list-cell>
                  <div class="invite-row">
                    <div class="invite-main">
                      <strong>{{ invite.person?.display || invite.email }}</strong>
                      <div class="muted">{{ invite.email }}</div>
                      <div class="muted">Expires: {{ invite.expires_at }}</div>
                      <div v-if="invite.message" class="muted">Message: {{ invite.message }}</div>
                    </div>
                    <div class="invite-meta">
                      <VlLabel :color="roleLabelColor(invite.role)" variant="outline">{{ invite.role.toUpperCase() }}</VlLabel>
                      <VlLabel :color="inviteStatusLabelColor(invite.status)" variant="outline">{{ invite.status.toUpperCase() }}</VlLabel>
                    </div>
                  </div>
                </pf-data-list-cell>
                <pf-data-list-cell class="invite-actions" align-right>
                  <pf-button type="button" variant="secondary" small :disabled="!canManage" @click="resendInvite(invite)">
                    Resend
                  </pf-button>
                  <pf-button type="button" variant="danger" small :disabled="!canManage" @click="requestRevokeInvite(invite)">
                    Revoke
                  </pf-button>
                </pf-data-list-cell>
              </pf-data-list-item-cells>
            </pf-data-list-item-row>
          </pf-data-list-item>
        </pf-data-list>
      </pf-card-body>
    </pf-card>

    <pf-modal
      v-if="inviteMaterial"
      :open="Boolean(inviteMaterial)"
      title="Invite link"
      variant="medium"
      @update:open="(open) => (!open ? dismissInviteMaterial() : undefined)"
    >
      <pf-content>
        <p class="muted">
          Share this link with the invitee.
          <span v-if="inviteMaterial.email_sent === true">Email sent.</span>
          <span v-else-if="inviteMaterial.email_sent === false">No email sent.</span>
        </p>
      </pf-content>
      <pf-form>
        <pf-form-group label="Invite URL" field-id="invite-url">
          <pf-textarea id="invite-url" :model-value="inviteMaterial.full_invite_url" rows="2" readonly />
        </pf-form-group>
        <div class="invite-copy-row">
          <pf-button type="button" variant="secondary" @click="copyText(inviteMaterial.full_invite_url)">Copy URL</pf-button>
          <span class="muted">{{ inviteClipboardStatus }}</span>
        </div>

        <pf-expandable-section toggle-text-collapsed="Token (advanced)" toggle-text-expanded="Hide token">
          <pf-form-group label="Token" field-id="invite-token">
            <pf-textarea id="invite-token" :model-value="inviteMaterial.token" rows="2" readonly />
          </pf-form-group>
          <pf-button type="button" variant="secondary" @click="copyText(inviteMaterial.token)">Copy token</pf-button>
        </pf-expandable-section>
      </pf-form>
      <template #footer>
        <pf-button type="button" variant="primary" @click="dismissInviteMaterial">Done</pf-button>
      </template>
    </pf-modal>

    <TeamPersonModal
      v-model:open="personModalOpen"
      :org-id="context.orgId"
      :person="selectedPerson"
      :can-manage="canManage"
      :initial-section="personModalInitialSection"
      @saved="() => refreshAll({ q: search.trim() || undefined })"
      @invite-material="showInviteMaterial"
    />

    <VlConfirmModal
      v-model:open="revokeInviteConfirmOpen"
      title="Revoke invite?"
      body="This will revoke the active invite. The person will remain in the directory as a candidate until re-invited."
      confirm-label="Revoke invite"
      confirm-variant="danger"
      @confirm="revokeInvite"
    />
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.toolbar {
  margin-top: 1rem;
}

.toolbar-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: flex-end;
}

.inline-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.person-card {
  height: 100%;
}

.person-header {
  display: flex;
  gap: 0.75rem;
}

.person-link {
  color: inherit;
  text-decoration: none;
}

.person-link:hover {
  text-decoration: underline;
}

.person-header-text {
  flex: 1;
  min-width: 0;
}

.name-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.skills {
  margin-top: 0.75rem;
}

.card-actions {
  margin-top: 1rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.invites-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.invites-title-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.invite-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.invite-main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.invite-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: flex-end;
}

.invite-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.invite-copy-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
</style>
