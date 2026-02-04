<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { InAppNotification } from "../api/types";
import { useContextStore } from "../stores/context";
import { useNotificationsStore } from "../stores/notifications";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();
const badge = useNotificationsStore();

const notifications = ref<InAppNotification[]>([]);
const loading = ref(false);
const markingRead = ref<Record<string, boolean>>({});
const error = ref("");
const unreadOnly = ref(false);

const eventLabels: Record<string, string> = {
  "assignment.changed": "Assignment changed",
  "status.changed": "Status changed",
  "comment.created": "Comment created",
  "report.published": "Report published",
};

const isClientOnly = computed(
  () => session.memberships.length > 0 && session.memberships.every((m) => m.role === "client")
);

const settingsPath = computed(() =>
  isClientOnly.value ? "/client/notifications/settings" : "/notifications/settings"
);

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canViewDeliveryLogs = computed(
  () => !isClientOnly.value && (currentRole.value === "admin" || currentRole.value === "pm")
);

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function notificationSummary(row: InAppNotification): string {
  const data = row.data ?? {};
  const workItemType = typeof data.work_item_type === "string" ? data.work_item_type : "";
  const workItemId = typeof data.work_item_id === "string" ? data.work_item_id : "";
  if (workItemType && workItemId) {
    return `${eventLabels[row.event_type] ?? row.event_type} (${workItemType} ${workItemId})`;
  }

  const reportRunId = typeof data.report_run_id === "string" ? data.report_run_id : "";
  if (reportRunId) {
    return `${eventLabels[row.event_type] ?? row.event_type} (report ${reportRunId})`;
  }

  return eventLabels[row.event_type] ?? row.event_type;
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
    if (next > prev) {
      void refresh();
    }
  }
);

function onFocus() {
  void refresh();
}

onMounted(() => {
  window.addEventListener("focus", onFocus);
});

onUnmounted(() => {
  window.removeEventListener("focus", onFocus);
});

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
</script>

<template>
  <div>
    <div class="header">
      <div>
        <h1 class="page-title">Notifications</h1>
        <p class="muted">In-app notifications for the selected org/project.</p>
      </div>
      <div class="actions">
        <RouterLink class="link" :to="settingsPath">Preferences</RouterLink>
        <RouterLink v-if="canViewDeliveryLogs" class="link" to="/notifications/delivery-logs">
          Delivery logs
        </RouterLink>
      </div>
    </div>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>

    <div v-else class="card">
      <div class="toolbar">
        <label class="toggle">
          <input v-model="unreadOnly" type="checkbox" />
          <span>Unread only</span>
        </label>
        <div class="spacer" />
        <button type="button" :disabled="loading" @click="refresh">
          {{ loading ? "Refreshing…" : "Refresh" }}
        </button>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="notifications.length === 0" class="muted">No notifications.</div>

      <ul v-else class="list">
        <li v-for="row in notifications" :key="row.id" class="item" :class="{ unread: !row.read_at }">
          <div class="meta">
            <div class="title">{{ notificationSummary(row) }}</div>
            <div class="muted time">
              {{ formatTimestamp(row.created_at) }}
              <span v-if="row.read_at">· read {{ formatTimestamp(row.read_at) }}</span>
            </div>
          </div>
          <button
            v-if="!row.read_at"
            type="button"
            class="mark"
            :disabled="Boolean(markingRead[row.id])"
            @click="markRead(row)"
          >
            {{ markingRead[row.id] ? "Marking…" : "Mark read" }}
          </button>
        </li>
      </ul>

      <p class="muted note">
        Badge count is refreshed automatically in the app header while you’re logged in.
      </p>
    </div>
  </div>
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

.link {
  color: var(--accent);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--muted);
  user-select: none;
}

.spacer {
  flex: 1;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.item {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.75rem;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.item.unread {
  border-color: #c7d2fe;
  background: #eef2ff;
}

.meta {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.title {
  font-weight: 600;
}

.time {
  font-size: 0.9rem;
}

.mark {
  white-space: nowrap;
}

.note {
  margin-top: 0.75rem;
}
</style>
