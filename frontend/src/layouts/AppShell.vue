<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Dialog, DialogPanel, TransitionChild, TransitionRoot } from "@headlessui/vue";
import { Bell, LogOut, Menu, X } from "lucide-vue-next";

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
                <button type="button" class="mobile-close" aria-label="Close navigation" @click="closeSidebar">
                  <X class="utility-icon" aria-hidden="true" />
                </button>
              </div>
              <SidebarNavigation :groups="shellNav.groups" @navigate="closeSidebar" />
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <aside class="sidebar desktop-sidebar">
      <div class="sidebar-header">
        <div class="brand">ViaRah</div>
      </div>
      <SidebarNavigation :groups="shellNav.groups" />
    </aside>

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
          <Menu class="utility-icon" aria-hidden="true" />
          <span>Menu</span>
        </button>

        <RouterLink class="utility-link" to="/notifications" active-class="active">
          <Bell class="utility-icon" aria-hidden="true" />
          <span>Notifications</span>
          <span v-if="unreadCountLabel" class="badge">{{ unreadCountLabel }}</span>
        </RouterLink>

        <RouterLink
          v-for="action in shellNav.quickActions"
          :key="action.id"
          class="utility-action"
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

        <button type="button" class="logout-action" @click="logout">
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

.mobile-close {
  border-radius: 10px;
  padding: 0.35rem 0.5rem;
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
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 0.4rem 0.6rem;
  background: var(--panel);
  color: var(--text);
  text-decoration: none;
}

.utility-link:hover,
.utility-action:hover {
  text-decoration: none;
}

.utility-link.active,
.utility-action.active {
  border-color: #93c5fd;
  background: #dbeafe;
  color: #1d4ed8;
}

.utility-icon {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
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
