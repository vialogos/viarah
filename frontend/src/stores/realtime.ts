import { defineStore } from "pinia";

export type OrgRealtimeEvent = {
  event_id?: string;
  occurred_at?: string;
  org_id?: string;
  type?: string;
  data?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

type Listener = (event: OrgRealtimeEvent) => void;
const listeners = new Set<Listener>();

export const useRealtimeStore = defineStore("realtime", {
  state: () => ({
    orgId: "" as string,
    connected: false,
    error: "" as string,

    acquireCount: 0,

    socket: null as WebSocket | null,
    reconnectAttempt: 0,
    reconnectTimeoutId: null as number | null,
    desiredOrgId: "" as string,
  }),
  actions: {
    acquire(orgId: string): () => void {
      const nextOrgId = String(orgId || "").trim();
      if (!nextOrgId) {
        return () => {};
      }

      this.acquireCount += 1;
      this.start(nextOrgId);

      let released = false;
      return () => {
        if (released) {
          return;
        }
        released = true;
        this.acquireCount = Math.max(0, this.acquireCount - 1);
        if (this.acquireCount === 0) {
          this.stop();
        }
      };
    },

    subscribe(listener: Listener): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },

    start(orgId: string) {
      if (!orgId) {
        this._stopSocket();
        this.desiredOrgId = "";
        this.orgId = "";
        return;
      }

      const alreadyOnOrg = this.socket && this.desiredOrgId === orgId && this.orgId === orgId;
      if (alreadyOnOrg) {
        return;
      }

      if (typeof WebSocket === "undefined") {
        return;
      }

      this._stopSocket();

      this.orgId = orgId;
      this.desiredOrgId = orgId;
      this.error = "";

      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      const wsUrl = `${scheme}://${window.location.host}/ws/orgs/${orgId}/events`;
      const ws = new WebSocket(wsUrl);
      this.socket = ws;

      ws.onopen = () => {
        this.connected = true;
        this.reconnectAttempt = 0;
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(String(event.data)) as unknown;
          if (!isRecord(parsed)) {
            return;
          }
          const payload: OrgRealtimeEvent = {
            event_id: typeof parsed.event_id === "string" ? parsed.event_id : undefined,
            occurred_at: typeof parsed.occurred_at === "string" ? parsed.occurred_at : undefined,
            org_id: typeof parsed.org_id === "string" ? parsed.org_id : undefined,
            type: typeof parsed.type === "string" ? parsed.type : undefined,
            data: parsed.data,
          };

          for (const listener of listeners) {
            try {
              listener(payload);
            } catch {
              continue;
            }
          }
        } catch {
          return;
        }
      };

      ws.onclose = (closeEvent) => {
        this.connected = false;
        this.socket = null;

        if (!this.desiredOrgId || this.desiredOrgId !== orgId || this.orgId !== orgId) {
          return;
        }

        if (closeEvent.code === 4400 || closeEvent.code === 4401 || closeEvent.code === 4403) {
          return;
        }

        this._scheduleReconnect(orgId);
      };
    },

    _stopSocket() {
      if (this.reconnectTimeoutId != null) {
        window.clearTimeout(this.reconnectTimeoutId);
      }
      this.reconnectTimeoutId = null;
      this.reconnectAttempt = 0;

      if (this.socket) {
        this.socket.close();
      }
      this.socket = null;
      this.connected = false;
      this.error = "";
    },

    stop() {
      this.desiredOrgId = "";
      this.acquireCount = 0;
      this._stopSocket();
      this.orgId = "";
    },

    _scheduleReconnect(orgId: string) {
      if (this.reconnectTimeoutId != null) {
        return;
      }
      const delayMs = Math.min(10_000, 1_000 * 2 ** this.reconnectAttempt);
      this.reconnectAttempt = Math.min(this.reconnectAttempt + 1, 10);

      this.reconnectTimeoutId = window.setTimeout(() => {
        this.reconnectTimeoutId = null;
        if (!this.desiredOrgId || this.desiredOrgId !== orgId || this.orgId !== orgId) {
          return;
        }
        this.start(orgId);
      }, delayMs);
    },
  },
});
