<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { ReportRunScope, ReportRunSummary, Template } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const templates = ref<Template[]>([]);
const reportRuns = ref<ReportRunSummary[]>([]);

const loadingTemplates = ref(false);
const loadingRuns = ref(false);
const loadingError = ref("");

const creating = ref(false);
const createError = ref("");

const selectedTemplateId = ref("");
const scopeFromDate = ref("");
const scopeToDate = ref("");
const scopeStatuses = ref<string[]>([]);

const STATUS_OPTIONS = [
  { value: "backlog", label: "Backlog" },
  { value: "in_progress", label: "In progress" },
  { value: "qa", label: "QA" },
  { value: "done", label: "Done" },
] as const;

const templateNameById = computed(() => {
  const map: Record<string, string> = {};
  for (const t of templates.value) {
    map[t.id] = t.name;
  }
  return map;
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refreshTemplates() {
  if (!context.orgId) {
    templates.value = [];
    return;
  }

  loadingTemplates.value = true;
  loadingError.value = "";
  try {
    const res = await api.listTemplates(context.orgId, { type: "report" });
    templates.value = res.templates;

    if (selectedTemplateId.value && !templates.value.some((t) => t.id === selectedTemplateId.value)) {
      selectedTemplateId.value = "";
    }
  } catch (err) {
    templates.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    loadingError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingTemplates.value = false;
  }
}

async function refreshRuns() {
  if (!context.orgId || !context.projectId) {
    reportRuns.value = [];
    return;
  }

  loadingRuns.value = true;
  loadingError.value = "";
  try {
    const res = await api.listReportRuns(context.orgId, { projectId: context.projectId });
    reportRuns.value = res.report_runs;
  } catch (err) {
    reportRuns.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    loadingError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingRuns.value = false;
  }
}

function refreshAll() {
  void refreshTemplates();
  void refreshRuns();
}

function scopeSummary(scope: Record<string, unknown>): string {
  const parts: string[] = [];
  const from = typeof scope.from_date === "string" ? scope.from_date : "";
  const to = typeof scope.to_date === "string" ? scope.to_date : "";
  const statuses = Array.isArray(scope.statuses) ? scope.statuses.filter((s) => typeof s === "string") : [];

  if (from) {
    parts.push(`from ${from}`);
  }
  if (to) {
    parts.push(`to ${to}`);
  }
  if (statuses.length > 0) {
    parts.push(`statuses: ${statuses.join(", ")}`);
  }

  return parts.length > 0 ? parts.join(" • ") : "—";
}

async function createReportRun() {
  createError.value = "";

  if (!context.orgId || !context.projectId) {
    createError.value = "Select an org and project first.";
    return;
  }

  if (!selectedTemplateId.value) {
    createError.value = "Select a template.";
    return;
  }

  const scope: ReportRunScope = {};
  if (scopeFromDate.value) {
    scope.from_date = scopeFromDate.value;
  }
  if (scopeToDate.value) {
    scope.to_date = scopeToDate.value;
  }
  if (scopeStatuses.value.length > 0) {
    scope.statuses = [...scopeStatuses.value];
  }

  creating.value = true;
  try {
    const res = await api.createReportRun(context.orgId, {
      project_id: context.projectId,
      template_id: selectedTemplateId.value,
      scope,
    });

    await router.push({ path: `/outputs/${res.report_run.id}` });
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
  () => [context.orgId, context.projectId],
  () => {
    void refreshTemplates();
    void refreshRuns();
  },
  { immediate: true }
);
</script>

<template>
  <div class="stack">
    <div class="card">
      <div class="header">
        <div>
          <h1 class="page-title">Outputs</h1>
          <div class="muted">Generate report runs (web + PDF) and manage expiring share links.</div>
        </div>
        <button type="button" :disabled="loadingTemplates || loadingRuns" @click="refreshAll">
          Refresh
        </button>
      </div>

      <p v-if="!context.orgId || !context.projectId" class="muted">
        Select an org and project to view outputs.
      </p>
      <p v-else-if="loadingRuns" class="muted">Loading report runs…</p>
      <p v-if="loadingError" class="error">{{ loadingError }}</p>

      <pf-table v-if="reportRuns.length > 0" aria-label="Report runs list">
        <pf-thead>
          <pf-tr>
            <pf-th>Created</pf-th>
            <pf-th>Template</pf-th>
            <pf-th class="muted">Scope</pf-th>
          </pf-tr>
        </pf-thead>
        <pf-tbody>
          <pf-tr v-for="r in reportRuns" :key="r.id">
            <pf-td data-label="Created">
              <RouterLink :to="`/outputs/${r.id}`">{{ formatTimestamp(r.created_at) }}</RouterLink>
            </pf-td>
            <pf-td data-label="Template">
              {{ templateNameById[r.template_id] || r.template_id }}
            </pf-td>
            <pf-td class="muted" data-label="Scope">
              {{ scopeSummary(r.scope) }}
            </pf-td>
          </pf-tr>
        </pf-tbody>
      </pf-table>

      <p v-else-if="context.orgId && context.projectId && !loadingRuns" class="muted">No report runs yet.</p>
    </div>

    <div class="card">
      <h2 class="section-title">Create report run</h2>
      <p class="muted small">At minimum, this sends `scope: {}`. Optional filters are passed to the backend.</p>

      <label class="block">
        Report template
        <select v-model="selectedTemplateId" :disabled="!context.orgId || loadingTemplates">
          <option value="">Select…</option>
          <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
      </label>

      <div class="form-grid">
        <label>
          From date (optional)
          <input v-model="scopeFromDate" type="date" />
        </label>
        <label>
          To date (optional)
          <input v-model="scopeToDate" type="date" />
        </label>
      </div>

      <div class="block">
        <div class="muted small" style="margin-bottom: 0.25rem">Statuses (optional)</div>
        <div class="status-grid">
          <label v-for="opt in STATUS_OPTIONS" :key="opt.value" class="status-option">
            <input v-model="scopeStatuses" type="checkbox" :value="opt.value" />
            {{ opt.label }}
          </label>
        </div>
      </div>

      <div class="actions">
        <button type="button" :disabled="creating || !context.orgId || !context.projectId" @click="createReportRun">
          {{ creating ? "Creating…" : "Create run" }}
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

.section-title {
  margin: 0 0 0.25rem 0;
  font-size: 1rem;
}

.small {
  font-size: 0.9rem;
}

.block {
  display: block;
  margin: 0.75rem 0;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.35rem 0.75rem;
}

.status-option {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
</style>
