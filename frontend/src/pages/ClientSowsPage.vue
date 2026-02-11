<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { SoWListItem, SoWVersionStatus } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const sows = ref<SoWListItem[]>([]);
const loading = ref(false);
const error = ref("");

const statusFilter = ref<SoWVersionStatus | "">("");

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function projectName(projectId: string): string {
  return context.projects.find((p) => p.id === projectId)?.name ?? projectId;
}

function statusLabel(status: SoWVersionStatus): string {
  if (status === "draft") {
    return "Draft";
  }
  if (status === "pending_signature") {
    return "Pending signature";
  }
  if (status === "signed") {
    return "Signed";
  }
  if (status === "rejected") {
    return "Rejected";
  }
  return status;
}

function statusColor(status: SoWVersionStatus): "info" | "success" | "danger" | "warning" | null {
  if (status === "draft") {
    return "info";
  }
  if (status === "pending_signature") {
    return "warning";
  }
  if (status === "signed") {
    return "success";
  }
  if (status === "rejected") {
    return "danger";
  }
  return null;
}

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    sows.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listSows(context.orgId, {
      projectId: context.projectId || undefined,
      status: statusFilter.value || undefined,
    });
    sows.value = res.sows;
  } catch (err) {
    sows.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgId, context.projectId, statusFilter.value], () => void refresh(), {
  immediate: true,
});

const hasProjectFilter = computed(() => Boolean(context.projectId));
</script>

<template>
  <div>
    <h1 class="page-title">Statements of Work</h1>
    <p class="muted">Review and sign SoWs assigned to you.</p>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>

    <div v-else class="card">
      <div class="header">
        <div>
          <div class="muted">Assigned SoWs</div>
          <div v-if="hasProjectFilter" class="muted meta">Project filter enabled</div>
        </div>
      </div>

      <div class="filters">
        <label class="field">
          <span class="label">Status</span>
          <select v-model="statusFilter" class="pf-v6-c-form-control">
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="pending_signature">Pending signature</option>
            <option value="signed">Signed</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>
      </div>

      <div v-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="sows.length === 0" class="muted">No assigned SoWs.</div>

      <ul v-else class="list">
        <li v-for="row in sows" :key="row.sow.id" class="row">
          <div class="main">
            <RouterLink class="name" :to="`/client/sows/${row.sow.id}`">
              SoW v{{ row.version.version }}
            </RouterLink>
            <div class="meta-row">
              <VlLabel :color="statusColor(row.version.status)" variant="filled">
                {{ statusLabel(row.version.status) }}
              </VlLabel>
              <VlLabel>Project: {{ projectName(row.sow.project_id) }}</VlLabel>
              <VlLabel>Updated {{ formatTimestamp(row.sow.updated_at) }}</VlLabel>
              <VlLabel v-if="row.pdf">PDF: {{ row.pdf.status }}</VlLabel>
            </div>
          </div>
          <RouterLink
            class="pf-v6-c-button pf-m-link pf-m-inline pf-m-small"
            :to="`/client/sows/${row.sow.id}`"
          >
            Open
          </RouterLink>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 220px;
}

.label {
  font-size: 0.85rem;
  color: var(--muted);
}

.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  border: 1px solid var(--pf-t--global--border--color--default);
  border-radius: 12px;
  padding: 0.75rem;
  background: var(--pf-t--global--background--color--secondary--default);
}

.main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.name {
  font-weight: 600;
  color: var(--pf-t--global--text--color--regular);
  text-decoration: none;
}

.name:hover {
  text-decoration: underline;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--pf-t--global--spacer--xs);
}
</style>
