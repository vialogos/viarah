<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Template, TemplateType } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

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
    <div class="card">
      <div class="header">
        <div>
          <h1 class="page-title">Templates</h1>
          <div class="muted">Create and manage report/SoW templates (edits create new versions).</div>
        </div>

        <div class="controls">
          <label class="muted">
            Type
            <select v-model="templateType">
              <option value="report">Report</option>
              <option value="sow">SoW</option>
            </select>
          </label>

          <button type="button" :disabled="!canLoad || loading" @click="refreshTemplates">
            Refresh
          </button>
        </div>
      </div>

      <p v-if="!context.orgId" class="muted">Select an org to view templates.</p>
      <p v-else-if="loading" class="muted">Loading templates…</p>
      <p v-if="error" class="error">{{ error }}</p>

      <pf-table v-if="templates.length > 0" aria-label="Templates list">
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

      <p v-else-if="canLoad && !loading" class="muted">No templates yet.</p>
    </div>

    <div class="card">
      <h2 class="section-title">Create template</h2>
      <p class="muted small">
        Note: editing a template creates a new version; template metadata edits (rename/delete) are not in
        scope for v1.
      </p>

      <div class="form-grid">
        <label>
          Name
          <input v-model="newName" type="text" placeholder="Weekly update" />
        </label>
        <label>
          Description (optional)
          <input v-model="newDescription" type="text" placeholder="Internal note…" />
        </label>
      </div>

      <label class="block">
        Body
        <textarea v-model="newBody" rows="10" spellcheck="false" />
      </label>

      <div class="actions">
        <button type="button" :disabled="!context.orgId || creating" @click="createTemplate">
          {{ creating ? "Creating…" : "Create" }}
        </button>
        <div v-if="createError" class="error">{{ createError }}</div>
      </div>
    </div>
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

.section-title {
  margin: 0 0 0.25rem 0;
  font-size: 1rem;
}

.small {
  font-size: 0.9rem;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  margin: 0.75rem 0;
}

.block {
  display: block;
  margin: 0.75rem 0;
}

textarea {
  width: 100%;
  border-radius: 12px;
  border: 1px solid var(--border);
  padding: 0.75rem;
  font: inherit;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
</style>
