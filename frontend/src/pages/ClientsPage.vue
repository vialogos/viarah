<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Client } from "../api/types";
import VlConfirmModal from "../components/VlConfirmModal.vue";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const realtime = useRealtimeStore();

const clients = ref<Client[]>([]);
const loading = ref(false);
const error = ref("");

const query = ref("");

const createModalOpen = ref(false);
const creating = ref(false);
const createError = ref("");
const newName = ref("");
const newNotes = ref("");

const editModalOpen = ref(false);
const saving = ref(false);
const editError = ref("");
const editingClient = ref<Client | null>(null);
const editName = ref("");
const editNotes = ref("");

const deleteModalOpen = ref(false);
const deleting = ref(false);
const deleteError = ref("");
const pendingDelete = ref<Client | null>(null);

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canEdit = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    clients.value = [];
    return;
  }

  loading.value = true;
  try {
    const q = query.value.trim();
    const res = await api.listClients(context.orgId, { q: q ? q : undefined });
    clients.value = res.clients;
  } catch (err) {
    clients.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

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
  if (!eventType.startsWith("client.")) {
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

watch(
  () => [context.orgId, query.value],
  () => void refresh(),
  { immediate: true }
);

function openCreateModal() {
  createError.value = "";
  newName.value = "";
  newNotes.value = "";
  createModalOpen.value = true;
}

async function createClient() {
  createError.value = "";
  if (!context.orgId) {
    createError.value = "Select an org first.";
    return;
  }
  if (!canEdit.value) {
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
    await api.createClient(context.orgId, { name, notes: newNotes.value.trim() || undefined });
    createModalOpen.value = false;
    await refresh();
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

function openEditModal(client: Client) {
  editError.value = "";
  editingClient.value = client;
  editName.value = client.name;
  editNotes.value = client.notes;
  editModalOpen.value = true;
}

async function saveClient() {
  editError.value = "";
  if (!context.orgId) {
    editError.value = "Select an org first.";
    return;
  }
  if (!editingClient.value) {
    editError.value = "No client selected.";
    return;
  }
  if (!canEdit.value) {
    editError.value = "Not permitted.";
    return;
  }

  const name = editName.value.trim();
  if (!name) {
    editError.value = "Name is required.";
    return;
  }

  saving.value = true;
  try {
    await api.updateClient(context.orgId, editingClient.value.id, {
      name,
      notes: editNotes.value.trim(),
    });
    editModalOpen.value = false;
    editingClient.value = null;
    await refresh();
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

function requestDelete(client: Client) {
  deleteError.value = "";
  pendingDelete.value = client;
  deleteModalOpen.value = true;
}

async function deleteClient() {
  deleteError.value = "";
  if (!context.orgId) {
    deleteError.value = "Select an org first.";
    return;
  }
  if (!pendingDelete.value) {
    deleteError.value = "No client selected.";
    return;
  }
  if (!canEdit.value) {
    deleteError.value = "Not permitted.";
    return;
  }

  deleting.value = true;
  try {
    await api.deleteClient(context.orgId, pendingDelete.value.id);
    deleteModalOpen.value = false;
    pendingDelete.value = null;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      deleteError.value = "Not permitted.";
      return;
    }
    deleteError.value = err instanceof Error ? err.message : String(err);
  } finally {
    deleting.value = false;
  }
}
</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <pf-title h="1" size="2xl">Clients</pf-title>
        <pf-button variant="primary" :disabled="!canEdit" @click="openCreateModal">Create client</pf-button>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to manage clients.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else>
        <pf-toolbar class="toolbar">
          <pf-toolbar-content>
            <pf-toolbar-group>
              <pf-toolbar-item>
                <pf-search-input v-model="query" placeholder="Search clients…" aria-label="Search clients" />
              </pf-toolbar-item>
            </pf-toolbar-group>
            <pf-toolbar-group align="end">
              <pf-toolbar-item>
                <pf-button variant="secondary" :disabled="loading" @click="refresh">
                  {{ loading ? "Refreshing…" : "Refresh" }}
                </pf-button>
              </pf-toolbar-item>
            </pf-toolbar-group>
          </pf-toolbar-content>
        </pf-toolbar>

        <pf-alert v-if="error" inline variant="danger" :title="error" />

        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading clients" />
        </div>

        <pf-empty-state v-else-if="clients.length === 0" variant="small">
          <pf-empty-state-header title="No clients yet" heading-level="h2" />
          <pf-empty-state-body>Create a client to link projects and deliverables.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else class="table-wrap">
          <pf-table aria-label="Clients">
            <pf-thead>
              <pf-tr>
                <pf-th>Name</pf-th>
                <pf-th>Updated</pf-th>
                <pf-th v-if="canEdit" screen-reader-text>Actions</pf-th>
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="client in clients" :key="client.id">
                <pf-td data-label="Name">
                  <div class="name">
                    <pf-button variant="link" :to="`/clients/${client.id}`" class="primary">{{ client.name }}</pf-button>
                    <div v-if="client.notes" class="muted notes">{{ client.notes }}</div>
                  </div>
                </pf-td>
                <pf-td data-label="Updated">
                  <VlLabel color="blue">{{ formatTimestamp(client.updated_at) }}</VlLabel>
                </pf-td>
                <pf-td v-if="canEdit" data-label="Actions" modifier="fitContent">
                  <div class="actions">
                    <pf-button variant="secondary" small @click="openEditModal(client)">Edit</pf-button>
                    <pf-button variant="danger" small @click="requestDelete(client)">Delete</pf-button>
                  </div>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>
        </div>
      </div>
    </pf-card-body>
  </pf-card>

  <pf-modal v-model:open="createModalOpen" title="Create client" variant="medium">
    <pf-form class="modal-form" @submit.prevent="createClient">
      <pf-form-group label="Name" field-id="client-create-name">
        <pf-text-input id="client-create-name" v-model="newName" type="text" placeholder="Client name" />
      </pf-form-group>
      <pf-form-group label="Notes (optional)" field-id="client-create-notes">
        <pf-textarea id="client-create-notes" v-model="newNotes" rows="4" />
      </pf-form-group>
      <pf-alert v-if="createError" inline variant="danger" :title="createError" />
    </pf-form>

    <template #footer>
      <pf-button variant="primary" :disabled="creating || !canEdit || !newName.trim()" @click="createClient">
        {{ creating ? "Creating…" : "Create" }}
      </pf-button>
      <pf-button variant="link" :disabled="creating" @click="createModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>

  <pf-modal v-model:open="editModalOpen" title="Edit client" variant="medium">
    <pf-form class="modal-form" @submit.prevent="saveClient">
      <pf-form-group label="Name" field-id="client-edit-name">
        <pf-text-input id="client-edit-name" v-model="editName" type="text" />
      </pf-form-group>
      <pf-form-group label="Notes" field-id="client-edit-notes">
        <pf-textarea id="client-edit-notes" v-model="editNotes" rows="6" />
      </pf-form-group>
      <pf-alert v-if="editError" inline variant="danger" :title="editError" />
    </pf-form>

    <template #footer>
      <pf-button
        variant="primary"
        :disabled="saving || !canEdit || !editingClient || !editName.trim()"
        @click="saveClient"
      >
        {{ saving ? "Saving…" : "Save" }}
      </pf-button>
      <pf-button variant="link" :disabled="saving" @click="editModalOpen = false">Cancel</pf-button>
    </template>
  </pf-modal>

  <VlConfirmModal
    v-model:open="deleteModalOpen"
    title="Delete client"
    :body="`Delete client '${pendingDelete?.name ?? ''}'? Projects linked to this client must be updated first.`"
    confirm-label="Delete client"
    confirm-variant="danger"
    :loading="deleting"
    @confirm="deleteClient"
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

.toolbar {
  margin-bottom: 0.75rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.name .primary {
  font-weight: 600;
}

.muted {
  color: #6b7280;
}

.notes {
  margin-top: 0.125rem;
  white-space: pre-wrap;
}
</style>
