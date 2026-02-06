export type NavVisibility = "all" | "org-admin" | "org-admin-outputs";

export type ShellNavItem = {
  label: string;
  to: string;
  visibility: NavVisibility;
};

export type ShellNavModel = {
  primary: ShellNavItem[];
  settings: ShellNavItem[];
  quickActions: ShellNavItem[];
};

export type ShellNavAccess = {
  canAccessOrgAdminRoutes: boolean;
  canAccessOutputsUi: boolean;
};

const PRIMARY_NAV_ITEMS: ShellNavItem[] = [
  { label: "Dashboard", to: "/dashboard", visibility: "all" },
  { label: "Work", to: "/work", visibility: "all" },
  { label: "Projects", to: "/projects", visibility: "org-admin" },
  { label: "Team", to: "/team", visibility: "org-admin" },
  { label: "Templates", to: "/templates", visibility: "org-admin-outputs" },
  { label: "Outputs", to: "/outputs", visibility: "org-admin-outputs" },
  { label: "SoWs", to: "/sows", visibility: "org-admin" },
  { label: "Notifications", to: "/notifications", visibility: "all" },
];

const SETTINGS_NAV_ITEMS: ShellNavItem[] = [
  { label: "Workflow settings", to: "/settings/workflows", visibility: "org-admin" },
  { label: "Project settings", to: "/settings/project", visibility: "org-admin" },
  { label: "GitLab integration", to: "/settings/integrations/gitlab", visibility: "org-admin" },
];

const QUICK_ACTION_ITEMS: ShellNavItem[] = [
  { label: "New SoW", to: "/sows/new", visibility: "org-admin" },
  { label: "New workflow", to: "/settings/workflows/new", visibility: "org-admin" },
];

function canSeeItem(item: ShellNavItem, access: ShellNavAccess): boolean {
  if (item.visibility === "all") {
    return true;
  }
  if (item.visibility === "org-admin") {
    return access.canAccessOrgAdminRoutes;
  }
  return access.canAccessOutputsUi;
}

function visibleItems(items: ShellNavItem[], access: ShellNavAccess): ShellNavItem[] {
  return items.filter((item) => canSeeItem(item, access));
}

export function buildShellNavModel(access: ShellNavAccess): ShellNavModel {
  return {
    primary: visibleItems(PRIMARY_NAV_ITEMS, access),
    settings: visibleItems(SETTINGS_NAV_ITEMS, access),
    quickActions: visibleItems(QUICK_ACTION_ITEMS, access),
  };
}
