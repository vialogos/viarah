import { defineStore } from "pinia";

import { api, ApiError } from "../api";

const DEFAULT_POLL_INTERVAL_MS = 20_000;

export const useNotificationsStore = defineStore("notifications", {
  state: () => ({
    orgId: "" as string,
    projectId: "" as string,
    unreadCount: 0,
    loadingBadge: false,
    error: "" as string,
    polling: false,
    intervalId: null as number | null,
  }),
  actions: {
    reset() {
      this.stopPolling();
      this.orgId = "";
      this.projectId = "";
      this.unreadCount = 0;
      this.loadingBadge = false;
      this.error = "";
    },
    startPolling(options: { orgId: string; projectId?: string; intervalMs?: number }) {
      const intervalMs = options.intervalMs ?? DEFAULT_POLL_INTERVAL_MS;
      const orgId = options.orgId;
      const projectId = options.projectId ?? "";

      if (!orgId) {
        this.stopPolling();
        return;
      }

      const alreadyPolling =
        this.polling && this.orgId === orgId && this.projectId === projectId;
      if (alreadyPolling) {
        return;
      }

      this.stopPolling();
      this.orgId = orgId;
      this.projectId = projectId;
      this.polling = true;

      void this.refreshBadge();
      this.intervalId = window.setInterval(() => void this.refreshBadge(), intervalMs);
    },
    stopPolling() {
      if (this.intervalId != null) {
        window.clearInterval(this.intervalId);
      }
      this.intervalId = null;
      this.polling = false;
    },
    async refreshBadge() {
      if (!this.orgId) {
        this.unreadCount = 0;
        return;
      }

      this.loadingBadge = true;
      this.error = "";
      try {
        const res = await api.getMyNotificationBadge(this.orgId, {
          projectId: this.projectId || undefined,
        });
        this.unreadCount = res.unread_count ?? 0;
      } catch (err) {
        this.unreadCount = 0;
        if (err instanceof ApiError && err.status === 401) {
          this.stopPolling();
          return;
        }
        this.error = err instanceof Error ? err.message : String(err);
      } finally {
        this.loadingBadge = false;
      }
    },
  },
});
