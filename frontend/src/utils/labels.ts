export type VlLabelColor =
  | "blue"
  | "teal"
  | "green"
  | "orange"
  | "purple"
  | "red"
  | "orangered"
  | "grey"
  | "yellow";

export function taskStatusLabelColor(status: string): VlLabelColor {
  const normalized = (status || "").trim().toLowerCase();
  if (normalized === "done") {
    return "green";
  }
  if (normalized === "qa") {
    return "purple";
  }
  if (normalized === "in_progress" || normalized === "in-progress" || normalized === "in progress") {
    return "orange";
  }
  return "blue";
}

export function workItemStatusLabel(status: string): string {
  const normalized = (status || "").trim().toLowerCase();
  if (normalized === "backlog") {
    return "Backlog";
  }
  if (normalized === "in_progress" || normalized === "in-progress" || normalized === "in progress") {
    return "In progress";
  }
  if (normalized === "qa") {
    return "QA";
  }
  if (normalized === "done") {
    return "Done";
  }
  return status;
}

export function sowVersionStatusLabelColor(status: string): VlLabelColor {
  if (status === "signed") {
    return "green";
  }
  if (status === "pending_signature") {
    return "orange";
  }
  if (status === "rejected") {
    return "red";
  }
  return "blue";
}

export function sowSignerStatusLabelColor(status: string): VlLabelColor {
  if (status === "approved") {
    return "green";
  }
  if (status === "rejected") {
    return "red";
  }
  if (status === "pending") {
    return "orange";
  }
  return "blue";
}

export function sowPdfStatusLabelColor(status: string): VlLabelColor {
  if (status === "success") {
    return "green";
  }
  if (status === "failed") {
    return "red";
  }
  if (status === "running") {
    return "orange";
  }
  return "blue";
}

export function deliveryStatusLabelColor(status: string): VlLabelColor {
  if (status === "success") {
    return "green";
  }
  if (status === "failure") {
    return "red";
  }
  if (status === "queued") {
    return "orange";
  }
  return "blue";
}

export function renderStatusLabelColor(status: string): VlLabelColor {
  const normalized = status.trim().toLowerCase();
  if (normalized === "success") {
    return "green";
  }
  if (normalized === "failed" || normalized === "error") {
    return "red";
  }
  if (normalized === "running" || normalized === "queued" || normalized === "pending") {
    return "orange";
  }
  return "blue";
}
