import { describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "./client";

describe("createApiClient", () => {
  it("sends credentials + CSRF token for POST", async () => {
    const fetchFn = vi.fn(async (_url: string, _init?: RequestInit) => {
      return new Response(JSON.stringify({ user: null, memberships: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.login("pm@example.com", "pw");

    expect(fetchFn).toHaveBeenCalledTimes(1);
    const [url, init] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/auth/login");
    expect(init.credentials).toBe("include");
    expect(init.method).toBe("POST");

    const headers = new Headers(init.headers);
    expect(headers.get("Accept")).toBe("application/json");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-CSRFToken")).toBe("abc");
    expect(init.body).toBe(JSON.stringify({ email: "pm@example.com", password: "pw" }));
  });

  it("does not send CSRF token for GET", async () => {
    const fetchFn = vi.fn(async (_url: string, _init?: RequestInit) => {
      return new Response(JSON.stringify({ user: null, memberships: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: () => "abc",
    });

    await api.getMe();

    const [, init] = fetchFn.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRFToken")).toBeNull();
  });

  it("throws ApiError with backend error message", async () => {
    const fetchFn = vi.fn(async (_url: string, _init?: RequestInit) => {
      return new Response(JSON.stringify({ error: "invalid credentials" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      });
    });

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: () => "abc",
    });

    try {
      await api.login("pm@example.com", "pw");
      throw new Error("expected login() to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(401);
      expect(apiErr.message).toBe("invalid credentials");
    }
  });

  it("parses list responses that are wrapped or bare arrays", async () => {
    const task = {
      id: "t1",
      epic_id: "e1",
      title: "Task",
      start_date: null,
      end_date: null,
      status: "backlog",
      progress: 0.25,
      progress_why: { policy: "average_of_subtask_progress" },
    };

    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ tasks: [task] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([task]), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

    const api = createApiClient({ fetchFn: fetchFn as unknown as typeof fetch });

    const wrapped = await api.listTasks("org", "project");
    expect(wrapped.tasks).toHaveLength(1);

    const bare = await api.listTasks("org", "project");
    expect(bare.tasks).toHaveLength(1);
  });

  it("sends CSRF token for PATCH", async () => {
    const fetchFn = vi.fn(async (_url: string, _init?: RequestInit) => {
      return new Response(
        JSON.stringify({
          subtask: {
            id: "s1",
            task_id: "t1",
            workflow_stage_id: "stage1",
            title: "Subtask",
            start_date: null,
            end_date: null,
            status: "backlog",
            progress: 0.1,
            progress_why: { policy: "stage_position" },
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    });

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.updateSubtaskStage("org", "s1", "stage1");

    expect(fetchFn).toHaveBeenCalledTimes(1);
    const [url, init] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/orgs/org/subtasks/s1");
    expect(init.method).toBe("PATCH");

    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRFToken")).toBe("abc");
    expect(init.body).toBe(JSON.stringify({ workflow_stage_id: "stage1" }));
  });
});
