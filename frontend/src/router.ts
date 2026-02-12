import { createRouter, createWebHistory } from "vue-router";

import {
  defaultAuthedPathForMemberships,
  getMembershipRoleForOrg,
  resolveInternalGuardDecision,
  rolesFromRouteMeta,
} from "./routerGuards";
import { useContextStore } from "./stores/context";
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
      path: "/invite/accept",
      name: "invite-accept",
      component: () => import("./pages/InviteAcceptPage.vue"),
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
        { path: "sows", name: "client-sows", component: () => import("./pages/ClientSowsPage.vue") },
        {
          path: "sows/:sowId",
          name: "client-sow-detail",
          component: () => import("./pages/ClientSowDetailPage.vue"),
          props: true,
        },
        {
          path: "timeline",
          name: "client-timeline",
          component: () => import("./pages/TimelinePage.vue"),
        },
        { path: "gantt", name: "client-gantt", component: () => import("./pages/GanttPage.vue") },
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
        { path: "dashboard", name: "dashboard", component: () => import("./pages/WorkListPage.vue") },
        { path: "work", name: "work-list", component: () => import("./pages/WorkListPage.vue") },
        {
          path: "projects",
          name: "projects",
          component: () => import("./pages/ProjectsPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "team",
          name: "team",
          component: () => import("./pages/TeamPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "team/roles",
          name: "team-roles",
          component: () => import("./pages/TeamRolesPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "team/api-keys",
          name: "team-api-keys",
          component: () => import("./pages/TeamApiKeysPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "templates",
          name: "templates",
          component: () => import("./pages/TemplatesPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "templates/:templateId",
          name: "template-detail",
          component: () => import("./pages/TemplateDetailPage.vue"),
          props: true,
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "outputs",
          name: "outputs",
          component: () => import("./pages/OutputsPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "outputs/:runId",
          name: "output-run-detail",
          component: () => import("./pages/OutputRunDetailPage.vue"),
          props: true,
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "sows",
          name: "sows",
          component: () => import("./pages/SowsPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "sows/new",
          name: "sow-create",
          component: () => import("./pages/SowCreatePage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "sows/:sowId",
          name: "sow-detail",
          component: () => import("./pages/SowDetailPage.vue"),
          props: true,
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
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
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "settings/workflows/new",
          name: "workflow-create",
          component: () => import("./pages/WorkflowCreatePage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "settings/workflows/:workflowId",
          name: "workflow-edit",
          component: () => import("./pages/WorkflowEditPage.vue"),
          props: true,
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "settings/project",
          name: "project-settings",
          component: () => import("./pages/ProjectSettingsPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "settings/integrations/gitlab",
          name: "gitlab-integration-settings",
          component: () => import("./pages/GitLabIntegrationSettingsPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "forbidden",
          name: "forbidden",
          component: () => import("./pages/ForbiddenPage.vue"),
        },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const session = useSessionStore();
  const context = useContextStore();
  if (!session.initialized) {
    await session.bootstrap();
  }

  if (to.meta.public) {
    if (session.user && to.path === "/login") {
      return { path: defaultAuthedPathForMemberships(session.memberships) };
    }
    return true;
  }

  const requiredRoles = rolesFromRouteMeta(to.meta.requiresOrgRole);
  if (requiredRoles.length > 0 && !context.orgId) {
    context.syncFromMemberships(session.memberships);
  }

  const decision = resolveInternalGuardDecision({
    hasUser: Boolean(session.user),
    toPath: to.path,
    memberships: session.memberships,
    requiredRoles,
    contextOrgId: context.orgId,
    currentOrgRole: getMembershipRoleForOrg(session.memberships, context.orgId),
  });

  if (decision.action === "redirect-login") {
    return { path: "/login", query: { redirect: to.fullPath } };
  }

  if (decision.action === "redirect") {
    return { path: decision.path };
  }

  return true;
});

export default router;
