"use client";

import { WorkingSetProvider } from "@/contexts/WorkingSetContext";
import { ReactNode } from "react";

export function ClientProviders({ children }: { children: ReactNode }) {
  return <WorkingSetProvider>{children}</WorkingSetProvider>;
}
