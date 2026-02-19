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
      getTask: vi.fn(async () => ({
        task: {
          id: "t1",
          epic_id: "e1",
          assignee_user_id: null,
          title: "Task",
          description: "",
          start_date: null,
          end_date: null,
          status: "backlog",
          client_safe: false,
          created_at: "2026-02-03T00:00:00Z",
          updated_at: "2026-02-03T00:00:00Z",
          custom_field_values: [],
          progress: 0,
          progress_why: { policy: "average_of_subtask_progress" },
        },
      })),
      listSubtasks: vi.fn(async () => ({ subtasks: [] })),
      getEpic: vi.fn(async () => ({
        epic: {
          id: "e1",
          project_id: "p1",
          title: "Epic",
          description: "",
          status: null,
          created_at: "2026-02-03T00:00:00Z",
          updated_at: "2026-02-03T00:00:00Z",
          progress: 0,
          progress_why: { policy: "average_of_subtask_progress" },
        },
      })),
      getProject: vi.fn(async () => ({
        project: {
          id: "p1",
          org_id: "org-1",
          workflow_id: null,
          name: "Project",
          description: "",
          created_at: "2026-02-03T00:00:00Z",
          updated_at: "2026-02-03T00:00:00Z",
        },
      })),
      listWorkflowStages: vi.fn(async () => ({ stages: [] })),
      listTaskComments: vi.fn(async () => ({ comments: [] })),
      listTaskAttachments: vi.fn(async () => ({ attachments: [] })),
      listTaskParticipants: vi.fn(async () => ({
        participants: [
          {
            user: { id: "u2", email: "alice@example.com", display_name: "Alice" },
            person: null,
            org_role: "member",
            sources: ["manual", "comment"],
          },
        ],
      })),
      listCustomFields: vi.fn(async () => ({ custom_fields: [] })),
      listProjectMemberships: vi.fn(async () => ({ memberships: [] })),
      createTaskParticipant: vi.fn(async () => ({
        participant: { task_id: "t1", user_id: "u2", created_at: "2026-02-03T00:00:00Z" },
      })),
      deleteTaskParticipant: vi.fn(async () => ({})),
      patchTask: vi.fn(async () => ({
        task: {
          id: "t1",
          epic_id: "e1",
          assignee_user_id: null,
          title: "Task",
          description: "",
          start_date: null,
          end_date: null,
          status: "backlog",
          client_safe: false,
          created_at: "2026-02-03T00:00:00Z",
          updated_at: "2026-02-03T00:00:00Z",
          custom_field_values: [],
          progress: 0,
          progress_why: { policy: "average_of_subtask_progress" },
        },
      })),
    },
  };
});

import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";

import { api } from "../api";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

import WorkDetailPage from "./WorkDetailPage.vue";

async function flushAsync() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("WorkDetailPage", () => {
  it("renders the assignment drawer and wires participant actions", async () => {
    vi.stubGlobal("WebSocket", undefined as unknown as typeof WebSocket);

    const pinia = createPinia();
    setActivePinia(pinia);

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/work/:taskId", component: WorkDetailPage, props: true },
        { path: "/login", component: { template: "<div />" } },
      ],
    });
    await router.push("/work/t1");
    await router.isReady();

    const session = useSessionStore();
    session.user = { id: "u1", email: "pm@example.com", display_name: "PM" } as never;
    session.memberships = [{ id: "m1", role: "pm", org: { id: "org-1", name: "Org" } }] as never;

    const context = useContextStore();
    context.setOrgId("org-1");
    context.setProjectId("p1");

    const wrapper = mount(WorkDetailPage, {
      props: { taskId: "t1" },
      global: {
        plugins: [pinia, router],
        components: {
          "pf-drawer": {
            template: "<div><slot /><slot name=\"content\" /></div>",
          },
        },
      },
    });

    await flushAsync();
    await flushAsync();
    await flushAsync();

    expect(api.getTask).toHaveBeenCalled();
    expect(api.listTaskParticipants).toHaveBeenCalled();

    const drawer = wrapper.find(".assignment-drawer");
    expect(drawer.exists()).toBe(true);

    const manage = wrapper
      .findAll("pf-button")
      .find((node) => node.text().trim() === "Manage assignment");
    expect(manage).toBeTruthy();
    expect(manage!.attributes("aria-expanded")).not.toBe("true");
    await manage!.trigger("click");
    await flushAsync();

    const manageAfterExpand = wrapper
      .findAll("pf-button")
      .find((node) => node.text().trim() === "Manage assignment");
    expect(manageAfterExpand).toBeTruthy();
    expect(manageAfterExpand!.attributes("aria-expanded")).toBe("true");
    expect(wrapper.text()).toContain("Participants:");
    expect(wrapper.text()).toContain("Alice");

    const removeManual = wrapper
      .findAll("pf-button")
      .find((node) => node.text().trim() === "Remove manual");
    expect(removeManual).toBeTruthy();
    await removeManual!.trigger("click");
    await flushAsync();

    expect(api.deleteTaskParticipant).toHaveBeenCalledWith("org-1", "t1", "u2");

    const close = wrapper.find("pf-drawer-close-button");
    expect(close.exists()).toBe(true);
    await close.trigger("click");
    await flushAsync();

    const manageAfterClose = wrapper
      .findAll("pf-button")
      .find((node) => node.text().trim() === "Manage assignment");
    expect(manageAfterClose).toBeTruthy();
    expect(manageAfterClose!.attributes("aria-expanded")).not.toBe("true");

    wrapper.unmount();
  });
});
