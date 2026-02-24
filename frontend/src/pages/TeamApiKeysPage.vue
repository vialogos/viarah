<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { ApiKey } from "../api/types";
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

const apiKeys = ref<ApiKey[]>([]);
const loading = ref(false);
const error = ref("");
const actionError = ref("");

const newName = ref("");
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

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManage = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const projectNameById = computed(() => {
  const map: Record<string, string> = {};
  for (const p of context.projects) {
    map[p.id] = p.name;
  }
  return map;
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  actionError.value = "";

  if (!context.orgId) {
    apiKeys.value = [];
    return;
  }

  loading.value = true;
  try {
    await context.refreshProjects();
    const res = await api.listApiKeys(context.orgId);
    apiKeys.value = res.api_keys;
  } catch (err) {
    apiKeys.value = [];
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
  if (!eventType.startsWith("api_key.") && !eventType.startsWith("project.")) {
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

async function createKey() {
  actionError.value = "";

  if (!context.orgId) {
    actionError.value = "Select an org first.";
    return;
  }
  if (!canManage.value) {
    actionError.value = "Not permitted.";
    return;
  }

  const name = newName.value.trim();
  if (!name) {
    actionError.value = "Name is required.";
    return;
  }

  creating.value = true;
  try {
    const res = await api.createApiKey(context.orgId, {
      name,
      project_id: newProjectId.value ? newProjectId.value : null,
      scopes: scopesForDraft(),
    });

    tokenMaterial.value = { token: res.token, apiKey: res.api_key };
    clipboardStatus.value = "";

    newName.value = "";
    newProjectId.value = "";
    scopeRead.value = true;
    scopeWrite.value = false;

    await refresh();
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
    await refresh();
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
    await refresh();
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
  <div class="stack">
    <pf-card v-if="tokenMaterial" class="token-card">
      <pf-card-title>
        <div class="token-header">
          <div>
            <pf-title h="2" size="xl">API key token (shown once)</pf-title>
            <pf-content>
              <p class="muted">
                Store this token now. You won’t be able to view it again. If you lose it, rotate the key to mint a
                new token.
              </p>
            </pf-content>
          </div>
          <pf-close-button aria-label="Dismiss token panel" @click="dismissTokenMaterial" />
        </div>
      </pf-card-title>
      <pf-card-body>
        <pf-form class="token-form">
          <pf-description-list horizontal compact>
            <pf-description-list-group>
              <pf-description-list-term>Name</pf-description-list-term>
              <pf-description-list-description>{{ tokenMaterial.apiKey.name }}</pf-description-list-description>
            </pf-description-list-group>
            <pf-description-list-group>
              <pf-description-list-term>Prefix</pf-description-list-term>
              <pf-description-list-description>{{ tokenMaterial.apiKey.prefix }}</pf-description-list-description>
            </pf-description-list-group>
          </pf-description-list>

          <pf-form-group label="Token" field-id="api-key-token">
            <div class="token-row">
              <pf-text-input-group class="token-input-group">
                <pf-text-input-group-main :model-value="tokenMaterial.token" readonly aria-label="API key token" />
              </pf-text-input-group>
              <pf-button variant="secondary" @click="copyText(tokenMaterial.token)">Copy</pf-button>
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
            <pf-title h="1" size="2xl">API keys</pf-title>
            <pf-content>
              <p class="muted">Admin/PM-only keys for automation (e.g., viarah-cli). Tokens are displayed once.</p>
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
          <pf-empty-state-body>Select an org to manage API keys.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading API keys" />
        </div>

        <pf-alert v-else-if="error" inline variant="danger" :title="error" />

        <div v-else>
          <pf-alert v-if="actionError" inline variant="danger" :title="actionError" class="spacer" />

          <pf-form v-if="canManage" class="create" @submit.prevent="createKey">
            <pf-title h="2" size="lg">Create key</pf-title>
            <div class="create-row">
              <pf-form-group label="Name" field-id="api-key-name" class="grow">
                <pf-text-input
                  id="api-key-name"
                  v-model="newName"
                  type="text"
                  placeholder="e.g., viarah-cli"
                  :disabled="creating"
                />
              </pf-form-group>

              <pf-form-group label="Project restriction" field-id="api-key-project" class="grow">
                <pf-form-select id="api-key-project" v-model="newProjectId" :disabled="creating">
                  <pf-form-select-option value="">All projects (org-wide)</pf-form-select-option>
                  <pf-form-select-option v-for="p in context.projects" :key="p.id" :value="p.id">
                    {{ p.name }}
                  </pf-form-select-option>
                </pf-form-select>
              </pf-form-group>

              <pf-form-group label="Scopes" field-id="api-key-scopes">
                <div class="scope-row">
                  <pf-checkbox id="api-key-scope-read" v-model="scopeRead" label="read" :disabled="creating" />
                  <pf-checkbox id="api-key-scope-write" v-model="scopeWrite" label="write" :disabled="creating" />
                </div>
              </pf-form-group>

              <pf-button type="submit" variant="primary" :disabled="creating">
                {{ creating ? "Creating…" : "Create" }}
              </pf-button>
            </div>
          </pf-form>

          <pf-helper-text v-else class="note">
            <pf-helper-text-item>Only PM/admin can manage API keys.</pf-helper-text-item>
          </pf-helper-text>

          <pf-title h="2" size="lg" class="spacer">Keys</pf-title>

          <pf-empty-state v-if="apiKeys.length === 0">
            <pf-empty-state-header title="No API keys" heading-level="h3" />
            <pf-empty-state-body>Create one to enable CLI or automation access.</pf-empty-state-body>
          </pf-empty-state>

          <pf-table v-else aria-label="API keys table">
            <pf-thead>
              <pf-tr>
                <pf-th>Name</pf-th>
                <pf-th>Project</pf-th>
                <pf-th>Scopes</pf-th>
                <pf-th>Status</pf-th>
                <pf-th>Created</pf-th>
                <pf-th />
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="k in apiKeys" :key="k.id">
                <pf-td data-label="Name">
                  <div class="name">{{ k.name }}</div>
                  <div class="muted small">{{ k.prefix }}</div>
                </pf-td>

                <pf-td data-label="Project">
                  <span v-if="!k.project_id" class="muted">All projects</span>
                  <span v-else>{{ projectNameById[k.project_id] ?? k.project_id }}</span>
                </pf-td>

                <pf-td data-label="Scopes">
                  <div class="labels">
                    <VlLabel v-for="s in k.scopes" :key="`${k.id}-scope-${s}`" variant="outline">{{ s }}</VlLabel>
                  </div>
                </pf-td>

                <pf-td data-label="Status">
                  <div class="labels">
                    <VlLabel v-if="k.revoked_at" color="red">REVOKED</VlLabel>
                    <VlLabel v-else color="green">ACTIVE</VlLabel>
                    <VlLabel v-if="k.rotated_at" color="grey">Rotated {{ formatTimestamp(k.rotated_at) }}</VlLabel>
                  </div>
                </pf-td>

                <pf-td data-label="Created" class="muted">{{ formatTimestamp(k.created_at) }}</pf-td>

                <pf-td data-label="Actions">
                  <div class="actions">
                    <pf-button
                      variant="secondary"
                      small
                      :disabled="!canManage || rotating || Boolean(k.revoked_at)"
                      @click="requestRotateKey(k)"
                    >
                      Rotate
                    </pf-button>
                    <pf-button
                      variant="danger"
                      small
                      :disabled="!canManage || revoking || Boolean(k.revoked_at)"
                      @click="requestRevokeKey(k)"
                    >
                      Revoke
                    </pf-button>
                  </div>
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>
        </div>
      </pf-card-body>
    </pf-card>

    <VlConfirmModal
      v-model:open="rotateModalOpen"
      title="Rotate API key"
      :body="`Rotate API key '${pendingRotateKey?.name ?? ''}'? The old token will stop working; the new token will be shown once.`"
      confirm-label="Rotate"
      confirm-variant="warning"
      :loading="rotating"
      @confirm="rotateKey"
    />

    <VlConfirmModal
      v-model:open="revokeModalOpen"
      title="Revoke API key"
      :body="`Revoke API key '${pendingRevokeKey?.name ?? ''}'? This cannot be undone.`"
      confirm-label="Revoke"
      confirm-variant="danger"
      :loading="revoking"
      @confirm="revokeKey"
    />
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

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

.create {
  margin-top: 0.75rem;
}

.create-row {
  margin-top: 0.5rem;
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.grow {
  flex: 1;
  min-width: 260px;
}

.scope-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.name {
  font-weight: 600;
}

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.muted {
  color: var(--pf-t--global--text--color--subtle);
}

.small {
  font-size: 0.875rem;
}

.note {
  margin-top: 0.75rem;
}

.spacer {
  margin-top: 1rem;
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
