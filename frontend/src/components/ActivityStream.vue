<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Activity,
  Briefcase,
  GitBranch,
  Mail,
  MessageSquareText,
  Paperclip,
  Send,
  User,
  UserPlus,
} from "lucide-vue-next";

import { api, ApiError } from "../api";
import type { AuditEvent, Client, Person, Project, Task, WorkflowStage } from "../api/types";
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
  taskIds?: string[];
  limit?: number;
}>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const realtime = useRealtimeStore();

const effectiveLimit = computed(() => Math.max(1, Math.min(Number(props.limit ?? 25) || 25, 100)));

const allowedTaskIdSet = computed(() => {
  if (props.taskIds == null) {
    return null;
  }
  const cleaned = props.taskIds.map((value) => value.trim()).filter(Boolean);
  return new Set(cleaned);
});

const taskIdSignature = computed(() => {
  if (props.taskIds == null) {
    return "__any__";
  }
  if (props.taskIds.length === 0) {
    return "__none__";
  }
  return [...new Set(props.taskIds.map((value) => value.trim()).filter(Boolean))].sort().join("|");
});

const loading = ref(false);
const error = ref("");
const events = ref<AuditEvent[]>([]);

const tasksById = ref<Record<string, Task>>({});
const clientsById = ref<Record<string, Client>>({});
const peopleById = ref<Record<string, Person>>({});
const projectsById = ref<Record<string, Project>>({});
const workflowStagesById = ref<Record<string, WorkflowStage>>({});

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
    case "project_membership.added":
      return "added a member to";
    case "project_membership.removed":
      return "removed a member from";
    case "org_membership.created":
      return "joined the organization";
    case "org_membership.role_changed": {
      const oldRole = metadataString(event, "old_role");
      const newRole = metadataString(event, "new_role");
      if (oldRole && newRole) {
        return `changed a team role (${oldRole} → ${newRole})`;
      }
      return "changed a team role";
    }
    case "org_membership.updated": {
      const fields = event.metadata?.fields_changed;
      if (Array.isArray(fields)) {
        const cleaned = fields
          .filter((item) => typeof item === "string")
          .map((value) => value.trim())
          .filter(Boolean);
        if (cleaned.length) {
          return `updated team details (${cleaned.join(", ")})`;
        }
      }
      return "updated team details";
    }
    case "comment.created":
      return "commented on";
    case "task.workflow_stage_changed":
    case "subtask.workflow_stage_changed":
      return "moved";
	    case "attachment.created":
	      return "attached a file to";
	    case "person_message.created":
	      return "messaged";
	    case "person_message_thread.created":
	      return "started a message thread with";
	    case "org_invite.created":
	      return "invited";
	    case "org_invite.accepted":
	      return "accepted an invite";
	    case "org_invite.revoked":
	      return "revoked an invite for";
	    case "org_invite.resent":
	      return "resent an invite for";
	    case "person_rate.created":
	      return "set a rate for";
	    case "person_payment.created":
	      return "recorded a payment for";
	    case "person_contact_entry.created": {
	      const kind = metadataString(event, "kind");
	      if (kind) {
	        return `added a ${kind} entry to`;
	      }
	      return "added a contact entry to";
	    }
	    default:
	      break;
	  }

	  return humanizeEventType(eventType);
	}

type ActivityTarget = { label: string; to?: string };

function activityTarget(event: AuditEvent): ActivityTarget | null {
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

  const projectId = metadataString(event, "project_id");
  if (projectId) {
    const project = projectsById.value[projectId];
    return { label: project?.name || `Project ${shortId(projectId)}` };
  }

  const email = metadataString(event, "email");
  if (email) {
    return { label: email };
  }

  return null;
}

function eventTypeLabel(eventType: string): string {
  const normalized = String(eventType || "");
  if (normalized.startsWith("project_membership.") || normalized.startsWith("org_membership.")) {
    return "Membership";
  }
  if (normalized.startsWith("org_invite.")) {
    return "Invite";
  }
  if (normalized.startsWith("task.") || normalized.startsWith("subtask.")) {
    return "Task";
  }
  if (normalized.startsWith("comment.")) {
    return "Comment";
  }
  if (normalized.startsWith("attachment.")) {
    return "Attachment";
  }
  if (normalized.startsWith("person_message.")) {
    return "Message";
  }
  if (
    normalized.startsWith("person_contact_entry.") ||
    normalized.startsWith("person_rate.") ||
    normalized.startsWith("person_payment.")
  ) {
    return "Person";
  }
  return "";
}

