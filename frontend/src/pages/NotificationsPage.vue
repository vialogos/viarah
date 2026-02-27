<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
	import type { InAppNotification } from "../api/types";
	import VlLabel from "../components/VlLabel.vue";
	import { useContextStore } from "../stores/context";
	import { useNotificationsStore } from "../stores/notifications";
	import { useSessionStore } from "../stores/session";
	import { formatTimestamp } from "../utils/format";
	import { workItemStatusLabel } from "../utils/labels";

const router = useRouter();
const route = useRoute();
	const session = useSessionStore();
	const context = useContextStore();
	const badge = useNotificationsStore();

	const notifications = ref<InAppNotification[]>([]);
	const loading = ref(false);
const markingRead = ref<Record<string, boolean>>({});
const markingAllRead = ref(false);
const error = ref("");
const unreadOnly = ref(false);

const eventLabels: Record<string, string> = {
  "assignment.changed": "Assignment changed",
  "status.changed": "Status changed",
  "comment.created": "Comment created",
  "person_message.created": "Message received",
  "report.published": "Report published",
};

const isClientOnly = computed(
  () => session.memberships.length > 0 && session.memberships.every((m) => m.role === "client")
);

const settingsPath = computed(() =>
  isClientOnly.value ? "/client/notifications/settings" : "/notifications/settings"
);

const currentRole = computed(() => {
  return session.effectiveOrgRole(context.orgId);
});

	const canViewDeliveryLogs = computed(
	  () => !isClientOnly.value && (currentRole.value === "admin" || currentRole.value === "pm")
	);

	const hasUnread = computed(() => notifications.value.some((n) => !n.read_at));

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function notificationSummary(row: InAppNotification): string {
  const data = row.data ?? {};
  if (row.event_type === "person_message.created") {
    const personName = typeof data.person_name === "string" ? data.person_name.trim() : "";
    const threadTitle = typeof data.thread_title === "string" ? data.thread_title.trim() : "";
    const label = eventLabels[row.event_type] ?? row.event_type;
    if (personName && threadTitle) {
      return `${personName} — ${threadTitle}`;
    }
    if (personName) {
      return `${personName} — ${label}`;
    }
    if (threadTitle) {
      return `${threadTitle} — ${label}`;
    }
    return label;
  }
  const workItemType = typeof data.work_item_type === "string" ? data.work_item_type : "";
  const workItemId = typeof data.work_item_id === "string" ? data.work_item_id : "";
  const workItemTitle = typeof data.work_item_title === "string" ? data.work_item_title : "";
  if (workItemType && workItemId) {
    const label = eventLabels[row.event_type] ?? row.event_type;
    const epicTitle = typeof data.epic_title === "string" ? data.epic_title : "";
    if (workItemTitle) {
      return `${workItemTitle} — ${label}`;
    }
    if (epicTitle) {
      return `${epicTitle} — ${label}`;
    }
    return `${label} (${workItemType} ${workItemId.slice(0, 8)})`;
  }

  const reportRunId = typeof data.report_run_id === "string" ? data.report_run_id : "";
  if (reportRunId) {
    return `${eventLabels[row.event_type] ?? row.event_type} (report ${reportRunId})`;
  }

  return eventLabels[row.event_type] ?? row.event_type;
}

function notificationDetail(row: InAppNotification): string {
  const data = row.data ?? {};
  if (row.event_type === "person_message.created") {
    const preview = typeof data.message_preview === "string" ? data.message_preview.trim() : "";
    return preview || "New message";
  }
  if (row.event_type === "status.changed") {
    const oldStatus = typeof data.old_status === "string" ? data.old_status : "";
    const newStatus = typeof data.new_status === "string" ? data.new_status : "";
    if (oldStatus && newStatus) {
      return `Status: ${workItemStatusLabel(oldStatus)} → ${workItemStatusLabel(newStatus)}`;
    }
  }
  if (row.event_type === "assignment.changed") {
    return "Assignment updated";
  }
  if (row.event_type === "comment.created") {
    return "New comment";
  }
  if (row.event_type === "report.published") {
    return "Report published";
  }
  return "";
}

function notificationLink(row: InAppNotification): string | null {
  const data = row.data ?? {};
  if (row.event_type === "person_message.created") {
    const personId = typeof data.person_id === "string" ? data.person_id : "";
    return personId ? `/people/${personId}` : null;
  }
  const workItemType = typeof data.work_item_type === "string" ? data.work_item_type : "";
  const workItemId = typeof data.work_item_id === "string" ? data.work_item_id : "";
  if (!workItemType || !workItemId) {
    return null;
  }
  if (workItemType === "task") {
    return isClientOnly.value ? `/client/tasks/${workItemId}` : `/work/${workItemId}`;
  }
  if (workItemType === "subtask") {
    const taskId = typeof data.task_id === "string" ? data.task_id : "";
    if (!taskId) {
      return null;
    }
    return isClientOnly.value ? `/client/tasks/${taskId}` : `/work/${taskId}`;
  }
  return null;
}

function notificationProjectName(row: InAppNotification): string {
  const data = row.data ?? {};
  const projectName = typeof data.project_name === "string" ? data.project_name : "";
  return projectName;
}

