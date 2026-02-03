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
  progress: number;
  progress_why: Record<string, unknown>;
}

export interface TasksResponse {
  tasks: Task[];
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
