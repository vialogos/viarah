<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { GitLabIntegrationSettings, GitLabIntegrationValidationResult } from "../api/types";
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
  <div>
    <h1 class="page-title">GitLab Integration</h1>
    <p class="muted">
      Configure the org’s GitLab base URL + personal access token. Tokens are write-only and are never shown after save.
    </p>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>

    <div v-else class="card">
      <div v-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!canEdit" class="muted">Not permitted.</div>
      <div v-else>
        <div class="status">
          <div class="status-row">
            <span class="muted">Token configured</span>
            <span>{{ integration?.has_token ? "Yes" : "No" }}</span>
          </div>
          <div class="status-row">
            <span class="muted">Token last set</span>
            <span>{{ formatTimestamp(integration?.token_set_at ?? null) }}</span>
          </div>
        </div>

        <label class="field">
          <span class="label">Base URL</span>
          <input
            v-model="baseUrlDraft"
            type="url"
            placeholder="https://gitlab.com"
            :disabled="saving || validating"
          />
        </label>

        <label class="field">
          <span class="label">Personal access token (write-only)</span>
          <input
            v-model="tokenDraft"
            type="password"
            autocomplete="new-password"
            placeholder="Paste a GitLab PAT…"
            :disabled="saving || validating"
          />
          <span class="muted hint">Leave blank to keep the existing token. Use “Clear token” to remove it.</span>
        </label>

        <div class="actions">
          <button type="button" :disabled="saving || validating" @click="save">
            {{ saving ? "Saving…" : "Save" }}
          </button>
          <button type="button" :disabled="saving || validating || !integration?.has_token" @click="clearToken">
            Clear token
          </button>
          <button type="button" :disabled="saving || validating" @click="validateToken">
            {{ validating ? "Validating…" : "Validate" }}
          </button>
        </div>

        <div v-if="validationSummary" class="card validation">
          <div class="validation-title">{{ validationSummary.title }}</div>
          <div class="muted">{{ validationSummary.detail }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.field {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.label {
  font-size: 0.9rem;
  color: var(--muted);
}

.hint {
  font-size: 0.9rem;
}

.actions {
  margin-top: 0.9rem;
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.status {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.35rem;
  margin-bottom: 0.25rem;
}

.status-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.validation {
  margin-top: 0.75rem;
  border-color: #c7d2fe;
  background: #eef2ff;
}

.validation-title {
  font-weight: 700;
}
</style>

