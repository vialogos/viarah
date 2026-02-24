<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Template, TemplateType } from "../api/types";
import { useContextStore } from "../stores/context";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const realtime = useRealtimeStore();

const templateType = ref<TemplateType>("report");

const templates = ref<Template[]>([]);
const loading = ref(false);
const creating = ref(false);
const error = ref("");
const createError = ref("");

const newName = ref("");
const newDescription = ref("");
const newBody = ref("");

const canLoad = computed(() => Boolean(context.orgId));

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refreshTemplates() {
  error.value = "";

  if (!context.orgId) {
    templates.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listTemplates(context.orgId, { type: templateType.value });
    templates.value = res.templates;
  } catch (err) {
    templates.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

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
    void refreshTemplates();
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
  if (!eventType.startsWith("template.")) {
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

async function createTemplate() {
  createError.value = "";
  if (!context.orgId) {
    createError.value = "Select an org first.";
    return;
  }

  if (!newName.value.trim()) {
    createError.value = "Name is required.";
    return;
  }

  if (!newBody.value.trim()) {
    createError.value = "Body is required.";
    return;
  }

  creating.value = true;
  try {
    const res = await api.createTemplate(context.orgId, {
      type: templateType.value,
      name: newName.value.trim(),
      description: newDescription.value.trim() ? newDescription.value.trim() : undefined,
      body: newBody.value,
    });

    newName.value = "";
    newDescription.value = "";
    newBody.value = "";

    await router.push({ path: `/templates/${res.template.id}` });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    createError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creating.value = false;
  }
}

watch(
  () => [context.orgId, templateType.value],
  () => {
    void refreshTemplates();
  },
  { immediate: true }
);
</script>

<template>
  <div class="stack">
    <pf-card>
      <pf-card-title>
        <div class="header">
          <div>
            <pf-title h="1" size="2xl">Templates</pf-title>
            <pf-content>
              <p class="muted">Create and manage report/SoW templates (edits create new versions).</p>
            </pf-content>
          </div>

          <div class="controls">
            <pf-form-group label="Type" field-id="template-type" class="type-field">
              <pf-form-select id="template-type" v-model="templateType">
                <pf-form-select-option value="report">Report</pf-form-select-option>
                <pf-form-select-option value="sow">SoW</pf-form-select-option>
              </pf-form-select>
            </pf-form-group>

            <pf-button variant="secondary" :disabled="!canLoad || loading" @click="refreshTemplates">
              Refresh
            </pf-button>
          </div>
        </div>
      </pf-card-title>

      <pf-card-body>
        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to view templates.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading templates" />
        </div>
        <pf-alert v-else-if="error" inline variant="danger" :title="error" />

        <pf-table v-else-if="templates.length > 0" aria-label="Templates list">
          <pf-thead>
            <pf-tr>
              <pf-th>Name</pf-th>
              <pf-th class="muted">Updated</pf-th>
              <pf-th class="muted">Current Version</pf-th>
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="t in templates" :key="t.id">
              <pf-td data-label="Name">
                <RouterLink :to="`/templates/${t.id}`">{{ t.name }}</RouterLink>
                <div v-if="t.description" class="muted small">{{ t.description }}</div>
              </pf-td>
              <pf-td class="muted" data-label="Updated">
                {{ formatTimestamp(t.updated_at) }}
              </pf-td>
              <pf-td class="muted" data-label="Current Version">
                {{ t.current_version_id ? "Yes" : "—" }}
              </pf-td>
            </pf-tr>
          </pf-tbody>
        </pf-table>

        <pf-empty-state v-else>
          <pf-empty-state-header title="No templates yet" heading-level="h2" />
          <pf-empty-state-body>Create a template to start generating reports and SoWs.</pf-empty-state-body>
        </pf-empty-state>
      </pf-card-body>
    </pf-card>

    <pf-card>
      <pf-card-body>
        <pf-title h="2" size="lg">Create template</pf-title>
        <pf-content>
          <p class="muted small">
            Note: editing a template creates a new version; template metadata edits (rename/delete) are not in
            scope for v1.
          </p>
        </pf-content>

        <pf-form class="create-form">
          <div class="form-grid">
            <pf-form-group label="Name" field-id="template-name">
              <pf-text-input
                id="template-name"
                v-model="newName"
                type="text"
                placeholder="Weekly update"
              />
            </pf-form-group>
            <pf-form-group label="Description (optional)" field-id="template-description">
              <pf-text-input
                id="template-description"
                v-model="newDescription"
                type="text"
                placeholder="Internal note…"
              />
            </pf-form-group>
          </div>

          <pf-form-group label="Body" field-id="template-body">
            <pf-textarea id="template-body" v-model="newBody" rows="10" spellcheck="false" />
          </pf-form-group>
        </pf-form>

        <div class="actions">
          <pf-button variant="primary" :disabled="!context.orgId || creating" @click="createTemplate">
            {{ creating ? "Creating…" : "Create" }}
          </pf-button>
        </div>
        <pf-alert v-if="createError" inline variant="danger" :title="createError" />
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
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.controls {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
}

.type-field {
  margin: 0;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.small {
  font-size: 0.9rem;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.create-form {
  margin-top: 0.75rem;
}

.actions {
  margin-top: 0.75rem;
}
</style>
