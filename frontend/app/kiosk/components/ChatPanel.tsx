"use client";

import { useState, useRef, useEffect } from "react";
import type { ChatMessage } from "../types";

interface Props {
  messages: ChatMessage[];
  isStreaming: boolean;
  onSend: (text: string) => void;
}

export default function ChatPanel({ messages, isStreaming, onSend }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
    inputRef.current?.focus();
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 py-4 border-b"
        style={{ borderColor: "#21262d", background: "#0d1117" }}>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: "linear-gradient(135deg, #58a6ff, #a78bfa)" }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white"
            strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
        </div>
        <div>
          <h2 className="text-base font-semibold" style={{ color: "#f0f6fc" }}>
            PriorIQ Triage
          </h2>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full" style={{ background: "#3fb950" }} />
            <span className="text-xs" style={{ color: "#8b949e" }}>Active</span>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-4"
        style={{ background: "#080c12" }}>
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {isStreaming && messages[messages.length - 1]?.content === "" && (
          <TypingIndicator />
        )}
      </div>

      {/* Input Bar */}
      <div className="px-6 py-4 border-t" style={{ borderColor: "#21262d", background: "#0d1117" }}>
        <div className="flex gap-3 max-w-3xl mx-auto">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Describe your symptoms..."
            disabled={isStreaming}
            className="flex-1 px-5 py-4 rounded-xl text-base border outline-none transition-all focus:ring-2 disabled:opacity-50"
            style={{
              background: "#161b22",
              borderColor: "#21262d",
              color: "#f0f6fc",
            }}
            autoFocus
          />
          <button
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            className="px-6 py-4 rounded-xl font-semibold transition-all hover:scale-105 active:scale-95 disabled:opacity-40 disabled:hover:scale-100 cursor-pointer"
            style={{
              background: "linear-gradient(135deg, #58a6ff, #a78bfa)",
              color: "#fff",
            }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Message Bubble ─────────────────────────────────────────────────────── */

function MessageBubble({ message }: { message: ChatMessage }) {
  const isAgent = message.role === "assistant";

  return (
    <div className={`flex ${isAgent ? "justify-start" : "justify-end"} max-w-3xl mx-auto`}>
      <div className={`flex gap-3 max-w-[80%] ${isAgent ? "" : "flex-row-reverse"}`}>
        {/* Avatar */}
        {isAgent && (
          <div className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center mt-1"
            style={{ background: "linear-gradient(135deg, #58a6ff, #a78bfa)" }}>
            <span className="text-xs font-bold text-white">P</span>
          </div>
        )}

        {/* Bubble */}
        <div
          className="px-5 py-3.5 rounded-2xl text-base leading-relaxed"
          style={{
            background: isAgent ? "#0d1a2e" : "#1a2332",
            border: isAgent ? "1px solid #1e3a5f" : "1px solid transparent",
            color: "#f0f6fc",
            borderRadius: isAgent
              ? "4px 20px 20px 20px"
              : "20px 4px 20px 20px",
          }}>
          {message.content}
          {message.isStreaming && (
            <span className="inline-block w-1.5 h-5 ml-1 rounded-sm animate-pulse"
              style={{ background: "#58a6ff", verticalAlign: "text-bottom" }} />
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Typing Indicator ───────────────────────────────────────────────────── */

function TypingIndicator() {
  return (
    <div className="flex justify-start max-w-3xl mx-auto">
      <div className="flex gap-3">
        <div className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center"
          style={{ background: "linear-gradient(135deg, #58a6ff, #a78bfa)" }}>
          <span className="text-xs font-bold text-white">P</span>
        </div>
        <div className="px-5 py-4 rounded-2xl flex gap-1.5 items-center"
          style={{ background: "#0d1a2e", border: "1px solid #1e3a5f", borderRadius: "4px 20px 20px 20px" }}>
          <span className="typing-dot w-2.5 h-2.5 rounded-full" style={{ background: "#58a6ff" }} />
          <span className="typing-dot w-2.5 h-2.5 rounded-full" style={{ background: "#58a6ff" }} />
          <span className="typing-dot w-2.5 h-2.5 rounded-full" style={{ background: "#58a6ff" }} />
        </div>
      </div>
    </div>
  );
}
