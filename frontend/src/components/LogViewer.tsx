"use client";

import { useEffect, useRef, useState } from "react";
import { api, LogArtifact, LogEntry } from "@/lib/api";

interface LogViewerProps {
  attemptId: string;
  attemptStatus: string;
}

// Tool icon component
function ToolIcon({ name }: { name: string }) {
  const icons: Record<string, string> = {
    Read: "📄",
    Write: "✏️",
    Edit: "🔧",
    Bash: "💻",
    Glob: "🔍",
    Grep: "🔎",
    Task: "🤖",
    AskUserQuestion: "❓",
  };
  return <span className="mr-1">{icons[name] || "🔧"}</span>;
}

// Parse log artifact content
function parseLogContent(artifact: LogArtifact): LogEntry | null {
  try {
    return JSON.parse(artifact.content);
  } catch {
    return null;
  }
}

// Truncate long text with expand option
function TruncatedText({ text, maxLength = 500 }: { text: string; maxLength?: number }) {
  const [expanded, setExpanded] = useState(false);

  if (text.length <= maxLength) {
    return <span className="whitespace-pre-wrap">{text}</span>;
  }

  return (
    <span>
      <span className="whitespace-pre-wrap">
        {expanded ? text : text.slice(0, maxLength) + "..."}
      </span>
      <button
        onClick={() => setExpanded(!expanded)}
        className="ml-2 text-blue-500 hover:text-blue-600 text-xs"
      >
        {expanded ? "Show less" : "Show more"}
      </button>
    </span>
  );
}

// Format a value for display - handles objects, arrays, and primitives
function formatDetailValue(v: unknown): string {
  if (v === null || v === undefined) return String(v);
  if (typeof v === "object") {
    // For objects/arrays, show a compact JSON representation
    const json = JSON.stringify(v);
    // Truncate if too long
    return json.length > 100 ? json.slice(0, 100) + "..." : json;
  }
  return String(v);
}

