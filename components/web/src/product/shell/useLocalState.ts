import { useCallback, useState } from 'react';

/** Persist a small boolean/string in localStorage, wrapped in try/catch. */
export function useLocalState<T extends string | boolean>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return initial;
      if (typeof initial === 'boolean') return (raw === 'true') as T;
      return raw as T;
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (next: T) => {
      setValue(next);
      try {
        localStorage.setItem(key, String(next));
      } catch {
        /* ignore */
      }
    },
    [key],
  );
  return [value, set] as const;
}
