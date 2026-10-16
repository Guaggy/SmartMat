import { useEffect, useState } from "react";

import type { Api } from "./api";
import { HEATMAP_STOPS, type Stops } from "./heatmap";

/** Colour ramp from the server's /api/theme, falling back to the built-in copy */
export function useStops(api: Api | null): Stops {
  const [stops, setStops] = useState<Stops>(HEATMAP_STOPS);
  useEffect(() => {
    if (!api) return;
    api.theme().then((theme) => { if (theme.heatmap_stops?.length >= 2) setStops(theme.heatmap_stops); }).catch(() => undefined);
  }, [api]);
  return stops;
}
