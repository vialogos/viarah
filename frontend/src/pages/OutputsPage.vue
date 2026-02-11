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

function statusEnabled(value: string): boolean {
  return scopeStatuses.value.includes(value);
}

function setStatusEnabled(value: string, enabled: boolean) {
  if (enabled) {
    scopeStatuses.value = Array.from(new Set([...scopeStatuses.value, value]));
    return;
  }
  scopeStatuses.value = scopeStatuses.value.filter((item) => item !== value);
}

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
    <pf-card>
      <pf-card-title>
        <div class="header">
          <div>
            <pf-title h="1" size="2xl">Outputs</pf-title>
            <pf-content>
              <p class="muted">Generate report runs (web + PDF) and manage expiring share links.</p>
            </pf-content>
          </div>
          <pf-button variant="secondary" :disabled="loadingTemplates || loadingRuns" @click="refreshAll">
            Refresh
          </pf-button>
        </div>
      </pf-card-title>

      <pf-card-body>
        <pf-empty-state v-if="!context.orgId || !context.projectId">
          <pf-empty-state-header title="Select an org and project" heading-level="h2" />
          <pf-empty-state-body>Select an org and project to view outputs.</pf-empty-state-body>
        </pf-empty-state>
        <div v-else-if="loadingRuns" class="loading-row">
          <pf-spinner size="md" aria-label="Loading report runs" />
        </div>
        <pf-alert v-else-if="loadingError" inline variant="danger" :title="loadingError" />

        <pf-table v-else-if="reportRuns.length > 0" aria-label="Report runs list">
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

        <pf-empty-state v-else>
          <pf-empty-state-header title="No report runs yet" heading-level="h2" />
          <pf-empty-state-body>Create a run to generate web output and PDFs.</pf-empty-state-body>
        </pf-empty-state>
      </pf-card-body>
    </pf-card>

    <pf-card>
      <pf-card-body>
        <pf-title h="2" size="lg">Create report run</pf-title>
        <pf-content>
          <p class="muted small">At minimum, this sends <code>scope: {}</code>. Optional filters are passed to the backend.</p>
        </pf-content>

        <pf-form class="create-form">
          <pf-form-group label="Report template" field-id="report-run-template">
            <pf-form-select id="report-run-template" v-model="selectedTemplateId" :disabled="!context.orgId || loadingTemplates">
              <pf-form-select-option value="">Select…</pf-form-select-option>
              <pf-form-select-option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</pf-form-select-option>
            </pf-form-select>
          </pf-form-group>

          <div class="form-grid">
            <pf-form-group label="From date (optional)" field-id="report-run-from">
              <pf-text-input id="report-run-from" v-model="scopeFromDate" type="date" />
            </pf-form-group>
            <pf-form-group label="To date (optional)" field-id="report-run-to">
              <pf-text-input id="report-run-to" v-model="scopeToDate" type="date" />
            </pf-form-group>
          </div>

          <pf-form-group label="Statuses (optional)">
            <div class="status-grid">
              <pf-checkbox
                v-for="opt in STATUS_OPTIONS"
                :id="`report-run-status-${opt.value}`"
                :key="opt.value"
                :label="opt.label"
                :model-value="statusEnabled(opt.value)"
                @update:model-value="setStatusEnabled(opt.value, Boolean($event))"
              />
            </div>
          </pf-form-group>
        </pf-form>

        <div class="actions">
          <pf-button
            variant="primary"
            :disabled="creating || !context.orgId || !context.projectId"
            @click="createReportRun"
          >
            {{ creating ? "Creating…" : "Create run" }}
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

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.35rem 0.75rem;
}

.actions {
  margin-top: 0.75rem;
}
</style>
