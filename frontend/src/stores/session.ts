import { defineStore } from "pinia";

import { api, ApiError } from "../api";
import type { ApiMembership, ApiUser, MeResponse, OrgSummary } from "../api/types";
import { useContextStore } from "./context";

export type PlatformRole = "admin" | "pm" | "none";

export const useSessionStore = defineStore("session", {
  state: () => ({
    initialized: false,
    loading: false,
    error: "" as string,
    user: null as ApiUser | null,
    memberships: [] as ApiMembership[],
    platformRole: "none" as PlatformRole,
    orgs: [] as OrgSummary[],
    orgsLoading: false,
    orgsError: "" as string,
  }),
  actions: {
    clearLocal(reason?: string) {
      this.user = null;
      this.memberships = [];
      this.platformRole = "none";
      this.orgs = [];
      this.orgsLoading = false;
      this.orgsError = "";
      this.error = reason ?? "";
      this.initialized = true;

      const context = useContextStore();
      context.reset();
    },
    applyMe(me: MeResponse) {
      this.user = me.user;
      this.memberships = me.memberships;
      this.platformRole = me.platform_role ?? "none";
    },
    async refreshOrgs() {
      this.orgsError = "";

      if (!this.user) {
        this.orgs = [];
        this.orgsLoading = false;
        return;
      }

      this.orgsLoading = true;
      try {
        const res = await api.listOrgs();
        this.orgs = res.orgs;
      } catch (err) {
        this.orgs = [];
        if (err instanceof ApiError && err.status === 401) {
          this.clearLocal("unauthorized");
          return;
        }
        this.orgsError = err instanceof Error ? err.message : String(err);
      } finally {
        this.orgsLoading = false;
      }
    },
    effectiveOrgRole(orgId: string): string {
      if (!orgId) {
        return "";
      }
      if (this.platformRole !== "none") {
        return this.platformRole;
      }
      return this.memberships.find((membership) => membership.org.id === orgId)?.role ?? "";
    },
    async bootstrap() {
      if (this.initialized) {
        return;
      }

      this.loading = true;
      this.error = "";
      try {
        const me = await api.getMe();
        this.applyMe(me);
        await this.refreshOrgs();
      } catch (err) {
        this.clearLocal(err instanceof Error ? err.message : String(err));
      } finally {
        this.initialized = true;
        this.loading = false;
      }
    },
    async login(email: string, password: string) {
      this.loading = true;
      this.error = "";
      try {
        const me = await api.login(email, password);
        this.applyMe(me);
        await this.refreshOrgs();

        const context = useContextStore();
        context.syncFromMemberships(this.memberships);
      } catch (err) {
        this.error = err instanceof Error ? err.message : String(err);
        throw err;
      } finally {
        this.loading = false;
        this.initialized = true;
      }
    },
    async logout() {
      try {
        await api.logout();
      } finally {
        this.user = null;
        this.memberships = [];
        this.platformRole = "none";
        this.orgs = [];
        this.orgsLoading = false;
        this.orgsError = "";

        const context = useContextStore();
        context.reset();
      }
    },
    async refresh() {
      this.loading = true;
      this.error = "";
      try {
        const me = await api.getMe();
        this.applyMe(me);
        await this.refreshOrgs();

        const context = useContextStore();
        context.syncFromMemberships(this.memberships);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          this.clearLocal("unauthorized");
          throw err;
        }

        this.error = err instanceof Error ? err.message : String(err);
        throw err;
      } finally {
        this.loading = false;
        this.initialized = true;
      }
    },
  },
});
