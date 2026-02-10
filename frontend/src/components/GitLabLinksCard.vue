<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import VlLabel from "./VlLabel.vue";
import type { GitLabLink } from "../api/types";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const props = defineProps<{
  orgId: string | null;
  taskId: string;
  canManageIntegration: boolean;
  canManageLinks: boolean;
}>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const links = ref<GitLabLink[]>([]);
const loading = ref(false);
const error = ref("");
const urlDraft = ref("");
const adding = ref(false);
const deletingId = ref("");

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function describeErrorCode(code: string | null): string {
  if (!code) {
    return "";
  }
  if (code === "missing_integration") {
    return "Integration not configured";
  }
  if (code === "missing_token") {
    return "Token missing";
  }
  if (code === "auth_error") {
    return "Auth error";
  }
  if (code === "rate_limited") {
    return "Rate limited";
  }
  if (code === "network_error") {
    return "Network error";
  }
  if (code === "not_found") {
    return "Not found";
  }
  if (code === "encryption_key_missing" || code === "encryption_key_invalid" || code === "invalid_token_ciphertext") {
    return "Server config error";
  }
  if (code.startsWith("http_")) {
    return code.replace("http_", "HTTP ");
  }
  return code;
}

function syncLabel(link: GitLabLink): string {
  if (link.sync.rate_limited && link.sync.rate_limited_until) {
    return `Rate limited until ${formatTimestamp(link.sync.rate_limited_until)}`;
  }
  if (link.sync.status === "ok") {
    return "Synced";
  }
  if (link.sync.status === "stale") {
    return "Stale (refresh queued)";
  }
  if (link.sync.status === "never") {
    return "Sync pending";
  }
  if (link.sync.status === "error") {
    return "Sync error";
  }
  return link.sync.status;
}

function syncColor(link: GitLabLink): "success" | "warning" | "danger" | "info" | null {
  if (link.sync.rate_limited) {
    return "warning";
  }
  if (link.sync.status === "ok") {
    return "success";
  }
  if (link.sync.status === "stale") {
    return "warning";
  }
  if (link.sync.status === "never") {
    return "info";
  }
  if (link.sync.status === "error") {
    return "danger";
  }
  return null;
}

function stateColor(state: string | null | undefined): "success" | "warning" | "danger" | "info" | null {
  const normalized = (state ?? "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (normalized.includes("merged") || normalized.includes("closed")) {
    return "success";
  }
  if (normalized.includes("open")) {
    return "info";
  }
  return null;
}

function assigneeNames(link: GitLabLink): string[] {
  return link.cached_assignees
    .map((assignee) => assignee.username || assignee.name)
    .filter((value): value is string => Boolean(value));
}

const hasIntegrationProblem = computed(() =>
  links.value.some(
    (link) => link.sync.error_code === "missing_integration" || link.sync.error_code === "missing_token"
  )
);

