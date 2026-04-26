"use client";

import { useState, useEffect, useCallback } from "react";
import { useTranslations } from "next-intl";
import type { TriageResult, DoctorAssignment } from "../types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

interface Props {
  result: TriageResult;
  sessionId: string;
  patientName: string;
  patientId: string;
  clinicId: string;
}

const DEMO_DOCTORS: Record<string, DoctorAssignment> = {
  "General Practice": {
    doctor_name: "Dr. Ananya Sharma",
    doctor_photo: "",
    specialty: "General Practice",
    room_number: "G-12",
    floor_number: "Ground Floor",
    department: "General Medicine",
    availability_status: "Available",
    estimated_wait_minutes: 8,
    queue_position: 3,
  },
  Cardiology: {
    doctor_name: "Dr. Rajesh Menon",
    doctor_photo: "",
    specialty: "Cardiology",
    room_number: "C-04",
    floor_number: "2nd Floor",
    department: "Cardiac Sciences",
    availability_status: "Available",
    estimated_wait_minutes: 15,
    queue_position: 2,
  },
  Neurology: {
    doctor_name: "Dr. Priya Nair",
    doctor_photo: "",
    specialty: "Neurology",
    room_number: "N-07",
    floor_number: "3rd Floor",
    department: "Neurosciences",
    availability_status: "Available",
    estimated_wait_minutes: 12,
    queue_position: 4,
  },
  Orthopaedics: {
    doctor_name: "Dr. Vikram Patel",
    doctor_photo: "",
    specialty: "Orthopaedics",
    room_number: "O-03",
    floor_number: "1st Floor",
    department: "Orthopaedic Surgery",
    availability_status: "Available",
    estimated_wait_minutes: 10,
    queue_position: 2,
  },
  Dermatology: {
    doctor_name: "Dr. Meera Krishnan",
    doctor_photo: "",
    specialty: "Dermatology",
    room_number: "D-06",
    floor_number: "1st Floor",
    department: "Dermatology",
    availability_status: "Available",
    estimated_wait_minutes: 6,
    queue_position: 1,
  },
  ENT: {
    doctor_name: "Dr. Suresh Iyer",
    doctor_photo: "",
    specialty: "ENT",
    room_number: "E-02",
    floor_number: "2nd Floor",
    department: "ENT & Head/Neck",
    availability_status: "Available",
    estimated_wait_minutes: 9,
    queue_position: 3,
  },
  Gastroenterology: {
    doctor_name: "Dr. Kavitha Rao",
    doctor_photo: "",
    specialty: "Gastroenterology",
    room_number: "GI-05",
    floor_number: "2nd Floor",
    department: "Gastro Sciences",
    availability_status: "Available",
    estimated_wait_minutes: 14,
    queue_position: 4,
  },
  Pulmonology: {
    doctor_name: "Dr. Arjun Desai",
    doctor_photo: "",
    specialty: "Pulmonology",
    room_number: "P-08",
    floor_number: "3rd Floor",
    department: "Pulmonary Medicine",
    availability_status: "Available",
    estimated_wait_minutes: 11,
    queue_position: 3,
  },
  Psychiatry: {
    doctor_name: "Dr. Lata Gupta",
    doctor_photo: "",
    specialty: "Psychiatry",
    room_number: "PS-01",
    floor_number: "4th Floor",
    department: "Behavioural Health",
    availability_status: "Available",
    estimated_wait_minutes: 20,
    queue_position: 2,
  },
  Emergency: {
    doctor_name: "Dr. Nikhil Reddy",
    doctor_photo: "",
    specialty: "Emergency Medicine",
    room_number: "ER-01",
    floor_number: "Ground Floor",
    department: "Emergency",
    availability_status: "On Duty",
    estimated_wait_minutes: 0,
    queue_position: 1,
  },
};

