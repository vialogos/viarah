import { getCookieValue } from "./cookies";
import type {
  Attachment,
  AttachmentResponse,
  AttachmentsResponse,
  AuditEvent,
	  Comment,
	  CommentResponse,
	  CommentsResponse,
	  Client,
	  ClientResponse,
	  ClientsResponse,
	  CustomFieldDefinition,
	  CustomFieldResponse,
	  CustomFieldType,
  CustomFieldValue,
  CustomFieldsResponse,
  EmailDeliveryLog,
  Epic,
  EpicResponse,
  EpicsResponse,
  GitLabIntegrationResponse,
  GitLabIntegrationSettings,
  GitLabIntegrationValidationResult,
  GitLabIntegrationValidationStatus,
  GitLabLink,
  GitLabLinkResponse,
  GitLabLinksResponse,
  InAppNotification,
  MeResponse,
  MyNotificationsResponse,
  MarkAllNotificationsReadResponse,
  NotificationDeliveryLogsResponse,
  NotificationPreferencesResponse,
  NotificationPreferenceRow,
  NotificationsBadgeResponse,
  NotificationResponse,
  AcceptInviteResponse,
  ApiMembership,
  ApiKey,
  CreateOrgInviteResponse,
  OrgInvite,
  OrgInvitesResponse,
  OrgMembershipResponse,
  OrgMembershipWithUser,
	  PeopleResponse,
	  Person,
	  PersonContactEntriesResponse,
	  PersonContactEntry,
	  PersonContactEntryKind,
	  PersonContactEntryResponse,
	  PersonMessage,
	  PersonMessageResponse,
	  PersonMessagesResponse,
	  PersonMessageThread,
	  PersonMessageThreadResponse,
	  PersonMessageThreadsResponse,
	  PersonPayment,
	  PersonPaymentResponse,
	  PersonPaymentsResponse,
	  PersonRate,
	  PersonRateResponse,
	  PersonRatesResponse,
	  PersonResponse,
	  PersonProjectMembership,
	  PersonProjectMembershipsResponse,
	  PersonSummary,
	  PersonAvailabilityResponse,
	  PeopleAvailabilitySearchResponse,
	  CreatePersonWeeklyWindowResponse,
	  PatchPersonWeeklyWindowResponse,
  CreatePersonAvailabilityExceptionResponse,
  PatchPersonAvailabilityExceptionResponse,
  PatchCustomFieldValuesResponse,
  Project,
  ProjectResponse,
  ProjectMembershipWithUser,
  ProjectNotificationSettingsResponse,
  ProjectNotificationSettingRow,
  ProjectsResponse,
  ReportRunDetail,
  ReportRunPdfRenderLog,
  ReportRunRenderLogsResponse,
  ReportRunResponse,
  ReportRunsResponse,
  ReportRunScope,
  ReportRunSummary,
  RequestReportRunPdfResponse,
  ShareLink,
  ShareLinkAccessLog,
  ShareLinkAccessLogsResponse,
  ShareLinkPublishResponse,
  ShareLinkResponse,
  ShareLinksResponse,
  SoWListItem,
  SoWPdfArtifact,
  SoWResponse,
  SowsResponse,
  Template,
  TemplateDetailResponse,
  TemplateResponse,
  TemplatesResponse,
  TemplateType,
  TemplateVersionResponse,
  TemplateVersionSummary,
  PushSubscriptionResponse,
  PushSubscriptionsResponse,
  PushSubscriptionRow,
  PushVapidConfigResponse,
  PushVapidPublicKeyResponse,
  SavedView,
  SavedViewResponse,
  SavedViewsResponse,
	  Subtask,
	  SubtaskResponse,
	  SubtasksResponse,
	  Task,
	  TaskParticipant,
	  TaskResponse,
	  TaskParticipantResponse,
	  TaskParticipantsResponse,
	  TasksResponse,
	  Workflow,
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

function extractNullableObjectValue<T>(payload: unknown, key: string): T | null {
  if (!isRecord(payload)) {
    throw new Error(`unexpected response shape (expected '${key}' object or null)`);
  }

  const value = payload[key];
  if (value == null) {
    return null;
  }

  if (isRecord(value)) {
    return value as T;
  }

  throw new Error(`unexpected response shape (expected '${key}' object or null)`);
}

function extractOptionalStringValue(payload: unknown, key: string): string | null {
  if (!isRecord(payload)) {
    return null;
  }

  const value = payload[key];
  if (typeof value === "string") {
    return value;
  }

  if (value == null) {
    return null;
  }

  throw new Error(`unexpected response shape (expected '${key}' to be a string or null)`);
}

function extractStringValue(payload: unknown, key: string): string {
  if (!isRecord(payload)) {
    throw new Error(`unexpected response shape (expected '${key}' string)`);
  }

  const value = payload[key];
  if (typeof value === "string") {
    return value;
  }

  throw new Error(`unexpected response shape (expected '${key}' string)`);
}

function extractNumberValue(payload: unknown, key: string): number {
  if (!isRecord(payload)) {
    throw new Error(`unexpected response shape (expected '${key}' number)`);
  }

  const value = payload[key];
  if (typeof value === "number") {
    return value;
  }

  throw new Error(`unexpected response shape (expected '${key}' number)`);
}

function extractBooleanValue(payload: unknown, key: string): boolean {
  if (!isRecord(payload)) {
    throw new Error(`unexpected response shape (expected '${key}' boolean)`);
  }

  const value = payload[key];
  if (typeof value === "boolean") {
    return value;
  }

  throw new Error(`unexpected response shape (expected '${key}' boolean)`);
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
  /**
   * Accept an org invite token (public or session).
   *
   * Note: This call creates/refreshes a session and should be followed by `getMe()` to
   * hydrate `{user, memberships}` for the SPA.
   */
  acceptInvite(payload: { token: string; password?: string; display_name?: string }): Promise<AcceptInviteResponse>;
  listProjects(orgId: string): Promise<ProjectsResponse>;
  getProject(orgId: string, projectId: string): Promise<ProjectResponse>;
  /**
   * Create a new project in an org.
   *
   * Note: project-restricted API keys cannot create new projects (backend returns 403).
   */
  createProject(
    orgId: string,
    payload: { name: string; description?: string; client_id?: string | null }
  ): Promise<ProjectResponse>;
  /**
   * Update project metadata and/or workflow.
   *
   * Note: changing `workflow_id` can be rejected by the backend when tasks/subtasks are already staged.
   */
  updateProject(
    orgId: string,
    projectId: string,
    payload: {
      name?: string;
      description?: string;
      workflow_id?: string | null;
      progress_policy?: string;
      client_id?: string | null;
    }
  ): Promise<ProjectResponse>;
  deleteProject(orgId: string, projectId: string): Promise<void>;
  setProjectWorkflow(
    orgId: string,
    projectId: string,
    workflowId: string | null
  ): Promise<ProjectResponse>;

  listClients(orgId: string, options?: { q?: string }): Promise<ClientsResponse>;
  getClient(orgId: string, clientId: string): Promise<ClientResponse>;
  createClient(orgId: string, payload: { name: string; notes?: string }): Promise<ClientResponse>;
  updateClient(
    orgId: string,
    clientId: string,
    payload: { name?: string; notes?: string }
  ): Promise<ClientResponse>;
  deleteClient(orgId: string, clientId: string): Promise<void>;

  /**
   * List project memberships (Admin/PM; session-only).
   */
  listProjectMemberships(
    orgId: string,
    projectId: string
  ): Promise<{ memberships: ProjectMembershipWithUser[] }>;
  /**
   * Add a user to a project (Admin/PM; session-only).
   */
  addProjectMembership(
    orgId: string,
    projectId: string,
    userId: string
  ): Promise<{ membership: ProjectMembershipWithUser }>;
  /**
   * Remove a user from a project (Admin/PM; session-only).
   */
  deleteProjectMembership(orgId: string, projectId: string, membershipId: string): Promise<void>;

  listTemplates(orgId: string, options?: { type?: TemplateType | string }): Promise<TemplatesResponse>;
  createTemplate(
    orgId: string,
    payload: { type: TemplateType | string; name: string; description?: string; body: string }
  ): Promise<TemplateResponse>;
  getTemplate(orgId: string, templateId: string): Promise<TemplateDetailResponse>;
  createTemplateVersion(orgId: string, templateId: string, body: string): Promise<TemplateVersionResponse>;

  /**
   * Create an org invite (Admin/PM; session-only).
   *
   * Note: `invite_url` is a relative SPA path (build an absolute URL from the frontend origin).
   */
  createOrgInvite(
    orgId: string,
    payload: { person_id?: string; email?: string; full_name?: string; role: string; message?: string }
  ): Promise<CreateOrgInviteResponse>;
  listOrgInvites(orgId: string, options?: { status?: string }): Promise<OrgInvitesResponse>;
  revokeOrgInvite(orgId: string, inviteId: string): Promise<{ invite: OrgInvite }>;
  resendOrgInvite(orgId: string, inviteId: string): Promise<CreateOrgInviteResponse>;

  listOrgPeople(orgId: string, options?: { q?: string }): Promise<PeopleResponse>;
	  createOrgPerson(
	    orgId: string,
	    payload: {
	      full_name?: string;
	      preferred_name?: string;
	      email?: string | null;
	      title?: string;
	      skills?: string[];
	      bio?: string;
	      notes?: string;
	      timezone?: string;
	      location?: string;
	      phone?: string;
	      slack_handle?: string;
	      linkedin_url?: string;
	      gitlab_username?: string | null;
	    }
	  ): Promise<PersonResponse>;
	  getOrgPerson(orgId: string, personId: string): Promise<PersonResponse>;
		  updateOrgPerson(
		    orgId: string,
		    personId: string,
			    payload: {
		      full_name?: string;
	      preferred_name?: string;
	      email?: string | null;
	      title?: string;
	      skills?: string[];
	      bio?: string;
	      notes?: string;
	      timezone?: string;
	      location?: string;
	      phone?: string;
	      slack_handle?: string;
		      linkedin_url?: string;
			      gitlab_username?: string | null;
			    }
			  ): Promise<PersonResponse>;
		  uploadPersonAvatar(orgId: string, personId: string, file: File): Promise<PersonResponse>;
		  clearPersonAvatar(orgId: string, personId: string): Promise<PersonResponse>;
		  /**
		   * List a person's project memberships (Admin/PM; session-only).
		   */
		  listPersonProjectMemberships(
	    orgId: string,
	    personId: string
	  ): Promise<PersonProjectMembershipsResponse>;
	  inviteOrgPerson(
	    orgId: string,
	    personId: string,
	    payload: { role: string; email?: string; message?: string }
  ): Promise<CreateOrgInviteResponse>;

  /**
   * Get or update the current user's Person record for an org (session-only).
   */
  getMyPerson(orgId: string): Promise<PersonResponse>;
  updateMyPerson(
    orgId: string,
    payload: {
      full_name?: string;
      preferred_name?: string;
      title?: string;
      skills?: string[];
      bio?: string;
      timezone?: string;
      location?: string;
      phone?: string;
      slack_handle?: string;
      linkedin_url?: string;
    }
  ): Promise<PersonResponse>;

  /**
   * Contact log entries for a Person (PM/admin; session-only).
   */
  listPersonContactEntries(orgId: string, personId: string): Promise<PersonContactEntriesResponse>;
  createPersonContactEntry(
    orgId: string,
    personId: string,
    payload: { kind: PersonContactEntryKind; occurred_at: string; summary?: string; notes?: string }
  ): Promise<PersonContactEntryResponse>;
  patchPersonContactEntry(
    orgId: string,
    personId: string,
    entryId: string,
    payload: { kind?: PersonContactEntryKind; occurred_at?: string; summary?: string; notes?: string }
  ): Promise<PersonContactEntryResponse>;
  deletePersonContactEntry(orgId: string, personId: string, entryId: string): Promise<void>;

  /**
   * Message threads + messages for a Person (PM/admin; session-only).
   */
  listPersonMessageThreads(orgId: string, personId: string): Promise<PersonMessageThreadsResponse>;
  createPersonMessageThread(
    orgId: string,
    personId: string,
    payload: { title: string }
  ): Promise<PersonMessageThreadResponse>;
  patchPersonMessageThread(
    orgId: string,
    personId: string,
    threadId: string,
    payload: { title?: string }
  ): Promise<PersonMessageThreadResponse>;
  deletePersonMessageThread(orgId: string, personId: string, threadId: string): Promise<void>;
  listPersonThreadMessages(orgId: string, personId: string, threadId: string): Promise<PersonMessagesResponse>;
  createPersonThreadMessage(
    orgId: string,
    personId: string,
    threadId: string,
    payload: { body_markdown: string }
  ): Promise<PersonMessageResponse>;

  /**
   * Rates for a Person (PM/admin; session-only).
   */
  listPersonRates(orgId: string, personId: string): Promise<PersonRatesResponse>;
  createPersonRate(
    orgId: string,
    personId: string,
    payload: { currency: string; amount_cents: number; effective_date: string; notes?: string }
  ): Promise<PersonRateResponse>;
  patchPersonRate(
    orgId: string,
    personId: string,
    rateId: string,
    payload: { currency?: string; amount_cents?: number; effective_date?: string; notes?: string }
  ): Promise<PersonRateResponse>;
  deletePersonRate(orgId: string, personId: string, rateId: string): Promise<void>;

  /**
   * Payments ledger for a Person (PM/admin; session-only).
   */
  listPersonPayments(orgId: string, personId: string): Promise<PersonPaymentsResponse>;
  createPersonPayment(
    orgId: string,
    personId: string,
    payload: { currency: string; amount_cents: number; paid_date: string; notes?: string }
  ): Promise<PersonPaymentResponse>;
  patchPersonPayment(
    orgId: string,
    personId: string,
    paymentId: string,
    payload: { currency?: string; amount_cents?: number; paid_date?: string; notes?: string }
  ): Promise<PersonPaymentResponse>;
  deletePersonPayment(orgId: string, personId: string, paymentId: string): Promise<void>;


  /**
   * Availability schedule (weekly windows + exceptions).
   */
  getPersonAvailability(
    orgId: string,
    personId: string,
    options?: { start_at?: string; end_at?: string }
  ): Promise<PersonAvailabilityResponse>;
  createPersonWeeklyWindow(
    orgId: string,
    personId: string,
    payload: { weekday: number; start_time: string; end_time: string }
  ): Promise<CreatePersonWeeklyWindowResponse>;
  patchPersonWeeklyWindow(
    orgId: string,
    personId: string,
    weeklyWindowId: string,
    payload: { weekday?: number; start_time?: string; end_time?: string }
  ): Promise<PatchPersonWeeklyWindowResponse>;
  deletePersonWeeklyWindow(orgId: string, personId: string, weeklyWindowId: string): Promise<void>;
  createPersonAvailabilityException(
    orgId: string,
    personId: string,
    payload: { kind: string; starts_at: string; ends_at: string; title?: string; notes?: string }
  ): Promise<CreatePersonAvailabilityExceptionResponse>;
  patchPersonAvailabilityException(
    orgId: string,
    personId: string,
    exceptionId: string,
    payload: { kind?: string; starts_at?: string; ends_at?: string; title?: string; notes?: string }
  ): Promise<PatchPersonAvailabilityExceptionResponse>;
  deletePersonAvailabilityException(orgId: string, personId: string, exceptionId: string): Promise<void>;
  searchPeopleAvailability(
    orgId: string,
    options: { start_at: string; end_at: string }
  ): Promise<PeopleAvailabilitySearchResponse>;
  listOrgMemberships(
    orgId: string,
    options?: { role?: string }
  ): Promise<{ memberships: OrgMembershipWithUser[] }>;
  /**
   * Update an org membership role (Admin/PM; session-only).
   */
  updateOrgMembership(
    orgId: string,
    membershipId: string,
    payload: {
      role?: string;
      display_name?: string;
      title?: string;
      skills?: string[] | null;
      bio?: string;
      availability_status?: string;
      availability_hours_per_week?: number | null;
      availability_next_available_at?: string | null;
      availability_notes?: string;
    }
  ): Promise<OrgMembershipResponse>;
  /**
   * List API keys for an org (Admin/PM; session-only).
   */
  listApiKeys(orgId: string, options?: { mine?: boolean; owner_user_id?: string }): Promise<{ api_keys: ApiKey[] }>;
  /**
   * Create an API key for an org (Admin/PM; session-only).
   *
   * Note: the token is returned once.
   */
  createApiKey(
    orgId: string,
    payload: { name: string; project_id?: string | null; scopes?: string[]; owner_user_id?: string | null }
  ): Promise<{ api_key: ApiKey; token: string }>;
  /**
   * Rotate an API key and return a new token once (Admin/PM; session-only).
   */
  rotateApiKey(apiKeyId: string): Promise<{ api_key: ApiKey; token: string }>;
  /**
   * Revoke an API key (Admin/PM; session-only).
   */
  revokeApiKey(apiKeyId: string): Promise<{ api_key: ApiKey }>;

  listSows(
    orgId: string,
    options?: { projectId?: string; status?: string }
  ): Promise<SowsResponse>;
  getSow(orgId: string, sowId: string): Promise<SoWResponse>;
  createSow(
    orgId: string,
    payload: {
      project_id: string;
      template_id: string;
      template_version_id?: string | null;
      variables?: Record<string, unknown>;
      signer_user_ids: string[];
    }
  ): Promise<SoWResponse>;
  sendSow(orgId: string, sowId: string): Promise<SoWResponse>;
  respondSow(
    orgId: string,
    sowId: string,
    payload:
      | { decision: "approve"; typed_signature: string; comment?: string }
      | { decision: "reject"; comment?: string }
  ): Promise<SoWResponse>;
  requestSowPdf(orgId: string, sowId: string): Promise<{ status: string; pdf: SoWPdfArtifact }>;

  listReportRuns(orgId: string, options?: { projectId?: string }): Promise<ReportRunsResponse>;
  createReportRun(
    orgId: string,
    payload: {
      project_id: string;
      template_id: string;
      template_version_id?: string | null;
      scope: ReportRunScope;
    }
  ): Promise<ReportRunResponse>;
  getReportRun(orgId: string, reportRunId: string): Promise<ReportRunResponse>;
  regenerateReportRun(orgId: string, reportRunId: string): Promise<ReportRunResponse>;
  requestReportRunPdf(orgId: string, reportRunId: string): Promise<RequestReportRunPdfResponse>;
  reportRunPdfDownloadUrl(orgId: string, reportRunId: string): string;
  listReportRunRenderLogs(orgId: string, reportRunId: string): Promise<ReportRunRenderLogsResponse>;

  publishReportRun(
    orgId: string,
    reportRunId: string,
    payload?: { expires_at?: string | null }
  ): Promise<ShareLinkPublishResponse>;
  listShareLinks(orgId: string, options?: { reportRunId?: string }): Promise<ShareLinksResponse>;
  revokeShareLink(orgId: string, shareLinkId: string): Promise<ShareLinkResponse>;
  listShareLinkAccessLogs(orgId: string, shareLinkId: string): Promise<ShareLinkAccessLogsResponse>;

  listEpics(orgId: string, projectId: string): Promise<EpicsResponse>;
  getEpic(orgId: string, epicId: string): Promise<EpicResponse>;
  patchEpic(
    orgId: string,
    epicId: string,
    payload: {
      title?: string;
      description?: string;
      progress_policy?: string | null;
    }
  ): Promise<EpicResponse>;
  /**
   * Create an epic in a project.
   */
  createEpic(
    orgId: string,
    projectId: string,
    payload: { title: string; description?: string; progress_policy?: string | null }
  ): Promise<EpicResponse>;
  /**
   * Create a task within an epic.
   */
  createTask(
    orgId: string,
    epicId: string,
    payload: {
      title: string;
      description?: string;
      status?: string;
      start_date?: string | null;
      end_date?: string | null;
    }
  ): Promise<TaskResponse>;
  /**
   * Create a subtask within a task.
   */
  createSubtask(
    orgId: string,
    taskId: string,
    payload: {
      title: string;
      description?: string;
      status?: string;
      start_date?: string | null;
      end_date?: string | null;
    }
  ): Promise<SubtaskResponse>;
  listTasks(
    orgId: string,
    projectId: string,
    options?: { status?: string; assignee_user_id?: string }
  ): Promise<TasksResponse>;
  getTask(orgId: string, taskId: string): Promise<TaskResponse>;
		  patchTask(
		    orgId: string,
		    taskId: string,
		    payload: {
		      title?: string;
		      description?: string;
		      status?: string;
		      workflow_stage_id?: string | null;
		      progress_policy?: string | null;
		      start_date?: string | null;
		      end_date?: string | null;
		      assignee_user_id?: string | null;
		      client_safe?: boolean;
		    }
		  ): Promise<TaskResponse>;
	  updateTaskStage(orgId: string, taskId: string, workflowStageId: string | null): Promise<TaskResponse>;
	  listTaskParticipants(orgId: string, taskId: string): Promise<TaskParticipantsResponse>;
	  createTaskParticipant(orgId: string, taskId: string, userId: string): Promise<TaskParticipantResponse>;
	  deleteTaskParticipant(orgId: string, taskId: string, userId: string): Promise<void>;
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
  patchSubtask(
    orgId: string,
    subtaskId: string,
    payload: {
      title?: string;
      description?: string;
      status?: string;
      workflow_stage_id?: string | null;
      start_date?: string | null;
      end_date?: string | null;
    }
  ): Promise<SubtaskResponse>;
  listWorkflows(orgId: string): Promise<{ workflows: Workflow[] }>;
  getWorkflow(orgId: string, workflowId: string): Promise<{ workflow: Workflow; stages: WorkflowStage[] }>;
  createWorkflow(
    orgId: string,
    payload: {
      name: string;
      stages: Array<{
        name: string;
        order: number;
        category: string;
        progress_percent: number;
        is_done?: boolean;
        is_qa?: boolean;
        counts_as_wip?: boolean;
      }>;
    }
  ): Promise<{ workflow: Workflow; stages: WorkflowStage[] }>;
  updateWorkflow(orgId: string, workflowId: string, payload: { name: string }): Promise<{ workflow: Workflow }>;
  deleteWorkflow(orgId: string, workflowId: string): Promise<void>;
  listWorkflowStages(orgId: string, workflowId: string): Promise<WorkflowStagesResponse>;
  createWorkflowStage(
    orgId: string,
    workflowId: string,
    payload: {
      name: string;
      order: number;
      category: string;
      progress_percent: number;
      is_done?: boolean;
      is_qa?: boolean;
      counts_as_wip?: boolean;
    }
  ): Promise<{ stage: WorkflowStage; stages: WorkflowStage[] }>;
  updateWorkflowStage(
    orgId: string,
    workflowId: string,
    stageId: string,
    payload: Partial<
      Pick<
        WorkflowStage,
        "name" | "order" | "category" | "progress_percent" | "is_done" | "is_qa" | "counts_as_wip"
      >
    >
  ): Promise<{ stage: WorkflowStage; stages: WorkflowStage[] }>;
  deleteWorkflowStage(orgId: string, workflowId: string, stageId: string): Promise<void>;
  listAuditEvents(orgId: string): Promise<{ events: AuditEvent[] }>;

  getOrgGitLabIntegration(orgId: string): Promise<GitLabIntegrationResponse>;
  patchOrgGitLabIntegration(
    orgId: string,
    payload: { base_url?: string; token?: string; webhook_secret?: string }
  ): Promise<GitLabIntegrationResponse>;
  validateOrgGitLabIntegration(orgId: string): Promise<GitLabIntegrationValidationResult>;

  listTaskGitLabLinks(orgId: string, taskId: string): Promise<GitLabLinksResponse>;
  createTaskGitLabLink(orgId: string, taskId: string, url: string): Promise<GitLabLinkResponse>;
  deleteTaskGitLabLink(orgId: string, taskId: string, linkId: string): Promise<void>;

  listMyNotifications(
    orgId: string,
    options?: { projectId?: string; unreadOnly?: boolean; limit?: number }
  ): Promise<MyNotificationsResponse>;
  getMyNotificationBadge(
    orgId: string,
    options?: { projectId?: string }
  ): Promise<NotificationsBadgeResponse>;
  markAllMyNotificationsRead(
    orgId: string,
    options?: { projectId?: string }
  ): Promise<MarkAllNotificationsReadResponse>;
  markMyNotificationRead(orgId: string, notificationId: string): Promise<NotificationResponse>;

  getNotificationPreferences(orgId: string, projectId: string): Promise<NotificationPreferencesResponse>;
  patchNotificationPreferences(
    orgId: string,
    projectId: string,
    preferences: NotificationPreferenceRow[]
  ): Promise<NotificationPreferencesResponse>;

  getProjectNotificationSettings(orgId: string, projectId: string): Promise<ProjectNotificationSettingsResponse>;
  patchProjectNotificationSettings(
    orgId: string,
    projectId: string,
    settings: ProjectNotificationSettingRow[]
  ): Promise<ProjectNotificationSettingsResponse>;

  listNotificationDeliveryLogs(
    orgId: string,
    projectId: string,
    options?: { status?: string; limit?: number }
  ): Promise<NotificationDeliveryLogsResponse>;

  getPushVapidPublicKey(): Promise<PushVapidPublicKeyResponse>;
  getPushVapidConfig(): Promise<PushVapidConfigResponse>;
  patchPushVapidConfig(payload: {
    public_key: string;
    private_key: string;
    subject: string;
  }): Promise<PushVapidConfigResponse>;
  generatePushVapidConfig(payload?: { subject?: string }): Promise<PushVapidConfigResponse>;
  deletePushVapidConfig(): Promise<PushVapidConfigResponse>;
  listPushSubscriptions(): Promise<PushSubscriptionsResponse>;
  createPushSubscription(
    subscription: PushSubscriptionJSON,
    userAgent?: string
  ): Promise<PushSubscriptionResponse>;
  deletePushSubscription(subscriptionId: string): Promise<void>;

  listTaskComments(orgId: string, taskId: string): Promise<CommentsResponse>;
  createTaskComment(
    orgId: string,
    taskId: string,
    bodyMarkdown: string,
    options?: { client_safe?: boolean }
  ): Promise<CommentResponse>;
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

  async function patchProject(
    orgId: string,
    projectId: string,
    body: {
      name?: string;
      description?: string;
      workflow_id?: string | null;
      progress_policy?: string;
      client_id?: string | null;
    }
  ): Promise<ProjectResponse> {
    const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}`, {
      method: "PATCH",
      body,
    });
    return { project: extractObjectValue<Project>(payload, "project") };
  }

  return {
    getMe: () => request<MeResponse>("/api/me"),
    login: (email: string, password: string) =>
      request<MeResponse>("/api/auth/login", { method: "POST", body: { email, password } }),
    logout: () => request<void>("/api/auth/logout", { method: "POST" }),

    acceptInvite: async (body: { token: string; password?: string; display_name?: string }) => {
      const payload = await request<unknown>("/api/invites/accept", { method: "POST", body });
      return {
        membership: extractObjectValue<ApiMembership>(payload, "membership"),
        person: extractObjectValue<PersonSummary>(payload, "person"),
        needs_profile_setup: extractBooleanValue(payload, "needs_profile_setup"),
      };
    },

    listMyNotifications: async (
      orgId: string,
      options?: { projectId?: string; unreadOnly?: boolean; limit?: number }
    ) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/me/notifications`, {
        query: {
          project_id: options?.projectId,
          unread_only: options?.unreadOnly ? "1" : undefined,
          limit: options?.limit != null ? String(options.limit) : undefined,
        },
      });
      return { notifications: extractListValue<InAppNotification>(payload, "notifications") };
    },
    getMyNotificationBadge: async (orgId: string, options?: { projectId?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/me/notifications/badge`, {
        query: {
          project_id: options?.projectId,
        },
      });
      return { unread_count: extractNumberValue(payload, "unread_count") };
    },
    markAllMyNotificationsRead: async (orgId: string, options?: { projectId?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/me/notifications/mark-all-read`, {
        method: "POST",
        query: {
          project_id: options?.projectId,
        },
      });
      return { updated_count: extractNumberValue(payload, "updated_count") };
    },
    markMyNotificationRead: async (orgId: string, notificationId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/me/notifications/${notificationId}`, {
        method: "PATCH",
        body: { read: true },
      });
      return { notification: extractObjectValue<InAppNotification>(payload, "notification") };
    },

    getNotificationPreferences: async (orgId: string, projectId: string) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/projects/${projectId}/notification-preferences`
      );
      return {
        preferences: extractListValue<NotificationPreferenceRow>(payload, "preferences"),
      };
    },
    patchNotificationPreferences: async (
      orgId: string,
      projectId: string,
      preferences: NotificationPreferenceRow[]
    ) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/projects/${projectId}/notification-preferences`,
        { method: "PATCH", body: { preferences } }
      );
      return {
        preferences: extractListValue<NotificationPreferenceRow>(payload, "preferences"),
      };
    },

    getProjectNotificationSettings: async (orgId: string, projectId: string) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/projects/${projectId}/notification-settings`
      );
      return {
        settings: extractListValue<ProjectNotificationSettingRow>(payload, "settings"),
      };
    },
    patchProjectNotificationSettings: async (
      orgId: string,
      projectId: string,
      settings: ProjectNotificationSettingRow[]
    ) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/projects/${projectId}/notification-settings`,
        { method: "PATCH", body: { settings } }
      );
      return {
        settings: extractListValue<ProjectNotificationSettingRow>(payload, "settings"),
      };
    },

    listNotificationDeliveryLogs: async (
      orgId: string,
      projectId: string,
      options?: { status?: string; limit?: number }
    ) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/projects/${projectId}/notification-delivery-logs`,
        {
          query: {
            status: options?.status,
            limit: options?.limit != null ? String(options.limit) : undefined,
          },
        }
      );
      return { deliveries: extractListValue<EmailDeliveryLog>(payload, "deliveries") };
    },

    getPushVapidPublicKey: async () => {
      const payload = await request<unknown>("/api/push/vapid_public_key");
      const key = extractOptionalStringValue(payload, "public_key");
      if (!key) {
        throw new Error("unexpected response shape (expected 'public_key' string)");
      }
      return { public_key: key };
    },
    getPushVapidConfig: async () => {
      const payload = await request<unknown>("/api/push/vapid_config");
      return { config: extractObjectValue(payload, "config") };
    },
    patchPushVapidConfig: async (body: { public_key: string; private_key: string; subject: string }) => {
      const payload = await request<unknown>("/api/push/vapid_config", { method: "PATCH", body });
      return { config: extractObjectValue(payload, "config") };
    },
    generatePushVapidConfig: async (body?: { subject?: string }) => {
      const payload = await request<unknown>("/api/push/vapid_config/generate", { method: "POST", body });
      return { config: extractObjectValue(payload, "config") };
    },
    deletePushVapidConfig: async () => {
      const payload = await request<unknown>("/api/push/vapid_config", { method: "DELETE" });
      return { config: extractObjectValue(payload, "config") };
    },
    listPushSubscriptions: async () => {
      const payload = await request<unknown>("/api/push/subscriptions");
      return { subscriptions: extractListValue<PushSubscriptionRow>(payload, "subscriptions") };
    },
    createPushSubscription: async (subscription: PushSubscriptionJSON, userAgent?: string) => {
      const body: Record<string, unknown> = { subscription };
      if (userAgent) {
        body.user_agent = userAgent;
      }
      const payload = await request<unknown>("/api/push/subscriptions", { method: "POST", body });
      return { subscription: extractObjectValue<PushSubscriptionRow>(payload, "subscription") };
    },
    deletePushSubscription: (subscriptionId: string) =>
      request<void>(`/api/push/subscriptions/${subscriptionId}`, { method: "DELETE" }),

    listProjects: async (orgId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects`);
      return { projects: extractListValue<Project>(payload, "projects") };
    },
    getProject: async (orgId: string, projectId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}`);
      return { project: extractObjectValue<Project>(payload, "project") };
    },
    createProject: async (orgId: string, body: { name: string; description?: string; client_id?: string | null }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects`, { method: "POST", body });
      return { project: extractObjectValue<Project>(payload, "project") };
    },
    updateProject: (
      orgId: string,
      projectId: string,
      body: {
        name?: string;
        description?: string;
        workflow_id?: string | null;
        progress_policy?: string;
        client_id?: string | null;
      }
    ) => patchProject(orgId, projectId, body),
    deleteProject: (orgId: string, projectId: string) =>
      request<void>(`/api/orgs/${orgId}/projects/${projectId}`, { method: "DELETE" }),
    setProjectWorkflow: async (orgId: string, projectId: string, workflowId: string | null) => {
      return patchProject(orgId, projectId, { workflow_id: workflowId });
    },

    listClients: async (orgId: string, options?: { q?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/clients`, {
        query: {
          q: options?.q ? String(options.q) : undefined,
        },
      });
      return { clients: extractListValue<Client>(payload, "clients") };
    },
    getClient: async (orgId: string, clientId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/clients/${clientId}`);
      return { client: extractObjectValue<Client>(payload, "client") };
    },
    createClient: async (orgId: string, body: { name: string; notes?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/clients`, { method: "POST", body });
      return { client: extractObjectValue<Client>(payload, "client") };
    },
    updateClient: async (orgId: string, clientId: string, body: { name?: string; notes?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/clients/${clientId}`, {
        method: "PATCH",
        body,
      });
      return { client: extractObjectValue<Client>(payload, "client") };
    },
    deleteClient: (orgId: string, clientId: string) =>
      request<void>(`/api/orgs/${orgId}/clients/${clientId}`, { method: "DELETE" }),

    listProjectMemberships: async (orgId: string, projectId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/memberships`);
      return { memberships: extractListValue<ProjectMembershipWithUser>(payload, "memberships") };
    },
    addProjectMembership: async (orgId: string, projectId: string, userId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/memberships`, {
        method: "POST",
        body: { user_id: userId },
      });
      return { membership: extractObjectValue<ProjectMembershipWithUser>(payload, "membership") };
    },
    deleteProjectMembership: (orgId: string, projectId: string, membershipId: string) =>
      request<void>(`/api/orgs/${orgId}/projects/${projectId}/memberships/${membershipId}`, {
        method: "DELETE",
      }),

    listTemplates: async (orgId: string, options?: { type?: TemplateType | string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/templates`, {
        query: { type: options?.type ? String(options.type) : undefined },
      });
      return { templates: extractListValue<Template>(payload, "templates") };
    },
    createTemplate: async (
      orgId: string,
      body: { type: TemplateType | string; name: string; description?: string; body: string }
    ) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/templates`, { method: "POST", body });
      return { template: extractObjectValue<Template>(payload, "template") };
    },
    getTemplate: async (orgId: string, templateId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/templates/${templateId}`);
      return {
        template: extractObjectValue<Template>(payload, "template"),
        current_version_body: extractOptionalStringValue(payload, "current_version_body"),
        versions: extractListValue<TemplateVersionSummary>(payload, "versions"),
      };
    },
    createTemplateVersion: async (orgId: string, templateId: string, bodyText: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/templates/${templateId}/versions`, {
        method: "POST",
        body: { body: bodyText },
      });
      return {
        template: extractObjectValue<Template>(payload, "template"),
        version: extractObjectValue<TemplateVersionSummary>(payload, "version"),
      };
    },

    createOrgInvite: async (
      orgId: string,
      body: { person_id?: string; email?: string; full_name?: string; role: string; message?: string }
    ) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/invites`, {
        method: "POST",
        body,
      });
      return {
        invite: extractObjectValue<OrgInvite>(payload, "invite"),
        token: extractStringValue(payload, "token"),
        invite_url: extractStringValue(payload, "invite_url"),
      };
    },

    listOrgInvites: async (orgId: string, options?: { status?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/invites`, {
        query: { status: options?.status },
      });
      return { invites: extractListValue<OrgInvite>(payload, "invites") };
    },

    revokeOrgInvite: async (orgId: string, inviteId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/invites/${inviteId}/revoke`, {
        method: "POST",
        body: {},
      });
      return { invite: extractObjectValue<OrgInvite>(payload, "invite") };
    },

    resendOrgInvite: async (orgId: string, inviteId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/invites/${inviteId}/resend`, {
        method: "POST",
        body: {},
      });
      return {
        invite: extractObjectValue<OrgInvite>(payload, "invite"),
        token: extractStringValue(payload, "token"),
        invite_url: extractStringValue(payload, "invite_url"),
      };
    },

    listOrgPeople: async (orgId: string, options?: { q?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people`, {
        query: { q: options?.q },
      });
      return { people: extractListValue<Person>(payload, "people") };
    },

    createOrgPerson: async (orgId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people`, {
        method: "POST",
        body,
      });
      return { person: extractObjectValue<Person>(payload, "person") };
    },

    getOrgPerson: async (orgId: string, personId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}`);
      return { person: extractObjectValue<Person>(payload, "person") };
    },

		    updateOrgPerson: async (orgId: string, personId: string, body) => {
		      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}`, {
		        method: "PATCH",
		        body,
		      });
		      return { person: extractObjectValue<Person>(payload, "person") };
		    },

		    uploadPersonAvatar: async (orgId: string, personId: string, file: File) => {
		      const form = new FormData();
		      form.append("file", file);
		      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/avatar`, {
		        method: "POST",
		        body: form,
		      });
		      return { person: extractObjectValue<Person>(payload, "person") };
		    },

		    clearPersonAvatar: async (orgId: string, personId: string) => {
		      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/avatar`, {
		        method: "DELETE",
		      });
		      return { person: extractObjectValue<Person>(payload, "person") };
		    },

		    listPersonProjectMemberships: async (orgId: string, personId: string) => {
		      const payload = await request<unknown>(
		        `/api/orgs/${orgId}/people/${personId}/project-memberships`
	      );
	      return { memberships: extractListValue<PersonProjectMembership>(payload, "memberships") };
	    },

	    inviteOrgPerson: async (orgId: string, personId: string, body) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/invite`, {
	        method: "POST",
	        body,
      });
      return {
        invite: extractObjectValue<OrgInvite>(payload, "invite"),
        token: extractStringValue(payload, "token"),
        invite_url: extractStringValue(payload, "invite_url"),
      };
    },

    getMyPerson: async (orgId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/me`);
      return { person: extractObjectValue<Person>(payload, "person") };
    },
    updateMyPerson: async (orgId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/me`, { method: "PATCH", body });
      return { person: extractObjectValue<Person>(payload, "person") };
    },

    listPersonContactEntries: async (orgId: string, personId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/contact-entries`);
      return { entries: extractListValue<PersonContactEntry>(payload, "entries") };
    },
    createPersonContactEntry: async (orgId: string, personId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/contact-entries`, {
        method: "POST",
        body,
      });
      return { entry: extractObjectValue<PersonContactEntry>(payload, "entry") };
    },
    patchPersonContactEntry: async (orgId: string, personId: string, entryId: string, body) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/people/${personId}/contact-entries/${entryId}`,
        { method: "PATCH", body }
      );
      return { entry: extractObjectValue<PersonContactEntry>(payload, "entry") };
    },
    deletePersonContactEntry: (orgId: string, personId: string, entryId: string) =>
      request<void>(`/api/orgs/${orgId}/people/${personId}/contact-entries/${entryId}`, { method: "DELETE" }),

    listPersonMessageThreads: async (orgId: string, personId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/message-threads`);
      return { threads: extractListValue<PersonMessageThread>(payload, "threads") };
    },
    createPersonMessageThread: async (orgId: string, personId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/message-threads`, {
        method: "POST",
        body,
      });
      return { thread: extractObjectValue<PersonMessageThread>(payload, "thread") };
    },
    patchPersonMessageThread: async (orgId: string, personId: string, threadId: string, body) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/people/${personId}/message-threads/${threadId}`,
        { method: "PATCH", body }
      );
      return { thread: extractObjectValue<PersonMessageThread>(payload, "thread") };
    },
    deletePersonMessageThread: (orgId: string, personId: string, threadId: string) =>
      request<void>(`/api/orgs/${orgId}/people/${personId}/message-threads/${threadId}`, { method: "DELETE" }),

    listPersonThreadMessages: async (orgId: string, personId: string, threadId: string) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/people/${personId}/message-threads/${threadId}/messages`
      );
      return { messages: extractListValue<PersonMessage>(payload, "messages") };
    },
    createPersonThreadMessage: async (orgId: string, personId: string, threadId: string, body) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/people/${personId}/message-threads/${threadId}/messages`,
        { method: "POST", body }
      );
      return { message: extractObjectValue<PersonMessage>(payload, "message") };
    },

    listPersonRates: async (orgId: string, personId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/rates`);
      return { rates: extractListValue<PersonRate>(payload, "rates") };
    },
    createPersonRate: async (orgId: string, personId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/rates`, {
        method: "POST",
        body,
      });
      return { rate: extractObjectValue<PersonRate>(payload, "rate") };
    },
    patchPersonRate: async (orgId: string, personId: string, rateId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/rates/${rateId}`, {
        method: "PATCH",
        body,
      });
      return { rate: extractObjectValue<PersonRate>(payload, "rate") };
    },
    deletePersonRate: (orgId: string, personId: string, rateId: string) =>
      request<void>(`/api/orgs/${orgId}/people/${personId}/rates/${rateId}`, { method: "DELETE" }),

    listPersonPayments: async (orgId: string, personId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/payments`);
      return { payments: extractListValue<PersonPayment>(payload, "payments") };
    },
    createPersonPayment: async (orgId: string, personId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/payments`, {
        method: "POST",
        body,
      });
      return { payment: extractObjectValue<PersonPayment>(payload, "payment") };
    },
    patchPersonPayment: async (orgId: string, personId: string, paymentId: string, body) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/people/${personId}/payments/${paymentId}`,
        { method: "PATCH", body }
      );
      return { payment: extractObjectValue<PersonPayment>(payload, "payment") };
    },
    deletePersonPayment: (orgId: string, personId: string, paymentId: string) =>
      request<void>(`/api/orgs/${orgId}/people/${personId}/payments/${paymentId}`, { method: "DELETE" }),

    getPersonAvailability: async (orgId: string, personId: string, options?: { start_at?: string; end_at?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/availability`, {
        query: { start_at: options?.start_at, end_at: options?.end_at },
      });
      return payload as PersonAvailabilityResponse;
    },

    createPersonWeeklyWindow: async (
      orgId: string,
      personId: string,
      body: { weekday: number; start_time: string; end_time: string }
    ) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/people/${personId}/availability/weekly-windows`,
        { method: "POST", body }
      );
      return { weekly_window: extractObjectValue<CreatePersonWeeklyWindowResponse["weekly_window"]>(payload, "weekly_window") };
    },

    patchPersonWeeklyWindow: async (
      orgId: string,
      personId: string,
      weeklyWindowId: string,
      body: { weekday?: number; start_time?: string; end_time?: string }
    ) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/people/${personId}/availability/weekly-windows/${weeklyWindowId}`,
        { method: "PATCH", body }
      );
      return { weekly_window: extractObjectValue<PatchPersonWeeklyWindowResponse["weekly_window"]>(payload, "weekly_window") };
    },

    deletePersonWeeklyWindow: (orgId: string, personId: string, weeklyWindowId: string) =>
      request<void>(
        `/api/orgs/${orgId}/people/${personId}/availability/weekly-windows/${weeklyWindowId}`,
        { method: "DELETE" }
      ),

    createPersonAvailabilityException: async (
      orgId: string,
      personId: string,
      body: { kind: string; starts_at: string; ends_at: string; title?: string; notes?: string }
    ) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/${personId}/availability/exceptions`, {
        method: "POST",
        body,
      });
      return { exception: extractObjectValue<CreatePersonAvailabilityExceptionResponse["exception"]>(payload, "exception") };
    },

    patchPersonAvailabilityException: async (
      orgId: string,
      personId: string,
      exceptionId: string,
      body: { kind?: string; starts_at?: string; ends_at?: string; title?: string; notes?: string }
    ) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/people/${personId}/availability/exceptions/${exceptionId}`,
        { method: "PATCH", body }
      );
      return { exception: extractObjectValue<PatchPersonAvailabilityExceptionResponse["exception"]>(payload, "exception") };
    },

    deletePersonAvailabilityException: (orgId: string, personId: string, exceptionId: string) =>
      request<void>(`/api/orgs/${orgId}/people/${personId}/availability/exceptions/${exceptionId}`, {
        method: "DELETE",
      }),

    searchPeopleAvailability: async (orgId: string, options: { start_at: string; end_at: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/people/availability-search`, {
        query: { start_at: options.start_at, end_at: options.end_at },
      });
      return payload as PeopleAvailabilitySearchResponse;
    },



    listOrgMemberships: async (orgId: string, options?: { role?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/memberships`, {
        query: { role: options?.role },
      });
      return { memberships: extractListValue<OrgMembershipWithUser>(payload, "memberships") };
    },

    updateOrgMembership: async (orgId: string, membershipId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/memberships/${membershipId}`, {
        method: "PATCH",
        body,
      });
      return { membership: extractObjectValue<ApiMembership>(payload, "membership") };
    },

    listApiKeys: async (orgId: string, options?: { mine?: boolean; owner_user_id?: string }) => {
      const payload = await request<unknown>("/api/api-keys", {
        query: {
          org_id: orgId,
          mine: options?.mine ? "1" : undefined,
          owner_user_id: options?.owner_user_id,
        },
      });
      return { api_keys: extractListValue<ApiKey>(payload, "api_keys") };
    },
    createApiKey: async (
      orgId: string,
      body: { name: string; project_id?: string | null; scopes?: string[]; owner_user_id?: string | null }
    ) => {
      const payload = await request<unknown>("/api/api-keys", {
        method: "POST",
        body: { org_id: orgId, ...body },
      });
      return {
        api_key: extractObjectValue<ApiKey>(payload, "api_key"),
        token: extractStringValue(payload, "token"),
      };
    },
    rotateApiKey: async (apiKeyId: string) => {
      const payload = await request<unknown>(`/api/api-keys/${apiKeyId}/rotate`, {
        method: "POST",
        body: {},
      });
      return {
        api_key: extractObjectValue<ApiKey>(payload, "api_key"),
        token: extractStringValue(payload, "token"),
      };
    },
    revokeApiKey: async (apiKeyId: string) => {
      const payload = await request<unknown>(`/api/api-keys/${apiKeyId}/revoke`, {
        method: "POST",
        body: {},
      });
      return { api_key: extractObjectValue<ApiKey>(payload, "api_key") };
    },

    listSows: async (orgId: string, options?: { projectId?: string; status?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/sows`, {
        query: { project_id: options?.projectId, status: options?.status },
      });
      return { sows: extractListValue<SoWListItem>(payload, "sows") };
    },
    getSow: async (orgId: string, sowId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/sows/${sowId}`);
      return {
        sow: extractObjectValue<SoWResponse["sow"]>(payload, "sow"),
        version: extractObjectValue<SoWResponse["version"]>(payload, "version"),
        signers: extractListValue<SoWResponse["signers"][number]>(payload, "signers"),
        pdf: extractNullableObjectValue<SoWPdfArtifact>(payload, "pdf"),
      };
    },
    createSow: async (orgId: string, payloadIn) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/sows`, {
        method: "POST",
        body: payloadIn,
      });
      return {
        sow: extractObjectValue<SoWResponse["sow"]>(payload, "sow"),
        version: extractObjectValue<SoWResponse["version"]>(payload, "version"),
        signers: extractListValue<SoWResponse["signers"][number]>(payload, "signers"),
        pdf: extractNullableObjectValue<SoWPdfArtifact>(payload, "pdf"),
      };
    },
    sendSow: async (orgId: string, sowId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/sows/${sowId}/send`, {
        method: "POST",
        body: {},
      });
      return {
        sow: extractObjectValue<SoWResponse["sow"]>(payload, "sow"),
        version: extractObjectValue<SoWResponse["version"]>(payload, "version"),
        signers: extractListValue<SoWResponse["signers"][number]>(payload, "signers"),
        pdf: extractNullableObjectValue<SoWPdfArtifact>(payload, "pdf"),
      };
    },
    respondSow: async (orgId: string, sowId: string, payloadIn) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/sows/${sowId}/respond`, {
        method: "POST",
        body: payloadIn,
      });
      return {
        sow: extractObjectValue<SoWResponse["sow"]>(payload, "sow"),
        version: extractObjectValue<SoWResponse["version"]>(payload, "version"),
        signers: extractListValue<SoWResponse["signers"][number]>(payload, "signers"),
        pdf: extractNullableObjectValue<SoWPdfArtifact>(payload, "pdf"),
      };
    },
    requestSowPdf: async (orgId: string, sowId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/sows/${sowId}/pdf`, {
        method: "POST",
        body: {},
      });
      return {
        status: extractStringValue(payload, "status"),
        pdf: extractObjectValue<SoWPdfArtifact>(payload, "pdf"),
      };
    },

    listReportRuns: async (orgId: string, options?: { projectId?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/report-runs`, {
        query: { project_id: options?.projectId },
      });
      return { report_runs: extractListValue<ReportRunSummary>(payload, "report_runs") };
    },
    createReportRun: async (orgId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/report-runs`, { method: "POST", body });
      return { report_run: extractObjectValue<ReportRunDetail>(payload, "report_run") };
    },
    getReportRun: async (orgId: string, reportRunId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/report-runs/${reportRunId}`);
      return { report_run: extractObjectValue<ReportRunDetail>(payload, "report_run") };
    },
    regenerateReportRun: async (orgId: string, reportRunId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/report-runs/${reportRunId}/regenerate`, {
        method: "POST",
      });
      return { report_run: extractObjectValue<ReportRunDetail>(payload, "report_run") };
    },
    requestReportRunPdf: async (orgId: string, reportRunId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/report-runs/${reportRunId}/pdf`, {
        method: "POST",
      });
      return {
        status: extractStringValue(payload, "status"),
        render_log: extractObjectValue<ReportRunPdfRenderLog>(payload, "render_log"),
      };
    },
    reportRunPdfDownloadUrl: (orgId: string, reportRunId: string) =>
      buildUrl(baseUrl, `/api/orgs/${orgId}/report-runs/${reportRunId}/pdf`),
    listReportRunRenderLogs: async (orgId: string, reportRunId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/report-runs/${reportRunId}/render-logs`);
      return { render_logs: extractListValue<ReportRunPdfRenderLog>(payload, "render_logs") };
    },

    publishReportRun: async (
      orgId: string,
      reportRunId: string,
      body?: { expires_at?: string | null }
    ) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/report-runs/${reportRunId}/publish`, {
        method: "POST",
        body: body ?? {},
      });
      return {
        share_link: extractObjectValue<ShareLink>(payload, "share_link"),
        share_url: extractStringValue(payload, "share_url"),
      };
    },
    listShareLinks: async (orgId: string, options?: { reportRunId?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/share-links`, {
        query: { report_run_id: options?.reportRunId },
      });
      return { share_links: extractListValue<ShareLink>(payload, "share_links") };
    },
    revokeShareLink: async (orgId: string, shareLinkId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/share-links/${shareLinkId}/revoke`, {
        method: "POST",
      });
      return { share_link: extractObjectValue<ShareLink>(payload, "share_link") };
    },
    listShareLinkAccessLogs: async (orgId: string, shareLinkId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/share-links/${shareLinkId}/access-logs`);
      return { access_logs: extractListValue<ShareLinkAccessLog>(payload, "access_logs") };
    },

	    listEpics: async (orgId: string, projectId: string) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/epics`);
	      return { epics: extractListValue<Epic>(payload, "epics") };
	    },
	    createEpic: async (orgId: string, projectId: string, body) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/epics`, {
	        method: "POST",
	        body,
	      });
	      return { epic: extractObjectValue<Epic>(payload, "epic") };
	    },
	    getEpic: async (orgId: string, epicId: string) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/epics/${epicId}`);
	      return { epic: extractObjectValue<Epic>(payload, "epic") };
	    },
	    patchEpic: async (orgId: string, epicId: string, body) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/epics/${epicId}`, {
	        method: "PATCH",
	        body,
	      });
	      return { epic: extractObjectValue<Epic>(payload, "epic") };
	    },
	    createTask: async (orgId: string, epicId: string, body) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/epics/${epicId}/tasks`, {
	        method: "POST",
	        body,
	      });
      return { task: extractObjectValue<Task>(payload, "task") };
    },

    listTasks: (orgId: string, projectId: string, options?: { status?: string; assignee_user_id?: string }) =>
      request<unknown>(`/api/orgs/${orgId}/projects/${projectId}/tasks`, {
        query: { status: options?.status, assignee_user_id: options?.assignee_user_id },
      }).then((payload) => ({
        tasks: extractListValue<Task>(payload, "tasks"),
        last_updated_at: extractOptionalStringValue(payload, "last_updated_at"),
      })),
    getTask: async (orgId: string, taskId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}`);
      return { task: extractObjectValue<Task>(payload, "task") };
    },
	    patchTask: async (orgId: string, taskId: string, body) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}`, {
	        method: "PATCH",
	        body,
	      });
	      return { task: extractObjectValue<Task>(payload, "task") };
	    },
	    updateTaskStage: async (orgId: string, taskId: string, workflowStageId: string | null) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}`, {
	        method: "PATCH",
	        body: { workflow_stage_id: workflowStageId },
	      });
	      return { task: extractObjectValue<Task>(payload, "task") };
	    },
	    listTaskParticipants: async (orgId: string, taskId: string) => {
	      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/participants`);
	      return { participants: extractListValue<TaskParticipant>(payload, "participants") };
	    },
    createTaskParticipant: async (orgId: string, taskId: string, userId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/participants`, {
        method: "POST",
        body: { user_id: userId },
      });
      return {
        participant: extractObjectValue<TaskParticipantResponse["participant"]>(payload, "participant"),
      };
    },
	    deleteTaskParticipant: (orgId: string, taskId: string, userId: string) =>
	      request<void>(`/api/orgs/${orgId}/tasks/${taskId}/participants/${userId}`, { method: "DELETE" }),

    listSubtasks: async (orgId: string, taskId: string, options?: { status?: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/subtasks`, {
        query: { status: options?.status },
      });
      return { subtasks: extractListValue<Subtask>(payload, "subtasks") };
    },
    createSubtask: async (orgId: string, taskId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/subtasks`, {
        method: "POST",
        body,
      });
      return { subtask: extractObjectValue<Subtask>(payload, "subtask") };
    },
    updateSubtaskStage: async (orgId: string, subtaskId: string, workflowStageId: string | null) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/subtasks/${subtaskId}`, {
        method: "PATCH",
        body: { workflow_stage_id: workflowStageId },
      });
      return { subtask: extractObjectValue<Subtask>(payload, "subtask") };
    },
    patchSubtask: async (orgId: string, subtaskId: string, body) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/subtasks/${subtaskId}`, {
        method: "PATCH",
        body,
      });
      return { subtask: extractObjectValue<Subtask>(payload, "subtask") };
    },
    listWorkflows: async (orgId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/workflows`);
      return { workflows: extractListValue<Workflow>(payload, "workflows") };
    },
    getWorkflow: async (orgId: string, workflowId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/workflows/${workflowId}`);
      return {
        workflow: extractObjectValue<Workflow>(payload, "workflow"),
        stages: extractListValue<WorkflowStage>(payload, "stages"),
      };
    },
    createWorkflow: async (orgId: string, payloadIn) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/workflows`, {
        method: "POST",
        body: payloadIn,
      });
      return {
        workflow: extractObjectValue<Workflow>(payload, "workflow"),
        stages: extractListValue<WorkflowStage>(payload, "stages"),
      };
    },
    updateWorkflow: async (orgId: string, workflowId: string, payloadIn: { name: string }) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/workflows/${workflowId}`, {
        method: "PATCH",
        body: payloadIn,
      });
      return { workflow: extractObjectValue<Workflow>(payload, "workflow") };
    },
    deleteWorkflow: (orgId: string, workflowId: string) =>
      request<void>(`/api/orgs/${orgId}/workflows/${workflowId}`, { method: "DELETE" }),
    listWorkflowStages: async (orgId: string, workflowId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/workflows/${workflowId}/stages`);
      return { stages: extractListValue<WorkflowStage>(payload, "stages") };
    },
    createWorkflowStage: async (orgId: string, workflowId: string, payloadIn) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/workflows/${workflowId}/stages`, {
        method: "POST",
        body: payloadIn,
      });
      return {
        stage: extractObjectValue<WorkflowStage>(payload, "stage"),
        stages: extractListValue<WorkflowStage>(payload, "stages"),
      };
    },
    updateWorkflowStage: async (orgId: string, workflowId: string, stageId: string, payloadIn) => {
      const payload = await request<unknown>(
        `/api/orgs/${orgId}/workflows/${workflowId}/stages/${stageId}`,
        { method: "PATCH", body: payloadIn }
      );
      return {
        stage: extractObjectValue<WorkflowStage>(payload, "stage"),
        stages: extractListValue<WorkflowStage>(payload, "stages"),
      };
    },
    deleteWorkflowStage: (orgId: string, workflowId: string, stageId: string) =>
      request<void>(`/api/orgs/${orgId}/workflows/${workflowId}/stages/${stageId}`, {
        method: "DELETE",
      }),
    listAuditEvents: async (orgId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/audit-events`);
      return { events: extractListValue<AuditEvent>(payload, "events") };
    },

    getOrgGitLabIntegration: async (orgId: string): Promise<GitLabIntegrationResponse> => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/integrations/gitlab`);
      return { gitlab: extractObjectValue<GitLabIntegrationSettings>(payload, "gitlab") };
    },
    patchOrgGitLabIntegration: async (orgId: string, payloadIn): Promise<GitLabIntegrationResponse> => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/integrations/gitlab`, {
        method: "PATCH",
        body: payloadIn,
      });
      return { gitlab: extractObjectValue<GitLabIntegrationSettings>(payload, "gitlab") };
    },
    validateOrgGitLabIntegration: async (orgId: string): Promise<GitLabIntegrationValidationResult> => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/integrations/gitlab/validate`, {
        method: "POST",
      });
      if (!isRecord(payload) || typeof payload.status !== "string") {
        throw new Error("unexpected response shape (expected 'status')");
      }
      const status = payload.status as GitLabIntegrationValidationStatus;
      if (status !== "valid" && status !== "invalid" && status !== "not_validated") {
        throw new Error("unexpected response value (expected 'status' to be valid/invalid/not_validated)");
      }
      return { status, error_code: extractOptionalStringValue(payload, "error_code") };
    },

    listTaskGitLabLinks: async (orgId: string, taskId: string): Promise<GitLabLinksResponse> => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/gitlab-links`);
      return { links: extractListValue<GitLabLink>(payload, "links") };
    },
    createTaskGitLabLink: async (
      orgId: string,
      taskId: string,
      url: string
    ): Promise<GitLabLinkResponse> => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/gitlab-links`, {
        method: "POST",
        body: { url },
      });
      return { link: extractObjectValue<GitLabLink>(payload, "link") };
    },
    deleteTaskGitLabLink: (orgId: string, taskId: string, linkId: string): Promise<void> =>
      request<void>(`/api/orgs/${orgId}/tasks/${taskId}/gitlab-links/${linkId}`, {
        method: "DELETE",
      }),

    listTaskComments: async (orgId: string, taskId: string) => {
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/comments`);
      return { comments: extractListValue<Comment>(payload, "comments") };
    },
    createTaskComment: async (orgId: string, taskId: string, bodyMarkdown: string, options) => {
      const body: Record<string, unknown> = { body_markdown: bodyMarkdown };
      if (typeof options?.client_safe === "boolean") {
        body.client_safe = options.client_safe;
      }
      const payload = await request<unknown>(`/api/orgs/${orgId}/tasks/${taskId}/comments`, {
        method: "POST",
        body,
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
