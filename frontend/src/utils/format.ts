export function formatTimestamp(value?: string | null): string {
  if (!value) {
    return "—";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

export function formatPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }

  return `${Math.round(value * 100)}%`;
}

export function progressLabelColor(
  value?: number | null
): "blue" | "teal" | "green" | "success" | null {
  if (value == null || Number.isNaN(value)) {
    return null;
  }

  const normalized = Math.max(0, Math.min(1, value));
  if (normalized >= 1) {
    return "success";
  }
  if (normalized >= 0.75) {
    return "green";
  }
  if (normalized >= 0.35) {
    return "teal";
  }
  return "blue";
}
