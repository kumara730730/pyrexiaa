"use client";

import { useState } from "react";
import type { RegistrationData, Language } from "../types";
import { LANGUAGE_OPTIONS } from "../types";

interface Props {
  onComplete: (data: RegistrationData) => void;
}

export default function RegistrationForm({ onComplete }: Props) {
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<"Male" | "Female" | "Other">("Male");
  const [language, setLanguage] = useState<Language>("en");
  const [errors, setErrors] = useState<Record<string, string>>({});

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = "Please enter your name";
    const ageNum = parseInt(age);
    if (!age || isNaN(ageNum) || ageNum < 0 || ageNum > 150)
      e.age = "Please enter a valid age";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function handleSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!validate()) return;
    onComplete({ name: name.trim(), age: parseInt(age), gender, language });
  }

  return (
    <div className="flex items-center justify-center min-h-screen p-6">
      <div className="w-full max-w-lg fade-in-up">
        {/* Logo / Brand */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
              style={{ background: "linear-gradient(135deg, #58a6ff 0%, #a78bfa 100%)" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5"
                strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </svg>
            </div>
            <h1 className="text-4xl font-bold tracking-tight"
              style={{ fontFamily: "Inter, sans-serif" }}>
              Prior<span style={{ color: "#58a6ff" }}>IQ</span>
            </h1>
          </div>
          <p className="text-xl" style={{ color: "#8b949e" }}>
            Patient Check-In
          </p>
        </div>

        {/* Form Card */}
        <form onSubmit={handleSubmit}
          className="rounded-3xl p-8 space-y-6 border"
          style={{
            background: "#0d1117",
            borderColor: "#21262d",
            boxShadow: "0 0 80px rgba(88, 166, 255, 0.05)",
          }}>

          {/* Name */}
          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "#8b949e" }}>
              Full Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter your full name"
              className="w-full px-5 py-4 rounded-xl text-lg border outline-none transition-all focus:ring-2"
              style={{
                background: "#161b22",
                borderColor: errors.name ? "#f85149" : "#21262d",
                color: "#f0f6fc",
                ...(errors.name ? {} : { "--tw-ring-color": "#58a6ff" } as React.CSSProperties),
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
                Age
              </label>
              <input
                type="number"
                value={age}
                onChange={(e) => setAge(e.target.value)}
                placeholder="Age"
                min={0}
                max={150}
                className="w-full px-5 py-4 rounded-xl text-lg border outline-none transition-all focus:ring-2"
                style={{
                  background: "#161b22",
                  borderColor: errors.age ? "#f85149" : "#21262d",
                  color: "#f0f6fc",
                }}
              />
              {errors.age && (
                <p className="text-sm mt-1" style={{ color: "#f85149" }}>{errors.age}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium mb-2" style={{ color: "#8b949e" }}>
                Gender
              </label>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value as typeof gender)}
                className="w-full px-5 py-4 rounded-xl text-lg border outline-none appearance-none cursor-pointer"
                style={{
                  background: "#161b22",
                  borderColor: "#21262d",
                  color: "#f0f6fc",
                }}>
                <option value="Male">Male</option>
                <option value="Female">Female</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>

          {/* Language */}
          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "#8b949e" }}>
              Preferred Language
            </label>
            <div className="grid grid-cols-5 gap-2">
              {LANGUAGE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setLanguage(opt.value)}
                  className="py-3 px-2 rounded-xl text-sm font-medium transition-all border"
                  style={{
                    background: language === opt.value ? "rgba(88,166,255,0.15)" : "#161b22",
                    borderColor: language === opt.value ? "#58a6ff" : "#21262d",
                    color: language === opt.value ? "#58a6ff" : "#8b949e",
                  }}>
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="w-full py-5 rounded-2xl text-lg font-semibold transition-all hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
            style={{
              background: "linear-gradient(135deg, #58a6ff 0%, #a78bfa 100%)",
              color: "#fff",
              boxShadow: "0 4px 20px rgba(88,166,255,0.3)",
            }}>
            Begin Check-In
          </button>
        </form>

        {/* Footer */}
        <p className="text-center text-sm mt-6" style={{ color: "#484f58" }}>
          Your information is encrypted and processed securely.
        </p>
      </div>
    </div>
  );
}
