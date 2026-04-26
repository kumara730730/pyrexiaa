"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslations } from "next-intl";
import type { ChatMessage } from "../types";
import VoiceMicButton from "./VoiceMicButton";

interface Props {
  messages: ChatMessage[];
  isStreaming: boolean;
  onSend: (text: string, voiceDistressScore?: number) => void;
  /** Language for voice recognition — maps to SpeechRecognition lang codes */
  language?: string;
}

export default function ChatPanel({ messages, isStreaming, onSend, language = "en" }: Props) {
  const t = useTranslations("kiosk");
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const userClickedElsewhereRef = useRef(false);

  // Auto-scroll to bottom — preserve input focus after scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    // Re-focus input after scroll if user hasn't deliberately clicked elsewhere
    if (!userClickedElsewhereRef.current) {
      inputRef.current?.focus();
    }
  }, [messages]);

  // Re-focus input when streaming ends
  useEffect(() => {
    if (!isStreaming) {
      userClickedElsewhereRef.current = false;
      inputRef.current?.focus();
    }
  }, [isStreaming]);

  // Track if user deliberately clicked outside the input (e.g. on mic or send button)
  // so we don't fight the user's intent
  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (inputRef.current && !inputRef.current.contains(e.target as Node)) {
        userClickedElsewhereRef.current = true;
      } else {
        userClickedElsewhereRef.current = false;
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, []);

  function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    userClickedElsewhereRef.current = false;
    onSend(trimmed);
    setInput("");
    inputRef.current?.focus();
  }

  // Voice transcript → fill input → auto-send with distress score
  const handleVoiceTranscript = useCallback(
    (text: string, distressScore: number) => {
      if (!text.trim() || isStreaming) return;
      setInput(text);
      userClickedElsewhereRef.current = false;
      // Auto-send with distress score after a brief visual delay
      setTimeout(() => {
        onSend(text.trim(), distressScore);
        setInput("");
        inputRef.current?.focus();
      }, 300);
    },
    [isStreaming, onSend]
  );

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 py-4 border-b"
        style={{ borderColor: "#21262d", background: "#0d1117" }}>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: "var(--color-accent-teal)" }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white"
            strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
        </div>
        <div>
          <h2 className="text-base font-semibold" style={{ color: "var(--color-text-primary)" }}>
            {t("triage_header")}
          </h2>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full" style={{ background: "#3fb950" }} />
            <span className="text-xs" style={{ color: "#8b949e" }}>{t("active")}</span>
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
        <div className="flex gap-3 max-w-3xl mx-auto items-center">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder={t("chat_placeholder")}
            disabled={isStreaming}
            className="flex-1 px-5 py-4 rounded-xl text-base border outline-none transition-all focus:ring-2 disabled:opacity-50"
            style={{
              background: "#161b22",
              borderColor: "#21262d",
              color: "var(--color-text-primary)",
              "--tw-ring-color": "var(--color-accent-teal)",
            } as React.CSSProperties}
            autoFocus
          />

          {/* Voice Mic Button — progressive enhancement, hides if unsupported */}
          <VoiceMicButton
            language={language}
            onTranscriptComplete={handleVoiceTranscript}
            disabled={isStreaming}
          />

          <button
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            className="px-6 py-4 rounded-xl font-semibold transition-all hover:scale-[0.98] active:scale-95 disabled:opacity-40 cursor-pointer"
            style={{
              background: "var(--color-accent-teal)",
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
            style={{ background: "var(--color-accent-teal)" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </div>
        )}

        {/* Bubble */}
        <div
          className="px-5 py-3.5 rounded-2xl text-base leading-relaxed"
          style={{
            background: isAgent ? "var(--color-agent-bubble)" : "var(--color-patient-bubble)",
            border: isAgent ? "1px solid var(--color-agent-border)" : "1px solid transparent",
            color: "var(--color-text-primary)",
            borderRadius: isAgent
              ? "4px 20px 20px 20px"
              : "20px 4px 20px 20px",
          }}>
          {message.content}
          {message.isStreaming && (
            <span className="inline-block w-1.5 h-5 ml-1 rounded-sm animate-pulse"
              style={{ background: "var(--color-accent-teal)", verticalAlign: "text-bottom" }} />
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
          style={{ background: "var(--color-accent-teal)" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
        </div>
        <div className="px-5 py-4 rounded-2xl flex gap-1.5 items-center"
          style={{ background: "var(--color-agent-bubble)", border: "1px solid var(--color-agent-border)", borderRadius: "4px 20px 20px 20px" }}>
          <span className="typing-dot w-2.5 h-2.5 rounded-full" style={{ background: "var(--color-accent-teal)" }} />
          <span className="typing-dot w-2.5 h-2.5 rounded-full" style={{ background: "var(--color-accent-teal)" }} />
          <span className="typing-dot w-2.5 h-2.5 rounded-full" style={{ background: "var(--color-accent-teal)" }} />
        </div>
      </div>
    </div>
  );
}
