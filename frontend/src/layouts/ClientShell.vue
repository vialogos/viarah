<script setup lang="ts">
import { onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";
import { LogOut } from "lucide-vue-next";

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
  <pf-page>
    <template #skeleton>
      <pf-masthead>
        <pf-masthead-main>
          <pf-masthead-brand href="/" @click.prevent>
            <pf-brand src="/vite.svg" alt="ViaRah client portal" />
          </pf-masthead-brand>
        </pf-masthead-main>
        <pf-masthead-content>
          <pf-toolbar full-height>
            <pf-toolbar-content>
              <pf-toolbar-item>
                <pf-nav variant="horizontal" aria-label="Client navigation">
                  <pf-nav-list>
                    <pf-nav-item to="/client">Overview</pf-nav-item>
                    <pf-nav-item to="/client/tasks">Tasks</pf-nav-item>
                    <pf-nav-item to="/client/sows">SoWs</pf-nav-item>
                    <pf-nav-item to="/client/timeline">Timeline</pf-nav-item>
                    <pf-nav-item to="/client/gantt">Gantt</pf-nav-item>
                    <pf-nav-item to="/client/notifications">
                      Notifications
                      <template #icon>
                        <pf-notification-badge variant="attention" :count="notifications.unreadCount" />
                      </template>
                    </pf-nav-item>
                  </pf-nav-list>
                </pf-nav>
              </pf-toolbar-item>

              <pf-toolbar-group align="end">
                <pf-toolbar-item v-if="session.user">
                  <div class="user muted" :title="session.user.email">
                    {{ session.user.display_name || session.user.email }}
                  </div>
                </pf-toolbar-item>
                <pf-toolbar-item>
                  <OrgProjectSwitcher />
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
    </template>

    <pf-page-section>
      <main class="container">
        <RouterView />
      </main>
    </pf-page-section>
  </pf-page>
</template>

<style scoped>
.logout-action {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 0.4rem 0.6rem;
  background: var(--panel);
  color: var(--text);
}

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
</style>
