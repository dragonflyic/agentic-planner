"use client";

import { useEffect, useState } from "react";
import { api, SignalWithStatus } from "@/lib/api";
import { useWorkingSet } from "@/contexts/WorkingSetContext";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-yellow-100 text-yellow-700",
  success: "bg-green-100 text-green-700",
  needs_human: "bg-orange-100 text-orange-700",
  failed: "bg-red-100 text-red-700",
  noop: "bg-gray-100 text-gray-500",
};

export default function WorkingSetPage() {
  const { workingSet, removeFromWorkingSet, clearWorkingSet } = useWorkingSet();
  const [signals, setSignals] = useState<SignalWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchWorkingSetSignals() {
      if (workingSet.size === 0) {
        setSignals([]);
        setLoading(false);
        return;
      }

      setLoading(true);
      try {
        // Fetch only the signals that are in the working set
        const ids = Array.from(workingSet);
        const data = await api.listSignals({ ids, page_size: ids.length, sort_by: "priority", sort_order: "desc" });
        setSignals(data.items);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message || "Failed to fetch signals");
      } finally {
        setLoading(false);
      }
    }
    fetchWorkingSetSignals();
  }, [workingSet]);

  async function handleRunAttempt(signalId: string) {
    try {
      await api.createAttempt(signalId);
      // Refresh the list
      const ids = Array.from(workingSet);
      const data = await api.listSignals({ ids, page_size: ids.length, sort_by: "priority", sort_order: "desc" });
      setSignals(data.items);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create attempt");
    }
  }

  if (loading && signals.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-red-700 dark:text-red-400">Error: {error}</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Working Set
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {signals.length} signal{signals.length !== 1 ? "s" : ""} in your working set
          </p>
        </div>
        {signals.length > 0 && (
          <button
            onClick={clearWorkingSet}
            className="px-3 py-1 text-sm text-red-600 hover:text-red-700 border border-red-300 rounded hover:bg-red-50 dark:text-red-400 dark:border-red-600 dark:hover:bg-red-900/20"
          >
            Clear All
          </button>
        )}
      </div>

      {/* Empty state */}
      {signals.length === 0 && !loading && (
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-8 text-center">
          <p className="text-gray-500 dark:text-gray-400">
            Your working set is empty. Add signals from the{" "}
            <a href="/signals" className="text-blue-600 hover:underline">
              Signals page
            </a>.
          </p>
        </div>
      )}

      {/* Signals Table */}
      {signals.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                  Priority
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                  Signal
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                  Latest Attempt
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {signals.map((signal, index) => (
                <tr key={signal.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-bold text-gray-400 dark:text-gray-500 w-6">
                        {index + 1}
                      </span>
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded ${
                          signal.priority >= 100
                            ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                            : signal.priority >= 0
                            ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                            : "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400"
                        }`}
                      >
                        {signal.priority}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div>
                      <a
                        href={`/signals/${signal.id}`}
                        className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                      >
                        {signal.title}
                      </a>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        {signal.repo}#{signal.issue_number}
                      </p>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    {signal.latest_attempt_status ? (
                      <div>
                        <span
                          className={`px-2 py-1 text-xs font-medium rounded-full ${
                            STATUS_COLORS[signal.latest_attempt_status] ||
                            STATUS_COLORS.pending
                          }`}
                        >
                          {signal.latest_attempt_status}
                        </span>
                        {signal.pending_clarifications > 0 && (
                          <span className="ml-2 text-orange-600 dark:text-orange-400 text-xs">
                            ({signal.pending_clarifications} questions)
                          </span>
                        )}
                        {signal.latest_pr_url && (
                          <a
                            href={signal.latest_pr_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ml-2 text-green-600 dark:text-green-400 text-xs hover:underline"
                          >
                            View PR
                          </a>
                        )}
                      </div>
                    ) : (
                      <span className="text-gray-400 text-sm">No attempts yet</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleRunAttempt(signal.id)}
                        disabled={signal.latest_attempt_status === "running" || signal.latest_attempt_status === "pending"}
                        className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Run Attempt
                      </button>
                      <button
                        onClick={() => removeFromWorkingSet(signal.id)}
                        className="px-3 py-1 text-sm text-gray-600 hover:text-gray-800 border border-gray-300 rounded hover:bg-gray-50 dark:text-gray-400 dark:border-gray-600 dark:hover:bg-gray-700"
                      >
                        Remove
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
