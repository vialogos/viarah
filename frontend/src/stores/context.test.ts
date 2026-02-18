import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useContextStore } from "./context";

function installLocalStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial));
  const localStorage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
  };

  (globalThis as any).window = { localStorage };
}

describe("useContextStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    installLocalStorage();
  });

  it("defaults to single scope with empty ids", () => {
    const context = useContextStore();
    expect(context.orgScope).toBe("single");
    expect(context.projectScope).toBe("single");
    expect(context.orgId).toBe("");
    expect(context.projectId).toBe("");
    expect(context.isAnyAllScopeActive).toBe(false);
    expect(context.hasConcreteScope).toBe(false);
  });

  it("treats All orgs as global scope and clears ids", () => {
    installLocalStorage({
      "viarah.org_scope": "all",
      "viarah.org_id": "org-1",
      "viarah.project_id": "project-1",
    });
    setActivePinia(createPinia());

    const context = useContextStore();
    expect(context.orgScope).toBe("all");
    expect(context.orgId).toBe("");
    expect(context.projectId).toBe("");
    expect(context.isAnyAllScopeActive).toBe(true);
    expect(context.hasConcreteScope).toBe(false);
  });

  it("setProjectScopeAll clears projectId but keeps orgId", () => {
    const context = useContextStore();
    context.setOrgId("org-1");
    context.setProjectId("project-1");
    expect(context.hasConcreteScope).toBe(true);

    context.setProjectScopeAll();
    expect(context.projectScope).toBe("all");
    expect(context.orgId).toBe("org-1");
    expect(context.projectId).toBe("");
    expect(context.isAnyAllScopeActive).toBe(true);
    expect(context.hasConcreteScope).toBe(false);
  });
});

