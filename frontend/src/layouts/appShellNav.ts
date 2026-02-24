export type NavVisibility = "all" | "org-admin" | "org-admin-outputs";

export type ShellNavIconName =
  | "dashboard"
  | "work"
  | "kanban"
  | "timeline"
  | "gantt"
  | "projects"
  | "clients"
  | "team"
  | "templates"
  | "outputs"
  | "sows"
  | "notifications"
  | "settings"
  | "workflow"
  | "project"
  | "integration"
  | "sparkles"
  | "quick-add";

export type ShellNavItem = {
  id: string;
  label: string;
  to: string;
  visibility: NavVisibility;
  icon: ShellNavIconName;
  activePrefixes?: string[];
};

export type ShellNavGroup = {
  id: string;
  label: string;
  visibility: NavVisibility;
  icon: ShellNavIconName;
  defaultExpanded: boolean;
  items: ShellNavItem[];
};

export type ShellNavModel = {
  groups: ShellNavGroup[];
  quickActions: ShellNavItem[];
};

export type ShellNavAccess = {
  canAccessOrgAdminRoutes: boolean;
  canAccessOutputsUi: boolean;
};

const NAV_GROUPS: ShellNavGroup[] = [
  {
    id: "overview",
    label: "Overview",
    visibility: "all",
    icon: "dashboard",
    defaultExpanded: true,
    items: [
      {
        id: "dashboard",
        label: "Dashboard",
        to: "/dashboard",
        visibility: "all",
        icon: "dashboard",
      },
      {
        id: "work",
        label: "Work",
        to: "/work",
        visibility: "all",
        icon: "work",
      },
      {
        id: "board",
        label: "Board",
        to: "/board",
        visibility: "all",
        icon: "kanban",
      },
      {
        id: "timeline",
        label: "Timeline",
        to: "/timeline",
        visibility: "all",
        icon: "timeline",
      },
      {
        id: "gantt",
        label: "Gantt",
        to: "/gantt",
        visibility: "all",
        icon: "gantt",
      },
      {
        id: "notifications",
        label: "Notifications",
        to: "/notifications",
        visibility: "all",
        icon: "notifications",
      },
    ],
  },
  {
    id: "delivery",
    label: "Delivery",
    visibility: "org-admin",
    icon: "work",
    defaultExpanded: true,
    items: [
      {
        id: "projects",
        label: "Projects",
        to: "/projects",
        visibility: "org-admin",
        icon: "projects",
      },
      {
        id: "clients",
        label: "Clients",
        to: "/clients",
        visibility: "org-admin",
        icon: "clients",
      },
      {
        id: "team",
        label: "Team",
        to: "/team",
        visibility: "org-admin",
        icon: "team",
      },
      {
        id: "templates",
        label: "Templates",
        to: "/templates",
        visibility: "org-admin-outputs",
        icon: "templates",
      },
      {
        id: "outputs",
        label: "Outputs",
        to: "/outputs",
        visibility: "org-admin-outputs",
        icon: "outputs",
      },
      {
        id: "sows",
        label: "SoWs",
        to: "/sows",
        visibility: "org-admin",
        icon: "sows",
      },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    visibility: "org-admin",
    icon: "settings",
    defaultExpanded: false,
    items: [
      {
        id: "workflow-settings",
        label: "Workflow settings",
        to: "/settings/workflows",
        visibility: "org-admin",
        icon: "workflow",
      },
      {
        id: "project-settings",
        label: "Project settings",
        to: "/settings/project",
        visibility: "org-admin",
        icon: "project",
      },
      {
        id: "gitlab-integration",
        label: "GitLab integration",
        to: "/settings/integrations/gitlab",
        visibility: "org-admin",
        icon: "integration",
      },
    ],
  },
];

const QUICK_ACTION_ITEMS: ShellNavItem[] = [
  {
    id: "new-sow",
    label: "New SoW",
    to: "/sows/new",
    visibility: "org-admin",
    icon: "quick-add",
  },
  {
    id: "new-workflow",
    label: "New workflow",
    to: "/settings/workflows/new",
    visibility: "org-admin",
    icon: "sparkles",
  },
];

function canSeeVisibility(visibility: NavVisibility, access: ShellNavAccess): boolean {
  if (visibility === "all") {
    return true;
  }
  if (visibility === "org-admin") {
    return access.canAccessOrgAdminRoutes;
  }
  return access.canAccessOutputsUi;
}

function canSeeItem(item: ShellNavItem, access: ShellNavAccess): boolean {
  return canSeeVisibility(item.visibility, access);
}

function visibleItems(items: ShellNavItem[], access: ShellNavAccess): ShellNavItem[] {
  return items.filter((item) => canSeeItem(item, access));
}

export function isShellNavItemActive(item: ShellNavItem, currentPath: string): boolean {
  if (currentPath === item.to || currentPath.startsWith(`${item.to}/`)) {
    return true;
  }

  if (!item.activePrefixes || item.activePrefixes.length === 0) {
    return false;
  }

  return item.activePrefixes.some(
    (prefix) => currentPath === prefix || currentPath.startsWith(`${prefix}/`)
  );
}

export function buildShellNavModel(access: ShellNavAccess): ShellNavModel {
  const groups = NAV_GROUPS.filter((group) => canSeeVisibility(group.visibility, access))
    .map((group) => ({
      ...group,
      items: visibleItems(group.items, access),
    }))
    .filter((group) => group.items.length > 0);

  return {
    groups,
    quickActions: visibleItems(QUICK_ACTION_ITEMS, access),
  };
}
