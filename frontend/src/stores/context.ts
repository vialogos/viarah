import { defineStore } from "pinia";

import { api } from "../api";
import type { ApiMembership, Project } from "../api/types";

const ORG_ID_KEY = "viarah.org_id";
const PROJECT_ID_KEY = "viarah.project_id";

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readLocalStorage(key: string): string {
  if (!canUseLocalStorage()) {
    return "";
  }
  return window.localStorage.getItem(key) ?? "";
}

function writeLocalStorage(key: string, value: string) {
  if (!canUseLocalStorage()) {
    return;
  }
  if (!value) {
    window.localStorage.removeItem(key);
  } else {
    window.localStorage.setItem(key, value);
  }
}

export const useContextStore = defineStore("context", {
  state: () => ({
    orgId: readLocalStorage(ORG_ID_KEY),
    projectId: readLocalStorage(PROJECT_ID_KEY),
    projects: [] as Project[],
    loadingProjects: false,
    error: "" as string,
  }),
  actions: {
    reset() {
      this.orgId = "";
      this.projectId = "";
      this.projects = [];
      this.loadingProjects = false;
      this.error = "";
      writeLocalStorage(ORG_ID_KEY, "");
      writeLocalStorage(PROJECT_ID_KEY, "");
    },
    syncFromMemberships(memberships: ApiMembership[]) {
      const orgIds = new Set(memberships.map((m) => m.org.id));
      if (this.orgId && orgIds.has(this.orgId)) {
        return;
      }

      const nextOrgId = memberships[0]?.org.id ?? "";
      this.setOrgId(nextOrgId);
    },
    setOrgId(orgId: string) {
      if (this.orgId === orgId) {
        return;
      }

      this.orgId = orgId;
      writeLocalStorage(ORG_ID_KEY, orgId);

      this.projectId = "";
      writeLocalStorage(PROJECT_ID_KEY, "");

      this.projects = [];
      this.error = "";
    },
    setProjectId(projectId: string) {
      this.projectId = projectId;
      writeLocalStorage(PROJECT_ID_KEY, projectId);
    },
    async refreshProjects() {
      if (!this.orgId) {
        this.projects = [];
        this.projectId = "";
        writeLocalStorage(PROJECT_ID_KEY, "");
        return;
      }

      this.loadingProjects = true;
      this.error = "";
      try {
        const res = await api.listProjects(this.orgId);
        this.projects = res.projects;

        if (this.projectId && this.projects.some((p) => p.id === this.projectId)) {
          return;
        }

        const nextProjectId = this.projects[0]?.id ?? "";
        this.setProjectId(nextProjectId);
      } catch (err) {
        this.projects = [];
        this.error = err instanceof Error ? err.message : String(err);
      } finally {
        this.loadingProjects = false;
      }
    },
  },
});