async function refresh() {
  error.value = "";
  if (!props.orgId) {
    links.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listTaskGitLabLinks(props.orgId, props.taskId);
    links.value = res.links;
  } catch (err) {
    links.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Not permitted.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [props.orgId, props.taskId], () => void refresh(), { immediate: true });

async function addLink() {
  error.value = "";
  if (!props.orgId || !props.canManageLinks) {
    return;
  }
  const url = urlDraft.value.trim();
  if (!url) {
    return;
  }

  adding.value = true;
  try {
    const res = await api.createTaskGitLabLink(props.orgId, props.taskId, url);
    urlDraft.value = "";
    links.value = [...links.value, res.link];
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Not permitted.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    adding.value = false;
  }
}

async function deleteLink(linkId: string) {
  error.value = "";
  if (!props.orgId || !props.canManageLinks) {
    return;
  }

  deletingId.value = linkId;
  try {
    await api.deleteTaskGitLabLink(props.orgId, props.taskId, linkId);
    links.value = links.value.filter((l) => l.id !== linkId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Not permitted.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    deletingId.value = "";
  }
}
</script>

<template>
  <div class="card">
    <h2 class="section-title">GitLab links</h2>
    <p class="muted">Attach GitLab Issues/MRs. Metadata is refreshed server-side and cached.</p>

    <div v-if="!orgId" class="muted">Select an org to view GitLab links.</div>
    <div v-else-if="loading" class="muted">Loading GitLab links…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="links.length === 0" class="muted">No GitLab links yet.</div>

      <div v-else class="link-list">
        <div v-for="link in links" :key="link.id" class="link-row">
          <div class="link-main">
            <a class="link-title" :href="link.url" target="_blank" rel="noopener noreferrer">
              {{ link.cached_title || link.url }}
            </a>
            <div v-if="link.cached_title" class="muted link-url">{{ link.url }}</div>

            <div class="chips">
              <VlLabel color="info" variant="outline">
                {{ link.gitlab_type === "mr" ? "MR" : "Issue" }} #{{ link.gitlab_iid }}
              </VlLabel>
              <VlLabel v-if="link.cached_state" :color="stateColor(link.cached_state)" variant="outline">
                {{ link.cached_state }}
              </VlLabel>
              <VlLabel :color="syncColor(link)" variant="outline">{{ syncLabel(link) }}</VlLabel>
              <VlLabel v-if="link.sync.error_code" color="danger" variant="filled">
                {{ describeErrorCode(link.sync.error_code) }}
              </VlLabel>
            </div>

            <div class="link-meta">
              <div class="link-meta-row">
                <span class="muted meta-label">Assignees</span>
                <div class="meta-chips">
                  <template v-if="assigneeNames(link).length">
                    <VlLabel
                      v-for="(name, idx) in assigneeNames(link).slice(0, 3)"
                      :key="`${link.id}-assignee-${idx}`"
                      variant="outline"
                    >
                      {{ name }}
                    </VlLabel>
                    <VlLabel v-if="assigneeNames(link).length > 3" variant="outline">
                      +{{ assigneeNames(link).length - 3 }}
                    </VlLabel>
                  </template>
                  <span v-else class="muted">—</span>
                </div>
              </div>

              <div class="link-meta-row">
                <span class="muted meta-label">Labels</span>
                <div class="meta-chips">
                  <template v-if="link.cached_labels.length">
                    <VlLabel
                      v-for="label in link.cached_labels.slice(0, 6)"
                      :key="`${link.id}-label-${label}`"
                      variant="outline"
                    >
                      {{ label }}
                    </VlLabel>
                    <VlLabel v-if="link.cached_labels.length > 6" variant="outline">
                      +{{ link.cached_labels.length - 6 }}
                    </VlLabel>
                  </template>
                  <span v-else class="muted">—</span>
                </div>
              </div>

              <div class="link-meta-row">
                <span class="muted meta-label">Last synced</span>
                <VlLabel variant="outline">{{ formatTimestamp(link.last_synced_at) }}</VlLabel>
              </div>
            </div>
          </div>

          <button
            type="button"
            class="pf-v6-c-button pf-m-secondary pf-m-danger pf-m-small"
            :disabled="deletingId === link.id"
            @click="deleteLink(link.id)"
          >
            {{ deletingId === link.id ? "Deleting…" : "Delete" }}
          </button>
        </div>
      </div>

      <div v-if="canManageLinks" class="add-row">
        <input
          v-model="urlDraft"
          class="pf-v6-c-form-control grow"
          type="url"
          placeholder="Paste a GitLab Issue or MR URL…"
          :disabled="adding"
        />
        <button
          type="button"
          class="pf-v6-c-button pf-m-primary pf-m-small"
          :disabled="adding || !urlDraft.trim()"
          @click="addLink"
        >
          {{ adding ? "Adding…" : "Add link" }}
        </button>
      </div>

      <div v-else class="muted">Not permitted.</div>

      <p v-if="canManageIntegration && (hasIntegrationProblem || links.length === 0)" class="muted note">
        Manage base URL + token in
        <RouterLink to="/settings/integrations/gitlab">GitLab Integration Settings</RouterLink>.
      </p>
      <p v-else-if="!canManageIntegration && hasIntegrationProblem" class="muted note">
        GitLab integration must be configured by an admin/PM.
      </p>
    </div>
  </div>
</template>

<style scoped>
.card {
}

.section-title {
  margin: 0 0 0.35rem 0;
  font-size: 1.1rem;
}

.link-list {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.link-row {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.75rem;
  align-items: start;
}

.link-main {
  min-width: 0;
}

.link-title {
  font-weight: 700;
  word-break: break-word;
}

.link-url {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
  font-size: 0.9rem;
  word-break: break-word;
}

.chips {
  margin-top: 0.35rem;
  display: flex;
  flex-wrap: wrap;
  gap: var(--pf-t--global--spacer--xs);
}

.link-meta {
  margin-top: 0.35rem;
  display: flex;
  flex-direction: column;
  gap: var(--pf-t--global--spacer--xs);
}

.link-meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--pf-t--global--spacer--xs);
}

.meta-label {
  min-width: 90px;
}

.meta-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--pf-t--global--spacer--xs);
}

.meta {
  font-size: 0.9rem;
}

.add-row {
  margin-top: 0.9rem;
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}

.grow {
  flex: 1;
  min-width: 280px;
}

.note {
  margin-top: 0.75rem;
}

@media (max-width: 720px) {
  .link-row {
    grid-template-columns: 1fr;
  }
}
</style>
