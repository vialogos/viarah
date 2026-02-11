<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { EmailDeliveryLog } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const loading = ref(false);
const error = ref("");
const deliveries = ref<EmailDeliveryLog[]>([]);
const statusFilter = ref("");

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canView = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

async function refresh() {
  error.value = "";
  if (!context.orgId || !context.projectId) {
    deliveries.value = [];
    return;
  }
  if (!canView.value) {
    deliveries.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listNotificationDeliveryLogs(context.orgId, context.projectId, {
      status: statusFilter.value || undefined,
      limit: 100,
    });
    deliveries.value = res.deliveries;
  } catch (err) {
    deliveries.value = [];
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

watch(() => [context.orgId, context.projectId, canView.value, statusFilter.value], () => void refresh(), {
  immediate: true,
});
</script>

<template>
  <div>
    <div class="header">
      <div>
        <h1 class="page-title">Notification Delivery Logs</h1>
        <p class="muted">Recent email delivery attempts for the selected project.</p>
      </div>
      <RouterLink class="muted" to="/notifications">Back to inbox</RouterLink>
    </div>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>
    <p v-else-if="!context.projectId" class="card">Select a project to continue.</p>
    <p v-else-if="!canView" class="card">Only PM/admin can view delivery logs.</p>

    <div v-else class="card">
      <pf-toolbar class="toolbar">
        <pf-toolbar-content>
          <pf-toolbar-group>
            <pf-toolbar-item>
              <label class="field">
                <span class="label">Status</span>
                <select v-model="statusFilter" :disabled="loading">
                  <option value="">All</option>
                  <option value="queued">Queued</option>
                  <option value="success">Success</option>
                  <option value="failure">Failure</option>
                </select>
              </label>
            </pf-toolbar-item>
            <pf-toolbar-item>
              <button type="button" :disabled="loading" @click="refresh">
                {{ loading ? "Refreshing…" : "Refresh" }}
              </button>
            </pf-toolbar-item>
          </pf-toolbar-group>
        </pf-toolbar-content>
      </pf-toolbar>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="deliveries.length === 0" class="muted">No delivery logs.</div>

      <div v-else class="table-wrap">
        <pf-table aria-label="Notification delivery logs">
          <pf-thead>
            <pf-tr>
              <pf-th>Queued</pf-th>
              <pf-th>To</pf-th>
              <pf-th>Subject</pf-th>
              <pf-th>Status</pf-th>
              <pf-th>Attempt</pf-th>
              <pf-th>Error</pf-th>
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="row in deliveries" :key="row.id">
              <pf-td class="mono" data-label="Queued">
                {{ formatTimestamp(row.queued_at) }}
              </pf-td>
              <pf-td class="mono" data-label="To">
                {{ row.to_email }}
              </pf-td>
              <pf-td data-label="Subject">
                {{ row.subject }}
              </pf-td>
              <pf-td class="mono" data-label="Status">
                {{ row.status }}
              </pf-td>
              <pf-td class="mono" data-label="Attempt">
                {{ row.attempt_number }}
              </pf-td>
              <pf-td class="muted" data-label="Error">
                {{ row.error_code || row.error_detail || "" }}
              </pf-td>
            </pf-tr>
          </pf-tbody>
        </pf-table>
      </div>
    </div>
  </div>
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

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.label {
  font-size: 0.9rem;
  color: var(--muted);
}

.table-wrap {
  overflow-x: auto;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
  white-space: nowrap;
}
</style>
