"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";

interface WorkingSetContextType {
  workingSet: Set<string>;
  addToWorkingSet: (id: string) => void;
  removeFromWorkingSet: (id: string) => void;
  toggleWorkingSet: (id: string) => void;
  clearWorkingSet: () => void;
  isInWorkingSet: (id: string) => boolean;
}

const WorkingSetContext = createContext<WorkingSetContextType | null>(null);

const STORAGE_KEY = "workbench-working-set";

export function WorkingSetProvider({ children }: { children: ReactNode }) {
  const [workingSet, setWorkingSet] = useState<Set<string>>(new Set());
  const [initialized, setInitialized] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const ids = JSON.parse(stored) as string[];
        setWorkingSet(new Set(ids));
      }
    } catch (e) {
      console.error("Failed to load working set from localStorage:", e);
    }
    setInitialized(true);
  }, []);

  // Persist to localStorage on change
  useEffect(() => {
    if (initialized) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...workingSet]));
      } catch (e) {
        console.error("Failed to save working set to localStorage:", e);
      }
    }
  }, [workingSet, initialized]);

  const addToWorkingSet = (id: string) => {
    setWorkingSet((prev) => new Set([...prev, id]));
  };

  const removeFromWorkingSet = (id: string) => {
    setWorkingSet((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const toggleWorkingSet = (id: string) => {
    setWorkingSet((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const clearWorkingSet = () => {
    setWorkingSet(new Set());
  };

  const isInWorkingSet = (id: string) => workingSet.has(id);

  return (
    <WorkingSetContext.Provider
      value={{
        workingSet,
        addToWorkingSet,
        removeFromWorkingSet,
        toggleWorkingSet,
        clearWorkingSet,
        isInWorkingSet,
      }}
    >
      {children}
    </WorkingSetContext.Provider>
  );
}

export function useWorkingSet() {
  const context = useContext(WorkingSetContext);
  if (!context) {
    throw new Error("useWorkingSet must be used within a WorkingSetProvider");
  }
  return context;
}
