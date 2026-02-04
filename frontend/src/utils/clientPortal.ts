const CLIENT_LAST_SEEN_PREFIX = "viarah.client_last_seen.";

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function readClientLastSeenAt(projectId: string): string {
  if (!canUseLocalStorage() || !projectId) {
    return "";
  }
  return window.localStorage.getItem(`${CLIENT_LAST_SEEN_PREFIX}${projectId}`) ?? "";
}

export function writeClientLastSeenAt(projectId: string, value: string) {
  if (!canUseLocalStorage() || !projectId) {
    return;
  }
  const key = `${CLIENT_LAST_SEEN_PREFIX}${projectId}`;
  if (!value) {
    window.localStorage.removeItem(key);
  } else {
    window.localStorage.setItem(key, value);
  }
}

