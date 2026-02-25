export type MembershipLike = {
  role: string;
  org: {
    id: string;
  };
};

export type GuardDecision =
  | { action: "allow" }
  | { action: "redirect-login" }
  | { action: "redirect"; path: "/client" | "/dashboard" | "/work" | "/forbidden" };

export type GuardDecisionInput = {
  hasUser: boolean;
  toPath: string;
  memberships: MembershipLike[];
  requiredRoles: string[];
  contextOrgScope: "single" | "all";
  contextOrgId: string;
  currentOrgRole: string;
};

export function isClientOnlyMemberships(memberships: MembershipLike[]): boolean {
  return memberships.length > 0 && memberships.every((membership) => membership.role === "client");
}

/**
 * Default post-auth landing path.
 *
 * - Client-only users must land in the client portal.
 * - Internal users land on the internal dashboard.
 */
export function defaultAuthedPathForMemberships(
  memberships: MembershipLike[]
): "/client" | "/dashboard" {
  return isClientOnlyMemberships(memberships) ? "/client" : "/dashboard";
}

export function getMembershipRoleForOrg(memberships: MembershipLike[], orgId: string): string {
  if (!orgId) {
    return "";
  }
  return memberships.find((membership) => membership.org.id === orgId)?.role ?? "";
}

export function rolesFromRouteMeta(metaValue: unknown): string[] {
  return Array.isArray(metaValue)
    ? metaValue.filter((value): value is string => typeof value === "string")
    : [];
}

export function resolveInternalGuardDecision(input: GuardDecisionInput): GuardDecision {
  if (!input.hasUser) {
    return { action: "redirect-login" };
  }

  // Internal app routes include `/clients`, which must not be treated as the client portal route.
  const clientPortalPath = input.toPath === "/client" || input.toPath.startsWith("/client/");
  const clientOnly = isClientOnlyMemberships(input.memberships);
  if (clientOnly && !clientPortalPath) {
    return { action: "redirect", path: "/client" };
  }

  if (!clientOnly && clientPortalPath) {
    return { action: "redirect", path: "/dashboard" };
  }

  if (input.requiredRoles.length > 0) {
    if (input.contextOrgScope === "all") {
      const hasAnyRole = input.memberships.some((membership) =>
        input.requiredRoles.includes(membership.role)
      );
      if (!hasAnyRole) {
        return { action: "redirect", path: "/forbidden" };
      }
    } else if (!input.contextOrgId || !input.requiredRoles.includes(input.currentOrgRole)) {
      return { action: "redirect", path: "/forbidden" };
    }
  }

  return { action: "allow" };
}
