"use client";

import { useEffect, useState } from "react";
import { api, PaginatedResponse, SignalWithStatus } from "@/lib/api";

const STATE_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  queued: "bg-blue-100 text-blue-700",
  in_progress: "bg-yellow-100 text-yellow-700",
  completed: "bg-green-100 text-green-700",
  blocked: "bg-red-100 text-red-700",
  skipped: "bg-gray-100 text-gray-500",
  archived: "bg-gray-100 text-gray-400",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-yellow-100 text-yellow-700",
  success: "bg-green-100 text-green-700",
  needs_human: "bg-orange-100 text-orange-700",
  failed: "bg-red-100 text-red-700",
  noop: "bg-gray-100 text-gray-500",
};

export default function SignalsPage() {
  const [signals, setSignals] = useState<PaginatedResponse<SignalWithStatus> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stateFilter, setStateFilter] = useState<string>("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    async function fetchSignals() {
      setLoading(true);
      try {
        const data = await api.listSignals({
          state: stateFilter || undefined,
          page,
          page_size: 20,
        });
        setSignals(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch signals");
      } finally {
        setLoading(false);
      }
    }
    fetchSignals();
  }, [stateFilter, page]);

  async function handleRunAttempt(signalId: string) {
    try {
      await api.createAttempt(signalId);
      // Refresh the list
      const data = await api.listSignals({ state: stateFilter || undefined, page });
      setSignals(data);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create attempt");
    }
  }

  if (loading && !signals) {
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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Signals
        </h1>
        <select
          value={stateFilter}
          onChange={(e) => {
            setStateFilter(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
        >
          <option value="">All States</option>
          <option value="pending">Pending</option>
          <option value="queued">Queued</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
          <option value="blocked">Blocked</option>
        </select>
      </div>

      {/* Signals Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-700">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                Signal
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                State
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
            {signals?.items.map((signal) => (
              <tr key={signal.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
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
                  <span
                    className={`px-2 py-1 text-xs font-medium rounded-full ${
                      STATE_COLORS[signal.state] || STATE_COLORS.pending
                    }`}
                  >
                    {signal.state}
                  </span>
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
                  <button
                    onClick={() => handleRunAttempt(signal.id)}
                    disabled={signal.state === "in_progress"}
                    className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Run Attempt
                  </button>
                </td>
              </tr>
            ))}
            {signals?.items.length === 0 && (
              <tr>
                <td
                  colSpan={4}
                  className="px-6 py-8 text-center text-gray-500 dark:text-gray-400"
                >
                  No signals found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {signals && signals.total_pages > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!signals.has_prev}
            className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          >
            Previous
          </button>
          <span className="px-3 py-1 text-gray-600 dark:text-gray-300">
            Page {signals.page} of {signals.total_pages}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!signals.has_next}
            className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