function iconForEvent(event: AuditEvent): Component {
  const normalized = String(event.event_type || "");
  if (normalized.startsWith("gitlab_link.")) {
    return GitBranch;
  }

  const label = eventTypeLabel(normalized);
  switch (label) {
    case "Task":
      return Briefcase;
    case "Comment":
      return MessageSquareText;
    case "Attachment":
      return Paperclip;
    case "Invite":
      return Send;
    case "Message":
      return Mail;
    case "Membership":
      return UserPlus;
    case "Person":
      return User;
    default:
      return Activity;
  }
}

function workflowStageLabel(stageId: string | null): string {
  if (!stageId) {
    return "";
  }
  const stage = workflowStagesById.value[stageId];
  return stage?.name || `Stage ${shortId(stageId)}`;
}

function eventDetail(event: AuditEvent): string {
  const details: string[] = [];

  if (event.event_type === "task.workflow_stage_changed" || event.event_type === "subtask.workflow_stage_changed") {
    const priorStageId = metadataString(event, "prior_workflow_stage_id");
    const nextStageId = metadataString(event, "workflow_stage_id");
    const priorLabel = workflowStageLabel(priorStageId);
    const nextLabel = workflowStageLabel(nextStageId);
    if (priorLabel && nextLabel) {
      details.push(`Stage: ${priorLabel} → ${nextLabel}`);
    } else if (nextLabel) {
      details.push(`Stage: ${nextLabel}`);
    }
  }

  if (event.event_type === "project_membership.added" || event.event_type === "project_membership.removed") {
    const role = metadataString(event, "org_role");
    const userId = metadataString(event, "user_id");
    if (role) {
      details.push(`Role: ${role}`);
    }
    if (userId) {
      details.push(`Member: ${shortId(userId)}`);
    }
  }

  if (event.event_type.startsWith("org_invite.")) {
    const role = metadataString(event, "role");
    const email = metadataString(event, "email");
    if (role) {
      details.push(`Role: ${role}`);
    }
    if (email) {
      details.push(email);
    }
  }

  return details.join(" · ");
}

