"use client";

import { useState, useCallback } from "react";
import type { Stage, RegistrationData, TriageResult } from "./types";
import { useTriageChat } from "./hooks";
import RegistrationForm from "./components/RegistrationForm";
import ChatPanel from "./components/ChatPanel";
import ScoringOverlay from "./components/ScoringOverlay";
import DoctorCard from "./components/DoctorCard";

export default function KioskPage() {
  const [stage, setStage] = useState<Stage>("registration");
  const [registration, setRegistration] = useState<RegistrationData | null>(null);
  const { messages, isStreaming, triageResult, sendMessage, startSession } = useTriageChat();

  // Stage 1 → 2
  const handleRegistration = useCallback(
    async (data: RegistrationData) => {
      setRegistration(data);
      await startSession(data.name, data.language);
      setStage("chat");
    },
    [startSession]
  );

  // Stage 2 → 3 (auto-triggered when triageResult appears)
  const handleSend = useCallback(
    (text: string, voiceDistressScore?: number) => {
      if (registration) sendMessage(text, registration.language, voiceDistressScore);
    },
    [registration, sendMessage]
  );

  // Stage 3 → 4
  const handleScoringComplete = useCallback(() => {
    setStage("assignment");
  }, []);

  // Detect triage result from chat hook → move to scoring
  if (triageResult && stage === "chat") {
    // Use setTimeout to avoid setState during render
    setTimeout(() => setStage("scoring"), 0);
  }

  return (
    <main className="min-h-screen" style={{ background: "#080c12" }}>
      {stage === "registration" && (
        <RegistrationForm onComplete={handleRegistration} />
      )}

      {stage === "chat" && (
        <ChatPanel
          messages={messages}
          isStreaming={isStreaming}
          onSend={handleSend}
          language={registration?.language}
        />
      )}

      {stage === "scoring" && triageResult && (
        <ScoringOverlay
          result={triageResult}
          onComplete={handleScoringComplete}
        />
      )}

      {stage === "assignment" && triageResult && registration && (
        <DoctorCard
          result={triageResult}
          sessionId="demo-session"
          patientName={registration.name}
        />
      )}
    </main>
  );
}
