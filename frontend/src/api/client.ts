import { getCookieValue } from "./cookies";
import type {
  Epic,
  EpicResponse,
  EpicsResponse,
  MeResponse,
  Project,
  ProjectResponse,
  ProjectsResponse,
  Subtask,
  SubtaskResponse,
  SubtasksResponse,
  Task,
  TaskResponse,
  TasksResponse,
  WorkflowStage,
  WorkflowStagesResponse,
} from "./types";

type FetchFn = typeof fetch;

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, options: { status: number; payload: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.payload = options.payload;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function extractListValue<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) {
    return payload as T[];
  }

  if (isRecord(payload) && Array.isArray(payload[key])) {
    return payload[key] as T[];
  }

  throw new Error(`unexpected response shape (expected '${key}' list)`);
}

function extractObjectValue<T>(payload: unknown, key: string): T {
  if (isRecord(payload) && isRecord(payload[key])) {
    return payload[key] as T;
  }

  throw new Error(`unexpected response shape (expected '${key}' object)`);
}

function buildUrl(baseUrl: string, path: string, query?: Record<string, string | undefined>) {
  const url = `${baseUrl}${path}`;
  if (!query) {
    return url;
  }

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value == null || value === "") {
      continue;
    }
    params.set(key, value);
  }

  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export interface ApiClient {
  getMe(): Promise<MeResponse>;
  login(email: string, password: string): Promise<MeResponse>;
  logout(): Promise<void>;
  listProjects(orgId: string): Promise<ProjectsResponse>;
  getProject(orgId: string, projectId: string): Promise<ProjectResponse>;
  listEpics(orgId: string, projectId: string): Promise<EpicsResponse>;
  getEpic(orgId: string, epicId: string): Promise<EpicResponse>;
  listTasks(
    orgId: string,
    projectId: string,
    options?: { status?: string }
  ): Promise<TasksResponse>;
  getTask(orgId: string, taskId: string): Promise<TaskResponse>;
  listSubtasks(
    orgId: string,
    taskId: string,
    options?: { status?: string }
  ): Promise<SubtasksResponse>;
  updateSubtaskStage(
    orgId: string,
    subtaskId: string,
    workflowStageId: string | null
  ): Promise<SubtaskResponse>;
  listWorkflowStages(orgId: string, workflowId: string): Promise<WorkflowStagesResponse>;
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchFn?: FetchFn;
  getCookie?: (name: string) => string | null;
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = options.baseUrl ?? "";
  const fetchFn = options.fetchFn ?? fetch;
  const getCookie = options.getCookie ?? ((name: string) => getCookieValue(name));

  async function request<TResponse>(
    path: string,
    {
      method = "GET",
      body,
      query,
    }: {
      method?: string;
      body?: unknown;
      query?: Record<string, string | undefined>;
    } = {}
  ): Promise<TResponse> {
    const url = buildUrl(baseUrl, path, query);
    const headers = new Headers();
    headers.set("Accept", "application/json");

    const upperMethod = method.toUpperCase();
    const isStateChanging = !["GET", "HEAD", "OPTIONS"].includes(upperMethod);
    if (isStateChanging) {
      const csrfToken = getCookie("csrftoken");
      if (csrfToken) {
        headers.set("X-CSRFToken", csrfToken);
      }
    }

    const init: RequestInit = {
      method: upperMethod,
      credentials: "include",
      headers,
    };

    if (body !== undefined) {
      headers.set("Content-Type", "application/json");
      init.body = JSON.stringify(body);
    }

    const res = await fetchFn(url, init);
    if (res.status === 204) {
      return undefined as TResponse;
    }

    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    let payload: unknown = null;
    if (isJson) {
      try {
        payload = await res.json();
      } catch {
        payload = null;
      }
    } else {
      payload = await res.text();
    }

    if (!res.ok) {
      const message =
        isRecord(payload) && typeof payload.error === "string" ? payload.error : res.statusText;
      throw new ApiError(message || "request failed", { status: res.status, payload });
    }

    return payload as TResponse;
  }

  return {
    getMe: () => request<MeResponse>("/api/me"),
    login: (email: string, password: string) =>
      request<MeResponse>("/api/auth/login", { method: "POST", body: { email, password } }),
    logout: () => request<void>("/api/auth/logout", { method: "POST" }),
    listProjects: async (orgId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects`);
      return { projects: extractListValue<Project>(payload, "projects") };
    },
    getProject: async (orgId: string, projectId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}`);
      return { project: extractObjectValue<Project>(payload, "project") };
    },
    listEpics: async (orgId: string, projectId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/epics`);
      return { epics: extractListValue<Epic>(payload, "epics") };
    },
    getEpic: async (orgId: string, epicId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/epics/${epicId}`);
      return { epic: extractObjectValue<Epic>(payload, "epic") };
    },
    listTasks: (orgId: string, projectId: string, options?: { status?: string }) =>
      request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/tasks`, {
        query: { status: options?.status },
      }).then((payload) => ({ tasks: extractListValue<Task>(payload, "tasks") })),
    getTask: async (orgId: string, taskId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}`);
      return { task: extractObjectValue<Task>(payload, "task") };
    },
    listSubtasks: async (orgId: string, taskId: string, options?: { status?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/subtasks`, {
        query: { status: options?.status },
      });
      return { subtasks: extractListValue<Subtask>(payload, "subtasks") };
    },
    updateSubtaskStage: async (
      orgId: string,
      subtaskId: string,
      workflowStageId: string | null
    ) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/subtasks/${subtaskId}`, {
        method: "PATCH",
        body: { workflow_stage_id: workflowStageId },
      });
      return { subtask: extractObjectValue<Subtask>(payload, "subtask") };
    },
    listWorkflowStages: async (orgId: string, workflowId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/workflows/${workflowId}/stages`);
      return { stages: extractListValue<WorkflowStage>(payload, "stages") };
    },
  };
}
