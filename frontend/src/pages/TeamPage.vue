<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { OrgMembershipWithUser, ProjectClientAccess } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const memberships = ref<OrgMembershipWithUser[]>([]);
const accessRows = ref<ProjectClientAccess[]>([]);

const loading = ref(false);
const error = ref("");

const provisionModalOpen = ref(false);
const provisioning = ref(false);
const provisionError = ref("");
const provisionEmail = ref("");
const provisionDisplayName = ref("");
const provisionRole = ref<"client" | "member" | "pm" | "admin">("client");

const manageAccessModalOpen = ref(false);
const manageAccessError = ref("");
const managingAccess = ref(false);
const manageAccessMembership = ref<OrgMembershipWithUser | null>(null);
const manageAccessSelectedProjectIds = ref<string[]>([]);
const manageAccessInitialProjectIds = ref<string[]>([]);

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManageTeam = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const projectNameById = computed(() => {
  const map: Record<string, string> = {};
  for (const project of context.projects) {
    map[project.id] = project.name;
  }
  return map;
});

const accessIdByUserProjectId = computed(() => {
  const map: Record<string, Record<string, string>> = {};
  for (const row of accessRows.value) {
    const userId = row.user.id;
    map[userId] ||= {};
    map[userId][row.project_id] = row.id;
  }
  return map;
});

const clientMemberships = computed(() =>
  memberships.value.filter((m) => String(m.role).toLowerCase() === "client")
);

function projectIdsForUser(userId: string): string[] {
  const row = accessIdByUserProjectId.value[userId] ?? {};
  return Object.keys(row).sort((a, b) => (projectNameById.value[a] || a).localeCompare(projectNameById.value[b] || b));
}

function projectSelected(projectId: string): boolean {
  return manageAccessSelectedProjectIds.value.includes(projectId);
}

