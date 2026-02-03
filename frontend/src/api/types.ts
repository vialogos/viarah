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
  created_at?: string;
  updated_at?: string;
  progress: number;
  progress_why: ProgressWhy;
}

export interface TasksResponse {
  tasks: Task[];
}

export interface TaskResponse {
  task: Task;
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
