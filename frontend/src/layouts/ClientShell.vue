<script setup lang="ts">
import { onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";

import OrgProjectSwitcher from "../components/OrgProjectSwitcher.vue";
import { useContextStore } from "../stores/context";
import { useNotificationsStore } from "../stores/notifications";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const session = useSessionStore();
const context = useContextStore();
const notifications = useNotificationsStore();

async function logout() {
  await session.logout();
  await router.push("/login");
}

onMounted(() => {
  context.syncFromMemberships(session.memberships);
});

watch(
  () => context.orgId,
  async (nextOrgId, prevOrgId) => {
    if (nextOrgId && nextOrgId !== prevOrgId) {
      await context.refreshProjects();
    }
  },
  { immediate: true }
);

watch(
  () => [session.user?.id, context.orgId, context.projectId],
  ([userId, orgId, projectId]) => {
    if (userId && orgId) {
      notifications.startPolling({ orgId, projectId: projectId || undefined });
      return;
    }

    notifications.stopPolling();
  },
  { immediate: true }
);

onUnmounted(() => {
  notifications.stopPolling();
});
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <div class="brand">ViaRah</div>
      <nav v-if="session.user" class="nav">
        <RouterLink class="nav-link" to="/client" active-class="active">Overview</RouterLink>
        <RouterLink class="nav-link" to="/client/tasks" active-class="active">Tasks</RouterLink>
        <RouterLink class="nav-link" to="/client/sows" active-class="active">SoWs</RouterLink>
        <RouterLink class="nav-link" to="/client/timeline" active-class="active">Timeline</RouterLink>
        <RouterLink class="nav-link" to="/client/gantt" active-class="active">Gantt</RouterLink>
        <RouterLink class="nav-link" to="/client/notifications" active-class="active">
          Notifications
          <span v-if="notifications.unreadCount > 0" class="pf-v6-c-badge pf-m-unread">{{
            notifications.unreadCount
          }}</span>
        </RouterLink>
      </nav>
      <div class="spacer" />
      <div v-if="session.user" class="user muted" :title="session.user.email">
        {{ session.user.display_name || session.user.email }}
      </div>
      <OrgProjectSwitcher />
      <button type="button" class="pf-v6-c-button pf-m-secondary pf-m-small" @click="logout">Logout</button>
    </header>

    <main class="container">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.brand {
  font-weight: 700;
}

.nav {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.nav-link {
  text-decoration: none;
  color: var(--text);
  padding: 0.25rem 0.5rem;
  border-radius: 8px;
}

.nav-link.active {
  background: #eef2ff;
  color: var(--accent);
}

.spacer {
  flex: 1;
}

.user {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
