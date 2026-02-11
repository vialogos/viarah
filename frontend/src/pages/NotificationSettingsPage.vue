<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type {
  NotificationPreferenceRow,
  ProjectNotificationSettingRow,
  PushSubscriptionRow,
} from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const loading = ref(false);
const savingPrefs = ref(false);
const savingProject = ref(false);
const error = ref("");
const pushLoading = ref(false);
const pushWorking = ref(false);
const pushError = ref("");

const pushSupported = ref(false);
const pushHasSecureContext = ref(true);
const pushPermission = ref<NotificationPermission>("default");
const pushConfigured = ref<boolean | null>(null);
const pushVapidPublicKey = ref<string | null>(null);
const pushBrowserEndpoint = ref<string | null>(null);
const pushServerMatch = ref<PushSubscriptionRow | null>(null);

const prefs = ref<Record<string, boolean>>({});
const projectSettings = ref<Record<string, boolean>>({});

const eventTypes = [
  { id: "assignment.changed", label: "Assignment changed" },
  { id: "status.changed", label: "Status changed" },
  { id: "comment.created", label: "Comment created" },
  { id: "report.published", label: "Report published" },
];
const channels = [
  { id: "in_app", label: "In-app" },
  { id: "email", label: "Email" },
  { id: "push", label: "Push" },
];

const isClientOnly = computed(
  () => session.memberships.length > 0 && session.memberships.every((m) => m.role === "client")
);

const inboxPath = computed(() => (isClientOnly.value ? "/client/notifications" : "/notifications"));

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManageProjectSettings = computed(
  () => currentRole.value === "admin" || currentRole.value === "pm"
);

const pushStatusLabel = computed(() => {
  if (!pushSupported.value) {
    return "Not supported";
  }

  if (pushPermission.value === "denied") {
    return "Permission blocked";
  }

  const hasBrowserSub = Boolean(pushBrowserEndpoint.value);
  const hasServerMatch = Boolean(pushServerMatch.value);
  if (hasBrowserSub && hasServerMatch) {
    return "Subscribed";
  }
  if (hasBrowserSub && !hasServerMatch) {
    return "Subscribed (not saved on server)";
  }
  return "Not subscribed";
});

const canSubscribePush = computed(() => {
  if (!pushSupported.value) {
    return false;
  }
  if (pushPermission.value === "denied") {
    return false;
  }
  if (pushConfigured.value === false) {
    return false;
  }
  return true;
});

const canUnsubscribePush = computed(
  () => pushSupported.value && Boolean(pushBrowserEndpoint.value)
);

function prefKey(eventType: string, channel: string): string {
  return `${eventType}:${channel}`;
}

function setPref(eventType: string, channel: string, enabled: boolean) {
  prefs.value[prefKey(eventType, channel)] = enabled;
}

function setProjectSetting(eventType: string, channel: string, enabled: boolean) {
  projectSettings.value[prefKey(eventType, channel)] = enabled;
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

function refreshPushEnvironmentFlags() {
  pushHasSecureContext.value = typeof window !== "undefined" ? Boolean(window.isSecureContext) : true;
  pushSupported.value =
    pushHasSecureContext.value &&
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window;

  pushPermission.value =
    typeof window !== "undefined" && "Notification" in window ? Notification.permission : "default";
}

function base64UrlToUint8Array(base64Url: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray: Uint8Array<ArrayBuffer> = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function ensureServiceWorkerRegistration(): Promise<ServiceWorkerRegistration> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    throw new Error("Service workers are not supported in this browser/device.");
  }

  const reg = await navigator.serviceWorker.register("/service-worker.js");
  await navigator.serviceWorker.ready;
  return reg;
}