const renderedEvents = computed(() => {
  return events.value.map((event) => {
    return {
      id: event.id,
      actor: actorLabel(event),
      action: actionPhrase(event).trim(),
      target: activityTarget(event),
      typeLabel: eventTypeLabel(event.event_type),
      icon: iconForEvent(event),
      detail: eventDetail(event),
      createdAtLabel: formatTimestamp(event.created_at),
    };
  });
});

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
    projectsById.value = {};
    workflowStagesById.value = {};
    return;
  }

  loading.value = true;
  try {
    const res = await api.listAuditEvents(props.orgId);
    const raw = res.events || [];
    const allowedTaskIds = allowedTaskIdSet.value;
    const filtered = raw
      .filter((event) => {
        if (props.projectId && metadataString(event, "project_id") !== props.projectId) {
          return false;
        }
        if (props.personId && metadataString(event, "person_id") !== props.personId) {
          return false;
        }
        if (allowedTaskIds !== null) {
          const taskId = metadataString(event, "task_id");
          if (!taskId || !allowedTaskIds.has(taskId)) {
            return false;
          }
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
	    const projectIds = Array.from(
	      new Set(filtered.map((event) => metadataString(event, "project_id")).filter(Boolean) as string[])
	    );
	    const workflowIds = Array.from(
	      new Set(filtered.map((event) => metadataString(event, "workflow_id")).filter(Boolean) as string[])
	    );

	    const FETCH_CONCURRENCY = 6;
	    const [taskResults, clientResults, personResults, projectResults, workflowStageResults] = await Promise.all([
	      mapAllSettledWithConcurrency(taskIds, FETCH_CONCURRENCY, async (taskId) => api.getTask(props.orgId, taskId)),
	      mapAllSettledWithConcurrency(clientIds, FETCH_CONCURRENCY, async (clientId) => api.getClient(props.orgId, clientId)),
	      mapAllSettledWithConcurrency(personIds, FETCH_CONCURRENCY, async (personId) => api.getOrgPerson(props.orgId, personId)),
	      mapAllSettledWithConcurrency(projectIds, FETCH_CONCURRENCY, async (projectId) =>
	        api.getProject(props.orgId, projectId)
	      ),
	      mapAllSettledWithConcurrency(workflowIds, FETCH_CONCURRENCY, async (workflowId) =>
	        api.listWorkflowStages(props.orgId, workflowId)
	      ),
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

	    const nextProjects: Record<string, Project> = {};
	    for (let i = 0; i < projectIds.length; i += 1) {
      const id = projectIds[i];
      const result = projectResults[i];
      if (!id || !result || result.status !== "fulfilled") {
        continue;
      }
      nextProjects[id] = result.value.project;
	    }
	    projectsById.value = nextProjects;

	    const nextStages: Record<string, WorkflowStage> = {};
	    for (let i = 0; i < workflowIds.length; i += 1) {
	      const result = workflowStageResults[i];
	      if (!result || result.status !== "fulfilled") {
	        continue;
	      }
	      for (const stage of result.value.stages) {
	        nextStages[stage.id] = stage;
	      }
	    }
	    workflowStagesById.value = nextStages;
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
    projectsById.value = {};
    workflowStagesById.value = {};
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.orgId, props.projectId, props.personId, taskIdSignature.value, effectiveLimit.value],
  () => void refresh(),
  { immediate: true }
);

let refreshQueued = false;
function scheduleRefresh() {
  if (refreshQueued) {
    return;
  }
  refreshQueued = true;
  Promise.resolve().then(() => {
    refreshQueued = false;
    if (loading.value) {
      return;
    }
    void refresh();
  });
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
  const allowedTaskIds = allowedTaskIdSet.value;
  if (allowedTaskIds !== null) {
    const meta = isRecord(event.data.metadata) ? event.data.metadata : {};
    const taskId = String(meta.task_id ?? "");
    if (!taskId || !allowedTaskIds.has(taskId)) {
      return;
    }
  }
  scheduleRefresh();
});

onBeforeUnmount(() => {
  unsubscribeRealtime();
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

      <pf-data-list v-else aria-label="Activity stream" class="timeline">
        <pf-data-list-item
          v-for="(item, index) in renderedEvents"
          :key="item.id"
          aria-label="Activity item"
          class="timeline-item"
        >
          <pf-data-list-item-row>
            <pf-data-list-item-cells>
              <pf-data-list-cell>
                <div class="timeline-row">
                  <div class="rail" aria-hidden="true">
                    <div class="dot">
                      <pf-icon inline>
                        <component :is="item.icon" class="dot-icon" aria-hidden="true" />
                      </pf-icon>
                    </div>
                    <div v-if="index < renderedEvents.length - 1" class="stem"></div>
                  </div>

                  <div class="content">
                    <div class="row">
                      <div class="main">
                        <span class="actor">{{ item.actor }}</span>
                        <VlLabel v-if="item.typeLabel" class="type-label" color="grey" variant="outline">
                          {{ item.typeLabel }}
                        </VlLabel>
                        <span v-if="item.action" class="action">{{ item.action }}</span>
                        <span v-if="item.target?.label" class="sep">—</span>
                        <RouterLink v-if="item.target?.to" class="link" :to="item.target.to">
                          {{ item.target.label }}
                        </RouterLink>
                        <span v-else-if="item.target?.label" class="target">{{ item.target.label }}</span>
                      </div>
                      <div class="meta">
                        <VlLabel color="blue">{{ item.createdAtLabel }}</VlLabel>
                      </div>
                    </div>

                    <div v-if="item.detail" class="detail muted small">
                      {{ item.detail }}
                    </div>
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

.timeline-row {
  display: grid;
  grid-template-columns: 1.75rem minmax(0, 1fr);
  gap: 0.75rem;
}

.rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  height: 100%;
}

.dot {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 9999px;
  border: 1px solid var(--pf-v6-global--BorderColor--200);
  background: var(--pf-v6-global--BackgroundColor--100);
  display: flex;
  align-items: center;
  justify-content: center;
}

.dot-icon {
  width: 1rem;
  height: 1rem;
  color: var(--pf-v6-global--Color--200);
}

.stem {
  width: 2px;
  flex: 1 1 auto;
  background: var(--pf-v6-global--BorderColor--200);
  margin-top: 0.25rem;
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

.type-label {
  margin-left: 0.25rem;
}

	.sep {
	  color: var(--pf-v6-global--Color--200);
	  padding: 0 0.1rem;
	}

	.meta {
	  flex: 0 0 auto;
	}

	.muted {
	  color: var(--pf-v6-global--Color--200);
	}

	.small {
	  font-size: 0.85rem;
	}

	.detail {
	  margin-top: 0.25rem;
	}
</style>
