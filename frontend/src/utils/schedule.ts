const MS_PER_DAY = 24 * 60 * 60 * 1000;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function parseIsoDateToEpochDay(value: string | null): number | null {
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

  const ms = Date.UTC(year, month - 1, day);
  if (Number.isNaN(ms)) {
    return null;
  }

  return Math.floor(ms / MS_PER_DAY);
}

export function epochDayToIsoDate(epochDay: number): string {
  const date = new Date(epochDay * MS_PER_DAY);
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth() + 1;
  const day = date.getUTCDate();
  const pad2 = (n: number) => String(n).padStart(2, "0");
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

function nullableEpochDaySortValue(epochDay: number | null): number {
  return epochDay == null ? Number.POSITIVE_INFINITY : epochDay;
}

export function sortTasksForTimeline<
  T extends { start_date: string | null; end_date: string | null; title: string },
>(tasks: T[]): T[] {
  const items = [...tasks];
  items.sort((a, b) => {
    const startDiff =
      nullableEpochDaySortValue(parseIsoDateToEpochDay(a.start_date)) -
      nullableEpochDaySortValue(parseIsoDateToEpochDay(b.start_date));
    if (startDiff !== 0) {
      return startDiff;
    }

    const endDiff =
      nullableEpochDaySortValue(parseIsoDateToEpochDay(a.end_date)) -
      nullableEpochDaySortValue(parseIsoDateToEpochDay(b.end_date));
    if (endDiff !== 0) {
      return endDiff;
    }

    return a.title.localeCompare(b.title);
  });
  return items;
}

export function formatDateRange(startDate: string | null, endDate: string | null): string {
  if (startDate && endDate) {
    return `${startDate} → ${endDate}`;
  }
  if (startDate) {
    return `Starts ${startDate}`;
  }
  if (endDate) {
    return `Ends ${endDate}`;
  }
  return "Unscheduled";
}

export function computeGanttWindow<T extends { start_date: string | null; end_date: string | null }>(
  tasks: T[]
): { windowStart: string | null; windowEnd: string | null; windowDays: number | null } {
  const scheduled = tasks.filter((t) => t.start_date && t.end_date) as Array<{
    start_date: string;
    end_date: string;
  }>;
  if (!scheduled.length) {
    return { windowStart: null, windowEnd: null, windowDays: null };
  }

  let minDay: number | null = null;
  let maxDay: number | null = null;
  for (const task of scheduled) {
    const startDay = parseIsoDateToEpochDay(task.start_date);
    const endDay = parseIsoDateToEpochDay(task.end_date);
    if (startDay == null || endDay == null) {
      continue;
    }

    if (minDay == null || startDay < minDay) {
      minDay = startDay;
    }
    if (maxDay == null || endDay > maxDay) {
      maxDay = endDay;
    }
  }

  if (minDay == null || maxDay == null) {
    return { windowStart: null, windowEnd: null, windowDays: null };
  }

  return {
    windowStart: epochDayToIsoDate(minDay),
    windowEnd: epochDayToIsoDate(maxDay),
    windowDays: Math.max(1, maxDay - minDay + 1),
  };
}

export function computeGanttBar(
  task: { start_date: string; end_date: string },
  windowStart: string,
  windowEnd: string
): { leftPct: number; widthPct: number } {
  const windowStartDay = parseIsoDateToEpochDay(windowStart);
  const windowEndDay = parseIsoDateToEpochDay(windowEnd);
  const startDay = parseIsoDateToEpochDay(task.start_date);
  const endDay = parseIsoDateToEpochDay(task.end_date);

  if (windowStartDay == null || windowEndDay == null || startDay == null || endDay == null) {
    return { leftPct: 0, widthPct: 0 };
  }

  const windowDays = Math.max(1, windowEndDay - windowStartDay + 1);
  const offset = startDay - windowStartDay;
  const durationDays = Math.max(1, endDay - startDay + 1);

  return {
    leftPct: clamp((offset / windowDays) * 100, 0, 100),
    widthPct: clamp((durationDays / windowDays) * 100, 0, 100),
  };
}

