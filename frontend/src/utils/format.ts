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

export function progressLabelColor(value?: number | null): "blue" | "orange" | "green" {
  if (value == null || Number.isNaN(value)) {
    return "blue";
  }
  if (value >= 1) {
    return "green";
  }
  if (value >= 0.5) {
    return "orange";
  }
  return "blue";
}
