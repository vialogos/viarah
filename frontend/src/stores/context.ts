import { defineStore } from "pinia";

import { api } from "../api";
import type { ApiMembership, Project } from "../api/types";

const ORG_ID_KEY = "viarah.org_id";
const PROJECT_ID_KEY = "viarah.project_id";
const ORG_SCOPE_KEY = "viarah.org_scope";
const PROJECT_SCOPE_KEY = "viarah.project_scope";

export type ContextScopeMode = "single" | "all";

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readLocalStorage(key: string): string {
  if (!canUseLocalStorage()) {
    return "";
  }
  return window.localStorage.getItem(key) ?? "";
}

function readScope(key: string): ContextScopeMode {
  const raw = readLocalStorage(key);
  if (raw === "all") {
    return "all";
  }
  return "single";
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
  state: () => {
    const orgScope = readScope(ORG_SCOPE_KEY);
    const projectScope = readScope(PROJECT_SCOPE_KEY);
    const orgId = orgScope === "all" ? "" : readLocalStorage(ORG_ID_KEY);
    const projectId = orgScope === "all" || projectScope === "all" ? "" : readLocalStorage(PROJECT_ID_KEY);

    return {
      orgScope,
      projectScope,
      orgId,
      projectId,
      projects: [] as Project[],
      loadingProjects: false,
      error: "" as string,
    };
  },
  getters: {
    isAnyAllScopeActive(state): boolean {
      return state.orgScope === "all" || state.projectScope === "all";
    },
    hasConcreteScope(state): boolean {
      return (
        state.orgScope === "single" &&
        state.projectScope === "single" &&
        Boolean(state.orgId) &&
        Boolean(state.projectId)
      );
    },
  },
  actions: {
    reset() {
      this.orgId = "";
      this.projectId = "";
      this.orgScope = "single";
      this.projectScope = "single";
      this.projects = [];
      this.loadingProjects = false;
      this.error = "";
      writeLocalStorage(ORG_ID_KEY, "");
      writeLocalStorage(PROJECT_ID_KEY, "");
      writeLocalStorage(ORG_SCOPE_KEY, "single");
      writeLocalStorage(PROJECT_SCOPE_KEY, "single");
    },
    syncFromMemberships(memberships: ApiMembership[]) {
      if (this.orgScope === "all") {
        return;
      }

      const orgIds = new Set(memberships.map((m) => m.org.id));
      if (this.orgId && orgIds.has(this.orgId)) {
        return;
      }

      const nextOrgId = memberships[0]?.org.id ?? "";
      this.setOrgId(nextOrgId);
    },
    setOrgScopeAll() {
      if (this.orgScope === "all") {
        return;
      }

      this.orgScope = "all";
      writeLocalStorage(ORG_SCOPE_KEY, "all");

      // In All orgs mode, project selection is not meaningful.
      this.projectScope = "single";
      writeLocalStorage(PROJECT_SCOPE_KEY, "single");

      this.orgId = "";
      this.projectId = "";
      writeLocalStorage(ORG_ID_KEY, "");
      writeLocalStorage(PROJECT_ID_KEY, "");

      this.projects = [];
      this.error = "";
    },
    setOrgId(orgId: string) {
      if (this.orgScope === "single" && this.orgId === orgId) {
        return;
      }

      this.orgScope = "single";
      writeLocalStorage(ORG_SCOPE_KEY, "single");

      this.orgId = orgId;
      writeLocalStorage(ORG_ID_KEY, orgId);

      // Reset to concrete project selection by default when switching orgs.
      this.projectScope = "single";
      writeLocalStorage(PROJECT_SCOPE_KEY, "single");

      this.projectId = "";
      writeLocalStorage(PROJECT_ID_KEY, "");

      this.projects = [];
      this.error = "";
    },
    setProjectScopeAll() {
      if (this.projectScope === "all") {
        return;
      }
      if (this.orgScope === "all") {
        return;
      }
      if (!this.orgId) {
        return;
      }

      this.projectScope = "all";
      writeLocalStorage(PROJECT_SCOPE_KEY, "all");

      this.projectId = "";
      writeLocalStorage(PROJECT_ID_KEY, "");
    },
    setProjectId(projectId: string) {
      this.projectScope = "single";
      writeLocalStorage(PROJECT_SCOPE_KEY, "single");

      this.projectId = projectId;
      writeLocalStorage(PROJECT_ID_KEY, projectId);
    },
    async refreshProjects() {
      if (this.orgScope === "all" || !this.orgId) {
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

        if (this.projectScope === "all") {
          this.projectId = "";
          writeLocalStorage(PROJECT_ID_KEY, "");
          return;
        }

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
