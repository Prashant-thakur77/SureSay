import { createContext, useContext } from "react";

/** The id of the item the single-switch scan has highlighted, or null. */
export const ScanContext = createContext<string | null>(null);

/** Props that mark an element as the scan target, so CSS can draw the highlight. */
export function useScanMark(id: string): { "data-scan"?: "on" } {
  const current = useContext(ScanContext);
  return current === id ? { "data-scan": "on" } : {};
}
