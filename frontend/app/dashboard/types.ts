export type UrgencyLevel = "CRITICAL" | "HIGH" | "MODERATE" | "LOW" | "NON_URGENT";

export interface QueueEntry {
  patient_id: string;
  clinic_id: string;
  urgency_score: number;
  urgency_level: UrgencyLevel;
  chief_complaint: string | null;
  position: number;
  enqueued_at: string;
  animating?: boolean;
  isNew?: boolean;
}

export interface QueueResponse {
  clinic_id: string;
  entries: QueueEntry[];
  total: number;
}

export interface Brief {
  patient_id: string;
  session_id: string | null;
  brief_text: string;
  created_at: string | null;
}

export interface ParsedBrief {
  brief_summary: string;
  priority_flags: string[];
  context_from_history: string;
  suggested_opening_questions: string[];
  watch_for: string;
}

export interface CriticalAlert {
  id: string;
  patient_name: string;
  room_assignment: string;
  urgency_score: number;
  timestamp: number;
}

export const URGENCY_COLORS: Record<UrgencyLevel, string> = {
  CRITICAL: "#f85149",
  HIGH: "#f0883e",
  MODERATE: "#d29922",
  LOW: "#3fb950",
  NON_URGENT: "#8b949e",
};

export const URGENCY_BG: Record<UrgencyLevel, string> = {
  CRITICAL: "rgba(248, 81, 73, 0.15)",
  HIGH: "rgba(240, 136, 62, 0.12)",
  MODERATE: "rgba(210, 153, 34, 0.10)",
  LOW: "rgba(63, 185, 80, 0.08)",
  NON_URGENT: "rgba(139, 148, 158, 0.08)",
};
