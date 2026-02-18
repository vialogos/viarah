import { describe, expect, it } from "vitest";

import { buildGanttTooltipDescription, formatGitLabReferenceSummary, progressFractionToPercent, stableGanttNumericId } from "./gantt";

describe("gantt utils", () => {
  it("hashes stable ids deterministically (non-zero)", () => {
    const a = stableGanttNumericId("task:123");
    const b = stableGanttNumericId("task:123");
    const c = stableGanttNumericId("task:124");

    expect(a).toBe(b);
    expect(a).not.toBe(0);
    expect(c).not.toBe(a);
  });

  it("converts progress fractions to 0-100 percent", () => {
    expect(progressFractionToPercent(0)).toBe(0);
    expect(progressFractionToPercent(0.123)).toBe(12);
    expect(progressFractionToPercent(1)).toBe(100);
    expect(progressFractionToPercent(10)).toBe(100);
    expect(progressFractionToPercent(-1)).toBe(0);
  });

  it("summarizes GitLab refs with a cap", () => {
    const summary = formatGitLabReferenceSummary([
      { project_path: "g/p", gitlab_type: "issue", gitlab_iid: 1 } as any,
      { project_path: "g/p", gitlab_type: "merge_request", gitlab_iid: 2 } as any,
      { project_path: "g/p", gitlab_type: "epic", gitlab_iid: 3 } as any,
      { project_path: "g/p", gitlab_type: "issue", gitlab_iid: 4 } as any,
    ]);
    expect(summary).toContain("g/p#1");
    expect(summary).toContain("g/p!2");
    expect(summary).toContain("g/p&3");
    expect(summary).toContain("(+1 more)");
  });

  it("builds tooltip descriptions with expected lines", () => {
    const desc = buildGanttTooltipDescription({
      title: "T",
      status: "in_progress",
      stageName: "Build",
      startDate: "2026-02-01",
      endDate: "2026-02-02",
      progress: 0.5,
      gitLabLinksSummary: "g/p#1",
    });

    expect(desc).toContain("Title: T");
    expect(desc).toContain("Status: in_progress");
    expect(desc).toContain("Stage: Build");
    expect(desc).toContain("Dates: 2026-02-01 → 2026-02-02");
    expect(desc).toContain("Progress: 50%");
    expect(desc).toContain("GitLab: g/p#1");
  });
});
