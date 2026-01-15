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

      {/* Priority & Context */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Priority & Context
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
            <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">Priority</div>
            <div className={`text-2xl font-bold ${
              signal.priority >= 100 ? "text-green-600" :
              signal.priority >= 0 ? "text-blue-600" : "text-gray-500"
            }`}>
              {signal.priority}
            </div>
          </div>
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
            <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">Context Score</div>
            <div className="text-2xl font-bold text-purple-600">
              {(signal.metadata_json as any)?.context?.context_score || 0}
            </div>
          </div>
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
            <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">Comments</div>
            <div className="text-2xl font-bold text-gray-700 dark:text-gray-300">
              {(signal.metadata_json as any)?.context?.comment_count || 0}
            </div>
          </div>
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
            <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">References</div>
            <div className="text-2xl font-bold text-gray-700 dark:text-gray-300">
              {(signal.metadata_json as any)?.context?.reference_count || 0}
            </div>
          </div>
        </div>

        {/* PR Activity */}
        {((signal.metadata_json as any)?.context?.open_pr_count > 0 ||
          (signal.metadata_json as any)?.context?.merged_pr_count > 0 ||
          (signal.metadata_json as any)?.context?.closed_pr_count > 0) && (
          <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
            <h3 className="text-sm font-medium text-amber-700 dark:text-amber-300 mb-2">PR Activity (may indicate work in progress)</h3>
            <div className="flex gap-4 text-sm">
              {(signal.metadata_json as any)?.context?.open_pr_count > 0 && (
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                  <span className="text-gray-700 dark:text-gray-300">
                    {(signal.metadata_json as any).context.open_pr_count} Open PR(s)
                  </span>
                </div>
              )}
              {(signal.metadata_json as any)?.context?.merged_pr_count > 0 && (
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-purple-500 rounded-full"></span>
                  <span className="text-gray-700 dark:text-gray-300">
                    {(signal.metadata_json as any).context.merged_pr_count} Merged PR(s)
                  </span>
                </div>
              )}
              {(signal.metadata_json as any)?.context?.closed_pr_count > 0 && (
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-red-500 rounded-full"></span>
                  <span className="text-gray-700 dark:text-gray-300">
                    {(signal.metadata_json as any).context.closed_pr_count} Closed PR(s)
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Project Fields */}
        {Object.keys(signal.project_fields_json || {}).length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Project Fields</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(signal.project_fields_json || {}).map(([key, value]) => (
                <span key={key} className="px-2 py-1 bg-gray-100 dark:bg-gray-600 rounded text-sm">
                  <span className="text-gray-500 dark:text-gray-400">{key}:</span>{" "}
                  <span className="text-gray-800 dark:text-gray-200">{String(value)}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Parent Issue */}
        {(signal.metadata_json as any)?.context?.parent_issue && (
          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Parent Issue</h3>
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
              <a
                href={`https://github.com/${(signal.metadata_json as any).context.parent_issue.repo}/issues/${(signal.metadata_json as any).context.parent_issue.number}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
              >
                {(signal.metadata_json as any).context.parent_issue.title}
              </a>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {(signal.metadata_json as any).context.parent_issue.repo}#{(signal.metadata_json as any).context.parent_issue.number}
              </p>
            </div>
          </div>
        )}

        {/* Referenced Issues */}
        {((signal.metadata_json as any)?.context?.referenced_issues?.length > 0 ||
          (signal.metadata_json as any)?.context?.referenced_prs?.length > 0) && (
          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Referenced Issues & PRs</h3>
            <div className="space-y-2">
              {[
                ...((signal.metadata_json as any)?.context?.referenced_issues || []),
                ...((signal.metadata_json as any)?.context?.referenced_prs || [])
              ].map((ref: any, i: number) => (
                <div key={i} className="bg-gray-50 dark:bg-gray-700 rounded p-2 text-sm">
                  <a
                    href={`https://github.com/${ref.repo}/issues/${ref.number}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    {ref.repo}#{ref.number}
                  </a>
                  <span className="text-gray-600 dark:text-gray-400 ml-2">{ref.title}</span>
                  {ref.state && (
                    <span className={`ml-2 px-1.5 py-0.5 text-xs rounded ${
                      ref.state === "OPEN" ? "bg-green-100 text-green-700" :
                      ref.state === "MERGED" ? "bg-purple-100 text-purple-700" :
                      "bg-gray-100 text-gray-600"
                    }`}>
                      {ref.state.toLowerCase()}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Comments */}
        {(signal.metadata_json as any)?.context?.comments?.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Recent Comments ({(signal.metadata_json as any)?.context?.comment_count || 0} total)
            </h3>
            <div className="space-y-3">
              {(signal.metadata_json as any).context.comments.map((comment: any, i: number) => (
                <div key={i} className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-medium text-gray-800 dark:text-gray-200">
                      {comment.author || "Unknown"}
                    </span>
                    {comment.created_at && (
                      <span className="text-xs text-gray-500">
                        {new Date(comment.created_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                    {comment.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
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
