<script setup lang="ts">
	import { computed, onBeforeUnmount, ref, watch } from "vue";
	import { useRoute, useRouter } from "vue-router";

	import { api, ApiError } from "../api";
	import type { AuditEvent } from "../api/types";
	import { useRealtimeStore } from "../stores/realtime";
	import { useSessionStore } from "../stores/session";
	import { formatTimestamp } from "../utils/format";
	import VlLabel from "./VlLabel.vue";

const props = defineProps<{
  orgId: string;
  title?: string;
  workflowId?: string;
  projectId?: string;
  eventTypes?: string[];
}>();

	const router = useRouter();
	const route = useRoute();
	const session = useSessionStore();
	const realtime = useRealtimeStore();

const loading = ref(false);
const error = ref("");
const events = ref<AuditEvent[]>([]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function actorLabel(event: AuditEvent): string {
  const actorUser = event.actor_user ?? null;
  if (actorUser) {
    return actorUser.display_name || actorUser.email;
  }

  const meta = isRecord(event.metadata) ? event.metadata : {};
  const actorType = typeof meta.actor_type === "string" ? meta.actor_type : "";
  const actorId = typeof meta.actor_id === "string" ? meta.actor_id : "";
  if (actorType === "api_key") {
    return actorId ? `API key ${actorId}` : "API key";
  }
  if (actorType) {
    return actorId ? `${actorType} ${actorId}` : actorType;
  }

  return event.actor_user_id ?? "—";
}

function summaryPairs(event: AuditEvent): Array<{ key: string; value: string }> {
  const meta = isRecord(event.metadata) ? event.metadata : {};
  const preferredKeys = ["project_id", "workflow_id", "stage_id", "prior_workflow_id"] as const;

  const pairs: Array<{ key: string; value: string }> = [];
  for (const key of preferredKeys) {
    const value = meta[key];
    if (typeof value === "string" && value) {
      pairs.push({ key, value });
    }
  }
  return pairs;
}

const filteredEvents = computed(() => {
  let out = events.value;

  if (props.eventTypes && props.eventTypes.length > 0) {
    const set = new Set(props.eventTypes);
    out = out.filter((e) => set.has(e.event_type));
  }

  if (props.workflowId) {
    out = out.filter((e) => {
      const meta = isRecord(e.metadata) ? e.metadata : {};
      return meta.workflow_id === props.workflowId;
    });
  }

  if (props.projectId) {
    out = out.filter((e) => {
      const meta = isRecord(e.metadata) ? e.metadata : {};
      return meta.project_id === props.projectId;
    });
  }

  return out;
});

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

	async function refresh() {
	  error.value = "";
  if (!props.orgId) {
    events.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listAuditEvents(props.orgId);
    events.value = res.events;
  } catch (err) {
    events.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Audit history is not available for your role.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
	}

	watch(() => props.orgId, () => void refresh(), { immediate: true });

	let refreshTimeoutId: number | null = null;
	function scheduleRefresh() {
	  if (refreshTimeoutId != null) {
	    return;
	  }
	  refreshTimeoutId = window.setTimeout(() => {
	    refreshTimeoutId = null;
	    void refresh();
	  }, 250);
	}

	const unsubscribeRealtime = realtime.subscribe((event) => {
	  if (!props.orgId || !event.org_id || event.org_id !== props.orgId) {
	    return;
	  }
	  if (event.type === "work_item.updated" || event.type === "comment.created" || event.type === "gitlab_link.updated") {
	    scheduleRefresh();
	  }
	});

	onBeforeUnmount(() => {
	  unsubscribeRealtime();
	  if (refreshTimeoutId != null) {
	    window.clearTimeout(refreshTimeoutId);
	    refreshTimeoutId = null;
	  }
	});
</script>

<template>
  <pf-card class="audit">
    <pf-card-title>
      <div class="header">
        <pf-title h="2" size="lg">{{ title ?? "Audit" }}</pf-title>
        <pf-button variant="secondary" :disabled="loading" @click="refresh">Refresh</pf-button>
      </div>
    </pf-card-title>

    <pf-card-body>
      <div v-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading audit history" />
      </div>

      <pf-alert v-else-if="error" inline variant="danger" :title="error" />

      <pf-empty-state v-else-if="filteredEvents.length === 0">
        <pf-empty-state-header title="No recent events" heading-level="h3" />
        <pf-empty-state-body>
          No audit events were found for the selected filters.
        </pf-empty-state-body>
      </pf-empty-state>

      <pf-data-list v-else compact aria-label="Audit events">
        <pf-data-list-item v-for="event in filteredEvents" :key="event.id">
          <pf-data-list-cell>
            <div class="event-top">
              <div class="event-type mono">{{ event.event_type }}</div>
              <VlLabel color="blue">{{ formatTimestamp(event.created_at) }}</VlLabel>
            </div>

            <div class="muted">Actor: {{ actorLabel(event) }}</div>

            <div v-if="summaryPairs(event).length > 0" class="labels">
              <VlLabel v-for="pair in summaryPairs(event)" :key="pair.key" color="blue">
                <span class="mono">{{ pair.key }}={{ pair.value }}</span>
              </VlLabel>
            </div>

            <pf-expandable-section
              class="meta-section"
              toggle-text-collapsed="Show metadata"
              toggle-text-expanded="Hide metadata"
            >
              <pre class="meta mono">{{ JSON.stringify(event.metadata ?? {}, null, 2) }}</pre>
            </pf-expandable-section>
          </pf-data-list-cell>
        </pf-data-list-item>
      </pf-data-list>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.audit {
  margin-top: 1rem;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.5rem 0;
}

.event-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.event-type {
  font-weight: 600;
}

.labels {
  margin-top: 0.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.meta-section {
  margin-top: 0.5rem;
}

.meta {
  margin: 0.5rem 0 0 0;
  padding: 0.75rem;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #0b1020;
  color: #e5e7eb;
  overflow: auto;
  font-size: 0.85rem;
  line-height: 1.4;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}
</style>
