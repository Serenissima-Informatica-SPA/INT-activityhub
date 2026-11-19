import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

function serialize<T>(value: T): string {
  return JSON.stringify(value, function (key, current) {
    const original = (this as Record<string, unknown> | undefined)?.[key];
    return original instanceof Date ? { $activityHubDate: original.toISOString() } : current;
  }) ?? "null";
}

function deserialize<T>(value: string): T {
  return JSON.parse(value, (_key, current) => {
    if (current && typeof current === "object" && typeof current.$activityHubDate === "string") {
      return new Date(current.$activityHubDate);
    }
    return current;
  }) as T;
}

export function useSessionState<T>(
  key: string,
  initialValue: T | (() => T),
): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key) ?? sessionStorage.getItem(key);
      if (stored !== null) return deserialize<T>(stored);
    } catch { /* Fall back to the default if storage is unavailable or invalid */ }
    return typeof initialValue === "function" ? (initialValue as () => T)() : initialValue;
  });

  useEffect(() => {
    try { localStorage.setItem(key, serialize(value)); }
    catch { /* Keep the page usable if storage is unavailable */ }
  }, [key, value]);

  return [value, setValue];
}

