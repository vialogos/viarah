import type { GitLabLink } from "../api/types";
import { formatDateRange } from "./schedule";

export type GanttTimeScale = "day" | "week" | "month";

export function stableGanttId(kind: "epic" | "task" | "subtask", id: string): string {
  return `${kind}:${id}`;
}

/**
 * Hash a stable string identifier to a positive 32-bit integer suitable for gantt libraries that require numeric IDs.
 *
 * Uses FNV-1a (32-bit) and returns a value in the range [1, 2^32-1].
 */
export function stableGanttNumericId(stableId: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < stableId.length; i += 1) {
    hash ^= stableId.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  // Avoid returning 0 (some libraries treat it as falsy/unset).
  return (hash >>> 0) || 1;
}

export function progressFractionToPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(value * 100)));
}

function gitLabRefPrefix(gitlabType: string): string {
  const normalized = gitlabType.trim().toLowerCase();
  if (normalized.includes("merge") || normalized === "mr" || normalized === "merge_request") {
    return "!";
  }
  if (normalized.includes("epic")) {
    return "&";
  }
  return "#";
}

export function formatGitLabReference(link: GitLabLink): string {
  const prefix = gitLabRefPrefix(link.gitlab_type);
  return `${link.project_path}${prefix}${link.gitlab_iid}`;
}

export function formatGitLabReferenceSummary(links: GitLabLink[]): string {
  if (!links.length) {
    return "—";
  }
  const refs = links.slice(0, 3).map((link) => formatGitLabReference(link));
  const suffix = links.length > refs.length ? ` (+${links.length - refs.length} more)` : "";
  return `${refs.join(", ")}${suffix}`;
}

export function buildGanttTooltipDescription(options: {
  title: string;
  status?: string | null;
  stageName?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  progress?: number | null;
  gitLabLinksSummary?: string | null;
}): string {
  const lines: string[] = [];

  lines.push(`Title: ${options.title}`);

  if (options.status) {
    lines.push(`Status: ${options.status}`);
  }
  if (options.stageName) {
    lines.push(`Stage: ${options.stageName}`);
  }
  lines.push(`Dates: ${formatDateRange(options.startDate ?? null, options.endDate ?? null)}`);

  if (options.progress != null && Number.isFinite(options.progress)) {
    lines.push(`Progress: ${progressFractionToPercent(options.progress)}%`);
  }

  if (options.gitLabLinksSummary) {
    lines.push(`GitLab: ${options.gitLabLinksSummary}`);
  }

  return lines.join("\n");
}
