import { getCookieValue } from "./cookies";
import type {
  Attachment,
  AttachmentResponse,
  AttachmentsResponse,
  Comment,
  CommentResponse,
  CommentsResponse,
  CustomFieldDefinition,
  CustomFieldResponse,
  CustomFieldType,
  CustomFieldValue,
  CustomFieldsResponse,
  Epic,
  EpicResponse,
  EpicsResponse,
  MeResponse,
  PatchCustomFieldValuesResponse,
  Project,
  ProjectResponse,
  ProjectsResponse,
  SavedView,
  SavedViewResponse,
  SavedViewsResponse,
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

  listSavedViews(orgId: string, projectId: string): Promise<SavedViewsResponse>;
  createSavedView(
    orgId: string,
    projectId: string,
    payload: {
      name: string;
      client_safe?: boolean;
      filters?: Record<string, unknown>;
      sort?: Record<string, unknown>;
      group_by?: string;
    }
  ): Promise<SavedViewResponse>;
  updateSavedView(
    orgId: string,
    savedViewId: string,
    payload: {
      name?: string;
      client_safe?: boolean;
      filters?: Record<string, unknown>;
      sort?: Record<string, unknown>;
      group_by?: string;
    }
  ): Promise<SavedViewResponse>;
  deleteSavedView(orgId: string, savedViewId: string): Promise<void>;

  listCustomFields(orgId: string, projectId: string): Promise<CustomFieldsResponse>;
  createCustomField(
    orgId: string,
    projectId: string,
    payload: {
      name: string;
      field_type: CustomFieldType;
      options?: string[];
      client_safe?: boolean;
    }
  ): Promise<CustomFieldResponse>;
  updateCustomField(
    orgId: string,
    fieldId: string,
    payload: { name?: string; options?: string[]; client_safe?: boolean }
  ): Promise<CustomFieldResponse>;
  deleteCustomField(orgId: string, fieldId: string): Promise<void>;

  patchTaskCustomFieldValues(
    orgId: string,
    taskId: string,
    values: Record<string, unknown | null>
  ): Promise<PatchCustomFieldValuesResponse>;
  patchSubtaskCustomFieldValues(
    orgId: string,
    subtaskId: string,
    values: Record<string, unknown | null>
  ): Promise<PatchCustomFieldValuesResponse>;
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
    updateSubtaskStage: async (orgId: string, subtaskId: string, workflowStageId: string | null) => {
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

    listTaskComments: async (orgId: string, taskId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/comments`);
      return { comments: extractListValue<Comment>(payload, "comments") };
    },
    createTaskComment: async (orgId: string, taskId: string, bodyMarkdown: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/comments`, {
        method: "POST",
        body: { body_markdown: bodyMarkdown },
      });
      return { comment: extractObjectValue<Comment>(payload, "comment") };
    },
    listTaskAttachments: async (orgId: string, taskId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/attachments`);
      return { attachments: extractListValue<Attachment>(payload, "attachments") };
    },
    uploadTaskAttachment: async (
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
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/attachments`, {
        method: "POST",
        body: form,
      });
      return { attachment: extractObjectValue<Attachment>(payload, "attachment") };
    },

    listEpicComments: async (orgId: string, epicId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/epics/${epicId}/comments`);
      return { comments: extractListValue<Comment>(payload, "comments") };
    },
    createEpicComment: async (orgId: string, epicId: string, bodyMarkdown: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/epics/${epicId}/comments`, {
        method: "POST",
        body: { body_markdown: bodyMarkdown },
      });
      return { comment: extractObjectValue<Comment>(payload, "comment") };
    },
    listEpicAttachments: async (orgId: string, epicId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/epics/${epicId}/attachments`);
      return { attachments: extractListValue<Attachment>(payload, "attachments") };
    },
    uploadEpicAttachment: async (
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
      const payload = await request<unknown>(`/api/orgs/${orgId}/epics/${epicId}/attachments`, {
        method: "POST",
        body: form,
      });
      return { attachment: extractObjectValue<Attachment>(payload, "attachment") };
    },

    listSavedViews: async (orgId: string, projectId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/saved-views`);
      return { saved_views: extractListValue<SavedView>(payload, "saved_views") };
    },
    createSavedView: async (orgId: string, projectId: string, payload) => {
      const res = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/saved-views`, {
        method: "POST",
        body: payload,
      });
      return { saved_view: extractObjectValue<SavedView>(res, "saved_view") };
    },
    updateSavedView: async (orgId: string, savedViewId: string, payload) => {
      const res = await request<unknown>(`/api/orgs/${orgId}/saved-views/${savedViewId}`, {
        method: "PATCH",
        body: payload,
      });
      return { saved_view: extractObjectValue<SavedView>(res, "saved_view") };
    },
    deleteSavedView: (orgId: string, savedViewId: string) =>
      request<void>(`/api/orgs/${orgId}/saved-views/${savedViewId}`, { method: "DELETE" }),

    listCustomFields: async (orgId: string, projectId: string) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/projects/${projectId}/custom-fields`
      );
      return { custom_fields: extractListValue<CustomFieldDefinition>(payload, "custom_fields") };
    },
    createCustomField: async (orgId: string, projectId: string, payload) => {
      const res = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/custom-fields`, {
        method: "POST",
        body: payload,
      });
      return { custom_field: extractObjectValue<CustomFieldDefinition>(res, "custom_field") };
    },
    updateCustomField: async (orgId: string, fieldId: string, payload) => {
      const res = await request<unknown>(`/api/orgs/${orgId}/custom-fields/${fieldId}`, {
        method: "PATCH",
        body: payload,
      });
      return { custom_field: extractObjectValue<CustomFieldDefinition>(res, "custom_field") };
    },
    deleteCustomField: (orgId: string, fieldId: string) =>
      request<void>(`/api/orgs/${orgId}/custom-fields/${fieldId}`, { method: "DELETE" }),

    patchTaskCustomFieldValues: async (orgId: string, taskId: string, values) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/tasks/${taskId}/custom-field-values`,
        { method: "PATCH", body: { values } }
      );
      return {
        custom_field_values: extractListValue<CustomFieldValue>(payload, "custom_field_values"),
      };
    },
    patchSubtaskCustomFieldValues: async (orgId: string, subtaskId: string, values) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/subtasks/${subtaskId}/custom-field-values`,
        { method: "PATCH", body: { values } }
      );
      return {
        custom_field_values: extractListValue<CustomFieldValue>(payload, "custom_field_values"),
      };
    },
  };
}
