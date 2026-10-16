import { ApiError } from "./api";
import type { StringKey } from "./strings";

/** Text key for a failed alert action (PIN or network problems) */
export function alertErrorKey(error: unknown): StringKey {
  if (error instanceof ApiError) {
    if (error.status === 403) return "errWrongPin";
    if (error.status === 401) return "errPinRequired";
    if (error.status === 429) return "errLocked";
    if (error.status === 404) return "errNotOpen";
  }
  return "netErr";
}
