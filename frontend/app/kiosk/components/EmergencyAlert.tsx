"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

interface Props {
  patientName: string;
}

/**
 * Full-screen emergency alert shown on the patient kiosk when a hard-rule
 * keyword triggers CRITICAL status. Pulses red to convey urgency while the
 * message reassures the patient to stay seated.
 */
export default function EmergencyAlert({ patientName }: Props) {
  const t = useTranslations("kiosk");
  const [pulse, setPulse] = useState(true);

  // Pulse animation toggle
  useEffect(() => {
    const id = setInterval(() => setPulse((p) => !p), 1200);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className="flex items-center justify-center min-h-screen p-6"
      style={{
        background: pulse
          ? "radial-gradient(ellipse at center, #2d0a0a 0%, #0d0101 70%)"
          : "radial-gradient(ellipse at center, #1a0606 0%, #080202 70%)",
        transition: "background 1.2s ease-in-out",
      }}
    >
      <div className="text-center max-w-lg fade-in-up">
        {/* Pulsing emergency icon */}
        <div className="flex justify-center mb-8">
          <div
            className="w-28 h-28 rounded-full flex items-center justify-center"
            style={{
              background: pulse
                ? "rgba(248, 81, 73, 0.25)"
                : "rgba(248, 81, 73, 0.12)",
              boxShadow: pulse
                ? "0 0 60px rgba(248, 81, 73, 0.4), 0 0 120px rgba(248, 81, 73, 0.15)"
                : "0 0 30px rgba(248, 81, 73, 0.2)",
              transition: "all 1.2s ease-in-out",
            }}
          >
            <svg
              width="56"
              height="56"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#f85149"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </div>
        </div>

        {/* Title */}
        <h1
          className="text-4xl font-bold mb-4 tracking-tight"
          style={{
            color: "#f85149",
            fontFamily: "Inter, sans-serif",
            textShadow: "0 0 30px rgba(248, 81, 73, 0.3)",
          }}
        >
          {t("emergency_title")}
        </h1>

        {/* Patient name */}
        <p
          className="text-xl mb-6"
          style={{ color: "#f0f6fc", fontFamily: "Inter, sans-serif" }}
        >
          {patientName}
        </p>

        {/* Reassurance message */}
        <div
          className="rounded-2xl p-6 border mb-8"
          style={{
            background: "rgba(248, 81, 73, 0.06)",
            borderColor: "rgba(248, 81, 73, 0.2)",
          }}
        >
          <p
            className="text-lg leading-relaxed"
            style={{ color: "#f0f6fc", fontFamily: "Inter, sans-serif" }}
          >
            {t("emergency_message")}
          </p>
        </div>

        {/* Status indicator */}
        <div className="flex items-center justify-center gap-3">
          <div
            className="w-3 h-3 rounded-full"
            style={{
              background: "#f85149",
              boxShadow: pulse
                ? "0 0 12px rgba(248, 81, 73, 0.8)"
                : "0 0 6px rgba(248, 81, 73, 0.4)",
              transition: "box-shadow 1.2s ease-in-out",
            }}
          />
          <span
            className="text-sm font-medium uppercase tracking-widest"
            style={{ color: "#f85149" }}
          >
            {t("active")}
          </span>
        </div>
      </div>
    </div>
  );
}
