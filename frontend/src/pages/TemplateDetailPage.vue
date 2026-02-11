<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { Template, TemplateVersionSummary } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
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
    <pf-button variant="link" to="/templates">Back</pf-button>

    <pf-card>
      <pf-card-title>
        <div class="top">
          <div>
            <pf-title h="1" size="2xl">Template</pf-title>
            <VlLabel v-if="template" color="blue">
              {{ template.type }} • updated {{ formatTimestamp(template.updated_at) }}
            </VlLabel>
          </div>
        </div>
      </pf-card-title>

      <pf-card-body>
        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to view this template.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading template" />
        </div>
        <pf-alert v-else-if="error" inline variant="danger" :title="error" />

        <pf-description-list v-else-if="template" class="meta" horizontal compact>
          <pf-description-list-group>
            <pf-description-list-term>Name</pf-description-list-term>
            <pf-description-list-description>{{ template.name }}</pf-description-list-description>
          </pf-description-list-group>
          <pf-description-list-group v-if="template.description">
            <pf-description-list-term>Description</pf-description-list-term>
            <pf-description-list-description>{{ template.description }}</pf-description-list-description>
          </pf-description-list-group>
          <pf-description-list-group>
            <pf-description-list-term>Current version id</pf-description-list-term>
            <pf-description-list-description>{{ template.current_version_id || "—" }}</pf-description-list-description>
          </pf-description-list-group>
        </pf-description-list>

        <pf-empty-state v-else>
          <pf-empty-state-header title="Not found" heading-level="h2" />
          <pf-empty-state-body>This template does not exist or is not accessible.</pf-empty-state-body>
        </pf-empty-state>
      </pf-card-body>
    </pf-card>

    <pf-card v-if="template && !loading">
      <pf-card-body>
        <pf-title h="2" size="lg">Current body</pf-title>
        <pre class="body">{{ currentVersionBody || "—" }}</pre>
      </pf-card-body>
    </pf-card>

    <pf-card v-if="template && !loading">
      <pf-card-body>
        <pf-title h="2" size="lg">Create new version</pf-title>
        <pf-content>
          <p class="muted small">Edits create a new version. Prior versions remain visible.</p>
        </pf-content>

        <pf-textarea v-model="bodyDraft" rows="10" spellcheck="false" />
        <div class="actions">
          <pf-button variant="primary" :disabled="saving" @click="createNewVersion">
            {{ saving ? "Saving…" : "Create new version" }}
          </pf-button>
        </div>
        <pf-alert v-if="saveError" inline variant="danger" :title="saveError" />
      </pf-card-body>
    </pf-card>

    <pf-card v-if="template && !loading">
      <pf-card-body>
        <pf-title h="2" size="lg">Version history</pf-title>
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
        <pf-empty-state v-else>
          <pf-empty-state-header title="No versions" heading-level="h3" />
          <pf-empty-state-body>No versions were found for this template.</pf-empty-state-body>
        </pf-empty-state>
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

.top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.meta {
  margin-top: 0.75rem;
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
  margin-top: 0.75rem;
}

</style>
