"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, SignalWithStatus, Attempt } from "@/lib/api";

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

export default function SignalDetailPage() {
  const params = useParams();
  const signalId = params.id as string;

  const [signal, setSignal] = useState<SignalWithStatus | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        const signalData = await api.getSignal(signalId);
        setSignal(signalData);

        const attemptsData = await api.listAttempts({ signal_id: signalId });
        setAttempts(attemptsData.items.map((a) => a as unknown as Attempt));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch signal");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [signalId]);

  async function handleRunAttempt() {
    try {
      await api.createAttempt(signalId);
      // Refresh data
      const signalData = await api.getSignal(signalId);
      setSignal(signalData);
      const attemptsData = await api.listAttempts({ signal_id: signalId });
      setAttempts(attemptsData.items.map((a) => a as unknown as Attempt));
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create attempt");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  if (error || !signal) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-red-700 dark:text-red-400">
          Error: {error || "Signal not found"}
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {signal.title}
          </h1>
          <span
            className={`px-2 py-1 text-xs font-medium rounded-full ${
              STATE_COLORS[signal.state] || STATE_COLORS.pending
            }`}
          >
            {signal.state}
          </span>
        </div>
        <p className="text-gray-500 dark:text-gray-400">
          <a
            href={`https://github.com/${signal.repo}/issues/${signal.issue_number}`}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            {signal.repo}#{signal.issue_number}
          </a>
        </p>
      </div>

      {/* Actions */}
      <div className="mb-6">
        <button
          onClick={handleRunAttempt}
          disabled={signal.state === "in_progress"}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Run New Attempt
        </button>
      </div>

      {/* Description */}
      {signal.body && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            Description
          </h2>
          <div className="prose dark:prose-invert max-w-none">
            <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">
              {signal.body}
            </pre>
          </div>
        </div>
      )}

      {/* Attempts History */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Attempt History ({attempts.length})
        </h2>
        {attempts.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400">
            No attempts yet. Click "Run New Attempt" to start.
          </p>
        ) : (
          <div className="space-y-3">
            {attempts.map((attempt) => (
              <div
                key={attempt.id}
                className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <span className="text-gray-600 dark:text-gray-300 font-medium">
                    #{attempt.attempt_number}
                  </span>
                  <span
                    className={`px-2 py-1 text-xs font-medium rounded-full ${
                      STATUS_COLORS[attempt.status] || STATUS_COLORS.pending
                    }`}
                  >
                    {attempt.status}
                  </span>
                  {attempt.started_at && (
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      {new Date(attempt.started_at).toLocaleString()}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {attempt.pr_url && (
                    <a
                      href={attempt.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-green-600 dark:text-green-400 text-sm hover:underline"
                    >
                      View PR
                    </a>
                  )}
                  <a
                    href={`/attempts/${attempt.id}`}
                    className="text-blue-600 dark:text-blue-400 text-sm hover:underline"
                  >
                    Details
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
