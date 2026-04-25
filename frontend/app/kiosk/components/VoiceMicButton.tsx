"use client";

import { useCallback } from "react";
import { useVoiceInput } from "../hooks/useVoiceInput";

/* ── Props ─────────────────────────────────────────────────────────────────── */

interface VoiceMicButtonProps {
  /** Language code: 'en' | 'hi' | 'kn' | 'ta' | 'te' */
  language?: string;
  /** Called when speech recognition completes with transcript + distress score */
  onTranscriptComplete: (text: string, score: number) => void;
  /** Whether to disable the button (e.g. while AI is streaming) */
  disabled?: boolean;
}

/* ── Component ─────────────────────────────────────────────────────────────── */

export default function VoiceMicButton({
  language = "en",
  onTranscriptComplete,
  disabled = false,
}: VoiceMicButtonProps) {
  const {
    isSupported,
    isListening,
    transcript,
    distressScore,
    startListening,
    stopListening,
  } = useVoiceInput(language, {
    onComplete: onTranscriptComplete,
  });

  // Graceful fallback: hide entirely if unsupported
  if (!isSupported) return null;

  const handleClick = useCallback(() => {
    if (disabled) return;
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, disabled, startListening, stopListening]);

  return (
    <div className="voice-mic-wrapper" style={{ position: "relative" }}>
      {/* Pulsing rings when listening */}
      {isListening && (
        <>
          <span className="voice-pulse-ring voice-pulse-ring-1" />
          <span className="voice-pulse-ring voice-pulse-ring-2" />
        </>
      )}

      {/* Main button */}
      <button
        id="voice-mic-button"
        type="button"
        onClick={handleClick}
        disabled={disabled && !isListening}
        aria-label={isListening ? "Stop recording" : "Start voice input"}
        className={`voice-mic-btn ${isListening ? "voice-mic-btn--active" : ""}`}
        style={{
          position: "relative",
          zIndex: 2,
          width: 52,
          height: 52,
          borderRadius: "50%",
          border: isListening ? "2px solid #f85149" : "2px solid #30363d",
          background: isListening
            ? "radial-gradient(circle, #2d1114 0%, #161b22 100%)"
            : "#161b22",
          color: isListening ? "#f85149" : "#8b949e",
          cursor: disabled && !isListening ? "not-allowed" : "pointer",
          opacity: disabled && !isListening ? 0.4 : 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "all 0.2s ease",
          flexShrink: 0,
        }}
      >
        {/* Microphone SVG icon */}
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            transition: "transform 0.2s ease",
            transform: isListening ? "scale(1.1)" : "scale(1)",
          }}
        >
          <rect x="9" y="1" width="6" height="12" rx="3" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="23" />
          <line x1="8" y1="23" x2="16" y2="23" />
        </svg>
      </button>

      {/* Live transcript preview tooltip */}
      {isListening && transcript && (
        <div className="voice-transcript-preview">
          <span className="voice-transcript-text">{transcript}</span>
          {distressScore > 0 && (
            <span
              className="voice-distress-badge"
              style={{
                background:
                  distressScore >= 7
                    ? "#f85149"
                    : distressScore >= 4
                    ? "#f0883e"
                    : "#d29922",
              }}
            >
              ⚡ {distressScore}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
