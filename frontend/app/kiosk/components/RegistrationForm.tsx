"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import type { RegistrationData, Language } from "../types";
import LanguagePicker from "./LanguagePicker";

interface Props {
  onComplete: (data: RegistrationData) => void;
}

export default function RegistrationForm({ onComplete }: Props) {
  const t = useTranslations("kiosk");

  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<"Male" | "Female" | "Other">("Male");
  const [language, setLanguage] = useState<Language>("en");
  const [symptoms, setSymptoms] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = t("validation_name");
    if (!symptoms.trim()) e.symptoms = "Please describe your symptoms";
    const ageNum = parseInt(age);
    if (!age || isNaN(ageNum) || ageNum < 0 || ageNum > 150)
      e.age = t("validation_age");
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function handleSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!validate()) return;
    onComplete({ name: name.trim(), age: parseInt(age), gender, language, symptoms: symptoms.trim() });
  }

  return (
    <div className="flex items-center justify-center min-h-screen p-6">
      <div className="w-full max-w-lg fade-in-up">
        {/* Logo / Brand */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ background: "var(--color-accent-teal)" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5"
                strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </svg>
            </div>
            <h1 className="text-4xl font-bold tracking-tight"
              style={{ fontFamily: "inherit" }}>
              Pyre<span style={{ color: "var(--color-accent-teal)" }}>xia</span>
            </h1>
          </div>
          <p className="text-xl" style={{ color: "#8b949e" }}>
            {t("subtitle")}
          </p>
        </div>

        {/* Form Card */}
        <form onSubmit={handleSubmit}
          className="rounded-xl p-8 space-y-6 border"
          style={{
            background: "#0d1117",
            borderColor: "#21262d",
            boxShadow: "0 4px 20px rgba(0, 0, 0, 0.05)",
          }}>

          {/* Name */}
          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "#8b949e" }}>
              {t("name_label")}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("name_placeholder")}
              className="w-full px-5 py-4 rounded-xl text-lg border outline-none transition-all focus:ring-2"
              style={{
                background: "#161b22",
                borderColor: errors.name ? "#f85149" : "#21262d",
                color: "var(--color-text-primary)",
                ...(errors.name ? {} : { "--tw-ring-color": "var(--color-accent-teal)" } as React.CSSProperties),
              }}
              autoFocus
            />
            {errors.name && (
              <p className="text-sm mt-1" style={{ color: "#f85149" }}>{errors.name}</p>
            )}
          </div>

          {/* Age + Gender Row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: "#8b949e" }}>
                {t("age_label")}
              </label>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={age}
                onChange={(e) => {
                  const val = e.target.value.replace(/\D/g, "");
                  setAge(val);
                }}
                placeholder={t("age_placeholder")}
                className="w-full px-5 py-4 rounded-xl text-lg border outline-none transition-all focus:ring-2"
                style={{
                  background: "#161b22",
                  borderColor: errors.age ? "#f85149" : "#21262d",
                  color: "var(--color-text-primary)",
                  ...(errors.age ? {} : { "--tw-ring-color": "var(--color-accent-teal)" } as React.CSSProperties),
                }}
              />
              {errors.age && (
                <p className="text-sm mt-1" style={{ color: "#f85149" }}>{errors.age}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: "#8b949e" }}>
                {t("gender_label")}
              </label>
              <div className="grid grid-cols-3 gap-2">
                {(["Male", "Female", "Other"] as const).map((opt) => {
                  const isActive = gender === opt;
                  return (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setGender(opt)}
                      className="flex items-center justify-center py-4 rounded-xl text-base font-medium transition-all border cursor-pointer"
                      style={{
                        background: isActive ? "rgba(15, 118, 110, 0.1)" : "#161b22",
                        borderColor: isActive ? "var(--color-accent-teal)" : "#21262d",
                        color: isActive ? "var(--color-accent-teal)" : "#8b949e",
                        boxShadow: isActive ? "0 0 12px rgba(15, 118, 110, 0.15)" : "none",
                      }}
                    >
                      {opt === "Male" ? t("gender_male") : opt === "Female" ? t("gender_female") : t("gender_other")}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Language Picker */}
          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "#8b949e" }}>
              {t("language_label")}
            </label>
            <LanguagePicker value={language} onChange={setLanguage} />
          </div>

          {/* Symptoms */}
          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "#8b949e" }}>
              What&apos;s bringing you in today?
            </label>
            <textarea
              value={symptoms}
              onChange={(e) => setSymptoms(e.target.value)}
              placeholder="e.g. I have a sharp pain in my chest..."
              className="w-full px-5 py-4 rounded-xl text-lg border outline-none transition-all focus:ring-2"
              rows={3}
              style={{
                background: "#161b22",
                borderColor: errors.symptoms ? "#f85149" : "#21262d",
                color: "var(--color-text-primary)",
                ...(errors.symptoms ? {} : { "--tw-ring-color": "var(--color-accent-teal)" } as React.CSSProperties),
              }}
            />
            {errors.symptoms && (
              <p className="text-sm mt-1" style={{ color: "#f85149" }}>{errors.symptoms}</p>
            )}
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="w-full py-5 rounded-xl text-lg font-semibold transition-all hover:scale-[0.98] active:scale-[0.95] cursor-pointer"
            style={{
              background: "var(--color-accent-teal)",
              color: "#fff",
              border: "1px solid transparent",
              boxShadow: "0 2px 12px rgba(15, 118, 110, 0.3)",
            }}>
            {t("begin_btn")}
          </button>
        </form>

        {/* Footer */}
        <p className="text-center text-sm mt-6" style={{ color: "#484f58" }}>
          {t("footer_privacy")}
        </p>
      </div>
    </div>
  );
}
