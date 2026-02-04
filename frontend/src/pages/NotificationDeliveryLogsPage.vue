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
      <div class="toolbar">
        <label class="field">
          <span class="label">Status</span>
          <select v-model="statusFilter" :disabled="loading">
            <option value="">All</option>
            <option value="queued">Queued</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
          </select>
        </label>
        <div class="spacer" />
        <button type="button" :disabled="loading" @click="refresh">
          {{ loading ? "Refreshing…" : "Refresh" }}
        </button>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="deliveries.length === 0" class="muted">No delivery logs.</div>

      <div v-else class="table-wrap">
        <table class="logs">
          <thead>
            <tr>
              <th>Queued</th>
              <th>To</th>
              <th>Subject</th>
              <th>Status</th>
              <th>Attempt</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in deliveries" :key="row.id">
              <td class="mono">{{ formatTimestamp(row.queued_at) }}</td>
              <td class="mono">{{ row.to_email }}</td>
              <td>{{ row.subject }}</td>
              <td class="mono">{{ row.status }}</td>
              <td class="mono">{{ row.attempt_number }}</td>
              <td class="muted">{{ row.error_code || row.error_detail || "" }}</td>
            </tr>
          </tbody>
        </table>
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
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
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

.spacer {
  flex: 1;
}

.table-wrap {
  overflow-x: auto;
}

.logs {
  width: 100%;
  border-collapse: collapse;
}

.logs th,
.logs td {
  padding: 0.5rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
  white-space: nowrap;
}
</style>
