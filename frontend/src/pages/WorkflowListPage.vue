<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Workflow } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const workflows = ref<Workflow[]>([]);
const loading = ref(false);
const error = ref("");

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
    workflows.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listWorkflows(context.orgId);
    workflows.value = res.workflows;
  } catch (err) {
    workflows.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => context.orgId, () => void refresh(), { immediate: true });
</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <div>
          <pf-title h="1" size="2xl">Workflows</pf-title>
          <pf-content>
            <p class="muted">Configure workflow stage ordering and flags for an org.</p>
          </pf-content>
        </div>
        <pf-button v-if="canEdit" variant="primary" to="/settings/workflows/new">Create workflow</pf-button>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading workflows" />
      </div>
      <pf-alert v-else-if="error" inline variant="danger" :title="error" />
      <pf-empty-state v-else-if="workflows.length === 0">
        <pf-empty-state-header title="No workflows yet" heading-level="h2" />
        <pf-empty-state-body>Create one to define stage ordering for this org.</pf-empty-state-body>
      </pf-empty-state>

      <pf-data-list v-else compact aria-label="Workflows">
        <pf-data-list-item v-for="workflow in workflows" :key="workflow.id">
          <pf-data-list-cell>
            <RouterLink class="name" :to="`/settings/workflows/${workflow.id}`">
              {{ workflow.name }}
            </RouterLink>
            <div class="meta">
              <VlLabel color="blue">Updated {{ formatTimestamp(workflow.updated_at) }}</VlLabel>
            </div>
          </pf-data-list-cell>
          <pf-data-list-cell align-right>
            <pf-button variant="link" :to="`/settings/workflows/${workflow.id}`">Open</pf-button>
          </pf-data-list-cell>
        </pf-data-list-item>
      </pf-data-list>

      <pf-helper-text v-if="!canEdit" class="note">
        <pf-helper-text-item>
          You can view workflows, but only PM/admin can create or edit them.
        </pf-helper-text-item>
      </pf-helper-text>
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

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.meta {
  display: flex;
  gap: 0.5rem;
}

.name {
  font-weight: 600;
  color: var(--text);
  text-decoration: none;
}

.name:hover {
  text-decoration: underline;
}

.note {
  margin-top: 0.75rem;
}
</style>
