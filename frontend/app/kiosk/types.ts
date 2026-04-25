export type Stage = "registration" | "chat" | "scoring" | "assignment" | "emergency";

export type Language = "en" | "hi" | "kn" | "ta" | "te";

export const LANGUAGE_OPTIONS: { value: Language; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिंदी" },
  { value: "kn", label: "ಕನ್ನಡ" },
  { value: "ta", label: "தமிழ்" },
  { value: "te", label: "తెలుగు" },
];

export interface RegistrationData {
  name: string;
  age: number;
  gender: "Male" | "Female" | "Other";
  language: Language;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

export interface TriageResult {
  urgency_score: number;
  urgency_level: "CRITICAL" | "HIGH" | "MODERATE" | "LOW";
  reasoning_trace: string[];
  presenting_complaint: string;
  red_flags: string[];
  suggested_doctor_questions: string[];
  recommended_doctor_specialty: string;
}

export interface DoctorAssignment {
  doctor_name: string;
  doctor_photo: string;
  specialty: string;
  room_number: string;
  estimated_wait_minutes: number;
  queue_position: number;
}

export const URGENCY_COLORS: Record<string, string> = {
  CRITICAL: "#f85149",
  HIGH: "#f0883e",
  MODERATE: "#d29922",
  LOW: "#3fb950",
};
