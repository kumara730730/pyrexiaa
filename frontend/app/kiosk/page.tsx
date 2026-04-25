"use client";

import { useState, useCallback } from "react";
import type { Stage, RegistrationData } from "./types";
import { useTriageChat } from "./hooks";
import RegistrationForm from "./components/RegistrationForm";
import ChatPanel from "./components/ChatPanel";
import ScoringOverlay from "./components/ScoringOverlay";
import DoctorCard from "./components/DoctorCard";
import EmergencyAlert from "./components/EmergencyAlert";

export default function KioskPage() {
  const [stage, setStage] = useState<Stage>("registration");
  const [registration, setRegistration] = useState<RegistrationData | null>(null);
  const { messages, isStreaming, triageResult, isEmergency, sendMessage, startSession, sessionIdRef } = useTriageChat();

  // Stage 1 → 2
  const handleRegistration = useCallback(
    async (data: RegistrationData) => {
      setRegistration(data);
      await startSession(data);
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

  // Detect emergency hard-rule trigger → jump straight to emergency screen
  if (isEmergency && stage === "chat") {
    setTimeout(() => setStage("emergency"), 0);
  }

  // Detect normal triage result from chat hook → move to scoring
  if (triageResult && !isEmergency && stage === "chat") {
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

      {stage === "emergency" && registration && (
        <EmergencyAlert patientName={registration.name} />
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
          sessionId={sessionIdRef.current || "demo-session"}
          patientName={registration.name}
        />
      )}
    </main>
  );
}