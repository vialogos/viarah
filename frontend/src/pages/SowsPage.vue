<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { SoWListItem, SoWVersionStatus } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { sowPdfStatusLabelColor, sowVersionStatusLabelColor } from "../utils/labels";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const sows = ref<SoWListItem[]>([]);
const loading = ref(false);
const error = ref("");

const statusFilter = ref<SoWVersionStatus | "">("");

const currentRole = computed(() => {
  return session.effectiveOrgRole(context.orgId);
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
  <pf-card>
    <pf-card-title>
      <div class="header">
        <div>
          <pf-title h="1" size="2xl">Statements of Work</pf-title>
          <pf-content>
            <p class="muted">Draft, send for signature, and track signer status and PDFs.</p>
          </pf-content>
        </div>
        <pf-button v-if="canManage" variant="primary" to="/sows/new">New SoW</pf-button>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
      </pf-empty-state>

      <pf-empty-state v-else-if="!canManage">
        <pf-empty-state-header title="Not permitted" heading-level="h2" />
        <pf-empty-state-body>Only PM/admin can view SoWs for this org.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else>
        <pf-toolbar class="toolbar">
          <pf-toolbar-content>
            <pf-toolbar-group>
              <pf-toolbar-item>
                <pf-form-group label="Status" field-id="sows-status-filter" class="filter-field">
                  <pf-form-select id="sows-status-filter" v-model="statusFilter">
                    <pf-form-select-option value="">All</pf-form-select-option>
                    <pf-form-select-option value="draft">Draft</pf-form-select-option>
                    <pf-form-select-option value="pending_signature">Pending signature</pf-form-select-option>
                    <pf-form-select-option value="signed">Signed</pf-form-select-option>
                    <pf-form-select-option value="rejected">Rejected</pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>
              </pf-toolbar-item>
              <pf-toolbar-item v-if="projectName">
                <VlLabel color="teal">Project: {{ projectName }}</VlLabel>
              </pf-toolbar-item>
            </pf-toolbar-group>
          </pf-toolbar-content>
        </pf-toolbar>

        <div v-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading statements of work" />
        </div>
        <pf-alert v-else-if="error" inline variant="danger" :title="error" />
        <pf-empty-state v-else-if="sows.length === 0">
          <pf-empty-state-header title="No SoWs yet" heading-level="h2" />
          <pf-empty-state-body>Create a new SoW to start the signature workflow.</pf-empty-state-body>
        </pf-empty-state>

        <pf-data-list v-else compact aria-label="Statements of work">
          <pf-data-list-item v-for="row in sows" :key="row.sow.id">
            <pf-data-list-cell>
              <RouterLink class="name" :to="`/sows/${row.sow.id}`">
                SoW v{{ row.version.version }}
              </RouterLink>
              <div class="muted meta labels">
                <VlLabel :color="sowVersionStatusLabelColor(row.version.status)">{{ row.version.status }}</VlLabel>
                <VlLabel color="blue">Updated {{ formatTimestamp(row.sow.updated_at) }}</VlLabel>
                <VlLabel color="blue">Signers: {{ signerSummary(row) }}</VlLabel>
                <VlLabel v-if="row.pdf" :color="sowPdfStatusLabelColor(row.pdf.status)">PDF: {{ row.pdf.status }}</VlLabel>
              </div>
            </pf-data-list-cell>
            <pf-data-list-cell align-right>
              <pf-button variant="link" :to="`/sows/${row.sow.id}`">Open</pf-button>
            </pf-data-list-cell>
          </pf-data-list-item>
        </pf-data-list>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.toolbar {
  margin-bottom: 0.75rem;
}

.filter-field {
  margin: 0;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
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

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
