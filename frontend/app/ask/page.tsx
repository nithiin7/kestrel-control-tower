"use client";

import { useEffect, useRef, useState } from "react";
import { askQuestion, type AskResponse } from "@/lib/api";
import { PageHeader } from "@/components/ui";

interface Turn {
  question: string;
  loading: boolean;
  response: AskResponse | null;
  networkError: string | null;
}

export default function AskPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;

    setQuestion("");
    setTurns((prev) => [...prev, { question: q, loading: true, response: null, networkError: null }]);

    try {
      const response = await askQuestion(q);
      setTurns((prev) => prev.map((t, i) => (i === prev.length - 1 ? { ...t, loading: false, response } : t)));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      setTurns((prev) => prev.map((t, i) => (i === prev.length - 1 ? { ...t, loading: false, networkError: message } : t)));
    }
  };

  return (
    <div className="flex h-[calc(100vh-230px)] min-h-105 flex-col gap-4">
      <PageHeader title="Ask" description="Ask a question about the data in plain English." />

      <div ref={scrollRef} className="flex-1 overflow-y-auto rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        {turns.length === 0 && (
          <p className="text-sm text-gray-400">
            Try, e.g. &quot;which five outlets had the lowest case fill rate last month, excluding closed and test
            outlets?&quot;
          </p>
        )}
        <div className="flex flex-col gap-6">
          {turns.map((turn, i) => (
            <div key={i} className="flex flex-col gap-2">
              <div className="self-start rounded-lg bg-[#eaf1fd] px-3 py-2 text-sm font-medium text-gray-900">
                {turn.question}
              </div>

              {turn.loading && (
                <div className="flex items-center gap-1.5 px-1 text-sm text-gray-400">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-300 [animation-delay:-0.2s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-300 [animation-delay:-0.1s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-300" />
                </div>
              )}

              {turn.networkError && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  Something went wrong talking to the API: {turn.networkError}
                </div>
              )}

              {turn.response && <AnswerView response={turn.response} />}
            </div>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about the data..."
          className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm outline-none transition-colors focus:border-[#2a78d6] focus:ring-2 focus:ring-[#2a78d6]/20"
        />
        <button
          type="submit"
          disabled={!question.trim()}
          className="rounded-lg bg-[#2a78d6] px-4 py-2 text-sm font-medium text-white shadow-sm transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </div>
  );
}

function AnswerView({ response }: { response: AskResponse }) {
  if ("error" in response && response.error === "no_llm_configured") {
    return (
      <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
        Ask-anything isn&apos;t configured — set <code className="font-mono">ANTHROPIC_API_KEY</code> or run
        Ollama locally to enable it.
      </div>
    );
  }

  if ("error" in response && response.error === "unsafe_sql_rejected") {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        <p className="font-medium">The generated SQL was rejected by the safety validator, not run.</p>
        <p className="mt-1 text-amber-700">{response.detail}</p>
        <pre className="mt-2 overflow-x-auto rounded bg-white px-2 py-1 text-xs text-gray-700">{response.sql}</pre>
      </div>
    );
  }

  const success = response as { sql: string; columns: string[]; rows: Record<string, unknown>[]; natural_language_answer: string };

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-gray-900">{success.natural_language_answer}</p>

      <details className="text-xs text-gray-500" open>
        <summary className="cursor-pointer select-none font-medium text-gray-600">SQL</summary>
        <pre className="mt-1 overflow-x-auto rounded-lg bg-gray-50 px-2 py-1 text-gray-700">{success.sql}</pre>
      </details>

      {success.rows.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-gray-100">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-500">
                {success.columns.map((c) => (
                  <th key={c} className="px-2 py-1.5 font-semibold">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {success.rows.map((row, i) => (
                <tr key={i} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                  {success.columns.map((c) => (
                    <td key={c} className="px-2 py-1.5">
                      {String(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-gray-400">Query returned no rows.</p>
      )}
    </div>
  );
}
