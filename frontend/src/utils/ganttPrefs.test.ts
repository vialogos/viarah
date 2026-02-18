import { beforeEach, describe, expect, it } from "vitest";

import { buildGanttPrefsStorageKey, defaultGanttPrefs, readGanttPrefs, writeGanttPrefs } from "./ganttPrefs";

function installLocalStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial));
  const localStorage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
  };

  (globalThis as any).window = { localStorage };
}

describe("ganttPrefs utils", () => {
  beforeEach(() => {
    installLocalStorage();
  });

  it("builds a stable storage key", () => {
    const key = buildGanttPrefsStorageKey({
      userId: "u1",
      orgId: "o1",
      projectId: "p1",
      scope: "internal",
    });
    expect(key).toBe("viarah.gantt_prefs.v1.internal.u1.o1.p1");
  });

  it("round-trips preferences via localStorage", () => {
    const options = { userId: "u1", orgId: "o1", projectId: "p1", scope: "internal" as const };
    writeGanttPrefs(options, { version: 1, timeScale: "month", collapsedByStableId: { "task:1": true } });
    const read = readGanttPrefs(options);
    expect(read.timeScale).toBe("month");
    expect(read.collapsedByStableId["task:1"]).toBe(true);
  });

  it("returns defaults for invalid payloads", () => {
    const key = buildGanttPrefsStorageKey({
      userId: "u1",
      orgId: "o1",
      projectId: "p1",
      scope: "internal",
    });
    installLocalStorage({ [key]: "{not valid json" });

    const prefs = readGanttPrefs({ userId: "u1", orgId: "o1", projectId: "p1", scope: "internal" });
    expect(prefs).toEqual(defaultGanttPrefs());
  });
});

