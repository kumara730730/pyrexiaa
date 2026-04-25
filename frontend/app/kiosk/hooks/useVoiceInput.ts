"use client";

import { useState, useRef, useCallback, useEffect } from "react";

/* ── Language mapping for SpeechRecognition ─────────────────────────────────── */

const LANG_MAP: Record<string, string> = {
  en: "en-IN",
  hi: "hi-IN",
  kn: "kn-IN",
  ta: "ta-IN",
  te: "te-IN",
};

/* ── Distress keyword sets (weighted) ──────────────────────────────────────── */

const SEVERE_KEYWORDS = [
  "i can't",
  "can't breathe",
  "cannot breathe",
  "very bad",
  "terrible",
  "awful",
  "emergency",
  "dying",
  "help me",
  "please help",
  "i'm dying",
  "heart attack",
  "stroke",
  "seizure",
  "unconscious",
  "bleeding heavily",
];

const MODERATE_KEYWORDS = [
  "pain",
  "hurts",
  "hurting",
  "severe",
  "worst",
  "unbearable",
  "excruciating",
  "agony",
  "throbbing",
  "stabbing",
  "crushing",
  "burning",
  "can't move",
  "dizzy",
  "faint",
  "vomiting",
  "blood",
  "swelling",
];

/* ── SpeechRecognition type augmentation ───────────────────────────────────── */

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message?: string;
}

type SpeechRecognitionInstance = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  onaudiostart: (() => void) | null;
  onaudioend: (() => void) | null;
};

/* ── Hook Return Type ──────────────────────────────────────────────────────── */

export interface UseVoiceInputReturn {
  /** Whether the browser supports SpeechRecognition */
  isSupported: boolean;
  /** Whether recognition is currently active */
  isListening: boolean;
  /** Current transcript (updated live with interim results) */
  transcript: string;
  /** Computed voice distress score (0–10) */
  distressScore: number;
  /** Start listening — creates a new SpeechRecognition instance */
  startListening: () => void;
  /** Stop listening — aborts recognition and triggers onComplete */
  stopListening: () => void;
}

export interface UseVoiceInputOptions {
  /** Called when recognition ends with the final transcript and distress score */
  onComplete?: (transcript: string, distressScore: number) => void;
}

/* ── Distress Score Computation ────────────────────────────────────────────── */

function computeDistressScore(
  transcript: string,
  durationMs: number,
  interimSnapshots: string[]
): number {
  if (!transcript.trim()) return 0;

  let score = 0;
  const lower = transcript.toLowerCase();
  const words = transcript.trim().split(/\s+/);
  const wordCount = words.length;

  // 1. Speaking rate — words per second > 3.5 indicates rushed/distressed speech
  const durationSec = Math.max(durationMs / 1000, 0.5);
  const wordsPerSecond = wordCount / durationSec;
  if (wordsPerSecond > 3.5) {
    score += 2;
  } else if (wordsPerSecond > 2.5) {
    score += 1;
  }

  // 2. Repetitions detected via interim result patterns
  //    If the same partial appears multiple times, the speaker is repeating/stuttering
  if (interimSnapshots.length > 3) {
    const normalized = interimSnapshots.map((s) =>
      s.toLowerCase().trim().replace(/\s+/g, " ")
    );
    const uniqueCount = new Set(normalized).size;
    const repetitionRatio = 1 - uniqueCount / normalized.length;
    if (repetitionRatio > 0.4) {
      score += 2; // High repetition/stuttering
    } else if (repetitionRatio > 0.2) {
      score += 1;
    }
  }

  // 3. Severe distress keywords: +3
  const hasSevere = SEVERE_KEYWORDS.some((kw) => lower.includes(kw));
  if (hasSevere) {
    score += 3;
  }

  // 4. Moderate distress keywords: +2
  const hasModerate = MODERATE_KEYWORDS.some((kw) => lower.includes(kw));
  if (hasModerate && !hasSevere) {
    score += 2;
  } else if (hasModerate && hasSevere) {
    score += 1; // Already got +3 from severe, add a bit more
  }

  // 5. Short fragmented speech (few words with pauses = possible distress)
  if (wordCount <= 3 && durationSec > 3) {
    score += 1; // Long pause for few words → possible hesitation/distress
  }

  // Cap at 10
  return Math.min(score, 10);
}

/* ── Browser Support Check ─────────────────────────────────────────────────── */

function getSpeechRecognitionConstructor(): (new () => SpeechRecognitionInstance) | null {
  if (typeof window === "undefined") return null;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const win = window as any;
  return (
    win.SpeechRecognition ||
    win.webkitSpeechRecognition ||
    null
  );
}

/* ── Hook ──────────────────────────────────────────────────────────────────── */

export function useVoiceInput(
  language: string = "en",
  options: UseVoiceInputOptions = {}
): UseVoiceInputReturn {
  const { onComplete } = options;

  const [isSupported] = useState<boolean>(() => getSpeechRecognitionConstructor() !== null);
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [distressScore, setDistressScore] = useState(0);

  // Refs for recognition instance and timing
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const startTimeRef = useRef<number>(0);
  const interimSnapshotsRef = useRef<string[]>([]);
  const finalTranscriptRef = useRef<string>("");
  const onCompleteRef = useRef(onComplete);
  const isStoppingRef = useRef(false);

  // Keep onComplete ref fresh
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const startListening = useCallback(() => {
    const SpeechRecognition = getSpeechRecognitionConstructor();
    if (!SpeechRecognition) return;

    // Clean up any existing instance
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        // Ignore abort errors
      }
    }

    // Reset state
    setTranscript("");
    setDistressScore(0);
    finalTranscriptRef.current = "";
    interimSnapshotsRef.current = [];
    isStoppingRef.current = false;

    const recognition = new SpeechRecognition();
    recognition.lang = LANG_MAP[language] || LANG_MAP.en;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      startTimeRef.current = Date.now();
      setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      let final = "";

      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }

      // Track interim snapshots for repetition/pause detection
      if (interim) {
        interimSnapshotsRef.current.push(interim);
      }

      // Update final transcript
      if (final) {
        finalTranscriptRef.current = final;
      }

      // Display the combined transcript
      const displayText = final || interim;
      setTranscript(displayText);

      // Live distress score preview
      const elapsed = Date.now() - startTimeRef.current;
      const score = computeDistressScore(
        displayText,
        elapsed,
        interimSnapshotsRef.current
      );
      setDistressScore(score);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      // "aborted" and "no-speech" are expected when user stops quickly
      if (event.error !== "aborted" && event.error !== "no-speech") {
        console.warn("[useVoiceInput] SpeechRecognition error:", event.error);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);

      const elapsed = Date.now() - startTimeRef.current;
      const finalText = finalTranscriptRef.current || transcript;
      const score = computeDistressScore(
        finalText,
        elapsed,
        interimSnapshotsRef.current
      );
      setDistressScore(score);

      // Fire completion callback
      if (finalText.trim() && onCompleteRef.current) {
        onCompleteRef.current(finalText.trim(), score);
      }

      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch (err) {
      console.warn("[useVoiceInput] Failed to start recognition:", err);
      setIsListening(false);
    }
  }, [language, transcript]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current && !isStoppingRef.current) {
      isStoppingRef.current = true;
      try {
        // Use stop() instead of abort() to allow final results to fire
        recognitionRef.current.stop();
      } catch {
        // Already stopped
        setIsListening(false);
      }
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // Ignore
        }
      }
    };
  }, []);

  return {
    isSupported,
    isListening,
    transcript,
    distressScore,
    startListening,
    stopListening,
  };
}
