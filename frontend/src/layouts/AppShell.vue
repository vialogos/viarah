<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Bell, LogOut, User } from "lucide-vue-next";

import OrgProjectSwitcher from "../components/OrgProjectSwitcher.vue";
import VlLabel from "../components/VlLabel.vue";
import { buildShellNavModel } from "./appShellNav";
	import SidebarNavigation from "./SidebarNavigation.vue";
	import { useContextStore } from "../stores/context";
	import { useNotificationsStore } from "../stores/notifications";
	import { useRealtimeStore } from "../stores/realtime";
	import { useSessionStore } from "../stores/session";

const router = useRouter();
const session = useSessionStore();
	const context = useContextStore();
	const notifications = useNotificationsStore();
	const realtime = useRealtimeStore();
	let releaseRealtime: (() => void) | null = null;

const isMobileView = ref(false);
const sidebarOpen = ref(false);
const sidebarRailCollapsed = ref(false);
const userMenuOpen = ref(false);

const scopeIndicator = computed(() => {
  if (context.isAllOrgsScopeActive) {
    return { label: "All orgs", title: "Select an org to scope changes." };
  }
  if (context.isAllProjectsScopeActive) {
    return { label: "All projects", title: "Aggregated view across projects." };
  }
  return null;
});

const currentOrgRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((membership) => membership.org.id === context.orgId)?.role ?? "";
});

const notificationButtonState = computed(() =>
  notifications.unreadCount > 0 ? "attention" : "read"
);

const notificationAriaLabel = computed(() => {
  if (notifications.unreadCount > 0) {
    return `Notifications (${notifications.unreadCount} unread)`;
  }

  return "Notifications";
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

const pageStyle = computed(() => {
  if (isMobileView.value || !sidebarRailCollapsed.value) {
    return undefined;
  }

  // Keep the sidebar visible on desktop but shrink it into an icon rail.
  return {
    "--pf-v6-c-page__sidebar--Width": "5rem",
    "--pf-v6-c-page__sidebar--MarginInlineEnd": "0",
    "--pf-v6-c-page__sidebar-body--PaddingInlineStart": "0",
    "--pf-v6-c-page__sidebar-body--PaddingInlineEnd": "0",
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

async function openNotifications() {
  await router.push("/notifications");
}

	onMounted(() => {
	  context.syncFromMemberships(session.memberships);
	});

	onUnmounted(() => {
	  if (releaseRealtime) {
	    releaseRealtime();
	    releaseRealtime = null;
	  }
	});

	watch(
	  () => [context.orgScope, context.orgId],
	  async ([scope, nextOrgId], prev) => {
	    const prevOrgId = Array.isArray(prev) ? prev[1] : undefined;
	    if (scope !== "single") {
	      if (releaseRealtime) {
	        releaseRealtime();
	        releaseRealtime = null;
	      }
	      return;
	    }
	    if (!nextOrgId) {
	      if (releaseRealtime) {
	        releaseRealtime();
	        releaseRealtime = null;
	      }
	      return;
	    }
	    if (nextOrgId && nextOrgId !== prevOrgId) {
	      if (releaseRealtime) {
	        releaseRealtime();
	      }
	      releaseRealtime = realtime.acquire(nextOrgId);
	      await context.refreshProjects();
	    }
	  },
	  { immediate: true }
	);

watch(
  () => [session.user?.id, context.orgId, context.projectId, context.orgScope, context.projectScope] as const,
  ([userId, orgId, projectId, orgScope, projectScope]) => {
    if (userId && orgScope === "single" && orgId) {
      const projectFilter = projectScope === "single" && projectId ? projectId : undefined;
      notifications.startPolling({ orgId, projectId: projectFilter });
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
  <pf-page class="app-shell-page" :style="pageStyle" @page-resize="onPageResize">
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
          <pf-toolbar static>
            <pf-toolbar-content>
              <pf-toolbar-group variant="action-group-plain">
                <pf-toolbar-item>
                  <pf-button
                    type="button"
                    variant="stateful"
                    :state="notificationButtonState"
                    :aria-label="notificationAriaLabel"
                    @click="openNotifications"
                  >
                    <span class="pf-v6-c-button__icon">
                      <pf-icon inline>
                        <Bell class="utility-icon" aria-hidden="true" />
                      </pf-icon>
                    </span>
                    <span v-if="notifications.unreadCount > 0" class="pf-v6-c-button__text">
                      {{ notifications.unreadCount }}
                      <span class="pf-v6-screen-reader">unread notifications</span>
                    </span>
                  </pf-button>
                </pf-toolbar-item>
              </pf-toolbar-group>

              <pf-toolbar-group align="end">
                <pf-toolbar-item>
                  <OrgProjectSwitcher />
                </pf-toolbar-item>
                <pf-toolbar-item v-if="scopeIndicator">
                  <div data-ui="global-scope-indicator">
                    <VlLabel color="orange" :title="scopeIndicator.title">
                      {{ scopeIndicator.label }}
                    </VlLabel>
                  </div>
                </pf-toolbar-item>

                <pf-toolbar-item v-if="session.user">
                  <pf-dropdown
                    :open="userMenuOpen"
                    append-to="body"
                    placement="bottom-end"
                    @update:open="(open) => (userMenuOpen = open)"
                  >
                    <template #toggle>
                      <pf-menu-toggle variant="plainText" :expanded="userMenuOpen" aria-label="User menu">
                        <template #icon>
                          <pf-icon inline>
                            <User class="utility-icon" aria-hidden="true" />
                          </pf-icon>
                        </template>
                        <span class="user">{{ session.user.display_name || session.user.email }}</span>
                      </pf-menu-toggle>
                    </template>

                    <pf-dropdown-list>
                      <pf-dropdown-item disabled>
                        Signed in as {{ session.user.email }}
                      </pf-dropdown-item>
                      <pf-dropdown-item v-if="currentOrgRole" disabled>
                        Role: {{ currentOrgRole }}
                      </pf-dropdown-item>
                      <pf-dropdown-item @click="logout">
                        <template #icon>
                          <pf-icon inline>
                            <LogOut class="utility-icon" aria-hidden="true" />
                          </pf-icon>
                        </template>
                        Logout
                      </pf-dropdown-item>
                    </pf-dropdown-list>
                  </pf-dropdown>
                </pf-toolbar-item>
              </pf-toolbar-group>
            </pf-toolbar-content>
          </pf-toolbar>
        </pf-masthead-content>
      </pf-masthead>

      <pf-page-sidebar id="internal-sidebar" :sidebar-open="pageSidebarOpen">
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
      <main class="content">
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
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.content {
  width: 100%;
}
</style>
