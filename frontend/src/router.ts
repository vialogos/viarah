import { createRouter, createWebHistory } from "vue-router";

import { useSessionStore } from "./stores/session";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("./pages/LoginPage.vue"),
      meta: { public: true },
    },
    {
      path: "/client",
      component: () => import("./layouts/ClientShell.vue"),
      children: [
        {
          path: "",
          name: "client-overview",
          component: () => import("./pages/ClientOverviewPage.vue"),
        },
        { path: "tasks", name: "client-tasks", component: () => import("./pages/ClientTasksPage.vue") },
        {
          path: "notifications",
          name: "client-notifications",
          component: () => import("./pages/NotificationsPage.vue"),
        },
        {
          path: "notifications/settings",
          name: "client-notification-settings",
          component: () => import("./pages/NotificationSettingsPage.vue"),
        },
        {
          path: "tasks/:taskId",
          name: "client-task-detail",
          component: () => import("./pages/ClientTaskDetailPage.vue"),
          props: true,
        },
      ],
    },
    {
      path: "/",
      component: () => import("./layouts/AppShell.vue"),
      children: [
        { path: "", redirect: "/work" },
        { path: "work", name: "work-list", component: () => import("./pages/WorkListPage.vue") },
        { path: "timeline", name: "timeline", component: () => import("./pages/TimelinePage.vue") },
        { path: "gantt", name: "gantt", component: () => import("./pages/GanttPage.vue") },
        {
          path: "notifications",
          name: "notifications",
          component: () => import("./pages/NotificationsPage.vue"),
        },
        {
          path: "notifications/settings",
          name: "notification-settings",
          component: () => import("./pages/NotificationSettingsPage.vue"),
        },
        {
          path: "notifications/delivery-logs",
          name: "notification-delivery-logs",
          component: () => import("./pages/NotificationDeliveryLogsPage.vue"),
        },
        {
          path: "work/:taskId",
          name: "work-detail",
          component: () => import("./pages/WorkDetailPage.vue"),
          props: true,
        },
        {
          path: "settings/workflows",
          name: "workflow-list",
          component: () => import("./pages/WorkflowListPage.vue"),
        },
        {
          path: "settings/workflows/new",
          name: "workflow-create",
          component: () => import("./pages/WorkflowCreatePage.vue"),
        },
        {
          path: "settings/workflows/:workflowId",
          name: "workflow-edit",
          component: () => import("./pages/WorkflowEditPage.vue"),
          props: true,
        },
        {
          path: "settings/project",
          name: "project-settings",
          component: () => import("./pages/ProjectSettingsPage.vue"),
        },
        {
          path: "settings/integrations/gitlab",
          name: "gitlab-integration-settings",
          component: () => import("./pages/GitLabIntegrationSettingsPage.vue"),
        },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const session = useSessionStore();
  if (!session.initialized) {
    await session.bootstrap();
  }

  const isClientOnly =
    session.memberships.length > 0 && session.memberships.every((m) => m.role === "client");
  const defaultAuthedPath = isClientOnly ? "/client" : "/work";

  if (to.meta.public) {
    if (session.user && to.path === "/login") {
      return { path: defaultAuthedPath };
    }
    return true;
  }

  if (!session.user) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }

  if (isClientOnly && !to.path.startsWith("/client")) {
    return { path: "/client" };
  }

  if (!isClientOnly && to.path.startsWith("/client")) {
    return { path: "/work" };
  }

  return true;
});

export default router;
