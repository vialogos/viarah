// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => {
  class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  }

  return {
    ApiError,
    api: {
      listOrgPeople: vi.fn(async () => ({ people: [] })),
      listOrgInvites: vi.fn(async () => ({ invites: [] })),
      searchPeopleAvailability: vi.fn(async () => ({ matches: [] })),
      resendOrgInvite: vi.fn(async () => ({ token: "tok", invite_url: "/invite/accept?token=tok" })),
      revokeOrgInvite: vi.fn(async () => ({})),
    },
  };
});

import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";

import { api } from "../api";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

import TeamPage from "./TeamPage.vue";

describe("TeamPage", () => {
  it("renders /team without crashing", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/team", component: TeamPage }],
    });
    await router.push("/team");
    await router.isReady();

    const session = useSessionStore();
    session.user = { id: "u1", email: "pm@example.com", display_name: "PM" } as never;
    session.memberships = [{ id: "m1", role: "pm", org: { id: "org-1", name: "Org" } }] as never;

    const context = useContextStore();
    context.setOrgId("org-1");

    vi.useFakeTimers();

    const wrapper = mount(TeamPage, {
      global: {
        plugins: [pinia, router],
      },
    });

    await vi.runAllTimersAsync();

    expect(api.listOrgPeople).toHaveBeenCalled();
    expect(api.listOrgInvites).toHaveBeenCalled();
    expect(wrapper.exists()).toBe(true);

    wrapper.unmount();

    vi.useRealTimers();
  });
});
