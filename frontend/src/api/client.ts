import { getCookieValue } from "./cookies";
import type {
  AttachmentResponse,
  AttachmentsResponse,
  CommentResponse,
  CommentsResponse,
  MeResponse,
  ProjectsResponse,
  TaskResponse,
  TasksResponse,
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
  listTasks(
    orgId: string,
    projectId: string,
    options?: { status?: string }
  ): Promise<TasksResponse>;
  getTask(orgId: string, taskId: string): Promise<TaskResponse>;

  listTaskComments(orgId: string, taskId: string): Promise<CommentsResponse>;
  createTaskComment(orgId: string, taskId: string, bodyMarkdown: string): Promise<CommentResponse>;
  listTaskAttachments(orgId: string, taskId: string): Promise<AttachmentsResponse>;
  uploadTaskAttachment(
    orgId: string,
    taskId: string,
    file: File,
    options?: { commentId?: string }
  ): Promise<AttachmentResponse>;

  listEpicComments(orgId: string, epicId: string): Promise<CommentsResponse>;
  createEpicComment(orgId: string, epicId: string, bodyMarkdown: string): Promise<CommentResponse>;
  listEpicAttachments(orgId: string, epicId: string): Promise<AttachmentsResponse>;
  uploadEpicAttachment(
    orgId: string,
    epicId: string,
    file: File,
    options?: { commentId?: string }
  ): Promise<AttachmentResponse>;
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
      const isFormData =
        typeof FormData !== "undefined" && body instanceof FormData;
      if (isFormData) {
        init.body = body as FormData;
      } else {
        headers.set("Content-Type", "application/json");
        init.body = JSON.stringify(body);
      }
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
    listProjects: (orgId: string) =>
      request<ProjectsResponse>(`/api/orgs/${orgId}/projects`),
    listTasks: (orgId: string, projectId: string, options?: { status?: string }) =>
      request<TasksResponse>(`/api/orgs/${orgId}/projects/${projectId}/tasks`, {
        query: { status: options?.status },
      }),
    getTask: (orgId: string, taskId: string) =>
      request<TaskResponse>(`/api/orgs/${orgId}/tasks/${taskId}`),

    listTaskComments: (orgId: string, taskId: string) =>
      request<CommentsResponse>(`/api/orgs/${orgId}/tasks/${taskId}/comments`),
    createTaskComment: (orgId: string, taskId: string, bodyMarkdown: string) =>
      request<CommentResponse>(`/api/orgs/${orgId}/tasks/${taskId}/comments`, {
        method: "POST",
        body: { body_markdown: bodyMarkdown },
      }),
    listTaskAttachments: (orgId: string, taskId: string) =>
      request<AttachmentsResponse>(`/api/orgs/${orgId}/tasks/${taskId}/attachments`),
    uploadTaskAttachment: (
      orgId: string,
      taskId: string,
      file: File,
      options?: { commentId?: string }
    ) => {
      const form = new FormData();
      form.set("file", file);
      if (options?.commentId) {
        form.set("comment_id", options.commentId);
      }
      return request<AttachmentResponse>(`/api/orgs/${orgId}/tasks/${taskId}/attachments`, {
        method: "POST",
        body: form,
      });
    },

    listEpicComments: (orgId: string, epicId: string) =>
      request<CommentsResponse>(`/api/orgs/${orgId}/epics/${epicId}/comments`),
    createEpicComment: (orgId: string, epicId: string, bodyMarkdown: string) =>
      request<CommentResponse>(`/api/orgs/${orgId}/epics/${epicId}/comments`, {
        method: "POST",
        body: { body_markdown: bodyMarkdown },
      }),
    listEpicAttachments: (orgId: string, epicId: string) =>
      request<AttachmentsResponse>(`/api/orgs/${orgId}/epics/${epicId}/attachments`),
    uploadEpicAttachment: (
      orgId: string,
      epicId: string,
      file: File,
      options?: { commentId?: string }
    ) => {
      const form = new FormData();
      form.set("file", file);
      if (options?.commentId) {
        form.set("comment_id", options.commentId);
      }
      return request<AttachmentResponse>(`/api/orgs/${orgId}/epics/${epicId}/attachments`, {
        method: "POST",
        body: form,
      });
    },
  };
}
