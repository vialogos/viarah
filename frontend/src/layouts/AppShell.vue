<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Dialog, DialogPanel, TransitionChild, TransitionRoot } from "@headlessui/vue";
import { Bell, ChevronsLeft, ChevronsRight, LogOut, Menu, X } from "lucide-vue-next";

import OrgProjectSwitcher from "../components/OrgProjectSwitcher.vue";
import { buildShellNavModel } from "./appShellNav";
import SidebarNavigation from "./SidebarNavigation.vue";
import { shellIconMap } from "./shellIcons";
import { useContextStore } from "../stores/context";
import { useNotificationsStore } from "../stores/notifications";
import { useSessionStore } from "../stores/session";

const route = useRoute();
const router = useRouter();
const session = useSessionStore();
const context = useContextStore();
const notifications = useNotificationsStore();

const sidebarOpen = ref(false);
const desktopSidebarCollapsed = ref(false);
let desktopMediaQuery: MediaQueryList | null = null;
const desktopSidebarStorageKey = "viarah.shell.desktop_sidebar_collapsed";

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

function toggleDesktopSidebar() {
  desktopSidebarCollapsed.value = !desktopSidebarCollapsed.value;
}

function handleDesktopMediaChange(event: MediaQueryListEvent) {
  if (event.matches) {
    sidebarOpen.value = false;
  }
}

