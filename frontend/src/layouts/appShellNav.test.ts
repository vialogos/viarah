import { describe, expect, it } from "vitest";

import { buildShellNavModel, isShellNavItemActive } from "./appShellNav";

describe("buildShellNavModel", () => {
  it("hides admin-only sections for non-admin org context", () => {
    const model = buildShellNavModel({
      canAccessOrgAdminRoutes: false,
      canAccessOutputsUi: false,
    });

    expect(model.groups).toHaveLength(1);
    expect(model.groups[0]!.label).toBe("Overview");
    expect(model.groups[0]!.items.map((item) => item.label)).toEqual([
      "Dashboard",
      "Work",
      "Notifications",
    ]);
    expect(model.quickActions).toEqual([]);
  });

  it("shows all sections for admin/pm org context", () => {
    const model = buildShellNavModel({
      canAccessOrgAdminRoutes: true,
      canAccessOutputsUi: true,
    });

    expect(model.groups.map((group) => group.label)).toEqual([
      "Overview",
      "Delivery",
      "Settings",
    ]);
    expect(model.groups[1]!.items.map((item) => item.label)).toEqual([
      "Projects",
      "Team",
      "Templates",
      "Outputs",
      "SoWs",
    ]);
    expect(model.groups[2]!.items.map((item) => item.label)).toEqual([
      "Workflow settings",
      "Project settings",
      "GitLab integration",
    ]);
    expect(model.quickActions.map((item) => item.label)).toEqual([
      "New SoW",
      "New workflow",
    ]);
  });

  it("keeps outputs hidden until output access is available", () => {
    const model = buildShellNavModel({
      canAccessOrgAdminRoutes: true,
      canAccessOutputsUi: false,
    });

    expect(model.groups[1]!.items.map((item) => item.label)).toEqual([
      "Projects",
      "Team",
      "SoWs",
    ]);
  });
});

describe("isShellNavItemActive", () => {
  it("marks nested paths as active for matching root routes", () => {
    const model = buildShellNavModel({
      canAccessOrgAdminRoutes: true,
      canAccessOutputsUi: true,
    });
    const notifications = model.groups[0]!.items.find((item) => item.id === "notifications");

    expect(notifications).toBeTruthy();
    expect(isShellNavItemActive(notifications!, "/notifications/settings")).toBe(true);
  });

  it("does not mark unrelated paths as active", () => {
    const model = buildShellNavModel({
      canAccessOrgAdminRoutes: true,
      canAccessOutputsUi: true,
    });
    const settingsGitLab = model.groups[2]!.items.find((item) => item.id === "gitlab-integration");

    expect(settingsGitLab).toBeTruthy();
    expect(isShellNavItemActive(settingsGitLab!, "/settings/workflows")).toBe(false);
  });
});
