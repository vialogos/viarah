import { describe, expect, it } from "vitest";

import {
  defaultAuthedPathForMemberships,
  getMembershipRoleForOrg,
  isClientOnlyMemberships,
  resolveInternalGuardDecision,
  rolesFromRouteMeta,
  type MembershipLike,
} from "./routerGuards";

function memberships(...roles: Array<{ role: string; orgId: string }>): MembershipLike[] {
  return roles.map(({ role, orgId }) => ({ role, org: { id: orgId } }));
}

describe("routerGuards", () => {
  it("detects client-only memberships", () => {
    expect(isClientOnlyMemberships(memberships({ role: "client", orgId: "org-1" }))).toBe(true);
    expect(
      isClientOnlyMemberships(
        memberships({ role: "client", orgId: "org-1" }, { role: "pm", orgId: "org-2" })
      )
    ).toBe(false);
  });

  it("returns the default authed path from membership mix", () => {
    expect(defaultAuthedPathForMemberships(memberships({ role: "client", orgId: "org-1" }))).toBe(
      "/client"
    );
    expect(defaultAuthedPathForMemberships(memberships({ role: "member", orgId: "org-1" }))).toBe(
      "/work"
    );
  });

  it("extracts required roles from route meta", () => {
    expect(rolesFromRouteMeta(["admin", "pm"])).toEqual(["admin", "pm"]);
    expect(rolesFromRouteMeta("admin")).toEqual([]);
    expect(rolesFromRouteMeta(["admin", 123])).toEqual(["admin"]);
  });

  it("resolves membership role for selected org", () => {
    const value = getMembershipRoleForOrg(
      memberships({ role: "admin", orgId: "org-a" }, { role: "member", orgId: "org-b" }),
      "org-b"
    );
    expect(value).toBe("member");
    expect(getMembershipRoleForOrg([], "org-b")).toBe("");
  });

  it("redirects unauthenticated users to login", () => {
    const decision = resolveInternalGuardDecision({
      hasUser: false,
      toPath: "/work",
      memberships: memberships({ role: "member", orgId: "org-1" }),
      requiredRoles: [],
      contextOrgId: "",
      currentOrgRole: "",
    });

    expect(decision).toEqual({ action: "redirect-login" });
  });

  it("keeps client-only users on /client routes", () => {
    const decision = resolveInternalGuardDecision({
      hasUser: true,
      toPath: "/work",
      memberships: memberships({ role: "client", orgId: "org-1" }),
      requiredRoles: [],
      contextOrgId: "org-1",
      currentOrgRole: "client",
    });

    expect(decision).toEqual({ action: "redirect", path: "/client" });
  });

  it("redirects non-client users away from /client", () => {
    const decision = resolveInternalGuardDecision({
      hasUser: true,
      toPath: "/client/tasks",
      memberships: memberships({ role: "pm", orgId: "org-1" }),
      requiredRoles: [],
      contextOrgId: "org-1",
      currentOrgRole: "pm",
    });

    expect(decision).toEqual({ action: "redirect", path: "/work" });
  });

  it("blocks restricted routes without an authorized org role", () => {
    const decision = resolveInternalGuardDecision({
      hasUser: true,
      toPath: "/settings/workflows",
      memberships: memberships({ role: "member", orgId: "org-1" }),
      requiredRoles: ["admin", "pm"],
      contextOrgId: "org-1",
      currentOrgRole: "member",
    });

    expect(decision).toEqual({ action: "redirect", path: "/forbidden" });
  });

  it("allows restricted routes for authorized org roles", () => {
    const decision = resolveInternalGuardDecision({
      hasUser: true,
      toPath: "/settings/workflows",
      memberships: memberships({ role: "pm", orgId: "org-1" }),
      requiredRoles: ["admin", "pm"],
      contextOrgId: "org-1",
      currentOrgRole: "pm",
    });

    expect(decision).toEqual({ action: "allow" });
  });
});
