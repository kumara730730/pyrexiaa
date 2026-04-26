"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import type { TriageResult } from "../types";

interface Props {
  result: TriageResult;
  onComplete: () => void;
}

export default function ScoringOverlay({ result, onComplete }: Props) {
  const t = useTranslations("kiosk");

  // Auto-transition after 2.5 seconds
  useEffect(() => {
    const timer = setTimeout(onComplete, 2500);
    return () => clearTimeout(timer);
  }, [onComplete]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(8,12,18,0.95)", backdropFilter: "blur(20px)" }}
    >
      <div className="text-center fade-in-up">
        {/* Pulsing ring animation */}
        <div className="relative inline-flex items-center justify-center mb-10">
          <div
            className="absolute w-28 h-28 rounded-full animate-ping"
            style={{
              background: "var(--color-accent-teal)",
              opacity: 0.08,
            }}
          />
          <div
            className="absolute w-20 h-20 rounded-full animate-pulse"
            style={{
              border: "2px solid var(--color-accent-teal)",
              opacity: 0.3,
            }}
          />
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center"
            style={{
              background: "rgba(56, 189, 176, 0.1)",
              border: "2px solid var(--color-accent-teal)",
            }}
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--color-accent-teal)"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
          </div>
        </div>

        {/* Processing text */}
        <p
          className="text-lg tracking-widest uppercase font-medium"
          style={{ color: "#8b949e" }}
        >
          {t("scoring")}
        </p>

        {/* Animated dots */}
        <div className="flex justify-center gap-2 mt-6">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-2.5 h-2.5 rounded-full"
              style={{
                background: "var(--color-accent-teal)",
                animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite`,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