onMounted(() => {
  context.syncFromMemberships(session.memberships);

  if (typeof window !== "undefined") {
    const persistedState = window.localStorage.getItem(desktopSidebarStorageKey);
    if (persistedState !== null) {
      desktopSidebarCollapsed.value = persistedState === "true";
    }

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

watch(desktopSidebarCollapsed, (value) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(desktopSidebarStorageKey, String(value));
});

onUnmounted(() => {
  notifications.stopPolling();
  desktopMediaQuery?.removeEventListener("change", handleDesktopMediaChange);
});
</script>

<template>
  <div class="app-shell">
    <TransitionRoot as="template" :show="sidebarOpen">
      <Dialog class="mobile-sidebar-root" @close="closeSidebar">
        <TransitionChild
          as="template"
          enter="fade-enter-active"
          enter-from="fade-enter-from"
          enter-to="fade-enter-to"
          leave="fade-leave-active"
          leave-from="fade-leave-from"
          leave-to="fade-leave-to"
        >
          <div class="sidebar-backdrop" />
        </TransitionChild>

        <div class="mobile-sidebar-wrapper">
          <TransitionChild
            as="template"
            enter="slide-enter-active"
            enter-from="slide-enter-from"
            enter-to="slide-enter-to"
            leave="slide-leave-active"
            leave-from="slide-leave-from"
            leave-to="slide-leave-to"
          >
            <DialogPanel id="internal-sidebar" class="sidebar mobile-sidebar">
              <div class="sidebar-header">
                <div class="brand">ViaRah</div>
                <button
                  type="button"
                  class="mobile-close pf-v6-c-button pf-m-plain pf-m-small"
                  aria-label="Close navigation"
                  @click="closeSidebar"
                >
                  <X class="utility-icon" aria-hidden="true" />
                </button>
              </div>
              <SidebarNavigation :groups="shellNav.groups" @navigate="closeSidebar" />
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <aside class="sidebar desktop-sidebar" :class="{ collapsed: desktopSidebarCollapsed }">
      <div class="sidebar-header">
        <div class="brand" :title="'ViaRah'">{{ desktopSidebarCollapsed ? "VR" : "ViaRah" }}</div>
        <button
          type="button"
          class="desktop-collapse pf-v6-c-button pf-m-control pf-m-small"
          :aria-label="desktopSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          :aria-pressed="desktopSidebarCollapsed ? 'true' : 'false'"
          @click="toggleDesktopSidebar"
        >
          <component :is="desktopSidebarCollapsed ? ChevronsRight : ChevronsLeft" class="utility-icon" aria-hidden="true" />
          <span class="collapse-label">{{ desktopSidebarCollapsed ? "Expand" : "Collapse" }}</span>
        </button>
      </div>
      <SidebarNavigation :groups="shellNav.groups" :collapsed="desktopSidebarCollapsed" />
    </aside>

    <div class="workspace">
      <header class="utility-bar">
        <button
          type="button"
          class="menu-toggle pf-v6-c-button pf-m-control pf-m-small"
          aria-label="Toggle navigation"
          aria-controls="internal-sidebar"
          :aria-expanded="sidebarOpen ? 'true' : 'false'"
          @click="toggleSidebar"
        >
          <Menu class="utility-icon" aria-hidden="true" />
          <span>Menu</span>
        </button>

        <RouterLink class="utility-link pf-v6-c-button pf-m-control pf-m-small" to="/notifications" active-class="active">
          <Bell class="utility-icon" aria-hidden="true" />
          <span>Notifications</span>
          <span v-if="unreadCountLabel" class="badge pf-v6-c-badge pf-m-unread">{{ unreadCountLabel }}</span>
        </RouterLink>

        <RouterLink
          v-for="action in shellNav.quickActions"
          :key="action.id"
          class="utility-action pf-v6-c-button pf-m-control pf-m-small"
          :to="action.to"
          active-class="active"
        >
          <component :is="shellIconMap[action.icon]" class="utility-icon" aria-hidden="true" />
          <span>{{ action.label }}</span>
        </RouterLink>

        <div class="utility-spacer" />

        <OrgProjectSwitcher />

        <div v-if="session.user" class="user muted" :title="session.user.email">
          {{ session.user.display_name || session.user.email }}
        </div>

        <button type="button" class="logout-action pf-v6-c-button pf-m-secondary pf-m-small" @click="logout">
          <LogOut class="utility-icon" aria-hidden="true" />
          <span>Logout</span>
        </button>
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
  box-sizing: border-box;
  background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.desktop-sidebar {
  display: none;
  width: 300px;
  padding: 1rem 0.75rem;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
  overflow-x: visible;
  transition: width 180ms ease, padding 180ms ease;
}

.desktop-sidebar.collapsed {
  width: 88px;
  padding: 1rem 0.5rem;
}

.mobile-sidebar-root {
  position: relative;
  z-index: 40;
}

.mobile-sidebar-wrapper {
  position: fixed;
  inset: 0;
  display: flex;
  pointer-events: none;
}

.mobile-sidebar {
  pointer-events: auto;
  width: min(84vw, 300px);
  height: 100%;
  padding: 1rem 0.75rem;
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.2);
}

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(17, 24, 39, 0.45);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 180ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.fade-enter-to,
.fade-leave-from {
  opacity: 1;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 200ms ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
}

.slide-enter-to,
.slide-leave-from {
  transform: translateX(0);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.2rem 0.45rem 0.8rem;
}

.brand {
  font-weight: 800;
  letter-spacing: 0.02em;
}

.desktop-collapse {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.desktop-sidebar.collapsed .sidebar-header {
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
}

.desktop-sidebar.collapsed .collapse-label {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.mobile-close {
  margin-inline-start: auto;
}

.workspace {
  flex: 1;
  min-width: 0;
}

.utility-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 0.95rem;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.menu-toggle,
.utility-link,
.utility-action,
.logout-action {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  text-decoration: none;
}

.utility-link:hover,
.utility-action:hover {
  text-decoration: none;
}

.utility-link.active,
.utility-action.active {
  border-color: var(--pf-t--global--border--color--brand--default);
  color: var(--pf-t--global--text--color--brand--default);
  box-shadow: inset 0 0 0 1px var(--pf-t--global--border--color--brand--default);
}

.utility-icon {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.badge {
  margin-inline-start: 0.1rem;
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
  .desktop-sidebar {
    display: flex;
  }

  .mobile-sidebar-root,
  .menu-toggle {
    display: none;
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
    flex: 1 1 auto;
  }
}
</style>