// Event card component for timeline events
function EventCard({ entry, sequenceNum }: { entry: any; sequenceNum: number }) {
  const [showDetails, setShowDetails] = useState(false);
  const eventIcons: Record<string, string> = {
    attempt_started: "🚀",
    cloning_repo: "📥",
    workspace_ready: "📁",
    execution_starting: "⚡",
    execution_complete: "✅",
    waiting_for_human: "⏳",
    human_answered: "✅",
  };

  // Check if details has complex objects worth expanding
  const hasComplexDetails = entry.details && Object.values(entry.details).some(
    (v) => typeof v === "object" && v !== null
  );

  return (
    <div className="py-2 px-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center gap-3">
        <span className="text-lg">{eventIcons[entry.event] || "📌"}</span>
        <div className="flex-1">
          <span className="text-sm text-gray-700 dark:text-gray-300">{entry.message}</span>
          {entry.details && !hasComplexDetails && (
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {Object.entries(entry.details).map(([k, v]) => (
                <span key={k} className="mr-3">
                  {k}: <span className="font-mono">{formatDetailValue(v)}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasComplexDetails && (
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="text-xs text-blue-500 hover:text-blue-600"
            >
              {showDetails ? "Hide details" : "Show details"}
            </button>
          )}
          <span className="text-xs text-gray-400">{new Date(entry.timestamp).toLocaleTimeString()}</span>
        </div>
      </div>
      {showDetails && entry.details && (
        <div className="mt-2 p-2 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
          <pre className="text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap overflow-x-auto">
            {JSON.stringify(entry.details, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// Prompt display component
function PromptCard({ entry }: { entry: any }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4 mb-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-purple-700 dark:text-purple-300 flex items-center gap-2">
          📝 Prompt sent to Claude
        </span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-purple-600 hover:text-purple-700 dark:text-purple-400"
        >
          {expanded ? "Collapse" : "Show full prompt"}
        </button>
      </div>
      {expanded && (
        <pre className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap bg-white dark:bg-gray-800 rounded p-3 max-h-96 overflow-y-auto border border-purple-100 dark:border-purple-900">
          {entry.content}
        </pre>
      )}
    </div>
  );
}

// Interrupted card component
function InterruptedCard({ entry }: { entry: any }) {
  return (
    <div className="border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3 mb-2">
      <div className="flex items-center gap-2">
        <span className="text-lg">⏸️</span>
        <span className="text-sm font-medium text-orange-700 dark:text-orange-300">
          {entry.content?.reason || "Execution paused"}
        </span>
      </div>
    </div>
  );
}

// Single log entry component
function LogEntryCard({ entry, sequenceNum }: { entry: LogEntry; sequenceNum: number }) {
  // Collapse tool_result entries by default to reduce noise
  const [collapsed, setCollapsed] = useState(entry.type === "tool_result");

  const typeColors: Record<string, string> = {
    assistant: "border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20",
    tool_result: "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50",
    result: "border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20",
    system: "border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800",
  };

  const typeLabels: Record<string, string> = {
    assistant: "Assistant",
    tool_result: "Tool Result",
    result: "Completed",
    system: "System",
  };

  return (
    <div className={`border rounded-lg p-3 mb-2 ${typeColors[entry.type]}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            #{sequenceNum}
          </span>
          <span className="text-xs font-medium px-2 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
            {typeLabels[entry.type]}
          </span>
          {entry.turn && (
            <span className="text-xs text-gray-400">Turn {entry.turn}</span>
          )}
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        >
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </div>

      {/* Content */}
      {!collapsed && (
        <div className="text-sm">
          {/* Assistant text */}
          {entry.content.text && (
            <div className="mb-2 text-gray-700 dark:text-gray-300">
              <TruncatedText text={entry.content.text} maxLength={800} />
            </div>
          )}

          {/* Tool calls */}
          {entry.content.tool_calls && entry.content.tool_calls.length > 0 && (
            <div className="space-y-1">
              {entry.content.tool_calls.map((tool, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 bg-white dark:bg-gray-800 rounded p-2 border border-gray-100 dark:border-gray-700"
                >
                  <ToolIcon name={tool.name} />
                  <div className="flex-1 min-w-0">
                    <span className="font-mono text-xs font-medium text-gray-800 dark:text-gray-200">
                      {tool.name}
                    </span>
                    {tool.input && Object.keys(tool.input).length > 0 && (
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 font-mono overflow-x-auto">
                        {tool.name === "Bash" && tool.input.command ? (
                          <code className="text-orange-600 dark:text-orange-400">
                            $ {String(tool.input.command).slice(0, 200)}
                            {String(tool.input.command).length > 200 ? "..." : ""}
                          </code>
                        ) : tool.name === "Read" && tool.input.file_path ? (
                          <code>{String(tool.input.file_path)}</code>
                        ) : tool.name === "Grep" && tool.input.pattern ? (
                          <code>pattern: {String(tool.input.pattern)}</code>
                        ) : tool.name === "Task" && tool.input.prompt ? (
                          <TruncatedText
                            text={String(tool.input.prompt)}
                            maxLength={200}
                          />
                        ) : (
                          <TruncatedText
                            text={JSON.stringify(tool.input, null, 2)}
                            maxLength={300}
                          />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Tool results */}
          {entry.content.tool_results && entry.content.tool_results.length > 0 && (
            <div className="space-y-1">
              {entry.content.tool_results.map((result, i) => (
                <div
                  key={i}
                  className="bg-white dark:bg-gray-800 rounded p-2 border border-gray-100 dark:border-gray-700"
                >
                  <div className="text-xs font-mono text-gray-500 dark:text-gray-400 overflow-x-auto max-h-40 overflow-y-auto">
                    <TruncatedText
                      text={typeof result.content === "string" ? result.content : JSON.stringify(result.content)}
                      maxLength={1000}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Result metrics */}
          {entry.type === "result" && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
              {entry.content.cost_usd !== undefined && (
                <div className="text-xs">
                  <span className="text-gray-500 dark:text-gray-400">Cost:</span>{" "}
                  <span className="font-medium">${entry.content.cost_usd.toFixed(4)}</span>
                </div>
              )}
              {entry.content.turns !== undefined && (
                <div className="text-xs">
                  <span className="text-gray-500 dark:text-gray-400">Turns:</span>{" "}
                  <span className="font-medium">{entry.content.turns}</span>
                </div>
              )}
              {entry.content.duration_ms !== undefined && (
                <div className="text-xs">
                  <span className="text-gray-500 dark:text-gray-400">Duration:</span>{" "}
                  <span className="font-medium">{(entry.content.duration_ms / 1000).toFixed(1)}s</span>
                </div>
              )}
              {entry.content.is_error && (
                <div className="text-xs text-red-600 dark:text-red-400 font-medium">
                  Error occurred
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function LogViewer({ attemptId, attemptStatus }: LogViewerProps) {
  const [logs, setLogs] = useState<LogArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (containerRef.current && streaming) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, streaming]);

  // Fetch or stream logs
  useEffect(() => {
    let mounted = true;

    // Clear previous logs immediately when attemptId changes
    setLogs([]);

    async function initLogs() {
      setLoading(true);
      setError(null);

      try {
        // First, fetch any existing logs
        const existingLogs = await api.getAttemptLogs(attemptId);
        if (!mounted) return;
        setLogs(existingLogs);
        setLoading(false);

        // Check if we should stream (attempt is running or pending)
        const isActive = attemptStatus === "running" || attemptStatus === "pending";
        const hasFinished = existingLogs.some((log) => log.is_final);

        if (isActive && !hasFinished) {
          // Start streaming from the last sequence we have
          const lastSeq = existingLogs.length > 0
            ? Math.max(...existingLogs.map((l) => l.sequence_num))
            : 0;

          setStreaming(true);
          eventSourceRef.current = api.streamAttemptLogs(
            attemptId,
            {
              onLog: (log) => {
                if (!mounted) return;
                setLogs((prev) => {
                  // Avoid duplicates
                  if (prev.some((l) => l.sequence_num === log.sequence_num)) {
                    return prev;
                  }
                  return [...prev, log];
                });
              },
              onDone: () => {
                if (!mounted) return;
                setStreaming(false);
              },
              onError: (err) => {
                if (!mounted) return;
                setError(err);
                setStreaming(false);
              },
            },
            lastSeq
          );
        }
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load logs");
        setLoading(false);
      }
    }

    initLogs();

    return () => {
      mounted = false;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [attemptId, attemptStatus]);

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Execution Logs
        </h2>
        <div className="flex items-center justify-center h-32 text-gray-500">
          Loading logs...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Execution Logs
        </h2>
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-3">
          <p className="text-red-600 dark:text-red-400 text-sm">Error: {error}</p>
        </div>
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Execution Logs
        </h2>
        <div className="flex items-center justify-center h-32 text-gray-500 dark:text-gray-400">
          {attemptStatus === "pending"
            ? "Waiting for execution to start..."
            : attemptStatus === "running"
            ? "Waiting for logs..."
            : "No logs available"}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          Execution Logs
        </h2>
        {streaming && (
          <span className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
            Streaming...
          </span>
        )}
      </div>

      <div
        ref={containerRef}
        className="max-h-[600px] overflow-y-auto space-y-2 pr-2"
      >
        {logs
          .sort((a, b) => a.sequence_num - b.sequence_num)
          .map((artifact) => {
            const entry = parseLogContent(artifact);
            if (!entry) return null;

            // Use attemptId + sequence_num as key to avoid collisions when switching attempts
            const key = `${attemptId}-${artifact.sequence_num}`;

            // Render different components based on entry type
            if (entry.type === "event") {
              return (
                <EventCard
                  key={key}
                  entry={entry}
                  sequenceNum={artifact.sequence_num}
                />
              );
            }

            if (entry.type === "prompt") {
              return <PromptCard key={key} entry={entry} />;
            }

            if (entry.type === "interrupted") {
              return <InterruptedCard key={key} entry={entry} />;
            }

            return (
              <LogEntryCard
                key={key}
                entry={entry}
                sequenceNum={artifact.sequence_num}
              />
            );
          })}
      </div>
    </div>
  );
}
