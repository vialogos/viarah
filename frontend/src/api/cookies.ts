export function getCookieValue(name: string, cookieString?: string): string | null {
  const raw =
    cookieString ?? (typeof document !== "undefined" ? String(document.cookie || "") : "");
  if (!raw.trim()) {
    return null;
  }

  const prefix = `${name}=`;
  for (const part of raw.split(";")) {
    const trimmed = part.trim();
    if (!trimmed.startsWith(prefix)) {
      continue;
    }
    const value = trimmed.slice(prefix.length);
    return value ? decodeURIComponent(value) : null;
  }

  return null;
}
