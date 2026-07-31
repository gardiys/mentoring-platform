import { useContext } from "react";

import type { PlatformAdapter } from "./PlatformAdapter";
import { PlatformContext } from "./platformContext";

export function usePlatform(): PlatformAdapter {
  const adapter = useContext(PlatformContext);
  if (!adapter) throw new Error("PlatformProvider is missing");
  return adapter;
}
