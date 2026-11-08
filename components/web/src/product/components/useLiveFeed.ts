import { useEffect, useRef, useState } from 'react';
import { useProductApi } from '../../api/product/context';
import type { FeedItem } from '../../api/product';

/**
 * Polls `GET /dashboard/feed?since=<cursor>` every `intervalMs` and accumulates
 * items newest-first. New items are flagged `isNew` on the first render after
 * arrival so the UI can animate them sliding in.
 */
export function useLiveFeed(intervalMs = 5000, max = 40) {
  const api = useProductApi();
  const [items, setItems] = useState<FeedItem[]>([]);
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  const cursorRef = useRef<string | undefined>(undefined);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const res = await api.getFeed(cursorRef.current);
        if (!active) return;
        cursorRef.current = res.cursor ?? cursorRef.current;
        const fresh = res.items.filter((i) => !seen.current.has(i.id));
        if (fresh.length) {
          fresh.forEach((i) => seen.current.add(i.id));
          setItems((prev) => [...fresh.reverse(), ...prev].slice(0, max));
          setNewIds(new Set(fresh.map((i) => i.id)));
        }
      } catch {
        /* keep the last good feed; try again next tick */
      } finally {
        if (active) timer = setTimeout(poll, intervalMs);
      }
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [api, intervalMs, max]);

  return { items, newIds };
}
