export type VlLabelColor = "blue" | "red" | "orange" | "yellow" | "green" | "teal" | "purple";

export function taskStatusLabelColor(status: string): VlLabelColor {
  if (status === "done") {
    return "green";
  }
  if (status === "qa") {
    return "purple";
  }
  if (status === "in_progress") {
    return "orange";
  }
  return "blue";
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

