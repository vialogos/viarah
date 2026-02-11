<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { GitLabIntegrationSettings, GitLabIntegrationValidationResult } from "../api/types";
import VlLabel from "../components/VlLabel.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const integration = ref<GitLabIntegrationSettings | null>(null);
const baseUrlDraft = ref("");
const tokenDraft = ref("");
const loading = ref(false);
const saving = ref(false);
const validating = ref(false);
const error = ref("");
const validation = ref<GitLabIntegrationValidationResult | null>(null);

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

function describeValidation(result: GitLabIntegrationValidationResult): { title: string; detail: string } {
  const code = result.error_code;

  if (result.status === "valid") {
    return { title: "Valid", detail: "GitLab accepted the token." };
  }
  if (result.status === "invalid") {
    return { title: "Invalid", detail: "GitLab rejected the token (auth error)." };
  }

  if (code === "missing_integration") {
    return { title: "Not validated", detail: "GitLab integration is not configured yet." };
  }
  if (code === "missing_token") {
    return { title: "Not validated", detail: "No GitLab token is configured yet." };
  }
  if (code === "rate_limited") {
    return { title: "Not validated", detail: "GitLab rate limited the request; try again later." };
  }
  if (code === "network_error") {
    return { title: "Not validated", detail: "Unable to reach GitLab; check the base URL and network." };
  }
  if (code === "encryption_key_missing" || code === "encryption_key_invalid" || code === "invalid_token_ciphertext") {
    return { title: "Not validated", detail: "Server encryption is misconfigured; contact an administrator." };
  }
  if (code && code.startsWith("http_")) {
    return { title: "Not validated", detail: `Unexpected GitLab response (${code.replace("http_", "HTTP ")}).` };
  }

  return { title: "Not validated", detail: code ? `Validation failed (${code}).` : "Validation not available." };
}

async function refresh() {
  error.value = "";
  validation.value = null;
  tokenDraft.value = "";

  if (!context.orgId) {
    integration.value = null;
    baseUrlDraft.value = "";
    return;
  }

  loading.value = true;
  try {
    const res = await api.getOrgGitLabIntegration(context.orgId);
    integration.value = res.gitlab;
    baseUrlDraft.value = res.gitlab.base_url ?? "";
  } catch (err) {
    integration.value = null;
    baseUrlDraft.value = "";
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

watch(() => context.orgId, () => void refresh(), { immediate: true });

async function save() {
  error.value = "";
  validation.value = null;

  if (!context.orgId) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  const nextBaseUrl = baseUrlDraft.value.trim();
  if (!nextBaseUrl) {
    error.value = "Base URL is required.";
    return;
  }

  const payload: { base_url: string; token?: string } = { base_url: nextBaseUrl };
  const nextToken = tokenDraft.value.trim();
  if (nextToken) {
    payload.token = nextToken;
  }

  saving.value = true;
  try {
    const res = await api.patchOrgGitLabIntegration(context.orgId, payload);
    integration.value = res.gitlab;
    baseUrlDraft.value = res.gitlab.base_url ?? "";
    tokenDraft.value = "";
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
    saving.value = false;
  }
}

async function clearToken() {
  error.value = "";
  validation.value = null;

  if (!context.orgId) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  saving.value = true;
  try {
    const res = await api.patchOrgGitLabIntegration(context.orgId, { token: "" });
    integration.value = res.gitlab;
    tokenDraft.value = "";
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
    saving.value = false;
  }
}

async function validateToken() {
  error.value = "";
  if (!context.orgId) {
    return;
  }
  if (!canEdit.value) {
    error.value = "Not permitted.";
    return;
  }

  validating.value = true;
  try {
    validation.value = await api.validateOrgGitLabIntegration(context.orgId);
  } catch (err) {
    validation.value = null;
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
    validating.value = false;
  }
}

const validationSummary = computed(() => (validation.value ? describeValidation(validation.value) : null));
</script>

<template>
  <pf-card>
    <pf-card-title>
      <pf-title h="1" size="2xl">GitLab Integration</pf-title>
    </pf-card-title>

    <pf-card-body>
      <pf-content>
        <p class="muted">
          Configure the org’s GitLab base URL + personal access token. Tokens are write-only and are never shown after save.
        </p>
      </pf-content>

      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading GitLab integration settings" />
      </div>
      <pf-alert v-else-if="error" inline variant="danger" :title="error" />
      <pf-empty-state v-else-if="!canEdit">
        <pf-empty-state-header title="Not permitted" heading-level="h2" />
        <pf-empty-state-body>Only PM/admin can manage GitLab integration settings.</pf-empty-state-body>
      </pf-empty-state>
      <div v-else>
        <pf-description-list class="status" columns="2Col">
          <pf-description-list-group>
            <pf-description-list-term>Token configured</pf-description-list-term>
            <pf-description-list-description>
              <VlLabel :color="integration?.has_token ? 'green' : 'orange'">
                {{ integration?.has_token ? "Yes" : "No" }}
              </VlLabel>
            </pf-description-list-description>
          </pf-description-list-group>
          <pf-description-list-group>
            <pf-description-list-term>Token last set</pf-description-list-term>
            <pf-description-list-description>
              <VlLabel color="blue">{{ formatTimestamp(integration?.token_set_at ?? null) }}</VlLabel>
            </pf-description-list-description>
          </pf-description-list-group>
        </pf-description-list>

        <pf-form class="form" @submit.prevent="save">
          <pf-form-group label="Base URL" field-id="gitlab-base-url">
            <pf-text-input
              id="gitlab-base-url"
              v-model="baseUrlDraft"
              type="url"
              placeholder="https://gitlab.com"
              :disabled="saving || validating"
              required
            />
          </pf-form-group>

          <pf-form-group label="Personal access token (write-only)" field-id="gitlab-token">
            <pf-text-input
              id="gitlab-token"
              v-model="tokenDraft"
              type="password"
              autocomplete="new-password"
              placeholder="Paste a GitLab PAT…"
              :disabled="saving || validating"
            />
            <pf-helper-text>
              <pf-helper-text-item>
                Leave blank to keep the existing token. Use “Clear token” to remove it.
              </pf-helper-text-item>
            </pf-helper-text>
          </pf-form-group>

          <div class="actions">
            <pf-button type="submit" variant="primary" :disabled="saving || validating">
              {{ saving ? "Saving…" : "Save" }}
            </pf-button>
            <pf-button
              type="button"
              variant="secondary"
              :disabled="saving || validating || !integration?.has_token"
              @click="clearToken"
            >
              Clear token
            </pf-button>
            <pf-button type="button" variant="secondary" :disabled="saving || validating" @click="validateToken">
              {{ validating ? "Validating…" : "Validate" }}
            </pf-button>
          </div>
        </pf-form>

        <pf-alert
          v-if="validationSummary"
          inline
          :variant="validation?.status === 'valid' ? 'success' : validation?.status === 'invalid' ? 'danger' : 'warning'"
          :title="validationSummary.title"
        >
          {{ validationSummary.detail }}
        </pf-alert>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.actions {
  margin-top: 0.9rem;
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.status {
  margin-bottom: 0.25rem;
}
</style>
