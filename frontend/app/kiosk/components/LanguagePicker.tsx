"use client";

import type { Language } from "../types";

const LANGUAGES: { code: Language; flag: string; label: string }[] = [
  { code: "en", flag: "🇬🇧", label: "English" },
  { code: "hi", flag: "🇮🇳", label: "हिंदी" },
  { code: "kn", flag: "🇮🇳", label: "ಕನ್ನಡ" },
  { code: "ta", flag: "🇮🇳", label: "தமிழ்" },
  { code: "te", flag: "🇮🇳", label: "తెలుగు" },
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
              background: isActive ? "rgba(88,166,255,0.15)" : "#161b22",
              borderColor: isActive ? "#58a6ff" : "#21262d",
              color: isActive ? "#58a6ff" : "#8b949e",
              boxShadow: isActive
                ? "0 0 12px rgba(88,166,255,0.15)"
                : "none",
              transform: isActive ? "scale(1.03)" : "scale(1)",
            }}
          >
            <span className="text-lg">{opt.flag}</span>
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
