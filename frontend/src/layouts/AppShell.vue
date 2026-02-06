<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import OrgProjectSwitcher from "../components/OrgProjectSwitcher.vue";
import { buildShellNavModel } from "./appShellNav";
import { useContextStore } from "../stores/context";
import { useNotificationsStore } from "../stores/notifications";
import { useSessionStore } from "../stores/session";

const route = useRoute();
const router = useRouter();
const session = useSessionStore();
const context = useContextStore();
const notifications = useNotificationsStore();

const sidebarOpen = ref(false);
let desktopMediaQuery: MediaQueryList | null = null;

const currentOrgRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((membership) => membership.org.id === context.orgId)?.role ?? "";
});

const canAccessOrgAdminRoutes = computed(
  () => Boolean(context.orgId) && (currentOrgRole.value === "admin" || currentOrgRole.value === "pm")
);

const shellNav = computed(() =>
  buildShellNavModel({
    canAccessOrgAdminRoutes: canAccessOrgAdminRoutes.value,
    canAccessOutputsUi: canAccessOrgAdminRoutes.value,
  })
);

const unreadCountLabel = computed(() => {
  if (notifications.unreadCount <= 0) {
    return "";
  }
  if (notifications.unreadCount > 99) {
    return "99+";
  }
  return String(notifications.unreadCount);
});

async function logout() {
  await session.logout();
  await router.push("/login");
}

function closeSidebar() {
  sidebarOpen.value = false;
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value;
}

function handleDesktopMediaChange(event: MediaQueryListEvent) {
  if (event.matches) {
    sidebarOpen.value = false;
  }
}

onMounted(() => {
  context.syncFromMemberships(session.memberships);

  if (typeof window !== "undefined") {
    desktopMediaQuery = window.matchMedia("(min-width: 960px)");
    desktopMediaQuery.addEventListener("change", handleDesktopMediaChange);
  }
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

watch(
  () => route.fullPath,
  () => {
    closeSidebar();
  }
);

onUnmounted(() => {
  notifications.stopPolling();
  desktopMediaQuery?.removeEventListener("change", handleDesktopMediaChange);
});
</script>

<template>
  <div class="app-shell">
    <aside id="internal-sidebar" class="sidebar" :class="{ open: sidebarOpen }">
      <div class="brand">ViaRah</div>

      <nav class="sidebar-nav" aria-label="Internal navigation">
        <RouterLink
          v-for="item in shellNav.primary"
          :key="item.label"
          class="sidebar-link"
          :to="item.to"
          active-class="active"
        >
          {{ item.label }}
        </RouterLink>

        <div v-if="shellNav.settings.length > 0" class="sidebar-group">
          <div class="sidebar-group-label">Settings</div>
          <RouterLink
            v-for="item in shellNav.settings"
            :key="item.label"
            class="sidebar-link sidebar-link-sub"
            :to="item.to"
            active-class="active"
          >
            {{ item.label }}
          </RouterLink>
        </div>
      </nav>
    </aside>

    <button
      v-if="sidebarOpen"
      class="sidebar-backdrop"
      type="button"
      aria-label="Close navigation"
      @click="closeSidebar"
    />

    <div class="workspace">
      <header class="utility-bar">
        <button
          type="button"
          class="menu-toggle"
          aria-label="Toggle navigation"
          aria-controls="internal-sidebar"
          :aria-expanded="sidebarOpen ? 'true' : 'false'"
          @click="toggleSidebar"
        >
          Menu
        </button>

        <RouterLink class="utility-link" to="/notifications" active-class="active">
          Notifications
          <span v-if="unreadCountLabel" class="badge">{{ unreadCountLabel }}</span>
        </RouterLink>

        <RouterLink
          v-for="action in shellNav.quickActions"
          :key="action.label"
          class="utility-action"
          :to="action.to"
        >
          {{ action.label }}
        </RouterLink>

        <div class="utility-spacer" />

        <OrgProjectSwitcher />

        <div v-if="session.user" class="user muted" :title="session.user.email">
          {{ session.user.display_name || session.user.email }}
        </div>

        <button type="button" @click="logout">Logout</button>
      </header>

      <main class="container content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  background: var(--bg);
}

.sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  width: 260px;
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 1rem 0.75rem;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  transform: translateX(-100%);
  transition: transform 180ms ease;
  z-index: 30;
}

.sidebar.open {
  transform: translateX(0);
}

.brand {
  font-weight: 700;
  padding: 0 0.5rem;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sidebar-link {
  display: block;
  border-radius: 10px;
  color: var(--text);
  text-decoration: none;
  padding: 0.5rem 0.65rem;
}

.sidebar-link:hover {
  background: #f3f4f6;
  text-decoration: none;
}

.sidebar-link.active {
  background: #eef2ff;
  color: var(--accent);
}

.sidebar-group {
  margin-top: 0.75rem;
  border-top: 1px solid var(--border);
  padding-top: 0.75rem;
}

.sidebar-group-label {
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 0 0.65rem 0.35rem;
}

.sidebar-link-sub {
  font-size: 0.92rem;
}

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  border: 0;
  padding: 0;
  background: rgba(17, 24, 39, 0.35);
  z-index: 20;
}

.workspace {
  flex: 1;
  min-width: 0;
}

.utility-bar {
  position: sticky;
  top: 0;
  z-index: 15;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  flex-wrap: wrap;
}

.menu-toggle {
  display: inline-flex;
  align-items: center;
}

.utility-link,
.utility-action {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 0.35rem 0.55rem;
  color: var(--text);
  text-decoration: none;
  background: var(--panel);
}

.utility-link.active,
.utility-action.active {
  border-color: #c7d2fe;
  background: #eef2ff;
  color: var(--accent);
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.35rem;
  border-radius: 999px;
  background: var(--accent);
  color: #ffffff;
  font-size: 0.75rem;
  line-height: 1;
}

.utility-spacer {
  flex: 1;
}

.user {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.content {
  padding-top: 1.25rem;
}

@media (min-width: 960px) {
  .sidebar {
    transform: translateX(0);
  }

  .sidebar-backdrop,
  .menu-toggle {
    display: none;
  }

  .workspace {
    margin-left: 260px;
  }

  .utility-bar {
    flex-wrap: nowrap;
  }
}

@media (max-width: 959px) {
  .utility-spacer {
    display: none;
  }

  .user {
    max-width: 100%;
  }
}
</style>
