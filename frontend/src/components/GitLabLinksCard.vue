<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { GitLabLink } from "../api/types";
import VlLabel from "./VlLabel.vue";
import VlLabelGroup from "./VlLabelGroup.vue";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import type { VlLabelColor } from "../utils/labels";

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

function gitLabTypeLabelColor(type: string): VlLabelColor {
  return type === "mr" ? "purple" : "teal";
}

function gitLabStateLabelColor(state: string): VlLabelColor {
  const normalized = state.trim().toLowerCase();
  if (normalized === "merged" || normalized === "resolved") {
    return "green";
  }
  if (normalized === "closed") {
    return "red";
  }
  if (normalized === "locked") {
    return "orange";
  }
  return "blue";
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

function syncLabelColor(link: GitLabLink): VlLabelColor {
  if (link.sync.rate_limited) {
    return "orange";
  }
  if (link.sync.status === "ok") {
    return "green";
  }
  if (link.sync.status === "stale") {
    return "orange";
  }
  if (link.sync.status === "error") {
    return "red";
  }
  return "blue";
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
  <pf-card class="gitlab-links">
    <pf-card-title>
      <pf-title h="2" size="lg">GitLab links</pf-title>
    </pf-card-title>

    <pf-card-body>
      <pf-content>
        <p class="muted">Attach GitLab Issues/MRs. Metadata is refreshed server-side and cached.</p>
      </pf-content>

      <pf-empty-state v-if="!orgId">
        <pf-empty-state-header title="Select an org" heading-level="h3" />
        <pf-empty-state-body>Select an org to view GitLab links.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading GitLab links" />
      </div>

      <pf-alert v-else-if="error" inline variant="danger" :title="error" />

      <div v-else>
        <pf-empty-state v-if="links.length === 0">
          <pf-empty-state-header title="No GitLab links" heading-level="h3" />
          <pf-empty-state-body>Attach an Issue or MR to sync metadata.</pf-empty-state-body>
        </pf-empty-state>

        <pf-data-list v-else compact aria-label="GitLab links">
          <pf-data-list-item v-for="link in links" :key="link.id" class="link-row">
            <pf-data-list-cell>
              <a class="link-title" :href="link.url" target="_blank" rel="noopener noreferrer">
                {{ link.cached_title || link.url }}
              </a>
              <div v-if="link.cached_title" class="muted link-url">{{ link.url }}</div>

              <VlLabelGroup class="labels" :num-labels="5">
                <VlLabel :color="gitLabTypeLabelColor(link.gitlab_type)">
                  {{ link.gitlab_type === "mr" ? "MR" : "Issue" }} #{{ link.gitlab_iid }}
                </VlLabel>
                <VlLabel v-if="link.cached_state" :color="gitLabStateLabelColor(link.cached_state)">
                  {{ link.cached_state }}
                </VlLabel>
                <VlLabel :color="syncLabelColor(link)">{{ syncLabel(link) }}</VlLabel>
                <VlLabel v-if="link.sync.error_code" color="red" variant="filled">
                  {{ describeErrorCode(link.sync.error_code) }}
                </VlLabel>
              </VlLabelGroup>

              <pf-description-list class="meta" horizontal compact>
                <pf-description-list-group>
                  <pf-description-list-term>Assignees</pf-description-list-term>
                  <pf-description-list-description>
                    <VlLabelGroup v-if="link.cached_assignees.length" :num-labels="3">
                      <VlLabel v-for="assignee in link.cached_assignees" :key="assignee.username || assignee.name">
                        {{ assignee.username || assignee.name }}
                      </VlLabel>
                    </VlLabelGroup>
                    <span v-else class="muted">—</span>
                  </pf-description-list-description>
                </pf-description-list-group>

                <pf-description-list-group>
                  <pf-description-list-term>Labels</pf-description-list-term>
                  <pf-description-list-description>
                    <VlLabelGroup v-if="link.cached_labels.length" :num-labels="6">
                      <VlLabel v-for="label in link.cached_labels" :key="label">{{ label }}</VlLabel>
                    </VlLabelGroup>
                    <span v-else class="muted">—</span>
                  </pf-description-list-description>
                </pf-description-list-group>

                <pf-description-list-group>
                  <pf-description-list-term>Last synced</pf-description-list-term>
                  <pf-description-list-description>
                    <VlLabel color="blue">{{ formatTimestamp(link.last_synced_at) }}</VlLabel>
                  </pf-description-list-description>
                </pf-description-list-group>
              </pf-description-list>
            </pf-data-list-cell>

            <pf-data-list-cell v-if="canManageLinks" align-right>
              <pf-button
                variant="danger"
                small
                :disabled="deletingId === link.id"
                @click="deleteLink(link.id)"
              >
                {{ deletingId === link.id ? "Deleting…" : "Delete" }}
              </pf-button>
            </pf-data-list-cell>
          </pf-data-list-item>
        </pf-data-list>

        <pf-form v-if="canManageLinks" class="add-row" @submit.prevent="addLink">
          <pf-form-group label="GitLab URL" field-id="gitlab-link-url" class="grow">
            <pf-text-input
              id="gitlab-link-url"
              v-model="urlDraft"
              type="url"
              placeholder="Paste a GitLab Issue or MR URL…"
              :disabled="adding"
            />
          </pf-form-group>
          <pf-button type="submit" :disabled="adding || !urlDraft.trim()">
            {{ adding ? "Adding…" : "Add link" }}
          </pf-button>
        </pf-form>

        <pf-alert v-else inline variant="warning" title="Not permitted." />

        <pf-helper-text v-if="canManageIntegration && (hasIntegrationProblem || links.length === 0)" class="note">
          <pf-helper-text-item>
            Manage base URL + token in
            <RouterLink to="/settings/integrations/gitlab">GitLab Integration Settings</RouterLink>.
          </pf-helper-text-item>
        </pf-helper-text>
        <pf-helper-text v-else-if="!canManageIntegration && hasIntegrationProblem" class="note">
          <pf-helper-text-item>GitLab integration must be configured by an admin/PM.</pf-helper-text-item>
        </pf-helper-text>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.5rem 0;
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

.labels {
  margin-top: 0.35rem;
}

.meta {
  margin-top: 0.35rem;
  font-size: 0.9rem;
  color: var(--muted);
}

.add-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: end;
  margin-top: 0.9rem;
}

.grow {
  flex: 1;
  min-width: 280px;
}

.note {
  margin-top: 0.75rem;
}

</style>
