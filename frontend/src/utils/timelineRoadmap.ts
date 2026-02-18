import type { Task } from "../api/types";
import type { DataItem, TimelineGroup } from "vis-timeline/standalone";

export type RoadmapScalePreset = "day" | "week" | "month";
export type RoadmapGroupBy = "status" | "epic";

export type ScheduledTask = Task & { start_date: string; end_date: string };

const KNOWN_STATUS_ORDER = ["backlog", "in_progress", "qa", "done"] as const;

function statusSortValue(status: string): number {
  const idx = KNOWN_STATUS_ORDER.indexOf(status as (typeof KNOWN_STATUS_ORDER)[number]);
  if (idx >= 0) {
    return idx;
  }
  return KNOWN_STATUS_ORDER.length;
}

function titleCaseFromKey(value: string): string {
  return value
    .split("_")
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(" ");
}

function statusLabel(status: string): string {
  if (status === "qa") {
    return "QA";
  }
  return titleCaseFromKey(status);
}

function safeCssKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function parseIsoDateToLocalDate(value: string | null): Date | null {
  if (!value) {
    return null;
  }

  const parts = value.split("-");
  if (parts.length !== 3) {
    return null;
  }

  const year = Number(parts[0]);
  const month = Number(parts[1]);
  const day = Number(parts[2]);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return null;
  }
  if (month < 1 || month > 12) {
    return null;
  }
  if (day < 1 || day > 31) {
    return null;
  }

  const date = new Date(year, month - 1, day);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date;
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

/**
 * Determines whether a task is scheduled for roadmap rendering (has a valid start+end ISO date).
 */
export function isScheduledTask(task: Task): task is ScheduledTask {
  if (typeof task.start_date !== "string" || typeof task.end_date !== "string") {
    return false;
  }

  const start = parseIsoDateToLocalDate(task.start_date);
  const end = parseIsoDateToLocalDate(task.end_date);
  if (!start || !end) {
    return false;
  }

  return end.getTime() >= start.getTime();
}

export function splitTasksBySchedule(tasks: Task[]): { scheduled: ScheduledTask[]; unscheduled: Task[] } {
  const scheduled: ScheduledTask[] = [];
  const unscheduled: Task[] = [];
  for (const task of tasks) {
    if (isScheduledTask(task)) {
      scheduled.push(task);
    } else {
      unscheduled.push(task);
    }
  }
  return { scheduled, unscheduled };
}

export function buildTimelineGroups(
  tasks: ScheduledTask[],
  groupBy: RoadmapGroupBy,
  options?: { epicTitlesById?: Record<string, string> }
): TimelineGroup[] {
  if (groupBy === "epic") {
    const epicTitlesById = options?.epicTitlesById ?? {};
    const epics = new Set<string>();
    for (const task of tasks) {
      epics.add(task.epic_id);
    }

    const entries = [...epics].map((epicId) => ({
      epicId,
      label: epicTitlesById[epicId] ?? epicId,
    }));

    entries.sort((a, b) => a.label.localeCompare(b.label));
    return entries.map((entry) => ({
      id: `epic:${entry.epicId}`,
      content: entry.label,
      title: entry.label,
    }));
  }

  const statuses = new Set<string>();
  for (const task of tasks) {
    statuses.add(task.status);
  }

  const entries = [...statuses].map((status) => ({ status, label: statusLabel(status) }));
  entries.sort((a, b) => {
    const aSort = statusSortValue(a.status);
    const bSort = statusSortValue(b.status);
    if (aSort !== bSort) {
      return aSort - bSort;
    }
    return a.label.localeCompare(b.label);
  });

  return entries.map((entry) => ({
    id: `status:${entry.status}`,
    content: entry.label,
    title: entry.label,
  }));
}

export function buildTimelineItems(tasks: ScheduledTask[], groupBy: RoadmapGroupBy): DataItem[] {
  const items: DataItem[] = [];

  for (const task of tasks) {
    const start = parseIsoDateToLocalDate(task.start_date);
    const end = parseIsoDateToLocalDate(task.end_date);
    if (!start || !end) {
      continue;
    }

    const endExclusive = addDays(end, 1);
    const group = groupBy === "epic" ? `epic:${task.epic_id}` : `status:${task.status}`;

    const statusKey = safeCssKey(task.workflow_stage?.category ?? task.status);
    items.push({
      id: task.id,
      group,
      start,
      end: endExclusive,
      type: "range",
      content: task.title,
      title: `${task.title}\n${task.start_date} → ${task.end_date}`,
      className: `vl-timeline-item vl-timeline-item--${statusKey}`,
    });
  }

  return items;
}
