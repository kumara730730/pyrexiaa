"use client";

import { useState, useEffect, useCallback } from "react";
import { useTranslations } from "next-intl";
import type { TriageResult, DoctorAssignment } from "../types";
import { URGENCY_COLORS } from "../types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

interface Props {
  result: TriageResult;
  sessionId: string;
  patientName: string;
}

const DEMO_DOCTORS: Record<string, DoctorAssignment> = {
  "General Practice": {
    doctor_name: "Dr. Ananya Sharma",
    doctor_photo: "",
    specialty: "General Practice",
    room_number: "G-12",
    estimated_wait_minutes: 8,
    queue_position: 3,
  },
  Cardiology: {
    doctor_name: "Dr. Rajesh Menon",
    doctor_photo: "",
    specialty: "Cardiology",
    room_number: "C-04",
    estimated_wait_minutes: 15,
    queue_position: 2,
  },
  Neurology: {
    doctor_name: "Dr. Priya Nair",
    doctor_photo: "",
    specialty: "Neurology",
    room_number: "N-07",
    estimated_wait_minutes: 12,
    queue_position: 4,
  },
};

export default function DoctorCard({ result, sessionId, patientName }: Props) {
  const t = useTranslations("kiosk");
  const [assignment, setAssignment] = useState<DoctorAssignment | null>(null);
  const [loading, setLoading] = useState(true);
  const color = URGENCY_COLORS[result.urgency_level] || "#58a6ff";

  const fetchAssignment = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/queue/assignment/${sessionId}`);
      if (res.ok) {
        setAssignment(await res.json());
        setLoading(false);
        return;
      }
    } catch {}
    // Fallback: demo data
    const spec = result.recommended_doctor_specialty || "General Practice";
    const doc = DEMO_DOCTORS[spec] || DEMO_DOCTORS["General Practice"];
    setAssignment(doc);
    setLoading(false);
  }, [sessionId, result.recommended_doctor_specialty]);

  useEffect(() => {
    fetchAssignment();
    const iv = setInterval(fetchAssignment, 30000);
    return () => clearInterval(iv);
  }, [fetchAssignment]);

  if (loading || !assignment) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "#58a6ff", borderTopColor: "transparent" }} />
      </div>
    );
  }

  const initials = assignment.doctor_name.split(" ").map(w => w[0]).join("").slice(0, 2);

  return (
    <div className="flex items-center justify-center min-h-screen p-6">
      <div className="w-full max-w-lg fade-in-up">
        {/* Success checkmark */}
        <div className="text-center mb-8">
          <div className="w-20 h-20 rounded-full mx-auto flex items-center justify-center mb-4"
            style={{ background: `${color}15`, border: `2px solid ${color}` }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
              stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold" style={{ color: "#f0f6fc" }}>
            {t("checkin_complete")}
          </h2>
          <p className="text-base mt-1" style={{ color: "#8b949e" }}>
            {t("added_to_queue", { name: patientName })}
          </p>
        </div>

        {/* Doctor Card */}
        <div className="rounded-2xl p-6 border"
          style={{ background: "#0d1117", borderColor: "#21262d" }}>
          <div className="flex items-center gap-4 mb-6">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-xl font-bold"
              style={{ background: "linear-gradient(135deg, #58a6ff, #a78bfa)", color: "#fff" }}>
              {initials}
            </div>
            <div>
              <h3 className="text-xl font-semibold" style={{ color: "#f0f6fc" }}>
                {assignment.doctor_name}
              </h3>
              <p className="text-sm" style={{ color: "#58a6ff" }}>
                {assignment.specialty}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-6">
            <InfoTile label={t("room")} value={assignment.room_number} icon="🚪" />
            <InfoTile label={t("wait")} value={`~${assignment.estimated_wait_minutes} min`} icon="⏱" />
            <InfoTile label={t("position")} value={`#${assignment.queue_position}`} icon="📋" />
          </div>

          {/* Urgency badge */}
          <div className="flex items-center gap-3 px-4 py-3 rounded-xl"
            style={{ background: `${color}10`, border: `1px solid ${color}30` }}>
            <div className="w-3 h-3 rounded-full" style={{ background: color }} />
            <span className="text-sm font-medium" style={{ color }}>
              {t("priority")}: {result.urgency_level}
            </span>
            <span className="text-sm ml-auto" style={{ color: "#8b949e" }}>
              {t("score")}: {result.urgency_score}
            </span>
          </div>
        </div>

        {/* Seat message */}
        <div className="mt-6 px-5 py-4 rounded-xl text-center border"
          style={{ background: "#0d1117", borderColor: "#21262d" }}>
          <p className="text-base" style={{ color: "#8b949e" }}>
            {t("seat_message")}
          </p>
          <p className="text-xs mt-2" style={{ color: "#484f58" }}>
            {t("wait_updates")}
          </p>
        </div>

        {/* New Check-In */}
        <button
          onClick={() => window.location.reload()}
          className="w-full mt-6 py-4 rounded-xl text-base font-medium border cursor-pointer transition-all hover:border-[#58a6ff]"
          style={{ background: "transparent", borderColor: "#21262d", color: "#8b949e" }}>
          {t("new_checkin")}
        </button>
      </div>
    </div>
  );
}

function InfoTile({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <div className="text-center px-3 py-3 rounded-xl" style={{ background: "#161b22" }}>
      <span className="text-lg">{icon}</span>
      <p className="text-base font-semibold mt-1" style={{ color: "#f0f6fc" }}>{value}</p>
      <p className="text-xs" style={{ color: "#8b949e" }}>{label}</p>
    </div>
  );
}
