import { useCallback, useEffect, useRef } from "react";

import type { Api } from "./api";

/** Returns now() in unix seconds corrected for the difference between the phone's and the server's clock,
 *  so alert ages are right even when the phone clock is off. Re-synced every minute from /api/health. */
export function useServerNow(api: Api | null): () => number {
  const skew = useRef(0);
  useEffect(() => {
    if (!api) return;
    let alive = true;
    const sync = () =>
      api.health().then((health) => { if (alive) skew.current = health.time - Date.now() / 1000; }).catch(() => undefined);
    sync();
    const timer = setInterval(sync, 60000);
    return () => { alive = false; clearInterval(timer); };
  }, [api]);
  return useCallback(() => Date.now() / 1000 + skew.current, []);
}
