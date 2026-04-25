"use client";

import { useState, useCallback, useRef } from "react";
import type { ChatMessage, TriageResult, Language } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

/* ── Client-side hard-rule keywords (mirrors backend) ─────────────────── */

const CRITICAL_KEYWORDS: string[] = [
  // Cardiac
  "chest pain", "chest tightness", "chest pressure", "heart attack",
  "left arm pain", "left arm heavy", "jaw pain", "radiating pain",
  // Respiratory
  "can't breathe", "cannot breathe", "not breathing", "difficulty breathing",
  "breathing stopped", "choking", "airway",
  // Neurological
  "stroke", "seizure", "unconscious", "unresponsive", "collapsed",
  "sudden numbness", "face drooping", "arm weakness", "speech slurred",
  // Trauma / Bleeding
  "severe bleeding", "blood everywhere", "deep cut", "stabbed", "shot",
  // Allergic
  "anaphylaxis", "severe allergic", "epipen", "throat closing",
  "tongue swelling",
  // Overdose
  "overdose", "took too many pills", "poisoning",
];

function checkHardRulesClient(text: string): string[] {
  const lower = text.toLowerCase();
  return CRITICAL_KEYWORDS.filter((kw) => lower.includes(kw));
}

/**
 * Hook to manage SSE-streamed triage chat with the backend.
 */
export function useTriageChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [triageResult, setTriageResult] = useState<TriageResult | null>(null);
  const [isEmergency, setIsEmergency] = useState(false);
  const sessionIdRef = useRef<string | null>(null);

  const startSession = useCallback(
    async (name: string, language: Language, chiefComplaint: string) => {
      setIsStreaming(true);
      try {
        const response = await fetch(`${API_BASE}/triage/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            patient_id: "00000000-0000-0000-0000-000000000000", // Placeholder if no registration
            clinic_id: "demo-clinic",
            chief_complaint: chiefComplaint,
            language,
          }),
        });

        if (!response.ok) throw new Error("Failed to start triage");
        const data = await response.json();
        
        sessionIdRef.current = data.session_id;
        
        if (data.hard_rule_triggered) {
          setIsEmergency(true);
          setTriageResult({
            urgency_score: data.urgency_score,
            urgency_level: data.urgency_level,
            reasoning_trace: data.reasoning_trace,
            presenting_complaint: chiefComplaint,
            red_flags: [],
            suggested_doctor_questions: [],
            recommended_doctor_specialty: "Emergency",
          });
        } else {
          setMessages([
            { role: "user", content: chiefComplaint },
            { role: "assistant", content: data.initial_question }
          ]);
        }
      } catch (error) {
        console.error("Start session failed:", error);
        setMessages([{ role: "assistant", content: "I'm sorry, I'm having trouble starting the session. Please try again." }]);
      } finally {
        setIsStreaming(false);
      }
    },
    []
  );

  const sendMessage = useCallback(
    async (text: string, language: Language, voiceDistressScore?: number) => {
      // ── Client-side hard-rule gate ─────────────────────────────────
      const matchedKeywords = checkHardRulesClient(text);
      if (matchedKeywords.length > 0) {
        setMessages((prev) => [...prev, { role: "user", content: text }]);
        setIsEmergency(true);
        setTriageResult({
          urgency_score: 100,
          urgency_level: "CRITICAL",
          reasoning_trace: [
            `AUTO-CRITICAL: Hard rule keyword match — ${matchedKeywords.join(", ")}`,
          ],
          presenting_complaint: text,
          red_flags: matchedKeywords,
          suggested_doctor_questions: [],
          recommended_doctor_specialty: "Emergency",
        });

        // Still try to notify the backend (fire-and-forget)
        try {
          fetch(`${API_BASE}/triage/message`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: sessionIdRef.current || "demo-session",
              message: text,
              language,
            }),
          });
        } catch {
          // Backend may be offline — kiosk already shows emergency screen
        }
        return;
      }

      // Append user message
      setMessages((prev) => [...prev, { role: "user", content: text }]);

      // Add empty assistant message for streaming
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", isStreaming: true },
      ]);
      setIsStreaming(true);

      try {
        const body = JSON.stringify({
          session_id: sessionIdRef.current || "demo-session",
          message: text,
          language,
          ...(voiceDistressScore !== undefined && { voice_distress_score: voiceDistressScore }),
        });

        const response = await fetch(`${API_BASE}/triage/message`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const contentType = response.headers.get("content-type") || "";

        // SSE stream
        if (contentType.includes("text/event-stream")) {
          const reader = response.body?.getReader();
          const decoder = new TextDecoder();
          let accumulated = "";

          if (reader) {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const chunk = decoder.decode(value, { stream: true });
              const lines = chunk.split("\n");

              for (const line of lines) {
                if (line.startsWith("data:")) {
                  const raw = line.slice(5).trim();
                  if (!raw) continue;
                  try {
                    const parsed = JSON.parse(raw);

                    if (parsed.token) {
                      accumulated += parsed.token;
                      setMessages((prev) => {
                        const updated = [...prev];
                        updated[updated.length - 1] = {
                          role: "assistant",
                          content: accumulated,
                          isStreaming: true,
                        };
                        return updated;
                      });
                    }

                    if (parsed.full_response) {
                      accumulated = parsed.full_response;
                    }
                  } catch {
                    // skip malformed lines
                  }
                }
              }
            }
          }

          // Finalize the message
          const finalContent = accumulated;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: finalContent,
              isStreaming: false,
            };
            return updated;
          });

          // Check if it's JSON triage output
          const trimmed = finalContent.trim();
          if (trimmed.startsWith("{") && trimmed.includes("urgency_score")) {
            try {
              const result: TriageResult = JSON.parse(trimmed);
              // Remove the JSON message from chat
              setMessages((prev) => prev.slice(0, -1));
              setTriageResult(result);
            } catch {
              // Not valid JSON, keep as message
            }
          }
        } else {
          // JSON response (hard-rule triggered on backend)
          const data = await response.json();
          if (data.hard_rule_triggered) {
            setIsEmergency(true);
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: "⚠️ Immediate attention required.",
                isStreaming: false,
              };
              return updated;
            });
            setTriageResult({
              urgency_score: data.urgency_score,
              urgency_level: data.urgency_level,
              reasoning_trace: data.reasoning_trace || [],
              presenting_complaint: text,
              red_flags: data.matched_keywords || data.reasoning_trace || [],
              suggested_doctor_questions: [],
              recommended_doctor_specialty: "Emergency",
            });
          }
        }
      } catch (error) {
        console.error("Send message failed:", error);
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: "I'm sorry, I'm having trouble connecting to the medical assistant. Please check your connection or wait a moment.",
            isStreaming: false,
          };
          return updated;
        });
      } finally {
        setIsStreaming(false);
      }
    },
    []
  );

  return { messages, isStreaming, triageResult, isEmergency, sendMessage, startSession, sessionIdRef };
}

/* ── Helpers ─────────────────────────────────────────────────────────── */

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
