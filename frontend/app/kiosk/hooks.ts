"use client";

import { useState, useCallback, useRef } from "react";
import type { ChatMessage, TriageResult, Language } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

/**
 * Hook to manage SSE-streamed triage chat with the backend.
 */
export function useTriageChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [triageResult, setTriageResult] = useState<TriageResult | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const startSession = useCallback(
    async (name: string, language: Language) => {
      // Seed the first agent message
      const greeting = getGreeting(name, language);
      setMessages([{ role: "assistant", content: greeting }]);
    },
    []
  );

  const sendMessage = useCallback(
    async (text: string, language: Language, voiceDistressScore?: number) => {
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
          // JSON response (hard-rule triggered)
          const data = await response.json();
          if (data.hard_rule_triggered) {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: "I've flagged this as requiring immediate attention.",
                isStreaming: false,
              };
              return updated;
            });
            setTriageResult({
              urgency_score: data.urgency_score,
              urgency_level: data.urgency_level,
              reasoning_trace: data.reasoning_trace || [],
              presenting_complaint: text,
              red_flags: data.reasoning_trace || [],
              suggested_doctor_questions: [],
              recommended_doctor_specialty: "Emergency",
            });
          }
        }
      } catch (error) {
        // Demo fallback: simulate AI responses when backend is offline
        await simulateResponse(text, language, setMessages, setTriageResult);
      } finally {
        setIsStreaming(false);
      }
    },
    []
  );

  return { messages, isStreaming, triageResult, sendMessage, startSession, sessionIdRef };
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function getGreeting(name: string, lang: Language): string {
  const greetings: Record<Language, string> = {
    en: `Hello ${name}! I'm Pyrexia, your check-in assistant. Please describe what's brought you in today.`,
    hi: `नमस्ते ${name}! मैं Pyrexia हूँ, आपका चेक-इन सहायक। कृपया बताएं कि आज आपको क्या तकलीफ है।`,
    kn: `ನಮಸ್ಕಾರ ${name}! ನಾನು Pyrexia, ನಿಮ್ಮ ಚೆಕ್-ಇನ್ ಸಹಾಯಕ. ಇಂದು ನಿಮ್ಮನ್ನು ಇಲ್ಲಿಗೆ ತಂದಿರುವುದನ್ನು ವಿವರಿಸಿ.`,
    ta: `வணக்கம் ${name}! நான் Pyrexia, உங்கள் செக்-இன் உதவியாளர். இன்று உங்களை இங்கு கொண்டு வந்ததை விவரிக்கவும்.`,
    te: `నమస్కారం ${name}! నేను Pyrexia, మీ చెక్-ఇన్ అసిస్టెంట్. ఈరోజు మిమ్మల్ని ఇక్కడకు తీసుకొచ్చిన విషయాన్ని వివరించండి.`,
  };
  return greetings[lang];
}

// Exchange counter for demo mode
let exchangeCount = 0;

async function simulateResponse(
  userText: string,
  language: Language,
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>,
  setTriageResult: React.Dispatch<React.SetStateAction<TriageResult | null>>
) {
  exchangeCount++;

  const demoQuestions = [
    "I understand. Can you tell me when this started — was it sudden or gradual?",
    "On a scale of 1 to 10, how would you rate the severity right now?",
    "Have you noticed any other symptoms alongside this — such as dizziness, nausea, or changes in vision?",
    "Do you have any existing medical conditions or take any regular medications?",
  ];

  if (exchangeCount >= 4) {
    // Output triage JSON
    const result: TriageResult = {
      urgency_score: 62,
      urgency_level: "MODERATE",
      reasoning_trace: [
        "Symptom duration exceeds 48 hours",
        "Moderate severity rating (6/10)",
        "No red-flag features identified",
        "Stable vital sign indicators based on patient report",
      ],
      presenting_complaint: userText,
      red_flags: [],
      suggested_doctor_questions: [
        "Confirm onset timeline and progression pattern",
        "Screen for associated systemic symptoms",
        "Review current medication interactions",
      ],
      recommended_doctor_specialty: "General Practice",
    };

    // Simulate streaming delay then reveal result
    await delay(1500);
    setMessages((prev) => {
      const updated = [...prev];
      updated[updated.length - 1] = {
        role: "assistant",
        content: "Analysing your responses...",
        isStreaming: false,
      };
      return updated;
    });

    await delay(500);
    setMessages((prev) => prev.slice(0, -1));
    setTriageResult(result);
    exchangeCount = 0;
    return;
  }

  const question = demoQuestions[exchangeCount - 1] || demoQuestions[0];

  // Simulate token-by-token streaming
  for (let i = 0; i < question.length; i++) {
    await delay(15);
    const partial = question.slice(0, i + 1);
    setMessages((prev) => {
      const updated = [...prev];
      updated[updated.length - 1] = {
        role: "assistant",
        content: partial,
        isStreaming: i < question.length - 1,
      };
      return updated;
    });
  }
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
