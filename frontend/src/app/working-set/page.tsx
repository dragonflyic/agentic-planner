"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api, SignalWithStatus, AttemptWithSignal, AttemptClarification, ClarificationOption } from "@/lib/api";
import { useWorkingSet } from "@/contexts/WorkingSetContext";
import { LogViewer } from "@/components/LogViewer";

// Single question input component (no submit button - parent handles submission)
function ClarificationInput({
  clarification,
  value,
  onChange,
}: {
  clarification: AttemptClarification;
  value: { selectedOptions: string[]; customText: string; showCustom: boolean };
  onChange: (value: { selectedOptions: string[]; customText: string; showCustom: boolean }) => void;
}) {
  const hasOptions = clarification.options && clarification.options.length > 0;

  const handleOptionChange = (label: string, checked: boolean) => {
    if (clarification.multi_select) {
      const newOptions = checked
        ? [...value.selectedOptions, label]
        : value.selectedOptions.filter((o) => o !== label);
      onChange({ ...value, selectedOptions: newOptions, showCustom: false, customText: "" });
    } else {
      onChange({ selectedOptions: checked ? [label] : [], showCustom: false, customText: "" });
    }
  };

  // Already answered
  if (clarification.is_answered) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded p-3 border border-green-200 dark:border-green-900">
        <p className="font-medium text-gray-900 dark:text-white text-sm">
          {clarification.question_text}
        </p>
        <p className="text-xs text-green-600 dark:text-green-400 mt-1">
          Answered: {clarification.answer_text}
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded p-3 border border-orange-100 dark:border-orange-900">
      <p className="font-medium text-gray-900 dark:text-white text-sm mb-2">
        {clarification.question_text}
      </p>
      {clarification.question_context && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          {clarification.question_context}
        </p>
      )}

      {hasOptions ? (
        <div className="space-y-2">
          {clarification.options!.map((option: ClarificationOption, idx: number) => (
            <label
              key={idx}
              className={`flex items-start gap-2 p-2 rounded border cursor-pointer transition-colors ${
                value.selectedOptions.includes(option.label)
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-900/30"
                  : "border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50"
              }`}
            >
              <input
                type={clarification.multi_select ? "checkbox" : "radio"}
                name={`clarification-${clarification.id}`}
                checked={value.selectedOptions.includes(option.label)}
                onChange={(e) => handleOptionChange(option.label, e.target.checked)}
                className="mt-0.5"
              />
              <div>
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {option.label}
                </span>
                {option.description && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {option.description}
                  </p>
                )}
              </div>
            </label>
          ))}

          {/* "Other" option for custom input */}
          <label
            className={`flex items-start gap-2 p-2 rounded border cursor-pointer transition-colors ${
              value.showCustom
                ? "border-blue-500 bg-blue-50 dark:bg-blue-900/30"
                : "border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50"
            }`}
          >
            <input
              type={clarification.multi_select ? "checkbox" : "radio"}
              name={`clarification-${clarification.id}`}
              checked={value.showCustom}
              onChange={(e) => {
                onChange({ selectedOptions: [], showCustom: e.target.checked, customText: value.customText });
              }}
              className="mt-0.5"
            />
            <span className="text-sm font-medium text-gray-900 dark:text-white">
              Other...
            </span>
          </label>
        </div>
      ) : null}

      {/* Custom text input (shown when "Other" is selected or no options exist) */}
      {(value.showCustom || !hasOptions) && (
        <textarea
          value={value.customText}
          onChange={(e) => onChange({ ...value, customText: e.target.value })}
          placeholder="Enter your answer..."
          className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 mt-2"
          rows={2}
        />
      )}
    </div>
  );
}

