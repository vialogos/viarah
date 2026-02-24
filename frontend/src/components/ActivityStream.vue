<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { AuditEvent, Client, Person, Task } from "../api/types";
import { useRealtimeStore } from "../stores/realtime";
import { useSessionStore } from "../stores/session";
import { formatTimestamp } from "../utils/format";
import { mapAllSettledWithConcurrency } from "../utils/promisePool";
import VlLabel from "./VlLabel.vue";

const props = defineProps<{
  orgId: string;
  title?: string;
  projectId?: string;
  personId?: string;
  limit?: number;
}>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const realtime = useRealtimeStore();

const effectiveLimit = computed(() => Math.max(1, Math.min(Number(props.limit ?? 25) || 25, 100)));

const loading = ref(false);
const error = ref("");
const events = ref<AuditEvent[]>([]);

const tasksById = ref<Record<string, Task>>({});
const clientsById = ref<Record<string, Client>>({});
const peopleById = ref<Record<string, Person>>({});

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function shortId(value: string): string {
  if (!value) {
    return "";
  }
  if (value.length <= 12) {
    return value;
  }
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function metadataString(event: AuditEvent, key: string): string | null {
  const value = event.metadata?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function actorLabel(event: AuditEvent): string {
  return event.actor_user?.display_name || event.actor_user?.email || "System";
}

function humanizeEventType(eventType: string): string {
  return String(eventType || "").trim().split("_").join(" ").split(".").join(" ");
}

function actionPhrase(event: AuditEvent): string {
  const eventType = event.event_type || "";
  switch (eventType) {
    case "comment.created":
      return "commented on";
    case "task.workflow_stage_changed":
    case "subtask.workflow_stage_changed":
      return "moved";
    case "attachment.created":
      return "attached a file to";
    case "person_message.created":
      return "messaged";
    case "org_invite.created":
      return "invited";
    case "org_invite.revoked":
      return "revoked an invite for";
    case "org_invite.resent":
      return "resent an invite for";
    default:
      break;
  }

  if (eventType.endsWith(".created")) {
    return "created";
  }
  if (eventType.endsWith(".updated")) {
    return "updated";
  }
  if (eventType.endsWith(".deleted")) {
    return "deleted";
  }

  return humanizeEventType(eventType);
}

function activityTarget(event: AuditEvent): { label: string; to?: string } {
  const taskId = metadataString(event, "task_id");
  if (taskId) {
    const task = tasksById.value[taskId];
    return { label: task?.title || `Task ${shortId(taskId)}`, to: `/work/${taskId}` };
  }

  const clientId = metadataString(event, "client_id");
  if (clientId) {
    const client = clientsById.value[clientId];
    return { label: client?.name || `Client ${shortId(clientId)}`, to: `/clients/${clientId}` };
  }

  const personId = metadataString(event, "person_id");
  if (personId) {
    const person = peopleById.value[personId];
    const label = (person?.preferred_name || person?.full_name || person?.email || "").trim();
    return { label: label || `Person ${shortId(personId)}`, to: `/people/${personId}` };
  }

  return { label: humanizeEventType(event.event_type) || "Activity" };
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";

  if (!props.orgId) {
    events.value = [];
    tasksById.value = {};
    clientsById.value = {};
    peopleById.value = {};
    return;
  }

  loading.value = true;
  try {
    const res = await api.listAuditEvents(props.orgId);
    const raw = res.events || [];
    const filtered = raw
      .filter((event) => {
        if (props.projectId && metadataString(event, "project_id") !== props.projectId) {
          return false;
        }
        if (props.personId && metadataString(event, "person_id") !== props.personId) {
          return false;
        }
        return true;
      })
      .slice(0, effectiveLimit.value);

    events.value = filtered;

    const taskIds = Array.from(
      new Set(filtered.map((event) => metadataString(event, "task_id")).filter(Boolean) as string[])
    );
    const clientIds = Array.from(
      new Set(filtered.map((event) => metadataString(event, "client_id")).filter(Boolean) as string[])
    );
    const personIds = Array.from(
      new Set(filtered.map((event) => metadataString(event, "person_id")).filter(Boolean) as string[])
    );

    const FETCH_CONCURRENCY = 6;
    const [taskResults, clientResults, personResults] = await Promise.all([
      mapAllSettledWithConcurrency(taskIds, FETCH_CONCURRENCY, async (taskId) => api.getTask(props.orgId, taskId)),
      mapAllSettledWithConcurrency(clientIds, FETCH_CONCURRENCY, async (clientId) => api.getClient(props.orgId, clientId)),
      mapAllSettledWithConcurrency(personIds, FETCH_CONCURRENCY, async (personId) => api.getOrgPerson(props.orgId, personId)),
    ]);

    const nextTasks: Record<string, Task> = {};
    for (let i = 0; i < taskIds.length; i += 1) {
      const id = taskIds[i];
      const result = taskResults[i];
      if (!id || !result || result.status !== "fulfilled") {
        continue;
      }
      nextTasks[id] = result.value.task;
    }
    tasksById.value = nextTasks;

    const nextClients: Record<string, Client> = {};
    for (let i = 0; i < clientIds.length; i += 1) {
      const id = clientIds[i];
      const result = clientResults[i];
      if (!id || !result || result.status !== "fulfilled") {
        continue;
      }
      nextClients[id] = result.value.client;
    }
    clientsById.value = nextClients;

    const nextPeople: Record<string, Person> = {};
    for (let i = 0; i < personIds.length; i += 1) {
      const id = personIds[i];
      const result = personResults[i];
      if (!id || !result || result.status !== "fulfilled") {
        continue;
      }
      nextPeople[id] = result.value.person;
    }
    peopleById.value = nextPeople;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Activity is not available for your role.";
      return;
    }
    events.value = [];
    tasksById.value = {};
    clientsById.value = {};
    peopleById.value = {};
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [props.orgId, props.projectId, props.personId, effectiveLimit.value], () => void refresh(), { immediate: true });

let refreshTimeoutId: number | null = null;
function scheduleRefresh() {
  if (refreshTimeoutId != null) {
    return;
  }
  refreshTimeoutId = window.setTimeout(() => {
    refreshTimeoutId = null;
    if (loading.value) {
      return;
    }
    void refresh();
  }, 250);
}

const unsubscribeRealtime = realtime.subscribe((event) => {
  if (event.type !== "audit_event.created") {
    return;
  }
  if (!props.orgId) {
    return;
  }
  if (event.org_id && event.org_id !== props.orgId) {
    return;
  }
  if (!isRecord(event.data)) {
    return;
  }
  if (props.projectId || props.personId) {
    const meta = isRecord(event.data.metadata) ? event.data.metadata : {};
    if (props.projectId && String(meta.project_id ?? "") !== props.projectId) {
      return;
    }
    if (props.personId && String(meta.person_id ?? "") !== props.personId) {
      return;
    }
  }
  scheduleRefresh();
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
  <pf-card class="activity">
    <pf-card-title>
      <div class="header">
        <pf-title h="2" size="lg">{{ title ?? "Activity" }}</pf-title>
      </div>
    </pf-card-title>

    <pf-card-body>
      <div v-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading activity" />
      </div>

      <pf-alert v-else-if="error" inline variant="danger" :title="error" />

      <pf-empty-state v-else-if="events.length === 0" variant="small">
        <pf-empty-state-header title="No recent activity" heading-level="h4" />
        <pf-empty-state-body>No audit events found for the current filters.</pf-empty-state-body>
      </pf-empty-state>

      <pf-data-list v-else aria-label="Activity stream">
        <pf-data-list-item v-for="event in events" :key="event.id" aria-label="Activity item">
          <pf-data-list-item-row>
            <pf-data-list-item-cells>
              <pf-data-list-cell>
                <div class="row">
                  <div class="main">
                    <span class="actor">{{ actorLabel(event) }}</span>
                    <span class="action">{{ actionPhrase(event) }}</span>
                    <RouterLink v-if="activityTarget(event).to" class="link" :to="activityTarget(event).to!">
                      {{ activityTarget(event).label }}
                    </RouterLink>
                    <span v-else class="target">{{ activityTarget(event).label }}</span>
                  </div>
                  <div class="meta">
                    <VlLabel color="blue">{{ formatTimestamp(event.created_at) }}</VlLabel>
                  </div>
                </div>
              </pf-data-list-cell>
            </pf-data-list-item-cells>
          </pf-data-list-item-row>
        </pf-data-list-item>
      </pf-data-list>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.activity {
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

.row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.main {
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
  flex-wrap: wrap;
}

.actor {
  font-weight: 600;
}

.meta {
  flex: 0 0 auto;
}
</style>

