import { createRouter, createWebHistory } from "vue-router";

import {
  defaultAuthedPathForMemberships,
  getMembershipRoleForOrg,
  isClientOnlyMemberships,
  resolveInternalGuardDecision,
  rolesFromRouteMeta,
} from "./routerGuards";
import { useContextStore } from "./stores/context";
import { useSessionStore } from "./stores/session";

function queryStringFirst(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === "string") {
    return value[0];
  }
  return "";
}

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    }
    if (to.hash) {
      return { el: to.hash, behavior: "smooth" };
    }
    return { top: 0 };
  },
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
        { path: "", redirect: "/dashboard" },
        { path: "dashboard", name: "dashboard", component: () => import("./pages/DashboardPage.vue") },
        {
          path: "profile/setup",
          name: "profile-setup",
          component: () => import("./pages/ProfileSetupPage.vue"),
        },
        { path: "work", name: "work-list", component: () => import("./pages/WorkListPage.vue") },
        { path: "board", name: "kanban", component: () => import("./pages/KanbanPage.vue") },
        {
          path: "projects",
          name: "projects",
          component: () => import("./pages/ProjectsPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "clients",
          name: "clients",
          component: () => import("./pages/ClientsPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "clients/:clientId",
          name: "client-detail",
          component: () => import("./pages/ClientDetailPage.vue"),
          props: true,
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "team",
          name: "team",
          component: () => import("./pages/TeamPage.vue"),
          meta: { requiresOrgRole: ["admin", "pm"] },
        },
        {
          path: "people/:personId",
          name: "person-detail",
          component: () => import("./pages/PersonDetailPage.vue"),
          props: true,
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
          meta: { requiresOrgRole: ["admin", "pm"] },
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
          path: "settings/organizations",
          name: "organizations-settings",
          component: () => import("./pages/OrganizationsPage.vue"),
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

  const isClientOnly = isClientOnlyMemberships(session.memberships);
  if (!isClientOnly && (to.path.startsWith("/work") || to.path === "/dashboard")) {
    const orgScope = queryStringFirst(to.query.orgScope).toLowerCase();
    const projectScope = queryStringFirst(to.query.projectScope).toLowerCase();

    if (orgScope === "all") {
      context.setOrgScopeAll();
    } else if (projectScope === "all") {
      context.setProjectScopeAll();
    }

    // Deterministic QA support: allow explicit context selection via query params.
    //
    // Safety: only applies for authenticated sessions, and project listing is used as the
    // membership gate (if unauthorized, ignore the override and preserve prior context).
    const orgId = queryStringFirst(to.query.orgId).trim();
    const projectId = queryStringFirst(to.query.projectId).trim();
    if (session.user && orgId) {
      const prior = {
        orgScope: context.orgScope,
        projectScope: context.projectScope,
        orgId: context.orgId,
        projectId: context.projectId,
      };

      context.setOrgId(orgId);
      await context.refreshProjects();

      if (context.error) {
        if (prior.orgScope === "all") {
          context.setOrgScopeAll();
        } else {
          context.setOrgId(prior.orgId);
        }
        if (prior.projectScope === "all") {
          context.setProjectScopeAll();
        } else {
          context.setProjectId(prior.projectId);
        }
        context.error = "";
      } else if (projectId && context.projects.some((p) => p.id === projectId)) {
        context.setProjectId(projectId);
      }
    }
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
    contextOrgScope: context.orgScope,
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
