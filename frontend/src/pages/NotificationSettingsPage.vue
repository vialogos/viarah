<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { NotificationPreferenceRow, ProjectNotificationSettingRow } from "../api/types";
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

          <table class="prefs">
            <thead>
              <tr>
                <th>Event</th>
                <th v-for="ch in channels" :key="ch.id">{{ ch.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="evt in eventTypes" :key="evt.id">
                <td>{{ evt.label }}</td>
                <td v-for="ch in channels" :key="ch.id" class="cell">
                  <input
                    type="checkbox"
                    :checked="Boolean(prefs[prefKey(evt.id, ch.id)])"
                    @change="setPref(evt.id, ch.id, ($event.target as HTMLInputElement).checked)"
                  />
                </td>
              </tr>
            </tbody>
          </table>

          <div class="actions">
            <button type="button" :disabled="savingPrefs" @click="savePreferences">
              {{ savingPrefs ? "Saving…" : "Save preferences" }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="canManageProjectSettings" class="card">
        <h2 class="section">Project settings (PM/admin)</h2>
        <p class="muted note">Disable specific event+channel pairs for everyone in this project.</p>

        <table class="prefs">
          <thead>
            <tr>
              <th>Event</th>
              <th v-for="ch in channels" :key="ch.id">{{ ch.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="evt in eventTypes" :key="evt.id">
              <td>{{ evt.label }}</td>
              <td v-for="ch in channels" :key="ch.id" class="cell">
                <input
                  type="checkbox"
                  :checked="Boolean(projectSettings[prefKey(evt.id, ch.id)])"
                  @change="
                    setProjectSetting(evt.id, ch.id, ($event.target as HTMLInputElement).checked)
                  "
                />
              </td>
            </tr>
          </tbody>
        </table>

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

.prefs {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.75rem;
}

.prefs th,
.prefs td {
  padding: 0.5rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.cell {
  width: 120px;
}

.actions {
  margin-top: 0.75rem;
  display: flex;
  gap: 0.75rem;
}
</style>
