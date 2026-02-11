<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type {
  ReportRunDetail,
  ReportRunPdfRenderLog,
  ShareLink,
  ShareLinkAccessLog,
} from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const props = defineProps<{ runId: string }>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const run = ref<ReportRunDetail | null>(null);
const renderLogs = ref<ReportRunPdfRenderLog[]>([]);
const shareLinks = ref<ShareLink[]>([]);

const loading = ref(false);
const error = ref("");

const requestingPdf = ref(false);
const pdfError = ref("");

const publishing = ref(false);
const publishError = ref("");
const publishExpiresAtLocal = ref("");

const publishedShareUrl = ref<string | null>(null);
const clipboardStatus = ref("");

const revokingShareLinkId = ref("");

const accessLogsByShareLinkId = ref<Record<string, ShareLinkAccessLog[]>>({});
const accessLogsErrorByShareLinkId = ref<Record<string, string>>({});
const accessLogsLoadingId = ref("");
const accessLogsOpen = ref<Record<string, boolean>>({});

const sortedRenderLogs = computed(() => {
  const parsed = [...renderLogs.value];
  parsed.sort((a, b) => {
    const aTime = new Date(a.created_at).getTime();
    const bTime = new Date(b.created_at).getTime();
    return (Number.isNaN(bTime) ? 0 : bTime) - (Number.isNaN(aTime) ? 0 : aTime);
  });
  return parsed;
});

const latestRenderLog = computed(() => sortedRenderLogs.value[0] ?? null);

const canDownloadPdf = computed(() => {
  const status = latestRenderLog.value?.status ?? "";
  return status === "success";
});

const pdfDownloadUrl = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return api.reportRunPdfDownloadUrl(context.orgId, props.runId);
});

function isTerminalStatus(status: string): boolean {
  return status === "success" || status === "failed";
}

let renderLogPollHandle: number | null = null;
function stopPollingRenderLogs() {
  if (renderLogPollHandle == null) {
    return;
  }
  window.clearInterval(renderLogPollHandle);
  renderLogPollHandle = null;
}

function startPollingRenderLogs() {
  stopPollingRenderLogs();
  renderLogPollHandle = window.setInterval(() => {
    void safeRefreshRenderLogs();
  }, 3000);
}

