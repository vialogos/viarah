import { describe, expect, it } from "vitest";

import { computeGanttBar, computeGanttWindow, sortTasksForTimeline } from "./schedule";

describe("schedule utils", () => {
  it("sorts timeline tasks by start_date (nulls last) then end_date", () => {
    const tasks = [
      { title: "A", start_date: null, end_date: null },
      { title: "B", start_date: "2026-02-01", end_date: null },
      { title: "C", start_date: "2026-02-01", end_date: "2026-02-02" },
      { title: "D", start_date: "2026-02-01", end_date: "2026-02-01" },
    ];

    const sorted = sortTasksForTimeline(tasks);
    expect(sorted.map((t) => t.title)).toEqual(["D", "C", "B", "A"]);
  });

  it("computes a gantt window from min start_date to max end_date", () => {
    const tasks = [
      { start_date: "2026-02-01", end_date: "2026-02-03" },
      { start_date: "2026-02-02", end_date: "2026-02-04" },
      { start_date: null, end_date: null },
    ];

    const window = computeGanttWindow(tasks);
    expect(window.windowStart).toBe("2026-02-01");
    expect(window.windowEnd).toBe("2026-02-04");
    expect(window.windowDays).toBe(4);
  });

  it("computes inclusive gantt bar offsets + widths", () => {
    const bar = computeGanttBar(
      { start_date: "2026-02-02", end_date: "2026-02-04" },
      "2026-02-01",
      "2026-02-04"
    );

    expect(bar.leftPct).toBeCloseTo(25);
    expect(bar.widthPct).toBeCloseTo(75);
  });
});

