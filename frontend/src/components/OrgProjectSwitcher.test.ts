// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

import OrgProjectSwitcher from "./OrgProjectSwitcher.vue";

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

describe("OrgProjectSwitcher", () => {
  it("renders org options for platform-role users without memberships", () => {
    installLocalStorage();
    const pinia = createPinia();
    setActivePinia(pinia);

    const session = useSessionStore();
    session.user = { id: "u1", email: "admin@example.com", display_name: "Admin" } as never;
    session.platformRole = "admin";
    session.memberships = [];
    session.orgs = [
      { id: "org-1", name: "Org One", logo_url: null },
      { id: "org-2", name: "Org Two", logo_url: null },
    ] as never;

    const context = useContextStore();
    context.setOrgId("org-1");

    const wrapper = mount(OrgProjectSwitcher, {
      global: {
        plugins: [pinia],
      },
    });

    expect(wrapper.text()).toContain("Org One");
    expect(wrapper.text()).toContain("Org Two");
  });
});