onUnmounted(() => {
  stopPollingRenderLogs();
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refreshRun() {
  if (!context.orgId) {
    run.value = null;
    return;
  }

  const res = await api.getReportRun(context.orgId, props.runId);
  run.value = res.report_run;
}

async function refreshRenderLogs() {
  if (!context.orgId) {
    renderLogs.value = [];
    return;
  }

  const res = await api.listReportRunRenderLogs(context.orgId, props.runId);
  renderLogs.value = res.render_logs;
}

async function safeRefreshRenderLogs() {
  pdfError.value = "";
  try {
    await refreshRenderLogs();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    pdfError.value = err instanceof Error ? err.message : String(err);
  }
}

async function refreshShareLinks() {
  if (!context.orgId) {
    shareLinks.value = [];
    return;
  }

  const res = await api.listShareLinks(context.orgId, { reportRunId: props.runId });
  shareLinks.value = res.share_links;
}

async function safeRefreshShareLinks() {
  publishError.value = "";
  try {
    await refreshShareLinks();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    publishError.value = err instanceof Error ? err.message : String(err);
  }
}

async function refreshAll() {
  error.value = "";

  if (!context.orgId) {
    run.value = null;
    renderLogs.value = [];
    shareLinks.value = [];
    return;
  }

  loading.value = true;
  try {
    await Promise.all([refreshRun(), refreshRenderLogs(), refreshShareLinks()]);
  } catch (err) {
    run.value = null;
    renderLogs.value = [];
    shareLinks.value = [];

    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function requestPdfRender() {
  pdfError.value = "";
  if (!context.orgId) {
    pdfError.value = "Select an org first.";
    return;
  }

  requestingPdf.value = true;
  try {
    await api.requestReportRunPdf(context.orgId, props.runId);
    await refreshRenderLogs();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    pdfError.value = err instanceof Error ? err.message : String(err);
  } finally {
    requestingPdf.value = false;
  }
}

function expiresAtIsoOrNull(): string | null {
  const value = publishExpiresAtLocal.value.trim();
  if (!value) {
    return null;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date.toISOString();
}

async function publishShareLink() {
  publishError.value = "";
  clipboardStatus.value = "";
  publishedShareUrl.value = null;

  if (!context.orgId) {
    publishError.value = "Select an org first.";
    return;
  }

  publishing.value = true;
  try {
    const expiresAt = expiresAtIsoOrNull();
    const res = await api.publishReportRun(context.orgId, props.runId, expiresAt ? { expires_at: expiresAt } : {});
    publishedShareUrl.value = res.share_url;
    await refreshShareLinks();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    publishError.value = err instanceof Error ? err.message : String(err);
  } finally {
    publishing.value = false;
  }
}

async function revokeShareLink(shareLinkId: string) {
  publishError.value = "";
  if (!context.orgId) {
    publishError.value = "Select an org first.";
    return;
  }

  revokingShareLinkId.value = shareLinkId;
  try {
    await api.revokeShareLink(context.orgId, shareLinkId);
    await refreshShareLinks();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    publishError.value = err instanceof Error ? err.message : String(err);
  } finally {
    revokingShareLinkId.value = "";
  }
}

async function copyPublishedUrl() {
  clipboardStatus.value = "";
  const url = publishedShareUrl.value;
  if (!url) {
    return;
  }

  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
      clipboardStatus.value = "Copied.";
      return;
    }
    throw new Error("Clipboard API unavailable");
  } catch {
    clipboardStatus.value = "Copy failed; select and copy manually.";
  }
}

function dismissPublishedUrl() {
  publishedShareUrl.value = null;
  clipboardStatus.value = "";
}

async function toggleAccessLogs(shareLinkId: string) {
  const next = !accessLogsOpen.value[shareLinkId];
  accessLogsOpen.value = { ...accessLogsOpen.value, [shareLinkId]: next };
  if (!next) {
    return;
  }

  if (accessLogsByShareLinkId.value[shareLinkId]) {
    return;
  }

  if (!context.orgId) {
    accessLogsErrorByShareLinkId.value = {
      ...accessLogsErrorByShareLinkId.value,
      [shareLinkId]: "Select an org first.",
    };
    return;
  }

  accessLogsLoadingId.value = shareLinkId;
  accessLogsErrorByShareLinkId.value = { ...accessLogsErrorByShareLinkId.value, [shareLinkId]: "" };
  try {
    const res = await api.listShareLinkAccessLogs(context.orgId, shareLinkId);
    accessLogsByShareLinkId.value = { ...accessLogsByShareLinkId.value, [shareLinkId]: res.access_logs };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    accessLogsErrorByShareLinkId.value = {
      ...accessLogsErrorByShareLinkId.value,
      [shareLinkId]: err instanceof Error ? err.message : String(err),
    };
  } finally {
    accessLogsLoadingId.value = "";
  }
}

watch(() => [context.orgId, props.runId], refreshAll, { immediate: true });

watch(
  () => latestRenderLog.value?.status ?? "",
  (status) => {
    if (!status) {
      stopPollingRenderLogs();
      return;
    }
    if (isTerminalStatus(status)) {
      stopPollingRenderLogs();
      return;
    }
    startPollingRenderLogs();
  },
  { immediate: true }
);
</script>

<template>
  <div class="stack">
    <div class="card">
      <div class="top">
        <div>
          <h1 class="page-title">Report run</h1>
          <div v-if="run" class="muted">created {{ formatTimestamp(run.created_at) }}</div>
        </div>
        <RouterLink to="/outputs">← Back</RouterLink>
      </div>

      <p v-if="!context.orgId" class="muted">Select an org to view this report run.</p>
      <p v-else-if="loading" class="muted">Loading…</p>
      <p v-if="error" class="error">{{ error }}</p>

      <div v-if="run && !loading" class="meta">
        <div><span class="muted">Project:</span> {{ run.project_id }}</div>
        <div><span class="muted">Template:</span> {{ run.template_id }}</div>
        <div class="muted">Run id: {{ run.id }}</div>
      </div>
    </div>

    <div v-if="publishedShareUrl" class="card token-card">
      <h2 class="section-title">Share URL (shown once)</h2>
      <p class="muted small">
        Copy this URL now. For security, it will not be shown again after you close this panel.
      </p>
      <div class="token-row">
        <input class="token-input" :value="publishedShareUrl" readonly />
        <button type="button" @click="copyPublishedUrl">Copy</button>
        <button type="button" @click="dismissPublishedUrl">Close</button>
      </div>
      <div v-if="clipboardStatus" class="muted small">{{ clipboardStatus }}</div>
    </div>

    <div v-if="run && !loading" class="card">
      <h2 class="section-title">Web output</h2>
      <!-- Backend provides sanitized HTML output for rendering. -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div v-if="run.output_html" class="output" v-html="run.output_html" />
      <p v-else class="muted">No output HTML stored.</p>
    </div>

    <div v-if="run && !loading" class="card">
      <h2 class="section-title">PDF</h2>
      <p class="muted small">
        PDF rendering is async. Request a render, then wait for status to become <code>success</code>.
      </p>

      <div class="actions">
        <button type="button" :disabled="requestingPdf" @click="requestPdfRender">
          {{ requestingPdf ? "Requesting…" : "Render PDF" }}
        </button>
        <a
          v-if="canDownloadPdf && pdfDownloadUrl"
          class="button-link"
          :href="pdfDownloadUrl"
          target="_blank"
          rel="noopener"
        >
          Download PDF
        </a>
        <button type="button" :disabled="!context.orgId" @click="safeRefreshRenderLogs">Refresh status</button>
      </div>

      <div v-if="pdfError" class="error">{{ pdfError }}</div>

      <div v-if="latestRenderLog" class="status">
        <div><span class="muted">Latest status:</span> {{ latestRenderLog.status }}</div>
        <div v-if="latestRenderLog.error_message" class="error">{{ latestRenderLog.error_message }}</div>
      </div>

      <details v-if="sortedRenderLogs.length > 0" class="details">
        <summary class="muted">Render logs ({{ sortedRenderLogs.length }})</summary>
        <pf-table aria-label="Report render logs">
          <pf-thead>
            <pf-tr>
              <pf-th>Status</pf-th>
              <pf-th class="muted">Created</pf-th>
              <pf-th class="muted">Started</pf-th>
              <pf-th class="muted">Completed</pf-th>
              <pf-th class="muted">Error</pf-th>
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="l in sortedRenderLogs" :key="l.id">
              <pf-td data-label="Status">{{ l.status }}</pf-td>
              <pf-td class="muted" data-label="Created">{{ formatTimestamp(l.created_at) }}</pf-td>
              <pf-td class="muted" data-label="Started">{{ formatTimestamp(l.started_at) }}</pf-td>
              <pf-td class="muted" data-label="Completed">{{ formatTimestamp(l.completed_at) }}</pf-td>
              <pf-td class="muted" data-label="Error">{{ l.error_code || "—" }}</pf-td>
            </pf-tr>
          </pf-tbody>
        </pf-table>
      </details>
    </div>

    <div v-if="run && !loading" class="card">
      <h2 class="section-title">Share links</h2>
      <p class="muted small">
        Tokens are shown only at publish time. This list never exposes tokenized URLs.
      </p>

      <div class="publish-row">
        <label class="publish-field">
          Expires at (optional)
          <input v-model="publishExpiresAtLocal" type="datetime-local" />
        </label>
        <button type="button" :disabled="publishing" @click="publishShareLink">
          {{ publishing ? "Publishing…" : "Publish" }}
        </button>
        <button type="button" :disabled="!context.orgId" @click="safeRefreshShareLinks">Refresh</button>
      </div>
      <div v-if="publishError" class="error">{{ publishError }}</div>

      <pf-table v-if="shareLinks.length > 0" aria-label="Share links table">
        <pf-thead>
          <pf-tr>
            <pf-th class="muted">Created</pf-th>
            <pf-th class="muted">Expires</pf-th>
            <pf-th class="muted">Revoked</pf-th>
            <pf-th class="muted">Accesses</pf-th>
            <pf-th class="muted">Last access</pf-th>
            <pf-th>Actions</pf-th>
          </pf-tr>
        </pf-thead>
        <pf-tbody>
          <template v-for="sl in shareLinks" :key="sl.id">
            <pf-tr>
              <pf-td class="muted" data-label="Created">{{ formatTimestamp(sl.created_at) }}</pf-td>
              <pf-td class="muted" data-label="Expires">{{ formatTimestamp(sl.expires_at) }}</pf-td>
              <pf-td class="muted" data-label="Revoked">{{ formatTimestamp(sl.revoked_at) }}</pf-td>
              <pf-td class="muted" data-label="Accesses">{{ sl.access_count }}</pf-td>
              <pf-td class="muted" data-label="Last access">{{ formatTimestamp(sl.last_access_at) }}</pf-td>
              <pf-td class="actions-cell" data-label="Actions">
                <button
                  type="button"
                  :disabled="Boolean(sl.revoked_at) || revokingShareLinkId === sl.id"
                  @click="revokeShareLink(sl.id)"
                >
                  {{ revokingShareLinkId === sl.id ? "Revoking…" : "Revoke" }}
                </button>
                <button type="button" @click="toggleAccessLogs(sl.id)">
                  {{ accessLogsOpen[sl.id] ? "Hide logs" : "Access logs" }}
                </button>
              </pf-td>
            </pf-tr>
            <pf-tr v-if="accessLogsOpen[sl.id]">
              <pf-td :colspan="6" class="logs-cell">
                <div class="muted small" style="margin-bottom: 0.5rem">
                  Share link id: {{ sl.id }} • Created by:
                  {{ sl.created_by?.display || sl.created_by?.id || "—" }}
                </div>
                <p v-if="accessLogsLoadingId === sl.id" class="muted">Loading access logs…</p>
                <p v-if="accessLogsErrorByShareLinkId[sl.id]" class="error">
                  {{ accessLogsErrorByShareLinkId[sl.id] }}
                </p>
                <pf-table
                  v-if="(accessLogsByShareLinkId[sl.id]?.length ?? 0) > 0"
                  aria-label="Share link access logs"
                  compact
                >
                  <pf-thead>
                    <pf-tr>
                      <pf-th class="muted">Accessed</pf-th>
                      <pf-th class="muted">IP</pf-th>
                      <pf-th class="muted">User agent</pf-th>
                    </pf-tr>
                  </pf-thead>
                  <pf-tbody>
                    <pf-tr
                      v-for="log in accessLogsByShareLinkId[sl.id] || []"
                      :key="log.accessed_at + log.ip_address"
                    >
                      <pf-td class="muted" data-label="Accessed">
                        {{ formatTimestamp(log.accessed_at) }}
                      </pf-td>
                      <pf-td class="muted" data-label="IP">
                        {{ log.ip_address || "—" }}
                      </pf-td>
                      <pf-td class="muted" data-label="User agent">
                        {{ log.user_agent || "—" }}
                      </pf-td>
                    </pf-tr>
                  </pf-tbody>
                </pf-table>
                <p
                  v-else-if="accessLogsByShareLinkId[sl.id] && (accessLogsByShareLinkId[sl.id]?.length ?? 0) === 0"
                  class="muted"
                >
                  No access logs yet.
                </p>
              </pf-td>
            </pf-tr>
          </template>
        </pf-tbody>
      </pf-table>

      <p v-else class="muted">No share links yet.</p>
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

.output {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem;
  background: #ffffff;
}

.token-card {
  border-color: #dbeafe;
  background: #eff6ff;
}

.token-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.token-input {
  flex: 1;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.75rem 0;
}

.button-link {
  display: inline-flex;
  align-items: center;
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 0.5rem 0.85rem;
  background: var(--panel);
  color: var(--text);
  text-decoration: none;
}

.button-link:hover {
  text-decoration: none;
  border-color: #cbd5e1;
}

.status {
  margin-top: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.details {
  margin-top: 0.75rem;
}

.publish-row {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  margin: 0.75rem 0;
  flex-wrap: wrap;
}

.publish-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.actions-cell {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.logs-cell {
  background: #f8fafc;
}
</style>
