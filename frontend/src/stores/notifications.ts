import { defineStore } from "pinia";

import { api, ApiError } from "../api";
import { useRealtimeStore } from "./realtime";

let unsubscribeRealtime: (() => void) | null = null;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export const useNotificationsStore = defineStore("notifications", {
  state: () => ({
    orgId: "" as string,
    projectId: "" as string,
    unreadCount: 0,
    loadingBadge: false,
    error: "" as string,
    watching: false,
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
      const orgId = options.orgId;
      const projectId = options.projectId ?? "";

      if (!orgId) {
        this.stopPolling();
        return;
      }

      const alreadyWatching = this.watching && this.orgId === orgId && this.projectId === projectId;
      if (alreadyWatching) {
        return;
      }

      this.stopPolling();
      this.orgId = orgId;
      this.projectId = projectId;
      this.watching = true;

      void this.refreshBadge();

      const realtime = useRealtimeStore();
      unsubscribeRealtime = realtime.subscribe((event) => {
        if (!this.orgId) {
          return;
        }
        if (event.org_id && event.org_id !== this.orgId) {
          return;
        }
        if (event.type === "notifications.updated") {
          if (this.projectId && isRecord(event.data)) {
            const projectId = typeof event.data.project_id === "string" ? event.data.project_id : "";
            if (projectId && projectId !== this.projectId) {
              return;
            }
          }
          void this.refreshBadge();
          return;
        }
        if (
          event.type === "work_item.updated" ||
          event.type === "comment.created" ||
          event.type === "gitlab_link.updated"
        ) {
          void this.refreshBadge();
        }
      });
    },
    stopPolling() {
      if (unsubscribeRealtime) {
        unsubscribeRealtime();
        unsubscribeRealtime = null;
      }
      this.watching = false;
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