async function refresh() {
  error.value = "";
  if (!context.orgId) {
    notifications.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listMyNotifications(context.orgId, {
      projectId: context.projectId || undefined,
      unreadOnly: unreadOnly.value,
      limit: 50,
    });
    notifications.value = res.notifications;
  } catch (err) {
    notifications.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgId, context.projectId, unreadOnly.value], () => void refresh(), {
  immediate: true,
});

watch(
  () => badge.unreadCount,
  (next, prev) => {
    if (next !== prev && !loading.value) {
      void refresh();
    }
  }
);

async function markRead(row: InAppNotification) {
  if (!context.orgId) {
    return;
  }

  markingRead.value[row.id] = true;
  try {
    const res = await api.markMyNotificationRead(context.orgId, row.id);
    const updated = res.notification;
    notifications.value = notifications.value
      .map((n) => (n.id === row.id ? updated : n))
      .filter((n) => !(unreadOnly.value && Boolean(n.read_at)));
    void badge.refreshBadge();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    markingRead.value[row.id] = false;
  }
}

async function markAllRead() {
  if (!context.orgId) {
    return;
  }
  if (!hasUnread.value) {
    return;
  }

  markingAllRead.value = true;
  error.value = "";
  try {
    await api.markAllMyNotificationsRead(context.orgId, {
      projectId: context.projectId || undefined,
    });
    await Promise.all([refresh(), badge.refreshBadge()]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    markingAllRead.value = false;
  }
}
</script>

<template>
  <pf-card>
    <pf-card-title>
      <div class="header">
        <div>
          <pf-title h="1" size="2xl">Notifications</pf-title>
          <pf-content>
            <p class="muted">In-app notifications for the selected org/project.</p>
          </pf-content>
        </div>
        <div class="actions">
          <pf-button variant="link" :to="settingsPath">Preferences</pf-button>
          <pf-button v-if="canViewDeliveryLogs" variant="link" to="/notifications/delivery-logs">
            Delivery logs
          </pf-button>
        </div>
      </div>
    </pf-card-title>

    <pf-card-body>
      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Notifications are org-scoped" heading-level="h2" />
        <pf-empty-state-body>Select a single org to view in-app notifications.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else>
        <pf-toolbar class="toolbar">
          <pf-toolbar-content>
            <pf-toolbar-group>
              <pf-toolbar-item>
                <pf-checkbox id="notifications-unread-only" v-model="unreadOnly" label="Unread only" />
              </pf-toolbar-item>
            </pf-toolbar-group>
            <pf-toolbar-group align="end">
              <pf-toolbar-item>
                <pf-button
                  variant="secondary"
                  :disabled="loading || markingAllRead || !hasUnread"
                  :title="!hasUnread ? 'No unread notifications' : undefined"
                  @click="markAllRead"
                >
                  {{ markingAllRead ? "Marking…" : "Mark all as read" }}
                </pf-button>
              </pf-toolbar-item>
            </pf-toolbar-group>
          </pf-toolbar-content>
        </pf-toolbar>

        <pf-alert v-if="error" inline variant="danger" :title="error" />

        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading notifications" />
        </div>

        <pf-empty-state v-else-if="notifications.length === 0">
          <pf-empty-state-header title="No notifications" heading-level="h2" />
          <pf-empty-state-body>No notifications were found for the selected scope.</pf-empty-state-body>
        </pf-empty-state>

        <pf-data-list v-else compact aria-label="Notifications">
          <pf-data-list-item v-for="row in notifications" :key="row.id" class="item" :class="{ unread: !row.read_at }">
            <pf-data-list-cell>
              <div class="title">
                <RouterLink v-if="notificationLink(row)" class="link" :to="notificationLink(row) ?? ''">
                  {{ notificationSummary(row) }}
                </RouterLink>
                <span v-else>{{ notificationSummary(row) }}</span>
              </div>
              <div v-if="notificationDetail(row) || notificationProjectName(row)" class="detail muted">
                <span v-if="notificationDetail(row)">{{ notificationDetail(row) }}</span>
                <span v-if="notificationDetail(row) && notificationProjectName(row)"> · </span>
                <span v-if="notificationProjectName(row)">Project: {{ notificationProjectName(row) }}</span>
              </div>
              <div class="labels">
                <VlLabel color="blue">{{ formatTimestamp(row.created_at) }}</VlLabel>
                <VlLabel v-if="row.read_at" color="green">Read {{ formatTimestamp(row.read_at) }}</VlLabel>
              </div>
            </pf-data-list-cell>
            <pf-data-list-cell v-if="!row.read_at" align-right>
              <pf-button
                variant="secondary"
                small
                :disabled="Boolean(markingRead[row.id])"
                @click="markRead(row)"
              >
                {{ markingRead[row.id] ? "Marking…" : "Mark read" }}
              </pf-button>
            </pf-data-list-cell>
          </pf-data-list-item>
        </pf-data-list>

        <pf-helper-text class="note">
          <pf-helper-text-item>
            Notifications update automatically.
          </pf-helper-text-item>
        </pf-helper-text>
      </div>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.toolbar {
  margin-bottom: 0.75rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.item.unread :deep(.pf-v6-c-data-list__item-row) {
  background: #eef2ff;
}

.title {
  font-weight: 600;
}

.link {
  text-decoration: none;
}

.link:hover {
  text-decoration: underline;
}

.detail {
  margin-top: 0.25rem;
}

.labels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.note {
  margin-top: 0.75rem;
}
</style>
