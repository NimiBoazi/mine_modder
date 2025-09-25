import { useEffect, useState } from "react";

import type { ChatMessage } from "@/lib/useSocketRun";

export const ResultStage = ({
  messages,
  onSendMessage,
  isBusy = false,
  statusMessage,
}: {
  messages: ChatMessage[];
  onSendMessage?: (msg: string) => void;
  isBusy?: boolean;
  statusMessage?: string;
}) => {
  const [expanded, setExpanded] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setExpanded(true), 10);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      className={[
        "bg-stone-100 shadow-[rgba(0,0,0,0)_0px_0px_0px_0px,rgba(0,0,0,0)_0px_0px_0px_0px,rgba(0,0,0,0.1)_0px_20px_25px_-5px,rgba(0,0,0,0.1)_0px_8px_10px_-6px]",
        "box-border caret-transparent w-full border border-stone-200 p-3 rounded-[28px] border-solid",
        "transition-all duration-500 ease-out",
        expanded ? "max-h-[1000px] py-6" : "max-h-[200px] overflow-hidden",
      ].join(" ")}
    >
      {/* Messages Board */}
      <div className="max-h-[60vh] overflow-auto pr-1 space-y-3">
        {messages.map((m) => (
          <div key={m.id} className={[
            "w-full flex",
            m.role === "user" ? "justify-end" : "justify-start",
          ].join(" ")}>
            <div className={[
              "px-3 py-2 rounded-2xl max-w-[85%] text-sm",
              m.role === "user" ? "bg-zinc-900 text-white rounded-br-sm" : "bg-white/80 text-zinc-900 rounded-bl-sm border border-stone-200",
            ].join(" ")}
            >
              <div className="whitespace-pre-wrap break-words">{m.text}</div>
              {m.downloadUrl && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <a
                    href={m.downloadUrl}
                    download
                    className="inline-flex items-center gap-2 bg-zinc-900 text-white text-xs px-3 py-1.5 rounded-full hover:bg-zinc-800"
                  >
                    <span aria-hidden>⬇</span>
                    <span>Download Project (MDK ZIP)</span>
                  </a>
                </div>
              )}
            </div>
          </div>
        ))}
        {isBusy && (
          <div className="w-full flex justify-start">
            <div className="px-3 py-2 rounded-2xl max-w-[85%] text-sm bg-white/80 text-zinc-900 rounded-bl-sm border border-stone-200 flex items-center gap-3">
              <div className="h-4 w-4 rounded-full border-2 border-zinc-300 border-t-zinc-900 animate-spin" aria-label="loading" />
              <div className="whitespace-pre-wrap break-words">
                {statusMessage || "Working..."}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Spacer */}
      <div className="h-3" />

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const text = message.trim();
          if (!text || isBusy) return;
          onSendMessage?.(text);
          setMessage("");
        }}
        className={`bg-white/60 border border-stone-200 rounded-2xl p-2 flex items-center gap-2 ${isBusy ? "opacity-60" : ""}`}
      >
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask a follow-up..."
          className="flex-1 bg-transparent outline-none px-2 py-2"
          disabled={isBusy}
        />
        <button
          type="submit"
          disabled={isBusy}
          aria-disabled={isBusy}
          className={`h-9 w-9 rounded-full grid place-items-center ${isBusy ? "bg-zinc-400 cursor-not-allowed" : "bg-zinc-900 text-white hover:bg-zinc-800"}`}
        >
          <span aria-hidden>→</span>
          <span className="sr-only">Send</span>
        </button>
      </form>
    </div>
  );
}

