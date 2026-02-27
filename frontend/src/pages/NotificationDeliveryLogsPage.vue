<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { EmailDeliveryLog } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { deliveryStatusLabelColor } from "../utils/labels";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const realtime = useRealtimeStore();

const loading = ref(false);
const error = ref("");
const deliveries = ref<EmailDeliveryLog[]>([]);
const statusFilter = ref("");

const currentRole = computed(() => {
  return session.effectiveOrgRole(context.orgId);
});

const canView = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
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
  if (!context.orgId || !context.projectId || !canView.value) {
    return;
  }
  if (event.org_id && event.org_id !== context.orgId) {
    return;
  }

  if (event.type !== "email_delivery_log.updated") {
    return;
  }
  if (!isRecord(event.data)) {
    return;
  }
  const projectId = typeof event.data.project_id === "string" ? event.data.project_id : "";
  if (!projectId || projectId !== context.projectId) {
    return;
  }
  if (statusFilter.value) {
    const status = typeof event.data.status === "string" ? event.data.status : "";
    if (status && status !== statusFilter.value) {
      return;
    }
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
          <pf-title h="1" size="2xl">Notification Delivery Logs</pf-title>
          <pf-content>
            <p class="muted">Recent email delivery attempts for the selected project.</p>
          </pf-content>
        </div>
        <pf-button variant="link" to="/notifications">Back to inbox</pf-button>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Delivery logs are project-scoped" heading-level="h2" />
        <pf-empty-state-body>Select a single org and project to view delivery logs.</pf-empty-state-body>
      </pf-empty-state>
      <pf-empty-state v-else-if="!context.projectId">
        <pf-empty-state-header title="Select a project" heading-level="h2" />
        <pf-empty-state-body>Select a project to continue.</pf-empty-state-body>
      </pf-empty-state>
      <pf-empty-state v-else-if="!canView">
        <pf-empty-state-header title="Not permitted" heading-level="h2" />
        <pf-empty-state-body>Only PM/admin can view delivery logs.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else>
        <pf-toolbar class="toolbar">
          <pf-toolbar-content>
            <pf-toolbar-group>
              <pf-toolbar-item>
                <pf-form-group label="Status" field-id="delivery-logs-status-filter" class="filter-field">
                  <pf-form-select id="delivery-logs-status-filter" v-model="statusFilter" :disabled="loading">
                    <pf-form-select-option value="">All</pf-form-select-option>
                    <pf-form-select-option value="queued">Queued</pf-form-select-option>
                    <pf-form-select-option value="success">Success</pf-form-select-option>
                    <pf-form-select-option value="failure">Failure</pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>
              </pf-toolbar-item>
            </pf-toolbar-group>
          </pf-toolbar-content>
        </pf-toolbar>

        <pf-alert v-if="error" inline variant="danger" :title="error" />
        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading notification delivery logs" />
        </div>
        <pf-empty-state v-else-if="deliveries.length === 0">
          <pf-empty-state-header title="No delivery logs" heading-level="h2" />
          <pf-empty-state-body>
            No email delivery attempts were found for the selected project.
          </pf-empty-state-body>
        </pf-empty-state>

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
                <pf-td data-label="Queued">
                  <VlLabel v-if="row.queued_at" color="blue">{{ formatTimestamp(row.queued_at) }}</VlLabel>
                  <span v-else class="muted">—</span>
                </pf-td>
                <pf-td class="mono" data-label="To">
                  {{ row.to_email }}
                </pf-td>
                <pf-td data-label="Subject">
                  {{ row.subject }}
                </pf-td>
                <pf-td data-label="Status">
                  <VlLabel :color="deliveryStatusLabelColor(row.status)">{{ row.status }}</VlLabel>
                </pf-td>
                <pf-td class="mono" data-label="Attempt">
                  {{ row.attempt_number }}
                </pf-td>
                <pf-td class="muted" data-label="Error">
                  {{ row.error_code || row.error_detail || "—" }}
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>
        </div>
      </div>
    </pf-card-body>
  </pf-card>
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

.filter-field {
  margin: 0;
}

.table-wrap {
  overflow-x: auto;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 1rem 0;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
  white-space: nowrap;
}
</style>
