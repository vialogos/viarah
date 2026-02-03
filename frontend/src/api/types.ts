export type UUID = string;

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

export interface Task {
  id: UUID;
  epic_id: UUID;
  title: string;
  description: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  custom_field_values: CustomFieldValue[];
  progress: number;
  progress_why: Record<string, unknown>;
}

export interface TasksResponse {
  tasks: Task[];
}

export interface TaskResponse {
  task: Task;
}
