import { useCallback, useRef } from 'react';
import { newOperationKey } from '../../api';

/**
 * WEB-005: a retry of the *same* command reuses its operation key, so the
 * server can deduplicate it. Changing the payload starts a new command.
 */
export function useOperationKey() {
  const ref = useRef<{ key: string; payload: string } | null>(null);
  const keyFor = useCallback((payload: unknown) => {
    const json = JSON.stringify(payload);
    if (!ref.current || ref.current.payload !== json) {
      ref.current = { key: newOperationKey(), payload: json };
    }
    return ref.current.key;
  }, []);
  const reset = useCallback(() => {
    ref.current = null;
  }, []);
  return { keyFor, reset };
}
