"use client";

import { useEffect, useState } from "react";
import { api, PaginatedResponse, SignalWithStatus } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-yellow-100 text-yellow-700",
  success: "bg-green-100 text-green-700",
  needs_human: "bg-orange-100 text-orange-700",
  failed: "bg-red-100 text-red-700",
  noop: "bg-gray-100 text-gray-500",
};

const DEFAULT_PAGE_SIZE = 10;
const EXPANDED_PAGE_SIZE = 50;

export default function SignalsPage() {
  const [signals, setSignals] = useState<PaginatedResponse<SignalWithStatus> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState(false);

  const pageSize = expanded ? EXPANDED_PAGE_SIZE : DEFAULT_PAGE_SIZE;

  useEffect(() => {
    async function fetchSignals() {
      setLoading(true);
      try {
        const data = await api.listSignals({
          page,
          page_size: pageSize,
          sort_by: "priority",
          sort_order: "desc",
        });
        setSignals(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch signals");
      } finally {
        setLoading(false);
      }
    }
    fetchSignals();
  }, [page, pageSize]);

  async function handleRunAttempt(signalId: string) {
    try {
      await api.createAttempt(signalId);
      // Refresh the list
      const data = await api.listSignals({
        page,
        page_size: pageSize,
        sort_by: "priority",
        sort_order: "desc",
      });
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
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Signals
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Showing top {signals?.items.length || 0} of {signals?.total || 0} signals by priority
          </p>
        </div>
      </div>

      {/* Signals Table */}
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
            {signals?.items.map((signal, index) => (
              <tr key={signal.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-bold text-gray-400 dark:text-gray-500 w-6">
                      {(page - 1) * pageSize + index + 1}
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
                  <button
                    onClick={() => handleRunAttempt(signal.id)}
                    disabled={signal.latest_attempt_status === "running" || signal.latest_attempt_status === "pending"}
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

      {/* Expand/Collapse and Pagination */}
      <div className="flex justify-center gap-4 mt-4">
        {!expanded && signals && signals.total > DEFAULT_PAGE_SIZE && (
          <button
            onClick={() => {
              setExpanded(true);
              setPage(1);
            }}
            className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition"
          >
            Show more ({signals.total - DEFAULT_PAGE_SIZE} more signals)
          </button>
        )}
        {expanded && (
          <button
            onClick={() => {
              setExpanded(false);
              setPage(1);
            }}
            className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition"
          >
            Show top 10 only
          </button>
        )}
      </div>

      {/* Pagination (only when expanded) */}
      {expanded && signals && signals.total_pages > 1 && (
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
