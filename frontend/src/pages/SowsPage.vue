<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { SoWListItem, SoWVersionStatus } from "../api/types";
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

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManage = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const projectName = computed(() => {
  if (!context.projectId) {
    return "";
  }
  return context.projects.find((p) => p.id === context.projectId)?.name ?? "";
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function signerSummary(item: SoWListItem): string {
  const counts = { pending: 0, approved: 0, rejected: 0 };
  for (const signer of item.signers) {
    if (signer.status === "approved") {
      counts.approved += 1;
    } else if (signer.status === "rejected") {
      counts.rejected += 1;
    } else {
      counts.pending += 1;
    }
  }

  const total = item.signers.length;
  const parts: string[] = [];
  if (counts.approved) {
    parts.push(`${counts.approved} approved`);
  }
  if (counts.pending) {
    parts.push(`${counts.pending} pending`);
  }
  if (counts.rejected) {
    parts.push(`${counts.rejected} rejected`);
  }
  return total ? parts.join(", ") : "—";
}

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    sows.value = [];
    return;
  }

  if (!canManage.value) {
    sows.value = [];
    error.value = "Only PM/admin can view SoWs for this org.";
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
</script>

<template>
  <div>
    <h1 class="page-title">Statements of Work</h1>
    <p class="muted">Draft, send for signature, and track signer status and PDFs.</p>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>

    <div v-else class="card">
      <div class="header">
        <div>
          <div class="muted">Org SoWs</div>
          <div v-if="projectName" class="muted meta">Project: {{ projectName }}</div>
        </div>
        <RouterLink v-if="canManage" class="button-link" to="/sows/new">New SoW</RouterLink>
      </div>

      <div class="filters">
        <label class="field">
          <span class="label">Status</span>
          <select v-model="statusFilter">
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
      <div v-else-if="sows.length === 0" class="muted">No SoWs yet.</div>

      <ul v-else class="list">
        <li v-for="row in sows" :key="row.sow.id" class="row">
          <div class="main">
            <RouterLink class="name" :to="`/sows/${row.sow.id}`">
              SoW v{{ row.version.version }}
            </RouterLink>
            <div class="muted meta">
              <span class="chip">{{ row.version.status }}</span>
              <span class="chip">Updated {{ formatTimestamp(row.sow.updated_at) }}</span>
              <span class="chip">Signers: {{ signerSummary(row) }}</span>
              <span v-if="row.pdf" class="chip">PDF: {{ row.pdf.status }}</span>
            </div>
          </div>
          <RouterLink class="muted" :to="`/sows/${row.sow.id}`">Open</RouterLink>
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

.button-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 0.5rem 0.85rem;
  background: var(--panel);
  color: var(--text);
  text-decoration: none;
}

.button-link:hover {
  border-color: #cbd5e1;
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
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem;
  background: #fbfbfd;
}

.main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.name {
  font-weight: 600;
  color: var(--text);
  text-decoration: none;
}

.name:hover {
  text-decoration: underline;
}

.meta {
  font-size: 0.9rem;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.85rem;
  padding: 0.1rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #f8fafc;
  margin-right: 0.5rem;
  margin-top: 0.25rem;
}
</style>
