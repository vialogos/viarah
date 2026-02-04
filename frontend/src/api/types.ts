export type UUID = string;

export type ProgressWhy = Record<string, unknown>;

export interface ApiUser {
  id: UUID;
  email: string;
  display_name: string;
}

export interface ApiOrgRef {
  id: UUID;
  name: string;
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
  project_id?: UUID | null;
  scopes?: string[];
}

export interface Project {
  id: UUID;
  org_id: UUID;
  workflow_id: UUID | null;
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
  status: string | null;
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

export interface Task {
  id: UUID;
  epic_id: UUID;
  title: string;
  description?: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
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
  start_date: string | null;
  end_date: string | null;
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
