export type UUID = string;

export type ProgressWhy = Record<string, unknown>;

export type ProgressPolicy = "subtasks_rollup" | "workflow_stage";

export type WorkflowStageCategory = "backlog" | "in_progress" | "qa" | "done";

export interface ApiUser {
  id: UUID;
  email: string;
  display_name: string;
}

export interface ApiOrgRef {
  id: UUID;
  name: string;
}

export interface ClientRef {
  id: UUID;
  name: string;
}

export interface Client {
  id: UUID;
  org_id: UUID;
  name: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface ApiMembership {
  id: UUID;
  org: ApiOrgRef;
  role: string;
}

export interface MeResponse {
  user: ApiUser | null;
  memberships: ApiMembership[];

  // When authenticated via API key rather than session auth.
  principal_type?: "api_key";
  api_key_id?: UUID;
  org_id?: UUID;
  owner_user_id?: UUID;
  project_id?: UUID | null;
  scopes?: string[];
}

export interface Project {
  id: UUID;
  org_id: UUID;
  client_id?: UUID | null;
  client?: ClientRef | null;
  workflow_id: UUID | null;
  progress_policy?: ProgressPolicy;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectsResponse {
  projects: Project[];
}

export interface ProjectResponse {
  project: Project;
}

export interface ClientsResponse {
  clients: Client[];
}

export interface ClientResponse {
  client: Client;
}

export type OrgAvailabilityStatus = "unknown" | "available" | "limited" | "unavailable";

export interface OrgMembershipWithUser {
  id: UUID;
  role: string;
  user: ApiUser;

  title: string;
  skills: string[];
  bio: string;

