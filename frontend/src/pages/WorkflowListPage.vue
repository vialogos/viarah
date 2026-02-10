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
  <div>
    <h1 class="page-title">Workflows</h1>
    <p class="muted">Configure workflow stage ordering and flags for an org.</p>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>

    <div v-else class="card">
      <div class="header">
        <div class="muted">Org workflows</div>
        <RouterLink v-if="canEdit" class="pf-v6-c-button pf-m-primary pf-m-small" to="/settings/workflows/new">
          Create workflow
        </RouterLink>
      </div>

      <div v-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="workflows.length === 0" class="muted">No workflows yet.</div>

      <ul v-else class="list">
        <li v-for="workflow in workflows" :key="workflow.id" class="row">
          <div class="main">
            <RouterLink class="name" :to="`/settings/workflows/${workflow.id}`">
              {{ workflow.name }}
            </RouterLink>
            <div class="meta-row">
              <VlLabel>Updated {{ formatTimestamp(workflow.updated_at) }}</VlLabel>
            </div>
          </div>
          <RouterLink
            class="pf-v6-c-button pf-m-link pf-m-inline pf-m-small"
            :to="`/settings/workflows/${workflow.id}`"
          >
            Open
          </RouterLink>
        </li>
      </ul>

      <p v-if="!canEdit" class="muted note">
        You can view workflows, but only PM/admin can create or edit them.
      </p>
    </div>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pf-t--global--spacer--md);
  margin-bottom: var(--pf-t--global--spacer--sm);
}

.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--pf-t--global--spacer--xs);
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pf-t--global--spacer--md);
  border: 1px solid var(--pf-t--global--border--color--default);
  border-radius: 12px;
  padding: var(--pf-t--global--spacer--sm);
  background: var(--pf-t--global--background--color--secondary--default);
}

.main {
  display: flex;
  flex-direction: column;
  gap: var(--pf-t--global--spacer--xs);
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

.note {
  margin-top: 0.75rem;
}
</style>