function setProjectSelected(projectId: string, selected: boolean) {
  if (selected) {
    manageAccessSelectedProjectIds.value = Array.from(
      new Set([...manageAccessSelectedProjectIds.value, projectId])
    );
    return;
  }
  manageAccessSelectedProjectIds.value = manageAccessSelectedProjectIds.value.filter((id) => id !== projectId);
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  if (!context.orgId) {
    memberships.value = [];
    accessRows.value = [];
    return;
  }

  loading.value = true;
  try {
    await context.refreshProjects();
    const [membersRes, accessRes] = await Promise.all([
      api.listOrgMemberships(context.orgId),
      api.listProjectClientAccess(context.orgId),
    ]);
    memberships.value = membersRes.memberships;
    accessRows.value = accessRes.access;
  } catch (err) {
    memberships.value = [];
    accessRows.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function openProvisionModal() {
  provisionError.value = "";
  provisionEmail.value = "";
  provisionDisplayName.value = "";
  provisionRole.value = "client";
  provisionModalOpen.value = true;
}

async function provisionUser() {
  provisionError.value = "";
  if (!context.orgId) {
    provisionError.value = "Select an org first.";
    return;
  }
  if (!canManageTeam.value) {
    provisionError.value = "Not permitted.";
    return;
  }
  const email = provisionEmail.value.trim().toLowerCase();
  if (!email) {
    provisionError.value = "Email is required.";
    return;
  }

  provisioning.value = true;
  try {
    await api.provisionOrgMembership(context.orgId, {
      email,
      display_name: provisionDisplayName.value.trim() ? provisionDisplayName.value.trim() : undefined,
      role: provisionRole.value,
    });
    provisionModalOpen.value = false;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      provisionError.value = "Not permitted.";
      return;
    }
    provisionError.value = err instanceof Error ? err.message : String(err);
  } finally {
    provisioning.value = false;
  }
}

function openManageAccessModal(membership: OrgMembershipWithUser) {
  manageAccessError.value = "";
  manageAccessMembership.value = membership;
  const current = projectIdsForUser(membership.user.id);
  manageAccessSelectedProjectIds.value = [...current];
  manageAccessInitialProjectIds.value = [...current];
  manageAccessModalOpen.value = true;
}

async function saveAccess() {
  manageAccessError.value = "";
  if (!context.orgId) {
    manageAccessError.value = "Select an org first.";
    return;
  }
  if (!canManageTeam.value) {
    manageAccessError.value = "Not permitted.";
    return;
  }
  if (!manageAccessMembership.value) {
    manageAccessError.value = "No client selected.";
    return;
  }

  const userId = manageAccessMembership.value.user.id;
  const initial = new Set(manageAccessInitialProjectIds.value);
  const selected = new Set(manageAccessSelectedProjectIds.value);

  const toAdd = Array.from(selected).filter((projectId) => !initial.has(projectId));
  const toRemove = Array.from(initial).filter((projectId) => !selected.has(projectId));

  managingAccess.value = true;
  try {
    const failures: string[] = [];

    for (const projectId of toAdd) {
      try {
        await api.grantProjectClientAccess(context.orgId, { project_id: projectId, user_id: userId });
      } catch (err) {
        failures.push(
          `Failed to grant access to '${projectNameById.value[projectId] ?? projectId}': ${
            err instanceof Error ? err.message : String(err)
          }`
        );
      }
    }

    for (const projectId of toRemove) {
      const accessId = accessIdByUserProjectId.value[userId]?.[projectId] ?? "";
      if (!accessId) {
        continue;
      }
      try {
        await api.revokeProjectClientAccess(context.orgId, accessId);
      } catch (err) {
        failures.push(
          `Failed to revoke access from '${projectNameById.value[projectId] ?? projectId}': ${
            err instanceof Error ? err.message : String(err)
          }`
        );
      }
    }

    if (failures.length > 0) {
      manageAccessError.value = failures.join("\n");
      return;
    }

    manageAccessModalOpen.value = false;
    manageAccessMembership.value = null;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    manageAccessError.value = err instanceof Error ? err.message : String(err);
  } finally {
    managingAccess.value = false;
  }
}

watch(
  () => context.orgId,
  () => {
    void refresh();
  },
  { immediate: true }
);
</script>

<template>
  <div class="stack">
    <div class="header-row">
      <pf-title h="1" size="2xl">Team</pf-title>
      <pf-button v-if="canManageTeam" type="button" variant="primary" small @click="openProvisionModal">
        Provision user
      </pf-button>
    </div>

    <pf-content>
      <p class="muted">
        Manage client users and which projects they can access in the client portal.
      </p>
    </pf-content>

    <pf-alert v-if="error" inline variant="danger" :title="error" />

    <pf-card>
      <pf-card-title>
        <pf-title h="2" size="lg">Clients</pf-title>
      </pf-card-title>
      <pf-card-body>
        <div v-if="loading" class="inline-loading">
          <pf-spinner size="md" aria-label="Loading team" />
          <span class="muted">Loading…</span>
        </div>

        <pf-empty-state v-else-if="clientMemberships.length === 0" variant="small">
          <pf-empty-state-header title="No client users yet" heading-level="h3" />
          <pf-empty-state-body>
            Provision a client user and then grant them access to one or more projects.
          </pf-empty-state-body>
        </pf-empty-state>

        <pf-table v-else aria-label="Client users">
          <pf-thead>
            <pf-tr>
              <pf-th>Name</pf-th>
              <pf-th>Email</pf-th>
              <pf-th>Projects</pf-th>
              <pf-th />
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="membership in clientMemberships" :key="membership.id">
              <pf-td data-label="Name">
                {{ membership.user.display_name || membership.user.email }}
              </pf-td>
              <pf-td data-label="Email">
                <span class="muted">{{ membership.user.email }}</span>
              </pf-td>
              <pf-td data-label="Projects">
                <div class="labels">
                  <VlLabel
                    v-for="projectId in projectIdsForUser(membership.user.id)"
                    :key="projectId"
                    color="blue"
                  >
                    {{ projectNameById[projectId] ?? projectId }}
                  </VlLabel>
                  <span v-if="projectIdsForUser(membership.user.id).length === 0" class="muted">None</span>
                </div>
              </pf-td>
              <pf-td>
                <pf-button
                  type="button"
                  variant="secondary"
                  small
                  :disabled="!canManageTeam"
                  @click="openManageAccessModal(membership)"
                >
                  Manage access
                </pf-button>
              </pf-td>
            </pf-tr>
          </pf-tbody>
        </pf-table>
      </pf-card-body>
    </pf-card>

    <pf-modal v-model:open="provisionModalOpen" title="Provision user">
      <pf-form class="modal-form" @submit.prevent="provisionUser">
        <pf-form-group label="Email" field-id="team-provision-email">
          <pf-text-input
            id="team-provision-email"
            v-model="provisionEmail"
            type="email"
            placeholder="name@example.com"
            autocomplete="off"
          />
        </pf-form-group>

        <pf-form-group label="Display name (optional)" field-id="team-provision-display-name">
          <pf-text-input
            id="team-provision-display-name"
            v-model="provisionDisplayName"
            type="text"
            placeholder="Jane Doe"
            autocomplete="off"
          />
        </pf-form-group>

        <pf-form-group label="Role" field-id="team-provision-role">
          <pf-form-select id="team-provision-role" v-model="provisionRole">
            <pf-form-select-option value="client">Client</pf-form-select-option>
            <pf-form-select-option value="member">Member</pf-form-select-option>
            <pf-form-select-option value="pm">PM</pf-form-select-option>
            <pf-form-select-option value="admin">Admin</pf-form-select-option>
          </pf-form-select>
        </pf-form-group>

        <pf-alert v-if="provisionError" inline variant="danger" :title="provisionError" />
      </pf-form>

      <template #footer>
        <pf-button
          variant="primary"
          :disabled="provisioning || !canManageTeam || !provisionEmail.trim()"
          @click="provisionUser"
        >
          {{ provisioning ? "Provisioning…" : "Provision" }}
        </pf-button>
        <pf-button variant="link" :disabled="provisioning" @click="provisionModalOpen = false">
          Cancel
        </pf-button>
      </template>
    </pf-modal>

    <pf-modal v-model:open="manageAccessModalOpen" title="Client project access">
      <pf-content v-if="manageAccessMembership">
        <p class="muted">
          Client: <strong>{{ manageAccessMembership.user.display_name || manageAccessMembership.user.email }}</strong>
        </p>
      </pf-content>

      <pf-form class="modal-form" @submit.prevent="saveAccess">
        <pf-empty-state v-if="context.projects.length === 0" variant="small">
          <pf-empty-state-header title="No projects found" heading-level="h3" />
          <pf-empty-state-body>Create a project first, then grant access.</pf-empty-state-body>
        </pf-empty-state>

        <pf-form-group v-else label="Projects" field-id="team-client-projects">
          <div class="project-grid" role="group" aria-label="Client project access">
            <pf-checkbox
              v-for="project in context.projects"
              :id="`client-access-${manageAccessMembership?.user.id ?? 'unknown'}-${project.id}`"
              :key="project.id"
              :label="project.name"
              :model-value="projectSelected(project.id)"
              :disabled="managingAccess"
              @update:model-value="setProjectSelected(project.id, Boolean($event))"
            />
          </div>
        </pf-form-group>

        <pf-alert
          v-if="manageAccessError"
          inline
          variant="danger"
          :title="manageAccessError"
        />
      </pf-form>

      <template #footer>
        <pf-button
          variant="primary"
          :disabled="managingAccess || !canManageTeam || !manageAccessMembership"
          @click="saveAccess"
        >
          {{ managingAccess ? "Saving…" : "Save" }}
        </pf-button>
        <pf-button variant="link" :disabled="managingAccess" @click="manageAccessModalOpen = false">
          Cancel
        </pf-button>
      </template>
    </pf-modal>
  </div>
</template>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.5rem 1rem;
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>