async function refreshPushStatus() {
  pushError.value = "";
  pushConfigured.value = null;
  pushVapidPublicKey.value = null;
  pushBrowserEndpoint.value = null;
  pushServerMatch.value = null;

  refreshPushEnvironmentFlags();

  if (!context.orgId || !context.projectId) {
    return;
  }
  if (!pushSupported.value) {
    return;
  }

  pushLoading.value = true;
  try {
    try {
      const res = await api.getPushVapidPublicKey();
      pushConfigured.value = true;
      pushVapidPublicKey.value = res.public_key;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await handleUnauthorized();
        return;
      }
      if (err instanceof ApiError && err.status === 503) {
        pushConfigured.value = false;
      } else {
        throw err;
      }
    }

    const reg = await ensureServiceWorkerRegistration();
    const browserSub = await reg.pushManager.getSubscription();
    pushBrowserEndpoint.value = browserSub?.endpoint ?? null;

    const subsRes = await api.listPushSubscriptions();
    if (pushBrowserEndpoint.value) {
      pushServerMatch.value =
        subsRes.subscriptions.find((s) => s.endpoint === pushBrowserEndpoint.value) ?? null;
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    pushError.value = err instanceof Error ? err.message : String(err);
  } finally {
    pushLoading.value = false;
  }
}

async function subscribeToPush() {
  pushError.value = "";
  refreshPushEnvironmentFlags();

  if (!context.orgId || !context.projectId) {
    pushError.value = "Select an org and project to continue.";
    return;
  }
  if (!pushSupported.value) {
    pushError.value = pushHasSecureContext.value
      ? "Push is not supported in this browser/device."
      : "Push requires HTTPS (or http://localhost).";
    return;
  }

  pushWorking.value = true;
  try {
    const perm = await Notification.requestPermission();
    pushPermission.value = perm;
    if (perm !== "granted") {
      pushError.value = "Notification permission was not granted.";
      return;
    }

    const reg = await ensureServiceWorkerRegistration();

    let publicKey = pushVapidPublicKey.value;
    if (!publicKey) {
      try {
        const res = await api.getPushVapidPublicKey();
        publicKey = res.public_key;
        pushVapidPublicKey.value = publicKey;
        pushConfigured.value = true;
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          await handleUnauthorized();
          return;
        }
        if (err instanceof ApiError && err.status === 503) {
          pushConfigured.value = false;
          pushError.value = "Push is not configured on the server.";
          return;
        }
        throw err;
      }
    }

    const appServerKey = base64UrlToUint8Array(publicKey);
    const subscription = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: appServerKey,
    });

    await api.createPushSubscription(subscription.toJSON(), navigator.userAgent);
    await refreshPushStatus();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    pushError.value = err instanceof Error ? err.message : String(err);
  } finally {
    pushWorking.value = false;
  }
}

async function unsubscribeFromPush() {
  pushError.value = "";
  refreshPushEnvironmentFlags();

  if (!context.orgId || !context.projectId) {
    pushError.value = "Select an org and project to continue.";
    return;
  }
  if (!pushSupported.value) {
    pushError.value = pushHasSecureContext.value
      ? "Push is not supported in this browser/device."
      : "Push requires HTTPS (or http://localhost).";
    return;
  }

  pushWorking.value = true;
  try {
    const reg = await ensureServiceWorkerRegistration();
    const sub = await reg.pushManager.getSubscription();
    if (!sub) {
      await refreshPushStatus();
      return;
    }

    const endpoint = sub.endpoint;
    try {
      const list = await api.listPushSubscriptions();
      const match = list.subscriptions.find((s) => s.endpoint === endpoint);
      if (match?.id) {
        await api.deletePushSubscription(match.id);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await handleUnauthorized();
        return;
      }
      if (!(err instanceof ApiError && err.status === 404)) {
        throw err;
      }
    }

    await sub.unsubscribe();
    await refreshPushStatus();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    pushError.value = err instanceof Error ? err.message : String(err);
  } finally {
    pushWorking.value = false;
  }
}

