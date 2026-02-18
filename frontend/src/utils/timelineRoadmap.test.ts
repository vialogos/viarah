import { describe, expect, it } from "vitest";

import type { Task } from "../api/types";
import { buildTimelineGroups, buildTimelineItems, isScheduledTask, splitTasksBySchedule } from "./timelineRoadmap";

function task(overrides: Partial<Task>): Task {
  return {
    id: "task-1",
    epic_id: "epic-1",
    workflow_stage_id: null,
    workflow_stage: null,
    assignee_user_id: null,
    title: "Title",
    start_date: null,
    end_date: null,
    status: "backlog",
    custom_field_values: [],
    progress: 0,
    progress_why: {},
    ...overrides,
  };
}

describe("timelineRoadmap", () => {
  it("detects scheduled tasks and splits lists", () => {
    const scheduled = task({ id: "a", start_date: "2026-02-01", end_date: "2026-02-03" });
    const unscheduled = task({ id: "b", start_date: "2026-02-01", end_date: null });

    expect(isScheduledTask(scheduled)).toBe(true);
    expect(isScheduledTask(unscheduled)).toBe(false);

    const split = splitTasksBySchedule([scheduled, unscheduled]);
    expect(split.scheduled.map((t) => t.id)).toEqual(["a"]);
    expect(split.unscheduled.map((t) => t.id)).toEqual(["b"]);
  });

  it("builds status groups in stable order", () => {
    const input = [
      task({ id: "a", status: "qa", start_date: "2026-02-01", end_date: "2026-02-03" }),
      task({ id: "b", status: "backlog", start_date: "2026-02-01", end_date: "2026-02-03" }),
      task({ id: "c", status: "done", start_date: "2026-02-01", end_date: "2026-02-03" }),
    ];
    const tasks = splitTasksBySchedule(input).scheduled;

    const groups = buildTimelineGroups(tasks, "status");
    expect(groups.map((g) => g.id)).toEqual(["status:backlog", "status:qa", "status:done"]);
    expect(groups.map((g) => g.content)).toEqual(["Backlog", "QA", "Done"]);
  });

  it("uses epic title map for epic group labels", () => {
    const input = [
      task({ id: "a", epic_id: "epic-a", start_date: "2026-02-01", end_date: "2026-02-03" }),
      task({ id: "b", epic_id: "epic-b", start_date: "2026-02-01", end_date: "2026-02-03" }),
    ];
    const tasks = splitTasksBySchedule(input).scheduled;

    const groups = buildTimelineGroups(tasks, "epic", { epicTitlesById: { "epic-b": "Beta epic" } });
    expect(groups.map((g) => g.content)).toEqual(["Beta epic", "epic-a"]);
  });

  it("builds range items with inclusive end-date semantics", () => {
    const tasks = splitTasksBySchedule([task({ id: "a", start_date: "2026-02-01", end_date: "2026-02-03" })])
      .scheduled;

    const items = buildTimelineItems(tasks, "status");
    expect(items).toHaveLength(1);

    const item = items[0]!;
    const expectedStart = new Date(2026, 1, 1);
    const expectedEndExclusive = new Date(2026, 1, 4);
    expect(item.start).toEqual(expectedStart);
    expect(item.end).toEqual(expectedEndExclusive);
  });
});
