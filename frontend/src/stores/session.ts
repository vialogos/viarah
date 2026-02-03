import { defineStore } from "pinia";

import { api } from "../api";
import type { ApiMembership, ApiUser, MeResponse } from "../api/types";
import { useContextStore } from "./context";

export const useSessionStore = defineStore("session", {
  state: () => ({
    initialized: false,
    loading: false,
    error: "" as string,
    user: null as ApiUser | null,
    memberships: [] as ApiMembership[],
  }),
  actions: {
    clearLocal(reason?: string) {
      this.user = null;
      this.memberships = [];
      this.error = reason ?? "";
      this.initialized = true;

      const context = useContextStore();
      context.reset();
    },
    applyMe(me: MeResponse) {
      this.user = me.user;
      this.memberships = me.memberships;
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

        const context = useContextStore();
        context.reset();
      }
    },
  },
});