// Form group that handles all clarifications together with a single submit
function ClarificationFormGroup({
  clarifications,
  onSubmitAll,
}: {
  clarifications: AttemptClarification[];
  onSubmitAll: (answers: { id: string; answer: string }[]) => Promise<void>;
}) {
  type AnswerState = { selectedOptions: string[]; customText: string; showCustom: boolean };
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({});
  const [submitting, setSubmitting] = useState(false);

  const pendingClarifications = clarifications.filter((c) => !c.is_answered);
  const answeredClarifications = clarifications.filter((c) => c.is_answered);

  const getAnswerValue = (id: string): AnswerState => {
    return answers[id] || { selectedOptions: [], customText: "", showCustom: false };
  };

  const setAnswerValue = (id: string, value: AnswerState) => {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  };

  const getAnswerText = (c: AttemptClarification): string | null => {
    const val = getAnswerValue(c.id);
    if (val.showCustom && val.customText.trim()) {
      return val.customText.trim();
    } else if (val.selectedOptions.length > 0) {
      return val.selectedOptions.join(", ");
    }
    return null;
  };

  const allAnswered = pendingClarifications.every((c) => getAnswerText(c) !== null);

  const handleSubmitAll = async () => {
    const answersToSubmit = pendingClarifications
      .map((c) => ({ id: c.id, answer: getAnswerText(c) }))
      .filter((a): a is { id: string; answer: string } => a.answer !== null);

    if (answersToSubmit.length === 0) return;

    setSubmitting(true);
    try {
      await onSubmitAll(answersToSubmit);
    } finally {
      setSubmitting(false);
    }
  };

  if (pendingClarifications.length === 0 && answeredClarifications.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {/* Show answered clarifications */}
      {answeredClarifications.map((c) => (
        <ClarificationInput
          key={c.id}
          clarification={c}
          value={getAnswerValue(c.id)}
          onChange={(v) => setAnswerValue(c.id, v)}
        />
      ))}

      {/* Show pending clarifications */}
      {pendingClarifications.map((c) => (
        <ClarificationInput
          key={c.id}
          clarification={c}
          value={getAnswerValue(c.id)}
          onChange={(v) => setAnswerValue(c.id, v)}
        />
      ))}

      {/* Single submit button for all pending answers */}
      {pendingClarifications.length > 0 && (
        <button
          onClick={handleSubmitAll}
          disabled={!allAnswered || submitting}
          className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          {submitting
            ? "Submitting..."
            : `Submit ${pendingClarifications.length === 1 ? "Answer" : `All ${pendingClarifications.length} Answers`}`}
        </button>
      )}
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-yellow-100 text-yellow-700",
  waiting: "bg-orange-100 text-orange-700",
  complete: "bg-green-100 text-green-700",
  error: "bg-red-100 text-red-700",
};

function formatDuration(ms: number | null): string {
  if (ms === null) return "-";
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

// Compact signal item for the middle column
function SignalListItem({
  signal,
  isSelected,
  onSelect,
  onRemove,
  onRunAttempt,
}: {
  signal: SignalWithStatus;
  isSelected: boolean;
  onSelect: () => void;
  onRemove: () => void;
  onRunAttempt: () => void;
}) {
  const isRunning = signal.latest_attempt_status === "running" || signal.latest_attempt_status === "pending";

  return (
    <div
      onClick={onSelect}
      className={`p-3 border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 ${
        isSelected ? "bg-blue-50 dark:bg-blue-900/30 border-l-2 border-l-blue-500" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`px-1.5 py-0.5 text-xs font-medium rounded ${
                signal.priority >= 100
                  ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                  : signal.priority >= 0
                  ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                  : "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400"
              }`}
            >
              P{signal.priority}
            </span>
            {signal.latest_attempt_status && (
              <span
                className={`px-1.5 py-0.5 text-xs font-medium rounded-full ${
                  STATUS_COLORS[signal.latest_attempt_status] || STATUS_COLORS.pending
                }`}
              >
                {signal.latest_attempt_status}
              </span>
            )}
          </div>
          <h3 className="text-sm font-medium text-gray-900 dark:text-white truncate">
            {signal.title}
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {signal.repo}#{signal.issue_number}
          </p>
          {signal.pending_clarifications > 0 && (
            <p className="text-xs text-orange-600 dark:text-orange-400 mt-1">
              {signal.pending_clarifications} question{signal.pending_clarifications !== 1 ? "s" : ""} pending
            </p>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRunAttempt();
            }}
            disabled={isRunning}
            className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Run
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}

// Loading skeleton for the detail panel
function DetailPanelSkeleton({ signalTitle }: { signalTitle: string }) {
  return (
    <div className="h-full overflow-y-auto animate-pulse">
      {/* Header skeleton */}
      <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 p-4 z-10">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="h-6 w-24 bg-gray-200 dark:bg-gray-700 rounded"></div>
              <div className="h-5 w-16 bg-gray-200 dark:bg-gray-700 rounded-full"></div>
            </div>
            <div className="text-sm text-blue-600 dark:text-blue-400">
              {signalTitle}
            </div>
          </div>
          <div className="h-8 w-20 bg-gray-200 dark:bg-gray-700 rounded"></div>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Stats skeleton */}
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
              <div className="h-3 w-12 bg-gray-200 dark:bg-gray-700 rounded mb-2"></div>
              <div className="h-6 w-16 bg-gray-200 dark:bg-gray-700 rounded"></div>
            </div>
          ))}
        </div>

        {/* Files changed skeleton */}
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
          <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded mb-3"></div>
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-3 bg-gray-200 dark:bg-gray-700 rounded" style={{ width: `${70 - i * 10}%` }}></div>
            ))}
          </div>
        </div>

        {/* Logs skeleton */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="h-5 w-32 bg-gray-200 dark:bg-gray-700 rounded mb-4"></div>
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="h-4 w-8 bg-gray-200 dark:bg-gray-700 rounded"></div>
                  <div className="h-4 w-16 bg-gray-200 dark:bg-gray-700 rounded"></div>
                </div>
                <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded" style={{ width: `${80 - i * 10}%` }}></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// Attempt detail panel for the right column
function AttemptDetailPanel({
  signal,
  attempt,
  clarifications,
  loading,
  onRefresh,
  onSubmitAllClarifications,
}: {
  signal: SignalWithStatus;
  attempt: AttemptWithSignal | null;
  clarifications: AttemptClarification[];
  loading: boolean;
  onRefresh: () => void;
  onSubmitAllClarifications: (answers: { id: string; answer: string }[]) => Promise<void>;
}) {
  if (loading) {
    return <DetailPanelSkeleton signalTitle={signal.title} />;
  }

  if (!attempt) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center p-6">
        <div className="text-gray-400 dark:text-gray-500 mb-4">
          <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </div>
        <p className="text-gray-500 dark:text-gray-400 mb-2">No attempts yet for this signal</p>
        <p className="text-sm text-gray-400 dark:text-gray-500">
          Click &quot;Run&quot; to start an attempt
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
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 p-4 z-10">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Attempt #{attempt.attempt_number}
              </h2>
              <span
                className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                  STATUS_COLORS[attempt.status] || STATUS_COLORS.pending
                }`}
              >
                {attempt.status}
              </span>
            </div>
            <a
              href={`/signals/${signal.id}`}
              className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
            >
              {signal.title}
            </a>
          </div>
          <button
            onClick={onRefresh}
            className="px-3 py-1 text-sm text-gray-600 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Quick Stats */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Duration</p>
            <p className="text-lg font-semibold text-gray-900 dark:text-white">
              {formatDuration(attempt.duration_ms)}
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Tool Calls</p>
            <p className="text-lg font-semibold text-gray-900 dark:text-white">
              {summary.metrics?.tool_calls ?? "-"}
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Turns</p>
            <p className="text-lg font-semibold text-gray-900 dark:text-white">
              {summary.metrics?.turns ?? "-"}
            </p>
          </div>
        </div>

        {/* PR Link */}
        {attempt.pr_url && (
          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
            <p className="text-green-700 dark:text-green-400 font-medium text-sm">
              Pull Request Created
            </p>
            <a
              href={attempt.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-green-600 dark:text-green-400 hover:underline text-sm"
            >
              {attempt.pr_url}
            </a>
          </div>
        )}

        {/* Error Message */}
        {attempt.error_message && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
            <p className="text-red-700 dark:text-red-400 font-medium text-sm">Error</p>
            <pre className="text-xs text-red-600 dark:text-red-400 mt-1 whitespace-pre-wrap">
              {attempt.error_message}
            </pre>
          </div>
        )}

        {/* Human Feedback Needed - show for waiting OR running with pending clarifications */}
        {(attempt.status === "waiting" || attempt.status === "running") && clarifications.length > 0 && (
          <div className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-lg p-3">
            <p className="text-orange-700 dark:text-orange-400 font-medium text-sm mb-3">
              {attempt.status === "running" ? "Waiting for Input" : "Human Feedback Needed"} ({clarifications.filter(c => !c.is_answered).length} pending)
            </p>
            <ClarificationFormGroup
              clarifications={clarifications}
              onSubmitAll={onSubmitAllClarifications}
            />
          </div>
        )}

        {/* Files Changed */}
        {summary.what_changed && summary.what_changed.length > 0 && (
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
              Files Changed ({summary.what_changed.length})
            </h3>
            <ul className="space-y-1">
              {summary.what_changed.slice(0, 5).map((file, i) => (
                <li
                  key={i}
                  className="text-xs text-gray-600 dark:text-gray-300 font-mono truncate"
                >
                  {file}
                </li>
              ))}
              {summary.what_changed.length > 5 && (
                <li className="text-xs text-gray-400">
                  +{summary.what_changed.length - 5} more files
                </li>
              )}
            </ul>
          </div>
        )}

        {/* Risk Flags */}
        {summary.risk_flags && summary.risk_flags.length > 0 && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3">
            <p className="text-yellow-700 dark:text-yellow-400 font-medium text-sm mb-2">
              Risk Flags
            </p>
            <div className="flex flex-wrap gap-1">
              {summary.risk_flags.map((flag, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-300 text-xs rounded"
                >
                  {flag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Log Viewer */}
        <LogViewer attemptId={attempt.id} attemptStatus={attempt.status} />
      </div>
    </div>
  );
}

export default function WorkingSetPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { workingSet, removeFromWorkingSet, clearWorkingSet } = useWorkingSet();
  const [signals, setSignals] = useState<SignalWithStatus[]>([]);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<AttemptWithSignal | null>(null);
  const [clarifications, setClarifications] = useState<AttemptClarification[]>([]);
  const [loading, setLoading] = useState(true);
  const [attemptLoading, setAttemptLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const [runAllProgress, setRunAllProgress] = useState<{ current: number; total: number } | null>(null);

  // Track initial URL signal to restore on first load
  const initialUrlSignalRef = useRef<string | null | undefined>(undefined);
  if (initialUrlSignalRef.current === undefined) {
    initialUrlSignalRef.current = searchParams.get("signal");
  }

  const selectedSignal = signals.find((s) => s.id === selectedSignalId) || null;

  // Update URL when selection changes
  useEffect(() => {
    // Skip if we haven't done initial selection yet
    if (initialUrlSignalRef.current === undefined) return;

    const urlSignalId = searchParams.get("signal");
    if (selectedSignalId && selectedSignalId !== urlSignalId) {
      router.replace(`/working-set?signal=${selectedSignalId}`, { scroll: false });
    } else if (!selectedSignalId && urlSignalId) {
      router.replace("/working-set", { scroll: false });
    }
  }, [selectedSignalId, searchParams, router]);

  // Fetch signals in the working set
  const fetchSignals = useCallback(async () => {
    if (workingSet.size === 0) {
      setSignals([]);
      setSelectedSignalId(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const ids = Array.from(workingSet);
      const data = await api.listSignals({ ids, page_size: ids.length, sort_by: "priority", sort_order: "desc" });
      setSignals(data.items);

      // On first load, try to restore selection from URL
      if (initialUrlSignalRef.current !== null) {
        const signalFromUrl = data.items.find((s) => s.id === initialUrlSignalRef.current);
        if (signalFromUrl) {
          setSelectedSignalId(signalFromUrl.id);
        } else {
          setSelectedSignalId(data.items.length > 0 ? data.items[0].id : null);
        }
        // Clear the ref so we don't re-process on subsequent fetches
        initialUrlSignalRef.current = null;
      } else if (!selectedSignalId || !data.items.find((s) => s.id === selectedSignalId)) {
        // After initial load, only auto-select if current selection is invalid
        setSelectedSignalId(data.items.length > 0 ? data.items[0].id : null);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message || "Failed to fetch signals");
    } finally {
      setLoading(false);
    }
  }, [workingSet, selectedSignalId]);

  useEffect(() => {
    fetchSignals();
  }, [fetchSignals]);

  // Track the current fetch to ignore stale results
  const fetchIdRef = useRef(0);

  // Fetch attempt details when selected signal changes
  useEffect(() => {
    // Increment fetch ID immediately to invalidate any in-flight requests
    const currentFetchId = ++fetchIdRef.current;

    const attemptIdOrNull = selectedSignal?.latest_attempt_id;

    if (!attemptIdOrNull) {
      setSelectedAttempt(null);
      setClarifications([]);
      setAttemptLoading(false);
      return;
    }

    // Copy to const for TypeScript narrowing in nested function
    const attemptId = attemptIdOrNull;

    setAttemptLoading(true);

    async function fetchAttemptDetails() {
      try {
        const attempt = await api.getAttempt(attemptId);

        // Ignore if a newer fetch has started
        if (fetchIdRef.current !== currentFetchId) return;

        setSelectedAttempt(attempt);

        // Fetch clarifications for waiting OR running attempts (bidirectional mode)
        if (attempt.status === "waiting" || attempt.status === "running") {
          const clars = await api.getAttemptClarifications(attempt.id);
          // Check again after async operation
          if (fetchIdRef.current !== currentFetchId) return;
          setClarifications(clars);
        } else {
          setClarifications([]);
        }
      } catch (err) {
        // Ignore errors from stale requests
        if (fetchIdRef.current !== currentFetchId) return;
        console.error("Failed to fetch attempt:", err);
        setSelectedAttempt(null);
      } finally {
        // Only clear loading if this is still the current fetch
        if (fetchIdRef.current === currentFetchId) {
          setAttemptLoading(false);
        }
      }
    }

    fetchAttemptDetails();
  }, [selectedSignalId, selectedSignal?.latest_attempt_id]);

  // Manual refresh function
  const handleRefreshAttempt = useCallback(async () => {
    const attemptId = selectedSignal?.latest_attempt_id;
    if (!attemptId) return;

    const currentFetchId = ++fetchIdRef.current;
    setAttemptLoading(true);

    try {
      const attempt = await api.getAttempt(attemptId);
      if (fetchIdRef.current !== currentFetchId) return;
      setSelectedAttempt(attempt);

      // Fetch clarifications for waiting OR running attempts (bidirectional mode)
      if (attempt.status === "waiting" || attempt.status === "running") {
        const clars = await api.getAttemptClarifications(attempt.id);
        if (fetchIdRef.current !== currentFetchId) return;
        setClarifications(clars);
      } else {
        setClarifications([]);
      }
    } catch (err) {
      if (fetchIdRef.current !== currentFetchId) return;
      console.error("Failed to fetch attempt:", err);
    } finally {
      if (fetchIdRef.current === currentFetchId) {
        setAttemptLoading(false);
      }
    }
  }, [selectedSignal?.latest_attempt_id]);

  // Polling for running attempts
  useEffect(() => {
    if (!selectedAttempt || (selectedAttempt.status !== "running" && selectedAttempt.status !== "pending")) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const updated = await api.getAttempt(selectedAttempt.id);
        setSelectedAttempt(updated);

        // Also refresh signals list to update status badges
        const ids = Array.from(workingSet);
        if (ids.length > 0) {
          const data = await api.listSignals({ ids, page_size: ids.length, sort_by: "priority", sort_order: "desc" });
          setSignals(data.items);
        }

        // Always fetch clarifications while running (bidirectional mode) or when finished as waiting
        if (updated.status === "running" || updated.status === "waiting") {
          const clars = await api.getAttemptClarifications(updated.id);
          setClarifications(clars);
        } else if (updated.status !== "pending") {
          // Finished with other status, clear clarifications
          setClarifications([]);
        }
      } catch {
        // Ignore polling errors
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [selectedAttempt, workingSet]);

  async function handleRunAttempt(signalId: string) {
    try {
      await api.createAttempt(signalId);
      // Refresh signals
      const ids = Array.from(workingSet);
      const data = await api.listSignals({ ids, page_size: ids.length, sort_by: "priority", sort_order: "desc" });
      setSignals(data.items);

      // If this is the selected signal, refresh its attempt
      if (signalId === selectedSignalId) {
        const signal = data.items.find((s) => s.id === signalId);
        if (signal?.latest_attempt_id) {
          setAttemptLoading(true);
          const attempt = await api.getAttempt(signal.latest_attempt_id);
          setSelectedAttempt(attempt);
          setAttemptLoading(false);
        }
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create attempt");
    }
  }

  async function handleRunAllAttempts() {
    const eligibleSignals = signals.filter(
      (s) => s.latest_attempt_status !== "running" && s.latest_attempt_status !== "pending"
    );

    if (eligibleSignals.length === 0) {
      alert("No eligible signals to run. All signals already have running or pending attempts.");
      return;
    }

    setRunningAll(true);
    setRunAllProgress({ current: 0, total: eligibleSignals.length });

    let completed = 0;
    const errors: string[] = [];

    for (const signal of eligibleSignals) {
      try {
        await api.createAttempt(signal.id);
      } catch (err) {
        errors.push(`${signal.title}: ${err instanceof Error ? err.message : "Failed"}`);
      }
      completed++;
      setRunAllProgress({ current: completed, total: eligibleSignals.length });
    }

    // Refresh signals
    try {
      const ids = Array.from(workingSet);
      const data = await api.listSignals({ ids, page_size: ids.length, sort_by: "priority", sort_order: "desc" });
      setSignals(data.items);

      // Refresh selected attempt
      if (selectedSignalId) {
        const signal = data.items.find((s) => s.id === selectedSignalId);
        if (signal?.latest_attempt_id) {
          const attempt = await api.getAttempt(signal.latest_attempt_id);
          setSelectedAttempt(attempt);
        }
      }
    } catch {
      // Ignore refresh errors
    }

    setRunningAll(false);
    setRunAllProgress(null);

    if (errors.length > 0) {
      alert(`Completed with ${errors.length} error(s):\n${errors.join("\n")}`);
    }
  }

  function handleRemoveSignal(signalId: string) {
    removeFromWorkingSet(signalId);
    // If removing selected signal, select the next one
    if (signalId === selectedSignalId) {
      const remaining = signals.filter((s) => s.id !== signalId);
      setSelectedSignalId(remaining.length > 0 ? remaining[0].id : null);
    }
  }

  // Handle submitting all clarification answers at once
  const handleSubmitAllClarifications = useCallback(async (answers: { id: string; answer: string }[]) => {
    try {
      // Submit all answers in parallel
      await Promise.all(
        answers.map((a) =>
          api.submitClarification(a.id, {
            answer_text: a.answer,
            answered_by: "user",
          })
        )
      );
      // Refresh clarifications
      if (selectedAttempt) {
        const clars = await api.getAttemptClarifications(selectedAttempt.id);
        setClarifications(clars);
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to submit clarifications");
    }
  }, [selectedAttempt]);

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

  // Empty state
  if (signals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-200px)]">
        <div className="text-gray-400 dark:text-gray-500 mb-4">
          <svg className="w-20 h-20 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
          Your working set is empty
        </h2>
        <p className="text-gray-500 dark:text-gray-400 mb-4">
          Add signals from the Signals page to get started
        </p>
        <a
          href="/signals"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Browse Signals
        </a>
      </div>
    );
  }

  return (
    <div className="fixed top-0 right-0 bottom-0 left-64 flex">
      {/* Middle Column: Signal List */}
      <div className="w-80 h-full flex-shrink-0 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 flex flex-col">
        {/* Header */}
        <div className="p-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
              Working Set
            </h1>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {signals.length}
            </span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleRunAllAttempts}
              disabled={runningAll || signals.every((s) => s.latest_attempt_status === "running" || s.latest_attempt_status === "pending")}
              className="flex-1 px-2 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {runningAll && runAllProgress
                ? `Running ${runAllProgress.current}/${runAllProgress.total}...`
                : "Run All"}
            </button>
            <button
              onClick={clearWorkingSet}
              className="px-2 py-1.5 text-xs text-red-600 hover:text-red-700 border border-red-300 rounded hover:bg-red-50 dark:text-red-400 dark:border-red-600 dark:hover:bg-red-900/20"
            >
              Clear
            </button>
          </div>
        </div>

        {/* Signal List */}
        <div className="flex-1 overflow-y-auto">
          {signals.map((signal) => (
            <SignalListItem
              key={signal.id}
              signal={signal}
              isSelected={signal.id === selectedSignalId}
              onSelect={() => {
                if (signal.id !== selectedSignalId) {
                  // Update selection indicator first for instant visual feedback
                  setSelectedSignalId(signal.id);
                  // Then clear previous attempt and show loading skeleton
                  setSelectedAttempt(null);
                  setClarifications([]);
                  setAttemptLoading(true);
                }
              }}
              onRemove={() => handleRemoveSignal(signal.id)}
              onRunAttempt={() => handleRunAttempt(signal.id)}
            />
          ))}
        </div>
      </div>

      {/* Right Column: Attempt Detail */}
      <div className="flex-1 h-full bg-gray-50 dark:bg-gray-900 overflow-hidden">
        {selectedSignal ? (
          <AttemptDetailPanel
            signal={selectedSignal}
            attempt={selectedAttempt}
            clarifications={clarifications}
            loading={attemptLoading}
            onRefresh={handleRefreshAttempt}
            onSubmitAllClarifications={handleSubmitAllClarifications}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
            Select a signal to view its latest attempt
          </div>
        )}
      </div>
    </div>
  );
}
