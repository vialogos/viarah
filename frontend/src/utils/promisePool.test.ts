import { describe, expect, it } from "vitest";

import { mapAllSettledWithConcurrency } from "./promisePool";

describe("mapAllSettledWithConcurrency", () => {
  it("runs all items and preserves order", async () => {
    const results = await mapAllSettledWithConcurrency([3, 1, 2], 2, async (value) => value * 2);
    expect(results).toEqual([
      { status: "fulfilled", value: 6 },
      { status: "fulfilled", value: 2 },
      { status: "fulfilled", value: 4 },
    ]);
  });

  it("captures rejections without throwing", async () => {
    const results = await mapAllSettledWithConcurrency([1, 2, 3], 3, async (value) => {
      if (value === 2) {
        throw new Error("boom");
      }
      return value;
    });

    expect(results[0]).toEqual({ status: "fulfilled", value: 1 });

    const second = results[1];
    expect(second?.status).toBe("rejected");
    if (second && second.status === "rejected") {
      expect(String(second.reason)).toContain("boom");
    }

    expect(results[2]).toEqual({ status: "fulfilled", value: 3 });
  });
});
