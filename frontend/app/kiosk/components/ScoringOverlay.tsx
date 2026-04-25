"use client";

import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import type { TriageResult } from "../types";
import { URGENCY_COLORS } from "../types";

interface Props {
  result: TriageResult;
  onComplete: () => void;
}

export default function ScoringOverlay({ result, onComplete }: Props) {
  const t = useTranslations("kiosk");
  const [phase, setPhase] = useState<"counting" | "reveal">("counting");
  const [displayScore, setDisplayScore] = useState(0);
  const [flagsVisible, setFlagsVisible] = useState(0);
  const color = URGENCY_COLORS[result.urgency_level] || "#58a6ff";

  useEffect(() => {
    const target = result.urgency_score;
    const duration = 1500;
    const start = performance.now();
    function tick(now: number) {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplayScore(Math.round(eased * target));
      if (p < 1) requestAnimationFrame(tick);
      else setTimeout(() => setPhase("reveal"), 300);
    }
    requestAnimationFrame(tick);
  }, [result.urgency_score]);

  useEffect(() => {
    if (phase !== "reveal") return;
    let idx = 0;
    const iv = setInterval(() => {
      idx++;
      setFlagsVisible(idx);
      if (idx >= result.reasoning_trace.length) {
        clearInterval(iv);
        setTimeout(onComplete, 1200);
      }
    }, 150);
    return () => clearInterval(iv);
  }, [phase, result.reasoning_trace.length, onComplete]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(8,12,18,0.95)", backdropFilter: "blur(20px)" }}>
      <div className="text-center fade-in-up">
        {phase === "counting" && (
          <p className="text-lg mb-8 tracking-widest uppercase font-medium"
            style={{ color: "#8b949e" }}>{t("scoring")}</p>
        )}

        <div className="relative inline-flex items-center justify-center mb-8">
          <div className="absolute w-48 h-48 rounded-full pulse-ring"
            style={{ border: `2px solid ${color}`, opacity: 0.3 }} />
          <div className="w-36 h-36 rounded-full flex items-center justify-center score-glow"
            style={{
              background: `radial-gradient(circle, ${color}22 0%, transparent 70%)`,
              border: `3px solid ${color}`,
            }}>
            <span className="text-6xl font-bold tabular-nums"
              style={{ color, fontFamily: "JetBrains Mono, monospace" }}>
              {displayScore}
            </span>
          </div>
        </div>

        {phase === "reveal" && (
          <>
            <div className="fade-in-up mb-8">
              <span className="inline-block px-6 py-2.5 rounded-full text-lg font-bold tracking-wider uppercase"
                style={{ background: `${color}20`, color, border: `2px solid ${color}` }}>
                {result.urgency_level}
              </span>
              <p className="text-base mt-4 max-w-md mx-auto" style={{ color: "#8b949e" }}>
                {result.presenting_complaint}
              </p>
            </div>
            <div className="space-y-2 max-w-md mx-auto">
              {result.reasoning_trace.map((flag, i) => (
                <div key={i}
                  className={`flex items-center gap-3 px-5 py-3 rounded-xl text-left ${i < flagsVisible ? "flag-enter" : "opacity-0"}`}
                  style={{ background: "#161b22", border: "1px solid #21262d", animationDelay: `${i * 150}ms` }}>
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
                  <span className="text-sm" style={{ color: "#f0f6fc" }}>{flag}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
