<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type {
  NotificationPreferenceRow,
  ProjectNotificationSettingRow,
  PushVapidConfigStatus,
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

const vapidLoading = ref(false);
const vapidWorking = ref(false);
const vapidError = ref("");
const vapidConfig = ref<PushVapidConfigStatus | null>(null);
const vapidSubject = ref("");
const vapidPublicKeyDraft = ref("");
const vapidPrivateKeyDraft = ref("");

const prefs = ref<Record<string, boolean>>({});
const projectSettings = ref<Record<string, boolean>>({});

const eventTypes = [
  { id: "assignment.changed", label: "Assignment changed" },
  { id: "status.changed", label: "Status changed" },
  { id: "comment.created", label: "Comment created" },
  { id: "person_message.created", label: "Message received" },
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

async function refreshVapidConfig() {
  vapidError.value = "";
  vapidConfig.value = null;

  if (!canManageProjectSettings.value) {
    return;
  }

  vapidLoading.value = true;
  try {
    const res = await api.getPushVapidConfig();
    vapidConfig.value = res.config;
    if (!vapidSubject.value) {
      vapidSubject.value =
        res.config.subject ??
        (session.user?.email ? `mailto:${session.user.email}` : "");
    }
    if (!vapidPublicKeyDraft.value) {
      vapidPublicKeyDraft.value = res.config.public_key ?? "";
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      vapidError.value = "Not permitted.";
      return;
    }
    vapidError.value = err instanceof Error ? err.message : String(err);
  } finally {
    vapidLoading.value = false;
  }
}

async function generateVapidConfig() {
  vapidError.value = "";
  if (!canManageProjectSettings.value) {
    vapidError.value = "Not permitted.";
    return;
  }

  vapidWorking.value = true;
  try {
    const subject = String(vapidSubject.value || "").trim();
    const res = await api.generatePushVapidConfig(subject ? { subject } : undefined);
    vapidConfig.value = res.config;
    vapidPublicKeyDraft.value = res.config.public_key ?? "";
    vapidPrivateKeyDraft.value = "";
    await refreshPushStatus();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      vapidError.value = "Not permitted.";
      return;
    }
    vapidError.value = err instanceof Error ? err.message : String(err);
  } finally {
    vapidWorking.value = false;
  }
}

async function saveVapidConfig() {
  vapidError.value = "";
  if (!canManageProjectSettings.value) {
    vapidError.value = "Not permitted.";
    return;
  }

  vapidWorking.value = true;
  try {
    const publicKey = String(vapidPublicKeyDraft.value || "").trim();
    const privateKey = String(vapidPrivateKeyDraft.value || "").trim();
    const subject = String(vapidSubject.value || "").trim();
    const res = await api.patchPushVapidConfig({
      public_key: publicKey,
      private_key: privateKey,
      subject,
    });
    vapidConfig.value = res.config;
    vapidPublicKeyDraft.value = res.config.public_key ?? "";
    vapidPrivateKeyDraft.value = "";
    await refreshPushStatus();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      vapidError.value = "Not permitted.";
      return;
    }
    vapidError.value = err instanceof Error ? err.message : String(err);
  } finally {
    vapidWorking.value = false;
  }
}

