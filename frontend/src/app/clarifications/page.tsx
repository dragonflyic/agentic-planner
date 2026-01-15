"use client";

import { useEffect, useState } from "react";
import { api, ClarificationWithAttempt } from "@/lib/api";

export default function ClarificationsPage() {
  const [clarifications, setClarifications] = useState<ClarificationWithAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState<string | null>(null);

  useEffect(() => {
    fetchClarifications();
  }, []);

  async function fetchClarifications() {
    setLoading(true);
    try {
      const data = await api.listPendingClarifications();
      setClarifications(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch clarifications");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(id: string, acceptDefault: boolean = false) {
    setSubmitting(id);
    try {
      if (acceptDefault) {
        await api.submitClarification(id, { accepted_default: true });
      } else {
        const answer = answers[id];
        if (!answer?.trim()) {
          alert("Please provide an answer");
          return;
        }
        await api.submitClarification(id, { answer_text: answer });
      }
      // Refresh the list
      await fetchClarifications();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to submit");
    } finally {
      setSubmitting(null);
    }
  }

  async function handleRetry(id: string) {
    setSubmitting(id);
    try {
      await api.retryWithClarification(id);
      // Refresh the list
      await fetchClarifications();
      alert("Retry started successfully");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to retry");
    } finally {
      setSubmitting(null);
    }
  }

  if (loading) {
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
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
        Needs Attention
      </h1>

      {clarifications.length === 0 ? (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-8 text-center">
          <p className="text-green-700 dark:text-green-400 text-lg">
            No pending clarifications
          </p>
          <p className="text-green-600 dark:text-green-500 text-sm mt-2">
            All attempts are either completed or have no questions.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {clarifications.map((c) => (
            <div
              key={c.id}
              className="bg-white dark:bg-gray-800 rounded-lg shadow p-6"
            >
              {/* Header */}
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-white">
                    {c.attempt.signal?.title || "Unknown Signal"}
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Attempt #{c.attempt.attempt_number}
                  </p>
                </div>
                <span className="px-2 py-1 text-xs font-medium rounded-full bg-orange-100 text-orange-700">
                  needs_human
                </span>
              </div>

              {/* Question */}
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 mb-4">
                <p className="font-medium text-gray-900 dark:text-white mb-2">
                  Question:
                </p>
                <p className="text-gray-700 dark:text-gray-300">
                  {c.question_text}
                </p>
                {c.question_context && (
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                    Context: {c.question_context}
                  </p>
                )}
              </div>

              {/* Default Answer (if available) */}
              {c.default_answer && (
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-4">
                  <p className="font-medium text-blue-900 dark:text-blue-300 mb-2">
                    Suggested Default:
                  </p>
                  <p className="text-blue-700 dark:text-blue-400">
                    {c.default_answer}
                  </p>
                  <button
                    onClick={() => handleSubmit(c.id, true)}
                    disabled={submitting === c.id}
                    className="mt-3 px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {submitting === c.id ? "Accepting..." : "Accept Default"}
                  </button>
                </div>
              )}

              {/* Answer Input */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Your Answer:
                </label>
                <textarea
                  value={answers[c.id] || ""}
                  onChange={(e) =>
                    setAnswers((prev) => ({ ...prev, [c.id]: e.target.value }))
                  }
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="Type your answer here..."
                />
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={() => handleSubmit(c.id)}
                  disabled={submitting === c.id || !answers[c.id]?.trim()}
                  className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                >
                  {submitting === c.id ? "Submitting..." : "Submit Answer"}
                </button>
                <button
                  onClick={() => handleRetry(c.id)}
                  disabled={submitting === c.id}
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                >
                  {submitting === c.id ? "Retrying..." : "Submit & Retry"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
