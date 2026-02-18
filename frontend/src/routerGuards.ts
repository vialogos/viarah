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
  contextOrgId: string;
  currentOrgRole: string;
};

export function isClientOnlyMemberships(memberships: MembershipLike[]): boolean {
  return memberships.length > 0 && memberships.every((membership) => membership.role === "client");
}

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

  const clientOnly = isClientOnlyMemberships(input.memberships);
  if (clientOnly && !input.toPath.startsWith("/client")) {
    return { action: "redirect", path: "/client" };
  }

  if (!clientOnly && input.toPath.startsWith("/client")) {
    return { action: "redirect", path: "/dashboard" };
  }

  if (input.requiredRoles.length > 0) {
    if (!input.contextOrgId || !input.requiredRoles.includes(input.currentOrgRole)) {
      return { action: "redirect", path: "/forbidden" };
    }
  }

  return { action: "allow" };
}