  availability_status: OrgAvailabilityStatus;
  availability_hours_per_week: number | null;
  availability_next_available_at: string | null;
  availability_notes: string;
}

export interface OrgMembershipsResponse {
  memberships: OrgMembershipWithUser[];
}


export interface ProjectMembershipWithUser {
  id: UUID;
  project_id: UUID;
  user: ApiUser;
  role: string;
  created_at: string;
}

export interface ProjectMembershipsResponse {
  memberships: ProjectMembershipWithUser[];
}

export interface ProjectMembershipResponse {
  membership: ProjectMembershipWithUser;
}

export interface ApiKey {
  id: UUID;
  org_id: UUID;
  owner_user_id: UUID;
  project_id: UUID | null;
  name: string;
  prefix: string;
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  created_by_user_id: UUID | null;
  created_at: string;
  revoked_at: string | null;
  rotated_at: string | null;
}

export interface ApiKeysResponse {
  api_keys: ApiKey[];
}

export interface CreateApiKeyResponse {
  api_key: ApiKey;
  token: string;
}

export interface RotateApiKeyResponse {
  api_key: ApiKey;
  token: string;
}

export interface RevokeApiKeyResponse {
  api_key: ApiKey;
}

export interface PersonSummary {
  id: UUID;
  display: string;
  email: string | null;
}

export type OrgInviteStatus = "active" | "accepted" | "revoked" | "expired";

export interface OrgInvite {
  id: UUID;
  org_id: UUID;
  person_id: UUID | null;
  person: PersonSummary | null;
  email: string;
  role: string;
  message: string;
  status: OrgInviteStatus;
  expires_at: string;
  created_by_user_id: UUID;
  created_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
}

export interface OrgInvitesResponse {
  invites: OrgInvite[];
}

export interface CreateOrgInviteResponse {
  invite: OrgInvite;
  token: string;
  invite_url: string;
}

export interface AcceptInviteResponse {
  membership: ApiMembership;
  person: PersonSummary;
  needs_profile_setup: boolean;
}

export type PersonStatus = "candidate" | "invited" | "active";

export interface Person {
  id: UUID;
  org_id: UUID;
  user: ApiUser | null;
  avatar_url: string | null;
  status: PersonStatus;
  membership_role: string | null;
  full_name: string;
  preferred_name: string;
  email: string | null;
  title: string;
  skills: string[];
  bio: string;
  notes: string;
  timezone: string;
  location: string;
  phone: string;
  slack_handle: string;
  linkedin_url: string;
  gitlab_username: string | null;
  created_at: string;
  updated_at: string;
  active_invite: OrgInvite | null;
}

export interface PeopleResponse {
  people: Person[];
}

export interface PersonResponse {
  person: Person;
}

export interface PersonProjectMembership {
  id: UUID;
  project: {
    id: UUID;
    workflow_id: UUID | null;
    name: string;
  };
  created_at: string;
}

export interface PersonProjectMembershipsResponse {
  memberships: PersonProjectMembership[];
}

export type PersonContactEntryKind = "note" | "call" | "email" | "meeting";

export interface PersonContactEntry {
  id: UUID;
  person_id: UUID;
  kind: PersonContactEntryKind;
  occurred_at: string;
  summary: string;
  notes: string;
  created_by_user_id: UUID;
  created_at: string;
}

export interface PersonContactEntriesResponse {
  entries: PersonContactEntry[];
}

export interface PersonContactEntryResponse {
  entry: PersonContactEntry;
}

export interface PersonMessageThread {
  id: UUID;
  person_id: UUID;
  title: string;
  created_by_user_id: UUID;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface PersonMessageThreadsResponse {
  threads: PersonMessageThread[];
}

export interface PersonMessageThreadResponse {
  thread: PersonMessageThread;
}

export interface PersonMessage {
  id: UUID;
  thread_id: UUID;
  author_user_id: UUID;
  body_markdown: string;
  body_html: string;
  created_at: string;
}

export interface PersonMessagesResponse {
  messages: PersonMessage[];
}

export interface PersonMessageResponse {
  message: PersonMessage;
}

export interface PersonRate {
  id: UUID;
  person_id: UUID;
  currency: string;
  amount_cents: number;
  effective_date: string;
  notes: string;
  created_by_user_id: UUID;
  created_at: string;
}

export interface PersonRatesResponse {
  rates: PersonRate[];
}

export interface PersonRateResponse {
  rate: PersonRate;
}

export interface PersonPayment {
  id: UUID;
  person_id: UUID;
  currency: string;
  amount_cents: number;
  paid_date: string;
  notes: string;
  created_by_user_id: UUID;
  created_at: string;
}

export interface PersonPaymentsResponse {
  payments: PersonPayment[];
}

export interface PersonPaymentResponse {
  payment: PersonPayment;
}


export type PersonAvailabilityExceptionKind = "time_off" | "available";

export interface PersonAvailabilityWeeklyWindow {
  id: UUID;
  weekday: number;
  start_time: string;
  end_time: string;
  created_at: string;
  updated_at: string;
}

export interface PersonAvailabilityException {
  id: UUID;
  kind: PersonAvailabilityExceptionKind;
  starts_at: string;
  ends_at: string;
  title: string;
  notes: string;
  created_by_user_id: UUID;
  created_at: string;
  updated_at: string;
}

export interface PersonAvailabilitySummary {
  has_availability: boolean;
  next_available_at: string | null;
  minutes_available: number;
}

export interface PersonAvailabilityResponse {
  timezone: string;
  weekly_windows: PersonAvailabilityWeeklyWindow[];
  exceptions: PersonAvailabilityException[];
  summary: PersonAvailabilitySummary;
}

export interface PeopleAvailabilitySearchMatch extends PersonAvailabilitySummary {
  person_id: UUID;
}

export interface PeopleAvailabilitySearchResponse {
  start_at: string;
  end_at: string;
  matches: PeopleAvailabilitySearchMatch[];
}

export interface CreatePersonWeeklyWindowResponse {
  weekly_window: PersonAvailabilityWeeklyWindow;
}

export interface PatchPersonWeeklyWindowResponse {
  weekly_window: PersonAvailabilityWeeklyWindow;
}

export interface CreatePersonAvailabilityExceptionResponse {
  exception: PersonAvailabilityException;
}

export interface PatchPersonAvailabilityExceptionResponse {
  exception: PersonAvailabilityException;
}

export interface OrgMembershipResponse {
  membership: ApiMembership;
}

export type SoWVersionStatus = "draft" | "pending_signature" | "signed" | "rejected";
export type SoWSignerStatus = "pending" | "approved" | "rejected";
export type SoWPdfStatus = "queued" | "running" | "success" | "failed";

export interface SoW {
  id: UUID;
  org_id: UUID;
  project_id: UUID;
  template_id: UUID;
  current_version_id: UUID | null;
  created_by_user_id: UUID | null;
  created_at: string;
  updated_at: string;
}

export interface SoWVersion {
  id: UUID;
  sow_id: UUID;
  version: number;
  template_version_id: UUID;
  variables: Record<string, unknown>;
  status: SoWVersionStatus;
  locked_at: string | null;
  content_sha256: string | null;
  created_by_user_id: UUID | null;
  created_at: string;
  body_markdown: string;
  body_html: string;
}

export interface SoWVersionSummary {
  id: UUID;
  version: number;
  status: SoWVersionStatus;
  locked_at: string | null;
  created_at: string;
}

export interface SoWSigner {
  id: UUID;
  sow_version_id: UUID;
  signer_user_id: UUID;
  status: SoWSignerStatus;
  decision_comment: string;
  typed_signature: string;
  responded_at: string | null;
  created_at: string;
}

export interface SoWPdfArtifact {
  id: UUID;
  sow_version_id: UUID;
  status: SoWPdfStatus;
  celery_task_id: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  blocked_urls: string[];
  missing_images: string[];
  error_code: string | null;
  error_message: string | null;
  qa_report: Record<string, unknown>;
  pdf_sha256: string | null;
  pdf_size_bytes: number;
  pdf_rendered_at: string | null;
}

export interface SoWResponse {
  sow: SoW;
  version: SoWVersion;
  signers: SoWSigner[];
  pdf: SoWPdfArtifact | null;
}

export interface SoWListItem {
  sow: SoW;
  version: SoWVersionSummary;
  signers: SoWSigner[];
  pdf: SoWPdfArtifact | null;
}

export interface SowsResponse {
  sows: SoWListItem[];
}

export interface SavedViewFilters {
  status: string[];
  search: string;
}

export interface SavedViewSort {
  field: "created_at" | "updated_at" | "title";
  direction: "asc" | "desc";
}

export interface SavedView {
  id: UUID;
  org_id: UUID;
  project_id: UUID;
  owner_user_id: UUID;
  name: string;
  client_safe: boolean;
  filters: SavedViewFilters;
  sort: SavedViewSort;
  group_by: "none" | "status";
  created_at: string;
  updated_at: string;
}

export interface SavedViewsResponse {
  saved_views: SavedView[];
}

export interface SavedViewResponse {
  saved_view: SavedView;
}

export type CustomFieldType = "text" | "number" | "date" | "select" | "multi_select";

export interface CustomFieldDefinition {
  id: UUID;
  org_id: UUID;
  project_id: UUID;
  name: string;
  field_type: CustomFieldType;
  options: string[];
  client_safe: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomFieldsResponse {
  custom_fields: CustomFieldDefinition[];
}

export interface CustomFieldResponse {
  custom_field: CustomFieldDefinition;
}

export interface CustomFieldValue {
  field_id: UUID;
  value: unknown;
}

export interface PatchCustomFieldValuesResponse {
  custom_field_values: CustomFieldValue[];
}

export interface Epic {
  id: UUID;
  project_id: UUID;
  title: string;
  description: string;
  description_html?: string;
  status: string | null;
  progress_policy: ProgressPolicy | null;
  created_at: string;
  updated_at: string;
  progress: number;
  progress_why: ProgressWhy;
}

export interface EpicsResponse {
  epics: Epic[];
}

export interface EpicResponse {
  epic: Epic;
}

export interface WorkflowStageMeta {
  id: UUID;
  name: string;
  order: number;
  category: WorkflowStageCategory;
  progress_percent: number;
  is_done: boolean;
  is_qa: boolean;
  counts_as_wip: boolean;
}

export interface Task {
  id: UUID;
  epic_id: UUID;
  workflow_stage_id: UUID | null;
  workflow_stage: WorkflowStageMeta | null;
  assignee_user_id: UUID | null;
  title: string;
  description?: string;
  description_html?: string;
  start_date: string | null;
  end_date: string | null;
  actual_started_at?: string | null;
  actual_ended_at?: string | null;
  status: string;
  progress_policy?: ProgressPolicy | null;
  client_safe?: boolean;
  created_at?: string;
  updated_at?: string;
  custom_field_values: CustomFieldValue[];
  progress: number;
  progress_why: ProgressWhy;
}

export interface TasksResponse {
  tasks: Task[];
  last_updated_at?: string | null;
}

export interface TaskResponse {
  task: Task;
}

export type TaskParticipantSource = "manual" | "assignee" | "comment" | "gitlab";

export interface TaskParticipantPersonRef {
  id: UUID;
  full_name: string;
  preferred_name: string;
  title: string;
}

export interface TaskParticipant {
  user: ApiUser;
  person: TaskParticipantPersonRef | null;
  org_role: string | null;
  sources: TaskParticipantSource[];
}

export interface TaskParticipantsResponse {
  participants: TaskParticipant[];
}

export interface TaskParticipantResponse {
  participant: {
    task_id: UUID;
    user_id: UUID;
    created_at: string;
  };
}

export interface GitLabIntegrationSettings {
  base_url: string | null;
  has_token: boolean;
  token_set_at: string | null;
  webhook_configured: boolean;
}

export interface GitLabIntegrationResponse {
  gitlab: GitLabIntegrationSettings;
}

export type GitLabIntegrationValidationStatus = "valid" | "invalid" | "not_validated";

export interface GitLabIntegrationValidationResult {
  status: GitLabIntegrationValidationStatus;
  error_code: string | null;
}

export interface GitLabLinkAssignee {
  username: string;
  name: string;
}

export type GitLabLinkSyncStatus = "ok" | "never" | "stale" | "error";

export interface GitLabLinkSync {
  status: GitLabLinkSyncStatus;
  stale: boolean;
  rate_limited: boolean;
  rate_limited_until: string | null;
  error_code: string | null;
}

export interface GitLabLink {
  id: UUID;
  url: string;
  project_path: string;
  gitlab_type: string;
  gitlab_iid: number;
  cached_title: string;
  cached_state: string;
  cached_labels: string[];
  cached_assignees: GitLabLinkAssignee[];
  last_synced_at: string | null;
  sync: GitLabLinkSync;
}

export interface GitLabLinksResponse {
  links: GitLabLink[];
}

export interface GitLabLinkResponse {
  link: GitLabLink;
}

export interface CommentAuthorRef {
  id: UUID;
  display_name: string;
}

export interface Comment {
  id: UUID;
  created_at: string;
  author: CommentAuthorRef;
  body_markdown: string;
  body_html: string;
  client_safe?: boolean;
  attachment_ids?: UUID[];
}

export interface CommentsResponse {
  comments: Comment[];
}

export interface CommentResponse {
  comment: Comment;
}

export interface Attachment {
  id: UUID;
  created_at: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  download_url: string;
  comment_id: UUID | null;
}

export interface AttachmentsResponse {
  attachments: Attachment[];
}

export interface AttachmentResponse {
  attachment: Attachment;
}

export interface Subtask {
  id: UUID;
  task_id: UUID;
  workflow_stage_id: UUID | null;
  title: string;
  description?: string;
  description_html?: string;
  start_date: string | null;
  end_date: string | null;
  actual_started_at?: string | null;
  actual_ended_at?: string | null;
  status: string;
  created_at?: string;
  updated_at?: string;
  custom_field_values: CustomFieldValue[];
  progress: number;
  progress_why: ProgressWhy;
}

export interface SubtasksResponse {
  subtasks: Subtask[];
}

export interface SubtaskResponse {
  subtask: Subtask;
}

export interface Workflow {
  id: UUID;
  org_id: UUID;
  name: string;
  created_by_user_id: UUID | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStage {
  id: UUID;
  workflow_id: UUID;
  name: string;
  order: number;
  category: WorkflowStageCategory;
  progress_percent: number;
  is_done: boolean;
  is_qa: boolean;
  counts_as_wip: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStagesResponse {
  stages: WorkflowStage[];
}

export interface WorkflowsResponse {
  workflows: Workflow[];
}

export interface WorkflowResponse {
  workflow: Workflow;
}

export interface WorkflowWithStagesResponse {
  workflow: Workflow;
  stages: WorkflowStage[];
}

export interface WorkflowStageResponse {
  stage: WorkflowStage;
}

export interface WorkflowStageWithStagesResponse {
  stage: WorkflowStage;
  stages: WorkflowStage[];
}

export interface AuditActorUser {
  id: UUID;
  email: string;
  display_name: string;
}

export interface AuditEvent {
  id: UUID;
  created_at: string;
  event_type: string;
  actor_user_id: UUID | null;
  actor_user?: AuditActorUser | null;
  metadata: Record<string, unknown>;
}

export interface AuditEventsResponse {
  events: AuditEvent[];
}

export interface InAppNotification {
  id: UUID;
  event_id: UUID;
  org_id: UUID;
  project_id: UUID | null;
  event_type: string;
  data: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface MyNotificationsResponse {
  notifications: InAppNotification[];
}

export interface NotificationsBadgeResponse {
  unread_count: number;
}

export interface NotificationResponse {
  notification: InAppNotification;
}

export interface MarkAllNotificationsReadResponse {
  updated_count: number;
}

export interface NotificationPreferenceRow {
  event_type: string;
  channel: string;
  enabled: boolean;
}

export interface NotificationPreferencesResponse {
  preferences: NotificationPreferenceRow[];
}

export interface ProjectNotificationSettingRow {
  event_type: string;
  channel: string;
  enabled: boolean;
}

export interface ProjectNotificationSettingsResponse {
  settings: ProjectNotificationSettingRow[];
}

export interface EmailDeliveryLog {
  id: UUID;
  org_id: UUID;
  project_id: UUID | null;
  notification_event_id: UUID | null;
  outbound_draft_id: UUID | null;
  recipient_user_id: UUID | null;
  to_email: string;
  subject: string;
  status: string;
  attempt_number: number;
  error_code: string | null;
  error_detail: string | null;
  queued_at: string | null;
  sent_at: string | null;
  updated_at: string | null;
}

export interface NotificationDeliveryLogsResponse {
  deliveries: EmailDeliveryLog[];
}

export interface PushVapidPublicKeyResponse {
  public_key: string;
}

export interface PushVapidConfigStatus {
  configured: boolean;
  source: string;
  public_key: string | null;
  subject: string | null;
  private_key_configured: boolean;
  encryption_configured: boolean;
  error_code: string | null;
}

export interface PushVapidConfigResponse {
  config: PushVapidConfigStatus;
}

export interface PushSubscriptionRow {
  id: UUID;
  endpoint: string;
  expiration_time: number | null;
  user_agent: string;
  created_at: string;
  updated_at: string;
}

export interface PushSubscriptionsResponse {
  subscriptions: PushSubscriptionRow[];
}

export interface PushSubscriptionResponse {
  subscription: PushSubscriptionRow;
}

export type TemplateType = "report" | "sow" | (string & {});

export interface Template {
  id: UUID;
  org_id: UUID;
  type: TemplateType;
  name: string;
  description: string | null;
  current_version_id: UUID | null;
  created_at: string;
  updated_at: string;
}

export interface TemplateVersionSummary {
  id: UUID;
  template_id: UUID;
  version: number;
  created_by_user_id: UUID;
  created_at: string;
}

export interface TemplatesResponse {
  templates: Template[];
}

export interface TemplateResponse {
  template: Template;
}

export interface TemplateDetailResponse {
  template: Template;
  current_version_body: string | null;
  versions: TemplateVersionSummary[];
}

export interface TemplateVersionResponse {
  template: Template;
  version: TemplateVersionSummary;
}

export type ReportRunScope = {
  from_date?: string;
  to_date?: string;
  statuses?: string[];
} & Record<string, unknown>;

export interface ReportRunSummary {
  id: UUID;
  org_id: UUID;
  project_id: UUID;
  template_id: UUID;
  template_version_id: UUID | null;
  scope: ReportRunScope;
  created_by_user_id: UUID;
  created_at: string;
  web_view_url: string | null;
}

export interface ReportRunDetail extends ReportRunSummary {
  output_markdown: string | null;
  output_html: string | null;
}

export interface ReportRunsResponse {
  report_runs: ReportRunSummary[];
}

export interface ReportRunResponse {
  report_run: ReportRunDetail;
}

export interface ReportRunPdfRenderLog {
  id: UUID;
  report_run_id: UUID;
  status: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  blocked_urls: string[];
  missing_images: string[];
  error_code: string | null;
  error_message: string | null;
  qa_report: Record<string, unknown> | null;
}

export interface ReportRunRenderLogsResponse {
  render_logs: ReportRunPdfRenderLog[];
}

export interface RequestReportRunPdfResponse {
  status: string;
  render_log: ReportRunPdfRenderLog;
}

export type ShareLinkCreatedByType = "user" | "api_key" | (string & {});

export interface ShareLinkCreatedByRef {
  type: ShareLinkCreatedByType;
  id: UUID;
  display: string;
}

export interface ShareLink {
  id: UUID;
  org_id: UUID;
  report_run_id: UUID;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
  created_by: ShareLinkCreatedByRef | null;
  access_count: number;
  last_access_at: string | null;
}

export interface ShareLinksResponse {
  share_links: ShareLink[];
}

export interface ShareLinkResponse {
  share_link: ShareLink;
}

export interface ShareLinkPublishResponse {
  share_link: ShareLink;
  share_url: string;
}

export interface ShareLinkAccessLog {
  accessed_at: string;
  ip_address: string | null;
  user_agent: string | null;
}

export interface ShareLinkAccessLogsResponse {
  access_logs: ShareLinkAccessLog[];
}
