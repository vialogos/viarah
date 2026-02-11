<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Template, TemplateVersionSummary } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const props = defineProps<{ templateId: string }>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const template = ref<Template | null>(null);
const currentVersionBody = ref<string | null>(null);
const versions = ref<TemplateVersionSummary[]>([]);
const loading = ref(false);
const error = ref("");

const saving = ref(false);
const saveError = ref("");
const bodyDraft = ref("");

const sortedVersions = computed(() =>
  [...versions.value].sort((a, b) => (b.version ?? 0) - (a.version ?? 0))
);

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    template.value = null;
    currentVersionBody.value = null;
    versions.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.getTemplate(context.orgId, props.templateId);
    template.value = res.template;
    currentVersionBody.value = res.current_version_body;
    versions.value = res.versions;
    bodyDraft.value = res.current_version_body ?? "";
  } catch (err) {
    template.value = null;
    currentVersionBody.value = null;
    versions.value = [];

    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function createNewVersion() {
  saveError.value = "";
  if (!context.orgId) {
    saveError.value = "Select an org first.";
    return;
  }

  if (!bodyDraft.value.trim()) {
    saveError.value = "Body is required.";
    return;
  }

  saving.value = true;
  try {
    await api.createTemplateVersion(context.orgId, props.templateId, bodyDraft.value);
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    saveError.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}

watch(() => [context.orgId, props.templateId], refresh, { immediate: true });
</script>

<template>
  <div class="stack">
    <div class="card">
      <div class="top">
        <div>
          <h1 class="page-title">Template</h1>
          <div v-if="template" class="muted">
            {{ template.type }} • updated {{ formatTimestamp(template.updated_at) }}
          </div>
        </div>
        <RouterLink to="/templates">← Back</RouterLink>
      </div>

      <p v-if="!context.orgId" class="muted">Select an org to view this template.</p>
      <p v-else-if="loading" class="muted">Loading…</p>
      <p v-if="error" class="error">{{ error }}</p>

      <div v-if="template && !loading" class="meta">
        <div><span class="muted">Name:</span> {{ template.name }}</div>
        <div v-if="template.description"><span class="muted">Description:</span> {{ template.description }}</div>
        <div><span class="muted">Current version id:</span> {{ template.current_version_id || "—" }}</div>
      </div>
    </div>

    <div v-if="template && !loading" class="card">
      <h2 class="section-title">Current body</h2>
      <pre class="body">{{ currentVersionBody || "—" }}</pre>
    </div>

    <div v-if="template && !loading" class="card">
      <h2 class="section-title">Create new version</h2>
      <p class="muted small">Edits create a new version. Prior versions remain visible.</p>

      <pf-textarea v-model="bodyDraft" rows="10" spellcheck="false" />
      <div class="actions">
        <button type="button" :disabled="saving" @click="createNewVersion">
          {{ saving ? "Saving…" : "Create new version" }}
        </button>
        <div v-if="saveError" class="error">{{ saveError }}</div>
      </div>
    </div>

    <div v-if="template && !loading" class="card">
      <h2 class="section-title">Version history</h2>
      <pf-table v-if="sortedVersions.length > 0" aria-label="Template version history">
        <pf-thead>
          <pf-tr>
            <pf-th>Version</pf-th>
            <pf-th class="muted">Created</pf-th>
            <pf-th class="muted">Created by</pf-th>
          </pf-tr>
        </pf-thead>
        <pf-tbody>
          <pf-tr v-for="v in sortedVersions" :key="v.id">
            <pf-td data-label="Version">{{ v.version }}</pf-td>
            <pf-td class="muted" data-label="Created">{{ formatTimestamp(v.created_at) }}</pf-td>
            <pf-td class="muted" data-label="Created by">{{ v.created_by_user_id }}</pf-td>
          </pf-tr>
        </pf-tbody>
      </pf-table>
      <p v-else class="muted">No versions.</p>
    </div>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.meta {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.75rem;
}

.section-title {
  margin: 0 0 0.5rem 0;
  font-size: 1rem;
}

.small {
  font-size: 0.9rem;
}

.body {
  white-space: pre-wrap;
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem;
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

</style>
