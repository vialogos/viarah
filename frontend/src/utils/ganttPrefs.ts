import type { GanttTimeScale } from "./gantt";

export type GanttRouteScope = "internal" | "client";

export interface GanttPrefsV1 {
  version: 1;
  timeScale: GanttTimeScale;
  collapsedByStableId: Record<string, boolean>;
}

const STORAGE_PREFIX = "viarah.gantt_prefs.v1.";

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function buildGanttPrefsStorageKey(options: {
  userId: string | null | undefined;
  orgId: string | null | undefined;
  projectId: string | null | undefined;
  scope: GanttRouteScope;
}): string {
  const userId = options.userId?.trim() || "anon";
  const orgId = options.orgId?.trim() || "none";
  const projectId = options.projectId?.trim() || "none";
  return `${STORAGE_PREFIX}${options.scope}.${userId}.${orgId}.${projectId}`;
}

/**
 * Defaults are chosen to match existing "schedule" semantics:
 * - `week` scale provides a stable overview for most projects.
 * - `collapsedByStableId` empty means "use sensible per-node defaults" at render time.
 */
export function defaultGanttPrefs(): GanttPrefsV1 {
  return { version: 1, timeScale: "week", collapsedByStableId: {} };
}

/**
 * Read persisted gantt preferences from localStorage.
 * Returns defaults when storage is unavailable or payload is invalid.
 */
export function readGanttPrefs(options: {
  userId: string | null | undefined;
  orgId: string | null | undefined;
  projectId: string | null | undefined;
  scope: GanttRouteScope;
}): GanttPrefsV1 {
  if (!canUseLocalStorage()) {
    return defaultGanttPrefs();
  }

  const key = buildGanttPrefsStorageKey(options);
  const raw = window.localStorage.getItem(key) ?? "";
  if (!raw) {
    return defaultGanttPrefs();
  }

  try {
    const parsed = JSON.parse(raw) as Partial<GanttPrefsV1>;
    if (parsed.version !== 1) {
      return defaultGanttPrefs();
    }

    const timeScale: GanttTimeScale =
      parsed.timeScale === "day" || parsed.timeScale === "week" || parsed.timeScale === "month"
        ? parsed.timeScale
        : "week";
    const collapsedByStableId =
      parsed.collapsedByStableId && typeof parsed.collapsedByStableId === "object"
        ? (parsed.collapsedByStableId as Record<string, boolean>)
        : {};
    return { version: 1, timeScale, collapsedByStableId };
  } catch {
    return defaultGanttPrefs();
  }
}

/**
 * Persist gantt preferences to localStorage.
 * This should be invoked only for view-only settings (never secrets).
 */
export function writeGanttPrefs(
  options: {
    userId: string | null | undefined;
    orgId: string | null | undefined;
    projectId: string | null | undefined;
    scope: GanttRouteScope;
  },
  prefs: GanttPrefsV1
) {
  if (!canUseLocalStorage()) {
    return;
  }

  const key = buildGanttPrefsStorageKey(options);
  window.localStorage.setItem(key, JSON.stringify(prefs));
}
