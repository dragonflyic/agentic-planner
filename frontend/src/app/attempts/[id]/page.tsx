"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, AttemptWithSignal } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-yellow-100 text-yellow-700",
  success: "bg-green-100 text-green-700",
  needs_human: "bg-orange-100 text-orange-700",
  failed: "bg-red-100 text-red-700",
  noop: "bg-gray-100 text-gray-500",
};

export default function AttemptDetailPage() {
  const params = useParams();
  const attemptId = params.id as string;

  const [attempt, setAttempt] = useState<AttemptWithSignal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        const data = await api.getAttempt(attemptId);
        setAttempt(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch attempt");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [attemptId]);

  function formatDuration(ms: number | null): string {
    if (ms === null) return "-";
    if (ms < 1000) return `${ms}ms`;
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  if (error || !attempt) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-red-700 dark:text-red-400">
          Error: {error || "Attempt not found"}
        </p>
      </div>
    );
  }

  const summary = attempt.summary_json as {
    status?: string;
    what_changed?: string[];
    assumptions?: string[];
    risk_flags?: string[];
    metrics?: {
      tool_calls?: number;
      turns?: number;
      cost_usd?: number;
    };
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Attempt #{attempt.attempt_number}
          </h1>
          <span
            className={`px-2 py-1 text-xs font-medium rounded-full ${
              STATUS_COLORS[attempt.status] || STATUS_COLORS.pending
            }`}
          >
            {attempt.status}
          </span>
        </div>
        <p className="text-gray-500 dark:text-gray-400">
          Signal:{" "}
          <a
            href={`/signals/${attempt.signal.id}`}
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            {attempt.signal.title}
          </a>
        </p>
      </div>

      {/* Overview Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">Duration</p>
          <p className="text-xl font-semibold text-gray-900 dark:text-white">
            {formatDuration(attempt.duration_ms)}
          </p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">Tool Calls</p>
          <p className="text-xl font-semibold text-gray-900 dark:text-white">
            {summary.metrics?.tool_calls ?? "-"}
          </p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">Turns</p>
          <p className="text-xl font-semibold text-gray-900 dark:text-white">
            {summary.metrics?.turns ?? "-"}
          </p>
        </div>
      </div>

      {/* PR Link */}
      {attempt.pr_url && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4 mb-6">
          <p className="text-green-700 dark:text-green-400 font-medium">
            Pull Request Created
          </p>
          <a
            href={attempt.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-600 dark:text-green-400 hover:underline"
          >
            {attempt.pr_url}
          </a>
        </div>
      )}

      {/* Error Message */}
      {attempt.error_message && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
          <p className="text-red-700 dark:text-red-400 font-medium">Error</p>
          <pre className="text-sm text-red-600 dark:text-red-400 mt-2 whitespace-pre-wrap">
            {attempt.error_message}
          </pre>
        </div>
      )}

      {/* What Changed */}
      {summary.what_changed && summary.what_changed.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            Files Changed ({summary.what_changed.length})
          </h2>
          <ul className="space-y-1">
            {summary.what_changed.map((file, i) => (
              <li
                key={i}
                className="text-sm text-gray-600 dark:text-gray-300 font-mono"
              >
                {file}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Risk Flags */}
      {summary.risk_flags && summary.risk_flags.length > 0 && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4 mb-6">
          <p className="text-yellow-700 dark:text-yellow-400 font-medium mb-2">
            Risk Flags
          </p>
          <div className="flex flex-wrap gap-2">
            {summary.risk_flags.map((flag, i) => (
              <span
                key={i}
                className="px-2 py-1 bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-300 text-xs rounded"
              >
                {flag}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Assumptions */}
      {summary.assumptions && summary.assumptions.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            Assumptions Made
          </h2>
          <ul className="space-y-2">
            {summary.assumptions.map((assumption, i) => (
              <li
                key={i}
                className="text-sm text-gray-600 dark:text-gray-300"
              >
                • {assumption}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
