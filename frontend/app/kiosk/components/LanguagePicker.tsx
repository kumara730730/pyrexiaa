"use client";

import type { Language } from "../types";

const LANGUAGES: { code: Language; flag: string; label: string }[] = [
  { code: "en", flag: "EN", label: "English" },
  { code: "hi", flag: "HI", label: "हिंदी" },
  { code: "kn", flag: "KN", label: "ಕನ್ನಡ" },
  { code: "ta", flag: "TA", label: "தமிழ்" },
  { code: "te", flag: "TE", label: "తెలుగు" },
];

interface Props {
  value: Language;
  onChange: (lang: Language) => void;
}

/**
 * LanguagePicker — 5 flag/text buttons in a row.
 * Sets locale in sessionStorage + cookie for next-intl to pick up.
 */
export default function LanguagePicker({ value, onChange }: Props) {
  function handleSelect(lang: Language) {
    // Persist to sessionStorage for client-side reads
    sessionStorage.setItem("pyrexia-locale", lang);

    // Set cookie so next-intl server can read it on next request
    document.cookie = `NEXT_LOCALE=${lang};path=/;max-age=${60 * 60 * 24 * 365};SameSite=Lax`;

    onChange(lang);
  }

  return (
    <div className="grid grid-cols-5 gap-2">
      {LANGUAGES.map((opt) => {
        const isActive = value === opt.code;
        return (
          <button
            key={opt.code}
            type="button"
            onClick={() => handleSelect(opt.code)}
            className="flex flex-col items-center gap-1.5 py-3 px-2 rounded-xl text-sm font-medium transition-all border cursor-pointer"
            style={{
              background: isActive ? "rgba(15, 118, 110, 0.1)" : "#161b22",
              borderColor: isActive ? "var(--color-accent-teal)" : "#21262d",
              color: isActive ? "var(--color-accent-teal)" : "#8b949e",
              boxShadow: isActive
                ? "0 0 12px rgba(15, 118, 110, 0.15)"
                : "none",
              transform: isActive ? "scale(1.03)" : "scale(1)",
            }}
          >
            <span className="text-lg font-bold">{opt.flag}</span>
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
