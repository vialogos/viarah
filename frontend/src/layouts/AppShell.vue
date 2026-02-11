<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";
import { Bell, LogOut } from "lucide-vue-next";

import OrgProjectSwitcher from "../components/OrgProjectSwitcher.vue";
import VlLabel from "../components/VlLabel.vue";
import { buildShellNavModel } from "./appShellNav";
import SidebarNavigation from "./SidebarNavigation.vue";
import { shellIconMap } from "./shellIcons";
import { useContextStore } from "../stores/context";
import { useNotificationsStore } from "../stores/notifications";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const session = useSessionStore();
const context = useContextStore();
const notifications = useNotificationsStore();

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
  <pf-page managed-sidebar class="app-shell-page">
    <template #skeleton>
      <pf-masthead>
        <pf-masthead-main>
          <pf-masthead-toggle>
            <pf-page-toggle-button hamburger />
          </pf-masthead-toggle>
          <pf-masthead-brand href="/" @click.prevent>
            <pf-brand src="/vite.svg" alt="ViaRah" />
          </pf-masthead-brand>
        </pf-masthead-main>

        <pf-masthead-content>
          <pf-toolbar full-height>
            <pf-toolbar-content>
              <pf-toolbar-item>
                <RouterLink class="utility-link" to="/notifications" active-class="active">
                  <pf-notification-badge variant="attention" :count="notifications.unreadCount">
                    <template #icon>
                      <pf-icon inline>
                        <Bell class="utility-icon" aria-hidden="true" />
                      </pf-icon>
                    </template>
                  </pf-notification-badge>
                  <span>Notifications</span>
                </RouterLink>
              </pf-toolbar-item>

              <pf-toolbar-item v-for="action in shellNav.quickActions" :key="action.id">
                <RouterLink class="utility-action" :to="action.to" active-class="active">
                  <pf-icon inline>
                    <component :is="shellIconMap[action.icon]" class="utility-icon" aria-hidden="true" />
                  </pf-icon>
                  <span>{{ action.label }}</span>
                </RouterLink>
              </pf-toolbar-item>

              <pf-toolbar-group align="end">
                <pf-toolbar-item>
                  <OrgProjectSwitcher />
                </pf-toolbar-item>

                <pf-toolbar-item v-if="session.user">
                  <div class="user muted" :title="session.user.email">
                    {{ session.user.display_name || session.user.email }}
                  </div>
                </pf-toolbar-item>

                <pf-toolbar-item v-if="currentOrgRole">
                  <VlLabel color="blue">{{ currentOrgRole }}</VlLabel>
                </pf-toolbar-item>

                <pf-toolbar-item>
                  <button type="button" class="logout-action" @click="logout">
                    <pf-icon inline>
                      <LogOut class="utility-icon" aria-hidden="true" />
                    </pf-icon>
                    <span>Logout</span>
                  </button>
                </pf-toolbar-item>
              </pf-toolbar-group>
            </pf-toolbar-content>
          </pf-toolbar>
        </pf-masthead-content>
      </pf-masthead>

      <pf-page-sidebar id="internal-sidebar">
        <pf-page-sidebar-body>
          <SidebarNavigation :groups="shellNav.groups" />
        </pf-page-sidebar-body>
      </pf-page-sidebar>
    </template>

    <pf-page-section>
      <main class="container content">
        <RouterView />
      </main>
    </pf-page-section>
  </pf-page>
</template>

<style scoped>
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

.user {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.content {
  padding-top: 0.5rem;
}
</style>
