<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { OrgSummary } from "../api/types";
import VlConfirmModal from "../components/VlConfirmModal.vue";
import VlInitialsAvatar from "../components/VlInitialsAvatar.vue";
import VlLabel from "../components/VlLabel.vue";
import { formatTimestamp } from "../utils/format";
import type { VlLabelColor } from "../utils/labels";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const orgs = ref<OrgSummary[]>([]);
const loading = ref(false);
const error = ref("");

const createModalOpen = ref(false);
const creating = ref(false);
const createError = ref("");
const newName = ref("");
const newLogoFile = ref<File | null>(null);
const newLogoUploadKey = ref(0);

const editModalOpen = ref(false);
const saving = ref(false);
const editError = ref("");
const editingOrg = ref<OrgSummary | null>(null);
const editName = ref("");
const editLogoFile = ref<File | null>(null);
const editLogoUploadKey = ref(0);

const deleteModalOpen = ref(false);
const deleting = ref(false);
const pendingDelete = ref<OrgSummary | null>(null);

const canCreateOrgs = computed(() => {
  const roles = session.memberships.map((membership) => membership.role);
  if (roles.length === 0) {
    return true;
  }
  return roles.some((role) => role !== "client");
});

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

function onSelectedNewLogoFileChange(payload: unknown) {
  if (payload instanceof File) {
    newLogoFile.value = payload;
    return;
  }
  newLogoFile.value = null;
}

