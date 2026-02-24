<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { OrgMembershipWithUser } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import type { VlLabelColor } from "../utils/labels";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const realtime = useRealtimeStore();

const memberships = ref<OrgMembershipWithUser[]>([]);
const loading = ref(false);
const error = ref("");

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManage = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const ROLE_DEFS = [
  {
    role: "admin",
    label: "Admin",
    color: "red" as VlLabelColor,
    permissions: [
      "Access all org projects by default.",
      "Invite users and change org roles.",
      "Manage project settings: members, workflows, and custom fields.",
      "Manage templates, outputs, SoWs, and integrations.",
      "Manage API keys (tokens are shown once; rotate to re-mint).",
    ],
  },
  {
    role: "pm",
    label: "PM",
    color: "purple" as VlLabelColor,
    permissions: [
      "Access all org projects by default.",
      "Same operational permissions as Admin in v1 (subject to future RBAC hardening).",
      "Manage project settings: members, workflows, and custom fields.",
      "Manage templates, outputs, SoWs, and integrations.",
      "Manage API keys (tokens are shown once; rotate to re-mint).",
    ],
  },
  {
    role: "member",
    label: "Member",
    color: "blue" as VlLabelColor,
    permissions: [
      "Sees only projects they’re added to via project membership.",
      "Works on tasks inside those projects (subject to feature-level permissions).",
      "Cannot invite users, change org roles, or manage settings.",
    ],
  },
  {
    role: "client",
    label: "Client",
    color: "teal" as VlLabelColor,
    permissions: [
      "Sees only projects they’re added to via project membership.",
      "Sees only client-safe tasks/subtasks/comments/attachments.",
      "Can sign/respond to SoWs when included as a signer and added to the project.",
    ],
  },
] as const;

const membershipsByRole = computed(() => {
  const map: Record<string, OrgMembershipWithUser[]> = {};
  for (const m of memberships.value) {
    const role = m.role || "";
    if (!map[role]) {
      map[role] = [];
    }
    map[role].push(m);
  }
  return map;
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    memberships.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listOrgMemberships(context.orgId);
    memberships.value = res.memberships;
  } catch (err) {
    memberships.value = [];
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

watch(() => context.orgId, () => void refresh(), { immediate: true });

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

let refreshTimeoutId: number | null = null;
function scheduleRefresh() {
  if (refreshTimeoutId != null) {
    return;
  }
  refreshTimeoutId = window.setTimeout(() => {
    refreshTimeoutId = null;
    if (loading.value) {
      return;
    }
    void refresh();
  }, 250);
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
  const eventType = typeof event.data.event_type === "string" ? event.data.event_type : "";
  if (!eventType.startsWith("org_membership.")) {
    return;
  }
  scheduleRefresh();
});

onBeforeUnmount(() => {
  unsubscribeRealtime();
  if (refreshTimeoutId != null) {
    window.clearTimeout(refreshTimeoutId);
    refreshTimeoutId = null;
  }
});
</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <div>
          <pf-title h="1" size="2xl">Roles &amp; permissions</pf-title>
          <pf-content>
            <p class="muted">These roles govern org-level access and project visibility.</p>
          </pf-content>
        </div>

        <div class="controls">
          <pf-button variant="secondary" :disabled="!context.orgId || loading" @click="refresh">Refresh</pf-button>
          <pf-button variant="secondary" :disabled="!canManage" @click="router.push('/team')">Team</pf-button>
        </div>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to view roles and permissions.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading roles" />
      </div>

      <pf-alert v-else-if="error" inline variant="danger" :title="error" />

      <div v-else class="stack">
        <pf-card v-for="role in ROLE_DEFS" :key="role.role">
          <pf-card-title>
            <div class="role-row">
              <VlLabel :color="role.color">{{ role.label }}</VlLabel>
              <span class="muted small">
                {{ membershipsByRole[role.role]?.length ?? 0 }} users
              </span>
            </div>
          </pf-card-title>

          <pf-card-body>
            <pf-content>
              <ul>
                <li v-for="item in role.permissions" :key="item">{{ item }}</li>
              </ul>
            </pf-content>

            <pf-empty-state v-if="(membershipsByRole[role.role]?.length ?? 0) === 0">
              <pf-empty-state-header title="No users" heading-level="h3" />
              <pf-empty-state-body>No users currently have this role.</pf-empty-state-body>
            </pf-empty-state>

            <pf-table v-else :aria-label="`${role.label} users`">
              <pf-thead>
                <pf-tr>
                  <pf-th>User</pf-th>
                  <pf-th>Email</pf-th>
                </pf-tr>
              </pf-thead>
              <pf-tbody>
                <pf-tr v-for="m in membershipsByRole[role.role]" :key="m.id">
                  <pf-td data-label="User">
                    <div class="name">{{ m.user.display_name || "—" }}</div>
                    <div v-if="m.title" class="muted small">{{ m.title }}</div>
                  </pf-td>
                  <pf-td data-label="Email" class="muted">{{ m.user.email }}</pf-td>
                </pf-tr>
              </pf-tbody>
            </pf-table>
          </pf-card-body>
        </pf-card>
      </div>
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

.controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.role-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.name {
  font-weight: 600;
}

.muted {
  color: var(--pf-t--global--text--color--subtle);
}

.small {
  font-size: 0.875rem;
}
</style>