export default function DoctorCard({ result, sessionId, patientName, patientId, clinicId }: Props) {
  const t = useTranslations("kiosk");
  const [assignment, setAssignment] = useState<DoctorAssignment | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAssignment = useCallback(async () => {
    try {
      // Try the convenience assignment endpoint first
      const assignRes = await fetch(`${API_BASE}/queue/assignment/${patientId}?clinic_id=${clinicId}`);
      if (assignRes.ok) {
        setAssignment(await assignRes.json());
        setLoading(false);
        return;
      }

      // Fallback: fetch full queue and find our patient
      const queueRes = await fetch(`${API_BASE}/queue/current?clinic_id=${clinicId}`);
      if (queueRes.ok) {
        const queue = await queueRes.json();
        const entry = queue.entries?.find((e: { patient_id: string }) => e.patient_id === patientId);
        if (entry) {
          const spec = result.recommended_doctor_specialty || "General Practice";
          const doc = DEMO_DOCTORS[spec] || DEMO_DOCTORS["General Practice"];
          setAssignment({
            ...doc,
            queue_position: entry.position,
            estimated_wait_minutes: entry.position * 5,
          });
          setLoading(false);
          return;
        }
      }
    } catch {}
    // Fallback: demo data
    const spec = result.recommended_doctor_specialty || "General Practice";
    const doc = DEMO_DOCTORS[spec] || DEMO_DOCTORS["General Practice"];
    setAssignment(doc);
    setLoading(false);
  }, [patientId, clinicId, result.recommended_doctor_specialty]);

  useEffect(() => {
    fetchAssignment();
    const iv = setInterval(fetchAssignment, 30000);
    return () => clearInterval(iv);
  }, [fetchAssignment]);

  if (loading || !assignment) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "var(--color-accent-teal)", borderTopColor: "transparent" }} />
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
            style={{ background: "rgba(56, 189, 176, 0.1)", border: "2px solid var(--color-accent-teal)" }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
              stroke="var(--color-accent-teal)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
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
        <div className="rounded-xl p-6 border"
          style={{ background: "#0d1117", borderColor: "#21262d" }}>
          {/* Doctor header */}
          <div className="flex items-center gap-4 mb-6">
            <div className="w-16 h-16 rounded-xl flex items-center justify-center text-xl font-bold"
              style={{ background: "var(--color-accent-teal)", color: "#fff" }}>
              {initials}
            </div>
            <div>
              <h3 className="text-xl font-semibold" style={{ color: "#f0f6fc" }}>
                {assignment.doctor_name}
              </h3>
              <p className="text-sm" style={{ color: "var(--color-accent-teal)" }}>
                {assignment.specialty}
              </p>
            </div>
          </div>

          {/* Info grid -- 6 tiles */}
          <div className="grid grid-cols-3 gap-3">
            <InfoTile label={t("room")} value={assignment.room_number} icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18"/><path d="M19 21V5a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v16"/><path d="M13 11v2"/></svg>
            } />
            <InfoTile label="Floor" value={assignment.floor_number} icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/></svg>
            } />
            <InfoTile label="Department" value={assignment.department} icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            } />
            <InfoTile label={t("wait")} value={`~${assignment.estimated_wait_minutes} min`} icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            } />
            <InfoTile label={t("position")} value={`#${assignment.queue_position}`} icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            } />
            <InfoTile label="Status" value={assignment.availability_status} icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            } highlight={assignment.availability_status === "Available" || assignment.availability_status === "On Duty"} />
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
          className="w-full mt-6 py-4 rounded-xl text-base font-medium border cursor-pointer transition-all hover:border-[var(--color-accent-teal)]"
          style={{ background: "transparent", borderColor: "#21262d", color: "#8b949e" }}>
          {t("new_checkin")}
        </button>
      </div>
    </div>
  );
}

function InfoTile({ label, value, icon, highlight }: { label: string; value: string; icon: React.ReactNode; highlight?: boolean }) {
  return (
    <div className="text-center px-2 py-3 rounded-xl flex flex-col items-center" style={{ background: "#161b22" }}>
      <span className="mb-1" style={{ color: "var(--color-text-secondary)" }}>{icon}</span>
      <p className="text-sm font-semibold mt-1 leading-tight" style={{
        color: highlight ? "#3fb950" : "var(--color-text-primary)",
      }}>{value}</p>
      <p className="text-xs mt-0.5" style={{ color: "#8b949e" }}>{label}</p>
    </div>
  );
}
