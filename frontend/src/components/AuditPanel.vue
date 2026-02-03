<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { AuditEvent } from "../api/types";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";

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
</script>

<template>
  <section class="audit card">
    <div class="header">
      <h2 class="section-title">{{ title ?? "Audit" }}</h2>
      <button type="button" :disabled="loading" @click="refresh">Refresh</button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="error" class="muted">{{ error }}</p>
    <p v-else-if="filteredEvents.length === 0" class="muted">No recent events.</p>

    <ul v-else class="events">
      <li v-for="event in filteredEvents" :key="event.id" class="event">
        <div class="event-header">
          <div class="event-type mono">{{ event.event_type }}</div>
          <div class="muted">{{ formatTimestamp(event.created_at) }}</div>
        </div>
        <div class="muted">Actor: {{ actorLabel(event) }}</div>

        <div v-if="summaryPairs(event).length > 0" class="summary">
          <div v-for="pair in summaryPairs(event)" :key="pair.key" class="pair mono">
            {{ pair.key }}={{ pair.value }}
          </div>
        </div>

        <details class="details">
          <summary class="muted">Metadata</summary>
          <pre class="meta mono">{{ JSON.stringify(event.metadata ?? {}, null, 2) }}</pre>
        </details>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.section-title {
  margin: 0;
  font-size: 1.1rem;
}

.events {
  list-style: none;
  padding: 0;
  margin: 1rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.event {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem;
  background: #fbfbfd;
}

.event-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
}

.event-type {
  font-weight: 600;
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.pair {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  font-size: 0.85rem;
}

.details {
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
