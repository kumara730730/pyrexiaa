"use client";

import React, { useEffect, useState } from 'react';

export type UrgencyLevel = "CRITICAL" | "HIGH" | "MODERATE" | "LOW";

export interface DoctorAssignmentCardProps {
  doctorName: string;
  specialty: string;
  photoUrl: string;
  roomNumber: string;
  queuePosition: number;
  estimatedWaitMins: number;
  patientUrgencyLevel: UrgencyLevel;
}

export default function DoctorAssignmentCard({
  doctorName,
  specialty,
  photoUrl,
  roomNumber,
  queuePosition,
  estimatedWaitMins,
  patientUrgencyLevel
}: DoctorAssignmentCardProps) {
  
  // Animated progress dots
  const [dotCount, setDotCount] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => {
      setDotCount(prev => (prev + 1) % 4);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  const dots = ".".repeat(dotCount);

  // Mapping for urgency colours using design tokens from globals.css
  const urgencyColors = {
    CRITICAL: "bg-urgency-critical/10 text-urgency-critical border-urgency-critical/20",
    HIGH: "bg-urgency-high/10 text-urgency-high border-urgency-high/20",
    MODERATE: "bg-urgency-moderate/10 text-urgency-moderate border-urgency-moderate/20",
    LOW: "bg-urgency-low/10 text-urgency-low border-urgency-low/20",
  };
  
  const specialtyColors: Record<string, string> = {
    "General Practitioner": "border-[#0F766E]",
    "Cardiologist": "border-urgency-critical",
    "Neurologist": "border-[#0F766E]",
    "Orthopedist": "border-urgency-moderate",
    // fallback
    "default": "border-[#0F766E]"
  };

  const photoBorderClass = specialtyColors[specialty] || specialtyColors["default"];

  return (
    <div 
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-kiosk-bg text-text-primary p-6 opacity-0 fade-in-up"
      style={{ animationDuration: '400ms' }}
    >
      
      {/* 1. Header */}
      <div className="mb-8 flex flex-col items-center gap-3">
        <div className="text-xl font-bold tracking-widest text-[#0F766E]">PriorIQ</div>
        <div className="flex items-center gap-2 rounded-full bg-urgency-low/10 px-4 py-2 border border-urgency-low/20">
          <svg className="h-5 w-5 text-urgency-low" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span className="text-urgency-low font-medium">Check-In Complete</span>
        </div>
      </div>

      {/* 2. Urgency Badge */}
      {patientUrgencyLevel === "CRITICAL" ? (
        <div className="mb-8 animate-pulse rounded-full border border-urgency-critical px-6 py-3 bg-urgency-critical/20 shadow-[0_0_20px_rgba(248,81,73,0.3)]">
          <span className="text-urgency-critical font-bold uppercase tracking-wider">Emergency Priority — Staff Notified</span>
        </div>
      ) : (
        <div className={`mb-8 rounded-full border px-4 py-1.5 text-sm font-semibold uppercase tracking-wider ${urgencyColors[patientUrgencyLevel]}`}>
          {patientUrgencyLevel} PRIORITY
        </div>
      )}

      {/* 3. Doctor Card Section */}
      <div className="w-full max-w-md rounded-3xl border border-kiosk-border bg-kiosk-surface/80 p-8 shadow-2xl backdrop-blur-sm flex flex-col items-center relative overflow-hidden">
        {/* Soft teal glow background inside card */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-32 bg-[#0F766E]/10 blur-3xl rounded-t-3xl pointer-events-none" />

        <div className="mb-4 relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img 
            src={photoUrl} 
            alt={doctorName} 
            className={`h-20 w-20 rounded-full object-cover border-2 shadow-lg ${photoBorderClass}`}
          />
        </div>
        
        <p className="text-sm text-text-secondary mb-1">You have been assigned to</p>
        <h2 className="text-2xl font-bold text-text-primary mb-2">{doctorName}</h2>
        
        <div className="flex items-center gap-2 mb-6">
          <span className="rounded-md bg-[#0F766E]/10 px-2.5 py-1 text-xs font-medium text-[#0F766E] border border-[#0F766E]/20">
            {specialty}
          </span>
          <span className="rounded-md bg-kiosk-elevated px-2.5 py-1 text-xs font-medium text-text-secondary border border-kiosk-border">
            Room {roomNumber}
          </span>
        </div>

        {/* 4. Wait info */}
        <div className="w-full rounded-2xl bg-kiosk-elevated p-5 text-center border border-kiosk-border/50 relative overflow-hidden">
          {patientUrgencyLevel !== "CRITICAL" && (
            <>
              {queuePosition === 1 ? (
                <div className="flex flex-col items-center gap-2">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#0F766E]/20 text-[#0F766E] mb-1">
                    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <p className="text-[#0F766E] font-semibold text-lg">You are next &mdash; the doctor will see you shortly</p>
                  <p className="text-text-secondary text-sm mt-1 h-5"><span className="inline-block w-4 text-left">{dots}</span></p>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <div className="text-sm text-text-secondary mb-2">Queue Status</div>
                  <div className="flex items-center justify-center gap-6 w-full">
                    <div className="flex flex-col items-center">
                      <span className="text-3xl font-light text-text-primary">{queuePosition}</span>
                      <span className="text-xs text-text-muted uppercase tracking-wider mt-1">Position</span>
                    </div>
                    <div className="h-8 w-px bg-kiosk-border" />
                    <div className="flex flex-col items-center">
                      <span className="text-3xl font-light text-text-primary flex items-baseline gap-1">
                        ~{estimatedWaitMins} <span className="text-base text-text-secondary">m</span>
                      </span>
                      <span className="text-xs text-text-muted uppercase tracking-wider mt-1">Est. Wait</span>
                    </div>
                  </div>
                  <div className="mt-4 text-xs text-text-secondary flex items-center justify-center gap-1 w-full">
                    <div className="flex items-center gap-1">
                      <span className="inline-block w-4 text-left">{dots}</span> Live updates
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          {patientUrgencyLevel === "CRITICAL" && (
            <div className="py-2">
              <p className="text-urgency-critical font-medium">Medical staff are preparing for your arrival.</p>
              <p className="text-text-secondary text-sm mt-1">Please remain seated or seek immediate assistance if condition worsens.</p>
            </div>
          )}
        </div>
      </div>

      {/* 5. Footer */}
      <div className="mt-12 text-text-secondary text-sm flex items-center gap-2">
        <svg className="h-5 w-5 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
        </svg>
        Please take a seat. Staff will call your name.
      </div>
    </div>
  );
}
