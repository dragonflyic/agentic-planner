"use client";

import { useEffect, useState } from "react";
import { api, AttemptWithSignal, PaginatedResponse } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-yellow-100 text-yellow-700",
  success: "bg-green-100 text-green-700",
  needs_human: "bg-orange-100 text-orange-700",
  failed: "bg-red-100 text-red-700",
  noop: "bg-gray-100 text-gray-500",
};

export default function AttemptsPage() {
  const [attempts, setAttempts] = useState<PaginatedResponse<AttemptWithSignal> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    async function fetchAttempts() {
      setLoading(true);
      try {
        const data = await api.listAttempts({
          status: statusFilter || undefined,
          page,
          page_size: 20,
        });
        setAttempts(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch attempts");
      } finally {
        setLoading(false);
      }
    }
    fetchAttempts();
  }, [statusFilter, page]);

  function formatDuration(ms: number | null): string {
    if (ms === null) return "-";
    if (ms < 1000) return `${ms}ms`;
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  }

  if (loading && !attempts) {
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
          Attempts
        </h1>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="running">Running</option>
          <option value="success">Success</option>
          <option value="needs_human">Needs Human</option>
          <option value="failed">Failed</option>
          <option value="noop">No-op</option>
        </select>
      </div>

      {/* Attempts Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-700">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                Signal
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                Attempt #
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                Duration
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                PR
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {attempts?.items.map((attempt) => (
              <tr key={attempt.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                <td className="px-6 py-4">
                  <div>
                    <a
                      href={`/attempts/${attempt.id}`}
                      className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                    >
                      {attempt.signal.title}
                    </a>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {attempt.signal.repo}#{attempt.signal.issue_number}
                    </p>
                  </div>
                </td>
                <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                  #{attempt.attempt_number}
                </td>
                <td className="px-6 py-4">
                  <span
                    className={`px-2 py-1 text-xs font-medium rounded-full ${
                      STATUS_COLORS[attempt.status] || STATUS_COLORS.pending
                    }`}
                  >
                    {attempt.status}
                  </span>
                </td>
                <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                  {formatDuration(attempt.duration_ms)}
                </td>
                <td className="px-6 py-4">
                  {attempt.pr_url ? (
                    <a
                      href={attempt.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-green-600 dark:text-green-400 hover:underline"
                    >
                      View PR
                    </a>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </td>
              </tr>
            ))}
            {attempts?.items.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-8 text-center text-gray-500 dark:text-gray-400"
                >
                  No attempts found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {attempts && attempts.total_pages > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!attempts.has_prev}
            className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          >
            Previous
          </button>
          <span className="px-3 py-1 text-gray-600 dark:text-gray-300">
            Page {attempts.page} of {attempts.total_pages}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!attempts.has_next}
            className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