function onSelectedEditLogoFileChange(payload: unknown) {
  if (payload instanceof File) {
    editLogoFile.value = payload;
    return;
  }
  editLogoFile.value = null;
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  loading.value = true;
  try {
    const res = await api.listOrgs();
    orgs.value = res.orgs;
  } catch (err) {
    orgs.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(
  () => session.user?.id,
  () => void refresh(),
  { immediate: true }
);

function openCreateModal() {
  createError.value = "";
  newName.value = "";
  newLogoFile.value = null;
  newLogoUploadKey.value += 1;
  createModalOpen.value = true;
}

async function createOrg() {
  createError.value = "";
  if (!canCreateOrgs.value) {
    createError.value = "Not permitted.";
    return;
  }

  const name = newName.value.trim();
  if (!name) {
    createError.value = "Name is required.";
    return;
  }

  creating.value = true;
  try {
    const created = await api.createOrg({ name });
    if (newLogoFile.value) {
      await api.uploadOrgLogo(created.org.id, newLogoFile.value);
    }
    createModalOpen.value = false;
    await Promise.all([refresh(), session.refresh()]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      createError.value = "Not permitted.";
      return;
    }
    createError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creating.value = false;
  }
}

function openEditModal(org: OrgSummary) {
  editError.value = "";
  editingOrg.value = org;
  editName.value = org.name;
  editLogoFile.value = null;
  editLogoUploadKey.value += 1;
  editModalOpen.value = true;
}

async function saveOrg() {
  editError.value = "";
  if (!editingOrg.value) {
    editError.value = "Select an org first.";
    return;
  }

  const name = editName.value.trim();
  if (!name) {
    editError.value = "Name is required.";
    return;
  }

  const canEdit = editingOrg.value.role === "admin" || editingOrg.value.role === "pm";
  if (!canEdit) {
    editError.value = "Not permitted.";
    return;
  }

  saving.value = true;
  try {
    let next = editingOrg.value;

    if (name !== next.name) {
      const res = await api.updateOrg(next.id, { name });
      next = res.org;
    }
    if (editLogoFile.value) {
      const res = await api.uploadOrgLogo(next.id, editLogoFile.value);
      next = res.org;
      editLogoFile.value = null;
      editLogoUploadKey.value += 1;
    }

    orgs.value = orgs.value.map((org) => (org.id === next.id ? next : org));
    editingOrg.value = next;
    editModalOpen.value = false;
    await session.refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      editError.value = "Not permitted.";
      return;
    }
    editError.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}

async function clearLogo() {
  editError.value = "";
  if (!editingOrg.value) {
    editError.value = "Select an org first.";
    return;
  }

  const canEdit = editingOrg.value.role === "admin" || editingOrg.value.role === "pm";
  if (!canEdit) {
    editError.value = "Not permitted.";
    return;
  }

  saving.value = true;
  try {
    const res = await api.clearOrgLogo(editingOrg.value.id);
    orgs.value = orgs.value.map((org) => (org.id === res.org.id ? res.org : org));
    editingOrg.value = res.org;
    await session.refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      editError.value = "Not permitted.";
      return;
    }
    editError.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}

function requestDelete(org: OrgSummary) {
  error.value = "";
  pendingDelete.value = org;
  deleteModalOpen.value = true;
}

async function deleteOrg() {
  if (!pendingDelete.value) {
    return;
  }

  deleting.value = true;
  error.value = "";
  try {
    await api.deleteOrg(pendingDelete.value.id);
    deleteModalOpen.value = false;
    pendingDelete.value = null;
    await Promise.all([refresh(), session.refresh()]);
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
    deleting.value = false;
  }
}

async function openOrgTeam(org: OrgSummary) {
  context.setOrgId(org.id);
  await router.push("/team");
}

async function openOrgClients(org: OrgSummary) {
  context.setOrgId(org.id);
  await router.push("/clients");
}
</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <pf-title h="1" size="2xl">Organizations</pf-title>
        <pf-button variant="primary" :disabled="!canCreateOrgs" @click="openCreateModal">Create org</pf-button>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-alert v-if="error" inline variant="danger" :title="error" />

      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading orgs" />
      </div>

      <pf-empty-state v-else-if="orgs.length === 0">
        <pf-empty-state-header title="No orgs found" heading-level="h2" />
        <pf-empty-state-body>Create an org to start organizing projects and work.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else class="table-wrap">
        <pf-table aria-label="Organizations">
          <pf-thead>
            <pf-tr>
              <pf-th>Organization</pf-th>
              <pf-th>Role</pf-th>
              <pf-th>Created</pf-th>
              <pf-th screen-reader-text>Actions</pf-th>
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="org in orgs" :key="org.id">
              <pf-td data-label="Organization">
                <div class="org-cell">
                  <VlInitialsAvatar :label="org.name" :src="org.logo_url" size="sm" bordered />
                  <div class="org-meta">
                    <div class="org-name">{{ org.name }}</div>
                    <div class="muted small">{{ org.id }}</div>
                  </div>
                </div>
              </pf-td>
              <pf-td data-label="Role">
                <VlLabel :color="roleLabelColor(org.role)" variant="outline">{{ org.role }}</VlLabel>
              </pf-td>
              <pf-td data-label="Created">
                <VlLabel color="grey">{{ formatTimestamp(org.created_at) }}</VlLabel>
              </pf-td>
              <pf-td data-label="Actions" modifier="fitContent">
                <div class="actions">
                  <pf-button
                    variant="secondary"
                    small
                    :disabled="org.role !== 'admin' && org.role !== 'pm'"
                    @click="openOrgTeam(org)"
                  >
                    Team
                  </pf-button>
                  <pf-button
                    variant="secondary"
                    small
                    :disabled="org.role !== 'admin' && org.role !== 'pm'"
                    @click="openOrgClients(org)"
                  >
                    Clients
                  </pf-button>
                  <pf-button
                    variant="secondary"
                    small
                    :disabled="org.role !== 'admin' && org.role !== 'pm'"
                    @click="openEditModal(org)"
                  >
                    Edit
                  </pf-button>
                  <pf-button
                    variant="danger"
                    small
                    :disabled="org.role !== 'admin'"
                    @click="requestDelete(org)"
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

  <pf-modal v-model:open="createModalOpen" title="Create org" variant="medium">
    <pf-form class="modal-form" @submit.prevent="createOrg">
      <pf-form-group label="Name" field-id="org-create-name">
        <pf-text-input id="org-create-name" v-model="newName" type="text" placeholder="Org name" />
      </pf-form-group>

      <pf-form-group label="Logo (optional)" field-id="org-create-logo">
        <pf-file-upload
          :key="newLogoUploadKey"
          browse-button-text="Choose image"
          hide-default-preview
          :disabled="creating"
          @file-input-change="onSelectedNewLogoFileChange"
        >
          <div class="muted small">
            {{ newLogoFile ? `${newLogoFile.name} (${newLogoFile.size} bytes)` : "No file selected." }}
          </div>
        </pf-file-upload>
      </pf-form-group>

      <pf-alert v-if="createError" inline variant="danger" :title="createError" />
    </pf-form>

    <template #footer>
      <pf-button variant="primary" :disabled="creating || !canCreateOrgs || !newName.trim()" @click="createOrg">
        {{ creating ? "Creating…" : "Create" }}
      </pf-button>
      <pf-button variant="link" :disabled="creating" @click="createModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>

  <pf-modal v-model:open="editModalOpen" title="Edit org" variant="medium">
    <pf-form class="modal-form" @submit.prevent="saveOrg">
      <pf-form-group label="Name" field-id="org-edit-name">
        <pf-text-input id="org-edit-name" v-model="editName" type="text" />
      </pf-form-group>

      <pf-form-group label="Logo" field-id="org-edit-logo">
        <div v-if="editingOrg" class="logo-row">
          <VlInitialsAvatar :label="editingOrg.name" :src="editingOrg.logo_url" size="xl" bordered />
          <div class="logo-actions">
            <pf-file-upload
              :key="editLogoUploadKey"
              browse-button-text="Choose image"
              hide-default-preview
              :disabled="saving"
              @file-input-change="onSelectedEditLogoFileChange"
            >
              <div class="muted small">
                {{ editLogoFile ? `${editLogoFile.name} (${editLogoFile.size} bytes)` : "No file selected." }}
              </div>
            </pf-file-upload>
          </div>
        </div>
      </pf-form-group>

      <pf-alert v-if="editError" inline variant="danger" :title="editError" />
    </pf-form>

    <template #footer>
      <pf-button variant="primary" :disabled="saving || !editingOrg || !editName.trim()" @click="saveOrg">
        {{ saving ? "Saving…" : "Save" }}
      </pf-button>
      <pf-button
        variant="secondary"
        :disabled="saving || !editingOrg || !editingOrg.logo_url"
        @click="clearLogo"
      >
        Clear logo
      </pf-button>
      <pf-button variant="link" :disabled="saving" @click="editModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>

  <VlConfirmModal
    v-model:open="deleteModalOpen"
    title="Delete org"
    :body="`Delete org '${pendingDelete?.name ?? ''}'? This will permanently delete its data.`"
    confirm-label="Delete org"
    confirm-variant="danger"
    :loading="deleting"
    @confirm="deleteOrg"
  />
</template>

<style scoped>
.header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.org-cell {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.org-meta {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.org-name {
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.muted {
  color: #6b7280;
}

.small {
  font-size: 0.85rem;
}

.logo-row {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.logo-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
