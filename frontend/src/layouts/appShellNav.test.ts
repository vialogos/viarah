import { describe, expect, it } from "vitest";

import { buildShellNavModel } from "./appShellNav";

describe("buildShellNavModel", () => {
  it("hides admin-only sections for non-admin org context", () => {
    const model = buildShellNavModel({
      canAccessOrgAdminRoutes: false,
      canAccessOutputsUi: false,
    });

    expect(model.primary.map((item) => item.label)).toEqual([
      "Dashboard",
      "Work",
      "Notifications",
    ]);
    expect(model.settings).toEqual([]);
    expect(model.quickActions).toEqual([]);
  });

  it("shows all sections for admin/pm org context", () => {
    const model = buildShellNavModel({
      canAccessOrgAdminRoutes: true,
      canAccessOutputsUi: true,
    });

    expect(model.primary.map((item) => item.label)).toEqual([
      "Dashboard",
      "Work",
      "Projects",
      "Team",
      "Templates",
      "Outputs",
      "SoWs",
      "Notifications",
    ]);
    expect(model.settings.map((item) => item.label)).toEqual([
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

    expect(model.primary.map((item) => item.label)).toEqual([
      "Dashboard",
      "Work",
      "Projects",
      "Team",
      "SoWs",
      "Notifications",
    ]);
  });
});
