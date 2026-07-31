import { createContext } from "react";

import type { PlatformAdapter } from "./PlatformAdapter";

export const PlatformContext = createContext<PlatformAdapter | null>(null);
