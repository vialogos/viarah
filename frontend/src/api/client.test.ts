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
        new Response(JSON.stringify({ tasks: [task], last_updated_at: "2026-02-03T00:00:00Z" }), {
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
    expect(wrapped.last_updated_at).toBe("2026-02-03T00:00:00Z");

    const bare = await api.listTasks("org", "project");
    expect(bare.tasks).toHaveLength(1);
    expect(bare.last_updated_at).toBeNull();
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

  it("supports project create + update + delete", async () => {
    const project = {
      id: "p1",
      org_id: "org",
      workflow_id: null,
      name: "Project",
      description: "Desc",
      created_at: "2026-02-03T00:00:00Z",
      updated_at: "2026-02-03T00:00:00Z",
    };

    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ project }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            project: { ...project, name: "Project 2", workflow_id: "w1", updated_at: "2026-02-04T00:00:00Z" },
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.createProject("org", { name: "Project", description: "Desc" });
    const [createUrl, createInit] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(createUrl).toBe("/api/orgs/org/projects");
    expect(createInit.method).toBe("POST");
    expect(createInit.body).toBe(JSON.stringify({ name: "Project", description: "Desc" }));
    expect(new Headers(createInit.headers).get("X-CSRFToken")).toBe("abc");

    await api.updateProject("org", "p1", { name: "Project 2", workflow_id: "w1" });
    const [updateUrl, updateInit] = fetchFn.mock.calls[1] as [string, RequestInit];
    expect(updateUrl).toBe("/api/orgs/org/projects/p1");
    expect(updateInit.method).toBe("PATCH");
    expect(updateInit.body).toBe(JSON.stringify({ name: "Project 2", workflow_id: "w1" }));
    expect(new Headers(updateInit.headers).get("X-CSRFToken")).toBe("abc");

    await api.deleteProject("org", "p1");
    const [deleteUrl, deleteInit] = fetchFn.mock.calls[2] as [string, RequestInit];
    expect(deleteUrl).toBe("/api/orgs/org/projects/p1");
    expect(deleteInit.method).toBe("DELETE");
    expect(new Headers(deleteInit.headers).get("X-CSRFToken")).toBe("abc");
    expect(deleteInit.body).toBeUndefined();
  });

  it("supports project membership list + add + delete", async () => {
    const membership = {
      id: "pm1",
      project_id: "p1",
      user: { id: "u1", email: "a@example.com", display_name: "Alice" },
      role: "member",
      created_at: "2026-02-03T00:00:00Z",
    };

    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ memberships: [membership] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ membership }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.listProjectMemberships("org", "p1");
    const [listUrl, listInit] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(listUrl).toBe("/api/orgs/org/projects/p1/memberships");
    expect(listInit.method).toBe("GET");
    expect(new Headers(listInit.headers).get("X-CSRFToken")).toBeNull();

    await api.addProjectMembership("org", "p1", "u1");
    const [addUrl, addInit] = fetchFn.mock.calls[1] as [string, RequestInit];
    expect(addUrl).toBe("/api/orgs/org/projects/p1/memberships");
    expect(addInit.method).toBe("POST");
    expect(addInit.body).toBe(JSON.stringify({ user_id: "u1" }));
    expect(new Headers(addInit.headers).get("X-CSRFToken")).toBe("abc");

    await api.deleteProjectMembership("org", "p1", "pm1");
    const [deleteUrl, deleteInit] = fetchFn.mock.calls[2] as [string, RequestInit];
    expect(deleteUrl).toBe("/api/orgs/org/projects/p1/memberships/pm1");
    expect(deleteInit.method).toBe("DELETE");
    expect(new Headers(deleteInit.headers).get("X-CSRFToken")).toBe("abc");
  });

  it("supports work item create + assignment patch", async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ epic: { id: "e1" } }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ task: { id: "t1" } }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ subtask: { id: "s1" } }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ task: { id: "t1", assignee_user_id: "u1" } }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.createEpic("org", "project", { title: "Epic", description: "Desc" });
    const [createEpicUrl, createEpicInit] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(createEpicUrl).toBe("/api/orgs/org/projects/project/epics");
    expect(createEpicInit.method).toBe("POST");
    expect(createEpicInit.body).toBe(JSON.stringify({ title: "Epic", description: "Desc" }));
    expect(new Headers(createEpicInit.headers).get("X-CSRFToken")).toBe("abc");

    await api.createTask("org", "e1", {
      title: "Task",
      description: "Task desc",
      status: "backlog",
      start_date: "2026-02-01",
      end_date: null,
    });
    const [createTaskUrl, createTaskInit] = fetchFn.mock.calls[1] as [string, RequestInit];
    expect(createTaskUrl).toBe("/api/orgs/org/epics/e1/tasks");
    expect(createTaskInit.method).toBe("POST");
    expect(createTaskInit.body).toBe(
      JSON.stringify({
        title: "Task",
        description: "Task desc",
        status: "backlog",
        start_date: "2026-02-01",
        end_date: null,
      })
    );
    expect(new Headers(createTaskInit.headers).get("X-CSRFToken")).toBe("abc");

    await api.createSubtask("org", "t1", {
      title: "Subtask",
      description: "Subtask desc",
      status: "backlog",
      start_date: null,
      end_date: "2026-02-02",
    });
    const [createSubtaskUrl, createSubtaskInit] = fetchFn.mock.calls[2] as [string, RequestInit];
    expect(createSubtaskUrl).toBe("/api/orgs/org/tasks/t1/subtasks");
    expect(createSubtaskInit.method).toBe("POST");
    expect(createSubtaskInit.body).toBe(
      JSON.stringify({
        title: "Subtask",
        description: "Subtask desc",
        status: "backlog",
        start_date: null,
        end_date: "2026-02-02",
      })
    );
    expect(new Headers(createSubtaskInit.headers).get("X-CSRFToken")).toBe("abc");

    await api.patchTask("org", "t1", { assignee_user_id: "u1" });
    const [patchTaskUrl, patchTaskInit] = fetchFn.mock.calls[3] as [string, RequestInit];
    expect(patchTaskUrl).toBe("/api/orgs/org/tasks/t1");
    expect(patchTaskInit.method).toBe("PATCH");
    expect(patchTaskInit.body).toBe(JSON.stringify({ assignee_user_id: "u1" }));
    expect(new Headers(patchTaskInit.headers).get("X-CSRFToken")).toBe("abc");
  });

  it("supports workflow create + list", async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            workflow: {
              id: "w1",
              org_id: "org",
              name: "Workflow",
              created_by_user_id: "u1",
              created_at: "2026-02-03T00:00:00Z",
              updated_at: "2026-02-03T00:00:00Z",
            },
            stages: [
              {
                id: "s1",
                workflow_id: "w1",
                name: "Done",
                order: 1,
                is_done: true,
                is_qa: false,
                counts_as_wip: false,
                created_at: "2026-02-03T00:00:00Z",
                updated_at: "2026-02-03T00:00:00Z",
              },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            workflows: [
              {
                id: "w1",
                org_id: "org",
                name: "Workflow",
                created_by_user_id: "u1",
                created_at: "2026-02-03T00:00:00Z",
                updated_at: "2026-02-03T00:00:00Z",
              },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
      );

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.createWorkflow("org", {
      name: "Workflow",
      stages: [{ name: "Done", order: 1, category: "done", progress_percent: 100, is_done: true }],
    });

    const [createUrl, createInit] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(createUrl).toBe("/api/orgs/org/workflows");
    expect(createInit.method).toBe("POST");
    expect(createInit.body).toBe(
      JSON.stringify({
        name: "Workflow",
        stages: [{ name: "Done", order: 1, category: "done", progress_percent: 100, is_done: true }],
      })
    );

    const createHeaders = new Headers(createInit.headers);
    expect(createHeaders.get("X-CSRFToken")).toBe("abc");

    const workflows = await api.listWorkflows("org");
    expect(workflows.workflows).toHaveLength(1);
  });

  it("lists audit events", async () => {
    const fetchFn = vi.fn(async (_url: string, _init?: RequestInit) => {
      return new Response(
        JSON.stringify({
          events: [
            {
              id: "e1",
              created_at: "2026-02-03T00:00:00Z",
              event_type: "workflow.created",
              actor_user_id: "u1",
              actor_user: { id: "u1", email: "pm@example.com", display_name: "PM" },
              metadata: { workflow_id: "w1" },
            },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    });

    const api = createApiClient({ fetchFn: fetchFn as unknown as typeof fetch });
    const res = await api.listAuditEvents("org");
    expect(res.events).toHaveLength(1);

    const [url, init] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/orgs/org/audit-events");
    expect(init.method).toBe("GET");
  });

  it("lists templates with type filter", async () => {
    const fetchFn = vi.fn(async (_url: string, _init?: RequestInit) => {
      return new Response(JSON.stringify({ templates: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });

    const api = createApiClient({ fetchFn: fetchFn as unknown as typeof fetch });

    await api.listTemplates("org", { type: "report" });

    expect(fetchFn).toHaveBeenCalledTimes(1);
    const [url, init] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/orgs/org/templates?type=report");
    expect(init.method).toBe("GET");
  });

  it("supports sow portal endpoints", async () => {
    const membership = {
      id: "mem1",
      role: "client",
      user: { id: "u1", email: "client@example.com", display_name: "Client" },
    };

    const sow = {
      id: "sow1",
      org_id: "org",
      project_id: "p1",
      template_id: "tpl1",
      current_version_id: "sv1",
      created_by_user_id: "pm1",
      created_at: "2026-02-03T00:00:00Z",
      updated_at: "2026-02-03T00:00:00Z",
    };

    const signer = {
      id: "sig1",
      sow_version_id: "sv1",
      signer_user_id: "u1",
      status: "pending",
      decision_comment: "",
      typed_signature: "",
      responded_at: null,
      created_at: "2026-02-03T00:00:00Z",
    };

    const listItem = {
      sow,
      version: {
        id: "sv1",
        version: 1,
        status: "pending_signature",
        locked_at: "2026-02-03T00:00:00Z",
        created_at: "2026-02-03T00:00:00Z",
      },
      signers: [signer],
      pdf: null,
    };

    const sowResponse = {
      sow,
      version: {
        id: "sv1",
        sow_id: "sow1",
        version: 1,
        template_version_id: "tplv1",
        variables: {},
        status: "pending_signature",
        locked_at: "2026-02-03T00:00:00Z",
        content_sha256: "abc",
        created_by_user_id: "pm1",
        created_at: "2026-02-03T00:00:00Z",
        body_markdown: "# SoW",
        body_html: "<h1>SoW</h1>",
      },
      signers: [signer],
      pdf: null,
    };

    const pdf = {
      id: "pdf1",
      sow_version_id: "sv1",
      status: "queued",
      celery_task_id: "celery1",
      created_at: "2026-02-03T00:00:00Z",
      started_at: null,
      completed_at: null,
      blocked_urls: [],
      missing_images: [],
      error_code: null,
      error_message: null,
      qa_report: {},
      pdf_sha256: null,
      pdf_size_bytes: 0,
      pdf_rendered_at: null,
    };

    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ memberships: [membership] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ sows: [listItem] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(sowResponse), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ sow: sowResponse.sow, version: sowResponse.version, signers: sowResponse.signers }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ sow: sowResponse.sow, version: sowResponse.version, signers: sowResponse.signers }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ sow: sowResponse.sow, version: sowResponse.version, signers: sowResponse.signers }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "accepted", pdf }), {
          status: 202,
          headers: { "content-type": "application/json" },
        })
      );

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.listOrgMemberships("org", { role: "client" });
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/orgs/org/memberships?role=client");

    await api.listSows("org", { projectId: "p1", status: "pending_signature" });
    expect(fetchFn.mock.calls[1]?.[0]).toBe("/api/orgs/org/sows?project_id=p1&status=pending_signature");

    const sowDetail = await api.getSow("org", "sow1");
    expect(sowDetail.sow.id).toBe("sow1");

    const createRes = await api.createSow("org", {
      project_id: "p1",
      template_id: "tpl1",
      template_version_id: null,
      variables: {},
      signer_user_ids: ["u1"],
    });
    expect(createRes.pdf).toBeNull();

    const sendRes = await api.sendSow("org", "sow1");
    expect(sendRes.version.status).toBe("pending_signature");

    const respondRes = await api.respondSow("org", "sow1", { decision: "reject", comment: "No" });
    expect(respondRes.sow.id).toBe("sow1");

    const pdfRes = await api.requestSowPdf("org", "sow1");
    expect(pdfRes.status).toBe("accepted");
    expect(pdfRes.pdf.id).toBe("pdf1");

    const [, sendInit] = fetchFn.mock.calls[4] as [string, RequestInit];
    const headers = new Headers(sendInit.headers);
    expect(sendInit.method).toBe("POST");
    expect(headers.get("X-CSRFToken")).toBe("abc");
  });

  it("publishes report run and returns share_url once", async () => {
    const fetchFn = vi.fn(async (_url: string, _init?: RequestInit) => {
      return new Response(
        JSON.stringify({
          share_link: {
            id: "sl1",
            org_id: "org",
            report_run_id: "r1",
            expires_at: null,
            revoked_at: null,
            created_at: "2026-02-05T00:00:00Z",
            created_by: null,
            access_count: 0,
            last_access_at: null,
          },
          share_url: "https://example.test/p/r/token",
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    });

    const api = createApiClient({ fetchFn: fetchFn as unknown as typeof fetch });

    const res = await api.publishReportRun("org", "r1");
    expect(res.share_link.id).toBe("sl1");
    expect(res.share_url).toBe("https://example.test/p/r/token");

    const [url, init] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/orgs/org/report-runs/r1/publish");
    expect(init.method).toBe("POST");
  });

  it("supports api key list + create + rotate + revoke", async () => {
    const apiKey = {
      id: "k1",
      org_id: "org",
      project_id: null,
      name: "viarah-cli",
      prefix: "vl_",
      scopes: ["work:read"],
      created_by_user_id: "u1",
      created_at: "2026-02-03T00:00:00Z",
      revoked_at: null,
      rotated_at: null,
    };

    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ api_keys: [apiKey] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ api_key: apiKey, token: "tok1" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ api_key: { ...apiKey, rotated_at: "2026-02-04T00:00:00Z" }, token: "tok2" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ api_key: { ...apiKey, revoked_at: "2026-02-05T00:00:00Z" } }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.listApiKeys("org");
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/api-keys?org_id=org");

    await api.createApiKey("org", { name: "viarah-cli", scopes: ["work:read"] });
    const [createUrl, createInit] = fetchFn.mock.calls[1] as [string, RequestInit];
    expect(createUrl).toBe("/api/api-keys");
    expect(createInit.method).toBe("POST");
    expect(createInit.body).toBe(JSON.stringify({ org_id: "org", name: "viarah-cli", scopes: ["work:read"] }));
    expect(new Headers(createInit.headers).get("X-CSRFToken")).toBe("abc");

    await api.rotateApiKey("k1");
    const [rotateUrl, rotateInit] = fetchFn.mock.calls[2] as [string, RequestInit];
    expect(rotateUrl).toBe("/api/api-keys/k1/rotate");
    expect(rotateInit.method).toBe("POST");
    expect(rotateInit.body).toBe(JSON.stringify({}));
    expect(new Headers(rotateInit.headers).get("X-CSRFToken")).toBe("abc");

    await api.revokeApiKey("k1");
    const [revokeUrl, revokeInit] = fetchFn.mock.calls[3] as [string, RequestInit];
    expect(revokeUrl).toBe("/api/api-keys/k1/revoke");
    expect(revokeInit.method).toBe("POST");
    expect(revokeInit.body).toBe(JSON.stringify({}));
    expect(new Headers(revokeInit.headers).get("X-CSRFToken")).toBe("abc");
  });

  it("supports org invites, membership updates, and invite accept", async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            invite: {
              id: "i1",
              org_id: "org",
              email: "invitee@example.com",
              role: "member",
              expires_at: "2026-02-03T00:00:00Z",
            },
            token: "tok",
            invite_url: "/invite/accept?token=tok",
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
	            membership: {
	              id: "m1",
	              org: { id: "org", name: "Org", logo_url: null },
	              role: "pm",
	            },
	          }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
	            membership: {
	              id: "m2",
	              org: { id: "org", name: "Org", logo_url: null },
	              role: "member",
	            },
	            person: {
              id: "p1",
              display: "Invitee",
              email: "invitee@example.com",
            },
            needs_profile_setup: true,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
      );

    const api = createApiClient({
      fetchFn: fetchFn as unknown as typeof fetch,
      getCookie: (name: string) => (name === "csrftoken" ? "abc" : null),
    });

    await api.createOrgInvite("org", { email: "invitee@example.com", role: "member" });
    const [inviteUrl, inviteInit] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(inviteUrl).toBe("/api/orgs/org/invites");
    expect(inviteInit.method).toBe("POST");
    expect(inviteInit.credentials).toBe("include");
    expect(new Headers(inviteInit.headers).get("X-CSRFToken")).toBe("abc");
    expect(inviteInit.body).toBe(JSON.stringify({ email: "invitee@example.com", role: "member" }));

    await api.updateOrgMembership("org", "m1", { role: "pm" });
    const [updateUrl, updateInit] = fetchFn.mock.calls[1] as [string, RequestInit];
    expect(updateUrl).toBe("/api/orgs/org/memberships/m1");
    expect(updateInit.method).toBe("PATCH");
    expect(updateInit.credentials).toBe("include");
    expect(new Headers(updateInit.headers).get("X-CSRFToken")).toBe("abc");
    expect(updateInit.body).toBe(JSON.stringify({ role: "pm" }));

    await api.acceptInvite({ token: "tok", password: "pw", display_name: "Invitee" });
    const [acceptUrl, acceptInit] = fetchFn.mock.calls[2] as [string, RequestInit];
    expect(acceptUrl).toBe("/api/invites/accept");
    expect(acceptInit.method).toBe("POST");
    expect(acceptInit.credentials).toBe("include");
    expect(new Headers(acceptInit.headers).get("X-CSRFToken")).toBe("abc");
    expect(acceptInit.body).toBe(JSON.stringify({ token: "tok", password: "pw", display_name: "Invitee" }));
  });

});
