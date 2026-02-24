<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Client, Project } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const props = defineProps<{ clientId: string }>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const loading = ref(false);
const error = ref("");

const client = ref<Client | null>(null);
const projects = ref<Project[]>([]);

const linkedProjects = computed(() =>
  projects.value.filter((project) => project.client_id === props.clientId).sort((a, b) => a.name.localeCompare(b.name))
);

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    client.value = null;
    projects.value = [];
    return;
  }

  loading.value = true;
  try {
    const [clientRes, projectsRes] = await Promise.all([
      api.getClient(context.orgId, props.clientId),
      api.listProjects(context.orgId),
    ]);
    client.value = clientRes.client;
    projects.value = projectsRes.projects;
  } catch (err) {
    client.value = null;
    projects.value = [];

    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgId, props.clientId], refresh, { immediate: true });
</script>

<template>
  <div class="stack">
    <pf-button variant="link" to="/clients">Back</pf-button>

    <pf-card>
      <pf-card-title>
        <div class="header">
          <div>
            <pf-title h="1" size="2xl">{{ client?.name || "Client" }}</pf-title>
            <VlLabel v-if="client" color="blue" variant="outline">Updated {{ formatTimestamp(client.updated_at) }}</VlLabel>
          </div>
        </div>
      </pf-card-title>
      <pf-card-body>
        <pf-alert v-if="error" inline variant="danger" :title="error" />

        <pf-empty-state v-else-if="!context.orgId" variant="small">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to view this client.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading client" />
        </div>

        <div v-else-if="client" class="client-body">
          <div class="notes">
            <div class="label">Notes</div>
            <div class="value">{{ client.notes || "—" }}</div>
          </div>
        </div>
      </pf-card-body>
    </pf-card>

    <pf-card>
      <pf-card-title>
        <div class="section-title">
          <pf-title h="2" size="xl">Projects</pf-title>
          <VlLabel v-if="linkedProjects.length" color="blue" variant="outline">{{ linkedProjects.length }}</VlLabel>
        </div>
      </pf-card-title>
      <pf-card-body>
        <pf-empty-state v-if="!linkedProjects.length" variant="small">
          <pf-empty-state-header title="No linked projects" heading-level="h3" />
          <pf-empty-state-body>
            Link a project to this client from Project settings (client field).
          </pf-empty-state-body>
        </pf-empty-state>

        <pf-table v-else aria-label="Client linked projects">
          <pf-thead>
            <pf-tr>
              <pf-th>Project</pf-th>
              <pf-th>Updated</pf-th>
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="project in linkedProjects" :key="project.id">
              <pf-td data-label="Project">{{ project.name }}</pf-td>
              <pf-td data-label="Updated">{{ formatTimestamp(project.updated_at) }}</pf-td>
            </pf-tr>
          </pf-tbody>
        </pf-table>
      </pf-card-body>
    </pf-card>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 1rem 0;
}

.label {
  font-size: 0.85rem;
  color: var(--pf-v6-global--Color--200);
}

.value {
  margin-top: 0.25rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
</style>

