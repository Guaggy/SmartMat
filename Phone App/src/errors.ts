import { ApiError } from "./api";
import type { StringKey } from "./strings";

/** Text key for a failed alert action (PIN or network problems) */
export function alertErrorKey(error: unknown): StringKey {
  if (error instanceof ApiError) {
    if (error.status === 403) return "errWrongPin";
    if (error.status === 401) return "errPinRequired";
    if (error.status === 429) return "errLocked";
    if (error.status === 409 || error.status === 404) return "errNotOpen"; // already handled, cleared or unknown
  }
  return "netErr";
}

/** Text key for a failed connection test. `address` is the normalised URL that was tried. */
export function connectionErrorKey(error: unknown, address: string): StringKey {
  if (error instanceof ApiError) {
    if (error.kind === "timeout") return "errTimeout";
    if (error.kind === "network") return address.startsWith("https://") ? "errNetworkHttps" : "errNetwork";
    if (error.kind === "notSmartMat" || error.status === 404) return "errNotSmartMat";
    return "errHttp";
  }
  return "errNetwork";
}