async function refresh() {
  error.value = "";
  if (!context.orgId || !context.projectId) {
    prefs.value = {};
    projectSettings.value = {};
    return;
  }

  loading.value = true;
  try {
    const [prefsRes, projectRes] = await Promise.all([
      api.getNotificationPreferences(context.orgId, context.projectId),
      canManageProjectSettings.value
        ? api.getProjectNotificationSettings(context.orgId, context.projectId)
        : Promise.resolve({ settings: [] as ProjectNotificationSettingRow[] }),
    ]);

    const nextPrefs: Record<string, boolean> = {};
    for (const row of prefsRes.preferences) {
      nextPrefs[prefKey(row.event_type, row.channel)] = Boolean(row.enabled);
    }
    prefs.value = nextPrefs;

    const nextProject: Record<string, boolean> = {};
    for (const row of projectRes.settings) {
      nextProject[prefKey(row.event_type, row.channel)] = Boolean(row.enabled);
    }
    projectSettings.value = nextProject;
  } catch (err) {
    prefs.value = {};
    projectSettings.value = {};
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => [context.orgId, context.projectId, canManageProjectSettings.value], () => void refresh(), {
  immediate: true,
});

watch(() => [context.orgId, context.projectId], () => void refreshPushStatus(), { immediate: true });

async function savePreferences() {
  if (!context.orgId || !context.projectId) {
    return;
  }

  error.value = "";
  savingPrefs.value = true;
  try {
    const payload: NotificationPreferenceRow[] = [];
    for (const evt of eventTypes) {
      for (const ch of channels) {
        payload.push({
          event_type: evt.id,
          channel: ch.id,
          enabled: Boolean(prefs.value[prefKey(evt.id, ch.id)]),
        });
      }
    }

    const res = await api.patchNotificationPreferences(context.orgId, context.projectId, payload);
    const nextPrefs: Record<string, boolean> = {};
    for (const row of res.preferences) {
      nextPrefs[prefKey(row.event_type, row.channel)] = Boolean(row.enabled);
    }
    prefs.value = nextPrefs;
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
    savingPrefs.value = false;
  }
}

async function saveProjectSettings() {
  if (!context.orgId || !context.projectId) {
    return;
  }
  if (!canManageProjectSettings.value) {
    error.value = "Not permitted.";
    return;
  }

  error.value = "";
  savingProject.value = true;
  try {
    const payload: ProjectNotificationSettingRow[] = [];
    for (const evt of eventTypes) {
      for (const ch of channels) {
        payload.push({
          event_type: evt.id,
          channel: ch.id,
          enabled: Boolean(projectSettings.value[prefKey(evt.id, ch.id)]),
        });
      }
    }

    const res = await api.patchProjectNotificationSettings(context.orgId, context.projectId, payload);
    const nextProject: Record<string, boolean> = {};
    for (const row of res.settings) {
      nextProject[prefKey(row.event_type, row.channel)] = Boolean(row.enabled);
    }
    projectSettings.value = nextProject;
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
    savingProject.value = false;
  }
}
</script>

<template>
  <div>
    <div class="header">
      <div>
        <h1 class="page-title">Notification Preferences</h1>
        <p class="muted">Control which notifications you receive for this project.</p>
      </div>
      <RouterLink class="muted" :to="inboxPath">Back to inbox</RouterLink>
    </div>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>
    <p v-else-if="!context.projectId" class="card">Select a project to continue.</p>

    <div v-else class="stack">
      <div class="card">
        <div v-if="loading" class="muted">Loading…</div>
        <div v-else-if="error" class="error">{{ error }}</div>
        <div v-else>
          <h2 class="section">Your preferences</h2>
          <p class="muted note">
            These are effective settings (project settings can override your preferences).
          </p>

          <pf-table aria-label="Notification user preferences">
            <pf-thead>
              <pf-tr>
                <pf-th>Event</pf-th>
                <pf-th v-for="ch in channels" :key="ch.id">
                  {{ ch.label }}
                </pf-th>
              </pf-tr>
            </pf-thead>
            <pf-tbody>
              <pf-tr v-for="evt in eventTypes" :key="evt.id">
                <pf-td data-label="Event">
                  {{ evt.label }}
                </pf-td>
                <pf-td v-for="ch in channels" :key="ch.id" class="cell" :data-label="ch.label">
                  <input
                    type="checkbox"
                    :checked="Boolean(prefs[prefKey(evt.id, ch.id)])"
                    @change="setPref(evt.id, ch.id, ($event.target as HTMLInputElement).checked)"
                  />
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>

          <div class="actions">
            <button type="button" :disabled="savingPrefs" @click="savePreferences">
              {{ savingPrefs ? "Saving…" : "Save preferences" }}
            </button>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 class="section">Push (this device)</h2>
        <p class="muted note">
          Subscribe/unsubscribe this browser/device for push notifications. Delivery also depends on
          your Push preference for each event above.
        </p>

        <div v-if="pushLoading" class="muted">Loading…</div>
        <div v-else-if="!pushSupported" class="muted">
          <span v-if="!pushHasSecureContext">Push requires HTTPS (or http://localhost).</span>
          <span v-else>Push is not supported in this browser/device.</span>
        </div>
        <div v-else class="push-stack">
          <div class="push-grid">
            <div>
              <div class="muted">Permission</div>
              <div>{{ pushPermission }}</div>
            </div>
            <div>
              <div class="muted">Status</div>
              <div>{{ pushStatusLabel }}</div>
            </div>
          </div>

          <p v-if="pushConfigured === false" class="error">
            Push is not configured on the server (VAPID keys missing).
          </p>
          <p v-if="pushPermission === 'denied'" class="error">
            Notifications permission is blocked for this site. Enable it in your browser settings
            to subscribe.
          </p>
          <p v-if="pushError" class="error">{{ pushError }}</p>

          <div class="actions">
            <button type="button" :disabled="pushWorking || !canSubscribePush" @click="subscribeToPush">
              {{ pushWorking ? "Working…" : "Subscribe" }}
            </button>
            <button
              type="button"
              :disabled="pushWorking || !canUnsubscribePush"
              @click="unsubscribeFromPush"
            >
              {{ pushWorking ? "Working…" : "Unsubscribe" }}
            </button>
            <button type="button" :disabled="pushWorking" @click="refreshPushStatus">
              Refresh status
            </button>
          </div>
        </div>
      </div>

      <div v-if="canManageProjectSettings" class="card">
        <h2 class="section">Project settings (PM/admin)</h2>
        <p class="muted note">Disable specific event+channel pairs for everyone in this project.</p>

        <pf-table aria-label="Project notification settings">
          <pf-thead>
            <pf-tr>
              <pf-th>Event</pf-th>
              <pf-th v-for="ch in channels" :key="ch.id">
                {{ ch.label }}
              </pf-th>
            </pf-tr>
          </pf-thead>
          <pf-tbody>
            <pf-tr v-for="evt in eventTypes" :key="evt.id">
              <pf-td data-label="Event">
                {{ evt.label }}
              </pf-td>
              <pf-td v-for="ch in channels" :key="ch.id" class="cell" :data-label="ch.label">
                <input
                  type="checkbox"
                  :checked="Boolean(projectSettings[prefKey(evt.id, ch.id)])"
                  @change="
                    setProjectSetting(evt.id, ch.id, ($event.target as HTMLInputElement).checked)
                  "
                />
              </pf-td>
            </pf-tr>
          </pf-tbody>
        </pf-table>

        <div class="actions">
          <button type="button" :disabled="savingProject" @click="saveProjectSettings">
            {{ savingProject ? "Saving…" : "Save project settings" }}
          </button>
        </div>
      </div>
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

.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.section {
  margin: 0 0 0.25rem 0;
  font-size: 1.05rem;
}

.note {
  margin-top: 0;
}

.cell {
  width: 120px;
}

.actions {
  margin-top: 0.75rem;
  display: flex;
  gap: 0.75rem;
}

.push-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.push-grid {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}
</style>
