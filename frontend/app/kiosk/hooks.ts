"use client";

import { useState, useCallback, useRef } from "react";
import type { ChatMessage, TriageResult, Language, RegistrationData } from "./types";

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
  const patientIdRef = useRef<string>("00000000-0000-0000-0000-000000000000");
  const clinicIdRef = useRef<string>("demo-clinic");

  const startSession = useCallback(
    async (data: RegistrationData) => {
      setIsStreaming(true);
      try {
        const regResponse = await fetch(`${API_BASE}/patients/kiosk-register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: data.name,
            age: data.age,
            gender: data.gender,
            language: data.language,
            clinic_id: "demo-clinic"
          }),
        });

        if (!regResponse.ok) {
          console.warn("Kiosk registration failed, using fallback placeholders.");
        } else {
          const regData = await regResponse.json();
          patientIdRef.current = regData.id;
          if (regData.clinic_id) {
            clinicIdRef.current = regData.clinic_id;
          }
        }

        const response = await fetch(`${API_BASE}/triage/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            patient_id: patientIdRef.current,
            clinic_id: clinicIdRef.current,
            chief_complaint: data.symptoms,
            language: data.language,
          }),
        });

        if (!response.ok) {
          const errorBody = await response.text().catch(() => "");
          console.error(`Triage start failed: HTTP ${response.status}`, errorBody);
          throw new Error(`Failed to start triage (HTTP ${response.status})`);
        }
        const sessionData = await response.json();
        
        sessionIdRef.current = sessionData.session_id;
        
        if (sessionData.hard_rule_triggered) {
          setIsEmergency(true);
          setTriageResult({
            urgency_score: sessionData.urgency_score,
            urgency_level: sessionData.urgency_level,
            reasoning_trace: sessionData.reasoning_trace,
            presenting_complaint: data.symptoms,
            red_flags: [],
            suggested_doctor_questions: [],
            recommended_doctor_specialty: "Emergency",
          });
        } else {
          setMessages([
            { role: "user", content: data.symptoms },
            { role: "assistant", content: sessionData.initial_question }
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
              patient_id: patientIdRef.current,
              clinic_id: clinicIdRef.current,
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
          patient_id: patientIdRef.current,
          clinic_id: clinicIdRef.current,
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
          let currentEvent = "message";
          let isScoreEvent = false;
          let isScoringJson = false;

          if (reader) {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const chunk = decoder.decode(value, { stream: true });
              const lines = chunk.split("\n");

              for (const line of lines) {
                if (line.startsWith("event:")) {
                  currentEvent = line.slice(6).trim();
                } else if (line.startsWith("data:")) {
                  const raw = line.slice(5).trim();
                  if (!raw) continue;
                  try {
                    const parsed = JSON.parse(raw);

                    if (currentEvent === "token" && parsed.token) {
                      accumulated += parsed.token;

                      // Detect if the streamed content is a scoring JSON response.
                      // If so, suppress it from the chat bubble entirely.
                      const trimmed = accumulated.trimStart();
                      if (
                        !isScoringJson &&
                        (trimmed.startsWith("{") || trimmed.startsWith("```")) &&
                        trimmed.includes("urgency_score")
                      ) {
                        isScoringJson = true;
                        // Clear the chat bubble so no JSON is visible
                        setMessages((prev) => {
                          const updated = [...prev];
                          if (updated.length > 0 && updated[updated.length - 1].role === "assistant") {
                            updated[updated.length - 1] = {
                              role: "assistant",
                              content: "",
                              isStreaming: true,
                            };
                          }
                          return updated;
                        });
                      }

                      // Only update the chat bubble if this is NOT scoring JSON
                      if (!isScoringJson) {
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
                    } else if (currentEvent === "score") {
                      isScoreEvent = true;
                      isScoringJson = true;
                      setTriageResult(parsed);
                      setMessages((prev) => {
                        const updated = [...prev];
                        if (updated.length > 0 && updated[updated.length - 1].role === "assistant") {
                          return updated.slice(0, -1);
                        }
                        return updated;
                      });
                    } else if (currentEvent === "done" && parsed.full_response) {
                      accumulated = parsed.full_response;
                    }
                  } catch {
                    // skip malformed lines
                  }
                }
              }
            }
          }

          // Fallback: if the stream completed with scoring JSON but no explicit
          // score event was emitted, parse the JSON manually and set triageResult.
          if (!isScoreEvent && isScoringJson) {
            try {
              let jsonText = accumulated.trim();
              // Strip markdown code fences if present
              if (jsonText.startsWith("```")) {
                const lines = jsonText.split("\n");
                const jsonLines: string[] = [];
                let inBlock = false;
                for (const l of lines) {
                  if (l.trim().startsWith("```") && !inBlock) { inBlock = true; continue; }
                  else if (l.trim().startsWith("```") && inBlock) { break; }
                  else if (inBlock) { jsonLines.push(l); }
                }
                jsonText = jsonLines.join("\n").trim();
              }
              const scoreData = JSON.parse(jsonText);
              if (scoreData.urgency_score !== undefined) {
                isScoreEvent = true;
                setTriageResult(scoreData);
                setMessages((prev) => {
                  const updated = [...prev];
                  if (updated.length > 0 && updated[updated.length - 1].role === "assistant") {
                    return updated.slice(0, -1);
                  }
                  return updated;
                });
              }
            } catch {
              // Not valid JSON despite looking like it — treat as normal text
              isScoringJson = false;
            }
          }

          // Finalize the message if it wasn't a score event
          if (!isScoreEvent && !isScoringJson) {
            setMessages((prev) => {
              const updated = [...prev];
              if (updated.length > 0 && updated[updated.length - 1].role === "assistant") {
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: accumulated,
                  isStreaming: false,
                };
              }
              return updated;
            });
          } else if (isScoringJson && !isScoreEvent) {
            // Scoring JSON detected but couldn't parse — remove empty bubble
            setMessages((prev) => {
              const updated = [...prev];
              if (updated.length > 0 && updated[updated.length - 1].role === "assistant" && !updated[updated.length - 1].content) {
                return updated.slice(0, -1);
              }
              return updated;
            });
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

  return { messages, isStreaming, triageResult, isEmergency, sendMessage, startSession, sessionIdRef, patientIdRef, clinicIdRef };
}

/* ── Helpers ─────────────────────────────────────────────────────────── */
