<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
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

const isMobileView = ref(false);
const sidebarOpen = ref(false);
const sidebarRailCollapsed = ref(false);

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

const navIsExpanded = computed(() => {
  if (isMobileView.value) {
    return sidebarOpen.value;
  }
  return !sidebarRailCollapsed.value;
});

const pageSidebarOpen = computed(() => (isMobileView.value ? sidebarOpen.value : true));

const pageSidebarStyle = computed(() => {
  if (isMobileView.value || !sidebarRailCollapsed.value) {
    return undefined;
  }

  // Keep the sidebar visible on desktop but shrink it into an icon rail.
  return {
    "--pf-v6-c-page__sidebar--Width": "4.5rem",
  };
});

function onPageResize(payload: { mobileView: boolean; windowSize: number }) {
  isMobileView.value = payload.mobileView;

  if (payload.mobileView) {
    sidebarOpen.value = false;
  }
}

function onNavToggle(nextExpanded: boolean) {
  if (isMobileView.value) {
    sidebarOpen.value = nextExpanded;
    return;
  }

  // Desktop: collapse to a rail rather than hiding the sidebar.
  sidebarRailCollapsed.value = !nextExpanded;
}

function onSidebarNavigate() {
  if (isMobileView.value) {
    sidebarOpen.value = false;
  }
}

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
  <pf-page class="app-shell-page" @page-resize="onPageResize">
    <template #skeleton>
      <pf-masthead>
        <pf-masthead-main>
          <pf-masthead-toggle>
            <pf-page-toggle-button
              hamburger
              :sidebar-open="navIsExpanded"
              :hamburger-variant="navIsExpanded ? 'collapse' : 'expand'"
              @update:sidebar-open="onNavToggle"
            />
          </pf-masthead-toggle>
          <pf-masthead-brand href="/" @click.prevent>
            <pf-brand src="/vite.svg" alt="ViaRah" />
          </pf-masthead-brand>
        </pf-masthead-main>

        <pf-masthead-content>
          <pf-toolbar full-height>
            <pf-toolbar-content>
              <pf-toolbar-item>
                <pf-button variant="plain" to="/notifications" aria-label="Notifications">
                  <template #icon>
                    <pf-notification-badge variant="attention" :count="notifications.unreadCount">
                      <template #icon>
                        <pf-icon inline>
                          <Bell class="utility-icon" aria-hidden="true" />
                        </pf-icon>
                      </template>
                    </pf-notification-badge>
                  </template>
                </pf-button>
              </pf-toolbar-item>

              <pf-toolbar-item v-for="action in shellNav.quickActions" :key="action.id">
                <pf-button variant="secondary" small :to="action.to">
                  <template #icon>
                    <pf-icon inline>
                      <component :is="shellIconMap[action.icon]" class="utility-icon" aria-hidden="true" />
                    </pf-icon>
                  </template>
                  {{ action.label }}
                </pf-button>
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
                  <pf-button variant="secondary" small @click="logout">
                    <template #icon>
                      <pf-icon inline>
                        <LogOut class="utility-icon" aria-hidden="true" />
                      </pf-icon>
                    </template>
                    Logout
                  </pf-button>
                </pf-toolbar-item>
              </pf-toolbar-group>
            </pf-toolbar-content>
          </pf-toolbar>
        </pf-masthead-content>
      </pf-masthead>

      <pf-page-sidebar id="internal-sidebar" :sidebar-open="pageSidebarOpen" :style="pageSidebarStyle">
        <pf-page-sidebar-body>
          <SidebarNavigation
            :groups="shellNav.groups"
            :collapsed="!isMobileView && sidebarRailCollapsed"
            @navigate="onSidebarNavigate"
          />
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