async function clearVapidConfig() {
  vapidError.value = "";
  if (!canManageProjectSettings.value) {
    vapidError.value = "Not permitted.";
    return;
  }

  vapidWorking.value = true;
  try {
    const res = await api.deletePushVapidConfig();
    vapidConfig.value = res.config;
    vapidPublicKeyDraft.value = res.config.public_key ?? "";
    vapidPrivateKeyDraft.value = "";
    await refreshPushStatus();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      vapidError.value = "Not permitted.";
      return;
    }
    vapidError.value = err instanceof Error ? err.message : String(err);
  } finally {
    vapidWorking.value = false;
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
watch(() => canManageProjectSettings.value, () => void refreshVapidConfig(), { immediate: true });

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
        <pf-title h="1" size="2xl">Notification Preferences</pf-title>
        <pf-content>
          <p class="muted">Control which notifications you receive for this project.</p>
        </pf-content>
      </div>
      <pf-button variant="link" :to="inboxPath">Back to inbox</pf-button>
    </div>

    <pf-empty-state v-if="!context.orgId">
      <pf-empty-state-header title="Select an org" heading-level="h2" />
      <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
    </pf-empty-state>
    <pf-empty-state v-else-if="!context.projectId">
      <pf-empty-state-header title="Select a project" heading-level="h2" />
      <pf-empty-state-body>Select a project to continue.</pf-empty-state-body>
    </pf-empty-state>

    <div v-else class="stack">
      <pf-card>
        <pf-card-body>
          <div v-if="loading" class="loading-row">
            <pf-spinner size="md" aria-label="Loading notification preferences" />
          </div>
          <pf-alert v-else-if="error" inline variant="danger" :title="error" />
          <div v-else>
            <pf-title h="2" size="lg">Your preferences</pf-title>
            <pf-content>
              <p class="muted note">
                These are effective settings (project settings can override your preferences).
              </p>
            </pf-content>
            <pf-helper-text class="prefs-helper">
              <pf-helper-text-item>
                Use this matrix to enable or disable each event/channel pair for your account.
              </pf-helper-text-item>
            </pf-helper-text>

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
                    <pf-checkbox
                      :id="`pref-${evt.id}-${ch.id}`"
                      label=""
                      :aria-label="`${evt.label} ${ch.label}`"
                      :model-value="Boolean(prefs[prefKey(evt.id, ch.id)])"
                      @update:model-value="setPref(evt.id, ch.id, Boolean($event))"
                    />
                  </pf-td>
                </pf-tr>
              </pf-tbody>
            </pf-table>

            <div class="actions">
              <pf-button variant="primary" :disabled="savingPrefs" @click="savePreferences">
                {{ savingPrefs ? "Saving…" : "Save preferences" }}
              </pf-button>
            </div>
          </div>
        </pf-card-body>
      </pf-card>

      <pf-card>
        <pf-card-body>
          <div class="push-header">
            <pf-title h="2" size="lg">Push (this device)</pf-title>
            <pf-tooltip>
              <template #content>
                Push delivery requires browser permission and server-side VAPID configuration.
              </template>
              <pf-button variant="plain" aria-label="Push notification help">?</pf-button>
            </pf-tooltip>
          </div>
          <pf-content>
            <p class="muted note">
              Subscribe/unsubscribe this browser/device for push notifications. Delivery also depends on
              your Push preference for each event above.
            </p>
          </pf-content>

          <div v-if="pushLoading" class="loading-row">
            <pf-spinner size="md" aria-label="Loading push notification status" />
          </div>
          <pf-empty-state v-else-if="!pushSupported">
            <pf-empty-state-header title="Push not available" heading-level="h3" />
            <pf-empty-state-body>
              <span v-if="!pushHasSecureContext">Push requires HTTPS (or http://localhost).</span>
              <span v-else>Push is not supported in this browser/device.</span>
            </pf-empty-state-body>
          </pf-empty-state>
          <div v-else class="push-stack">
            <pf-description-list columns="2Col">
              <pf-description-list-group>
                <pf-description-list-term>Permission</pf-description-list-term>
                <pf-description-list-description>{{ pushPermission }}</pf-description-list-description>
              </pf-description-list-group>
              <pf-description-list-group>
                <pf-description-list-term>Status</pf-description-list-term>
                <pf-description-list-description>{{ pushStatusLabel }}</pf-description-list-description>
              </pf-description-list-group>
            </pf-description-list>

            <pf-alert
              v-if="pushConfigured === false"
              inline
              variant="danger"
              title="Push is not configured on the server (VAPID keys missing)."
            />
            <pf-alert
              v-if="pushPermission === 'denied'"
              inline
              variant="danger"
              title="Notifications permission is blocked for this site."
            >
              Enable it in your browser settings to subscribe.
            </pf-alert>
            <pf-alert v-if="pushError" inline variant="danger" :title="pushError" />

	            <div class="actions">
	              <pf-button variant="primary" :disabled="pushWorking || !canSubscribePush" @click="subscribeToPush">
	                {{ pushWorking ? "Working…" : "Subscribe" }}
	              </pf-button>
              <pf-button
                variant="secondary"
                :disabled="pushWorking || !canUnsubscribePush"
                @click="unsubscribeFromPush"
	              >
	                {{ pushWorking ? "Working…" : "Unsubscribe" }}
	              </pf-button>
	            </div>

            <pf-divider v-if="canManageProjectSettings" />

            <div v-if="canManageProjectSettings" class="push-server">
              <pf-title h="3" size="md">Server configuration (PM/admin)</pf-title>

              <div v-if="vapidLoading" class="loading-row">
                <pf-spinner size="md" aria-label="Loading VAPID config" />
              </div>
              <pf-alert v-else-if="vapidError" inline variant="danger" :title="vapidError" />
              <div v-else class="push-server-stack">
                <pf-description-list columns="2Col" v-if="vapidConfig">
                  <pf-description-list-group>
                    <pf-description-list-term>Configured</pf-description-list-term>
                    <pf-description-list-description>
                      {{ vapidConfig.configured ? "Yes" : "No" }}
                    </pf-description-list-description>
                  </pf-description-list-group>
                  <pf-description-list-group>
                    <pf-description-list-term>Source</pf-description-list-term>
                    <pf-description-list-description>{{ vapidConfig.source }}</pf-description-list-description>
                  </pf-description-list-group>
                  <pf-description-list-group>
                    <pf-description-list-term>Subject</pf-description-list-term>
                    <pf-description-list-description>
                      {{ vapidConfig.subject ?? "—" }}
                    </pf-description-list-description>
                  </pf-description-list-group>
                  <pf-description-list-group>
                    <pf-description-list-term>Private key stored</pf-description-list-term>
                    <pf-description-list-description>
                      {{ vapidConfig.private_key_configured ? "Yes" : "No" }}
                    </pf-description-list-description>
                  </pf-description-list-group>
                  <pf-description-list-group>
                    <pf-description-list-term>Encryption ready</pf-description-list-term>
                    <pf-description-list-description>
                      {{ vapidConfig.encryption_configured ? "Yes" : "No" }}
                    </pf-description-list-description>
                  </pf-description-list-group>
                  <pf-description-list-group>
                    <pf-description-list-term>Error</pf-description-list-term>
                    <pf-description-list-description>
                      {{ vapidConfig.error_code ?? "—" }}
                    </pf-description-list-description>
                  </pf-description-list-group>
                </pf-description-list>

                <pf-alert
                  v-if="vapidConfig && !vapidConfig.encryption_configured"
                  inline
                  variant="warning"
                  title="Server encryption is not configured."
                >
                  Set `VIA_RAH_ENCRYPTION_KEY` so the server can decrypt the stored VAPID private key.
                </pf-alert>

	                <pf-form class="push-server-form" @submit.prevent="saveVapidConfig">
                  <pf-form-group label="Subject" field-id="vapid-subject">
                    <pf-text-input
                      id="vapid-subject"
                      v-model="vapidSubject"
                      type="text"
                      placeholder="mailto:notifications@example.com"
                    />
                  </pf-form-group>
                  <pf-form-group label="Public key" field-id="vapid-public-key">
                    <pf-textarea
                      id="vapid-public-key"
                      v-model="vapidPublicKeyDraft"
                      rows="2"
                      spellcheck="false"
                      class="mono"
                    />
                  </pf-form-group>
                  <pf-form-group label="Private key" field-id="vapid-private-key">
                    <pf-textarea
                      id="vapid-private-key"
                      v-model="vapidPrivateKeyDraft"
                      rows="2"
                      spellcheck="false"
                      class="mono"
                      placeholder="Paste private key to save (never displayed after saving)"
                    />
                  </pf-form-group>

	                  <div class="actions">
	                    <pf-button variant="primary" :disabled="vapidWorking" type="submit">
	                      {{ vapidWorking ? "Working…" : "Save keys" }}
	                    </pf-button>
                    <pf-button variant="secondary" :disabled="vapidWorking" type="button" @click="generateVapidConfig">
                      {{ vapidWorking ? "Working…" : "Generate keys" }}
                    </pf-button>
                    <pf-button variant="danger" :disabled="vapidWorking" type="button" @click="clearVapidConfig">
                      {{ vapidWorking ? "Working…" : "Clear DB keys" }}
                    </pf-button>
                  </div>
                </pf-form>
              </div>
            </div>
          </div>
        </pf-card-body>
      </pf-card>

      <pf-card v-if="canManageProjectSettings">
        <pf-card-body>
          <pf-title h="2" size="lg">Project settings (PM/admin)</pf-title>
          <pf-content>
            <p class="muted note">Disable specific event+channel pairs for everyone in this project.</p>
          </pf-content>
          <pf-helper-text class="prefs-helper">
            <pf-helper-text-item variant="warning">
              Disabling a channel here overrides individual user preferences for this project.
            </pf-helper-text-item>
          </pf-helper-text>

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
                  <pf-checkbox
                    :id="`project-pref-${evt.id}-${ch.id}`"
                    label=""
                    :aria-label="`Project ${evt.label} ${ch.label}`"
                    :model-value="Boolean(projectSettings[prefKey(evt.id, ch.id)])"
                    @update:model-value="setProjectSetting(evt.id, ch.id, Boolean($event))"
                  />
                </pf-td>
              </pf-tr>
            </pf-tbody>
          </pf-table>

          <div class="actions">
            <pf-button variant="primary" :disabled="savingProject" @click="saveProjectSettings">
              {{ savingProject ? "Saving…" : "Save project settings" }}
            </pf-button>
          </div>
        </pf-card-body>
      </pf-card>
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

.push-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.note {
  margin-top: 0;
}

.prefs-helper {
  margin-bottom: 0.75rem;
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

.push-server {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.push-server-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.push-server-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}
</style>
