"use client";

import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type CSSProperties,
} from "react";
import { supabase } from "./supabase";
import type {
  QueueEntry,
  QueueResponse,
  Brief,
  ParsedBrief,
  CriticalAlert,
  UrgencyLevel,
} from "./types";
import { URGENCY_COLORS, URGENCY_BG } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";
const CLINIC_ID = "clinic_1";
const DOCTOR_ID = "doctor_1";

// ── Hooks ───────────────────────────────────────────────────────────────────

function useQueue() {
  const [entries, setEntries] = useState<QueueEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const prevEntriesRef = useRef<QueueEntry[]>([]);

  const animateQueueUpdate = useCallback((incoming: QueueEntry[]) => {
    const prevIds = new Set(prevEntriesRef.current.map((e) => e.patient_id));
    const withFlags = incoming.map((entry) => ({
      ...entry,
      isNew: !prevIds.has(entry.patient_id),
      animating: true,
    }));
    setEntries(withFlags);

    setTimeout(() => {
      setEntries((cur) =>
        cur.map((e) => ({ ...e, animating: false, isNew: false }))
      );
    }, 1200);

    prevEntriesRef.current = incoming;
  }, []);

  useEffect(() => {
    fetch(`${API}/queue/current?clinic_id=${CLINIC_ID}`)
      .then((r) => r.json())
      .then((data: QueueResponse) => {
        prevEntriesRef.current = data.entries;
        setEntries(data.entries);
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    const channel = supabase
      .channel(`queue:${CLINIC_ID}`)
      .on("broadcast", { event: "queue_update" }, ({ payload }) => {
        const data = payload as QueueResponse;
        animateQueueUpdate(data.entries);
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [animateQueueUpdate]);

  return { entries, loading };
}

function useBrief(patientId: string | null) {
  const [brief, setBrief] = useState<ParsedBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!patientId) {
      setBrief(null);
      return;
    }
    setLoading(true);
    setError(null);

    fetch(`${API}/brief/${patientId}`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "No brief yet" : "Failed to load");
        return r.json();
      })
      .then((data: Brief) => {
        try {
          setBrief(JSON.parse(data.brief_text));
        } catch {
          setBrief({
            brief_summary: data.brief_text,
            priority_flags: [],
            context_from_history: "None provided",
            suggested_opening_questions: [],
            watch_for: "",
          });
        }
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [patientId]);

  return { brief, loading, error };
}

function useAlerts() {
  const [alerts, setAlerts] = useState<CriticalAlert[]>([]);

  useEffect(() => {
    const channel = supabase
      .channel(`clinic:${CLINIC_ID}:doctor:${DOCTOR_ID}:alerts`)
      .on("broadcast", { event: "new_critical" }, ({ payload }) => {
        const alert: CriticalAlert = {
          ...(payload as Omit<CriticalAlert, "id" | "timestamp">),
          id: crypto.randomUUID(),
          timestamp: Date.now(),
        };
        setAlerts((prev) => [alert, ...prev]);

        setTimeout(() => {
          setAlerts((prev) => prev.filter((a) => a.id !== alert.id));
        }, 8000);
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const dismiss = useCallback((id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }, []);

  return { alerts, dismiss };
}

// ── Dashboard Component ─────────────────────────────────────────────────────

export default function DashboardPage() {
  const { entries, loading: queueLoading } = useQueue();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { brief, loading: briefLoading, error: briefError } = useBrief(selectedId);
  const { alerts, dismiss } = useAlerts();
  const [callingIds, setCallingIds] = useState<Set<string>>(new Set());

  const selectedEntry = entries.find((e) => e.patient_id === selectedId) ?? null;

  const handleCallIn = useCallback(
    async (patientId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setCallingIds((prev) => new Set(prev).add(patientId));
      try {
        await fetch(
          `${API}/queue/call/${patientId}?clinic_id=${CLINIC_ID}`,
          { method: "POST" }
        );
        if (selectedId === patientId) setSelectedId(null);
      } catch {
        // queue update will arrive via realtime
      } finally {
        setCallingIds((prev) => {
          const next = new Set(prev);
          next.delete(patientId);
          return next;
        });
      }
    },
    [selectedId]
  );

  return (
    <div style={styles.root}>
      {/* ── Critical alert banners ── */}
      <div style={styles.alertContainer}>
        {alerts.map((alert) => (
          <div
            key={alert.id}
            style={styles.alertBanner}
            onClick={() => dismiss(alert.id)}
          >
            <span style={styles.pulseDot} />
            <span style={styles.alertLabel}>CRITICAL</span>
            <span style={styles.alertText}>
              {alert.patient_name} — Room {alert.room_assignment}
            </span>
            <span style={styles.alertDismiss}>&times;</span>
          </div>
        ))}
      </div>

      {/* ── Header ── */}
      <header style={styles.header}>
        <div>
          <h1 style={styles.title}>Pyrexia Dashboard</h1>
          <p style={styles.subtitle}>
            Live queue &middot; {entries.length} patient
            {entries.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div style={styles.liveIndicator}>
          <span style={styles.liveDot} />
          Live
        </div>
      </header>

      <div style={styles.content}>
        {/* ── Queue Panel ── */}
        <section style={styles.queuePanel}>
          <h2 style={styles.sectionTitle}>Patient Queue</h2>
          {queueLoading ? (
            <div style={styles.skeleton}>
              {[1, 2, 3].map((i) => (
                <div key={i} style={styles.skeletonRow} />
              ))}
            </div>
          ) : entries.length === 0 ? (
            <p style={styles.emptyText}>No patients in queue</p>
          ) : (
            <div style={styles.queueList}>
              {entries.map((entry) => (
                <QueueRow
                  key={entry.patient_id}
                  entry={entry}
                  isSelected={entry.patient_id === selectedId}
                  isCalling={callingIds.has(entry.patient_id)}
                  onSelect={() => setSelectedId(entry.patient_id)}
                  onCallIn={(e) => handleCallIn(entry.patient_id, e)}
                />
              ))}
            </div>
          )}
        </section>

        {/* ── Brief Panel ── */}
        <section style={styles.briefPanel}>
          <h2 style={styles.sectionTitle}>Clinical Brief</h2>
          {!selectedId ? (
            <p style={styles.emptyText}>Select a patient to view their brief</p>
          ) : briefLoading ? (
            <BriefSkeleton />
          ) : briefError ? (
            <p style={styles.emptyText}>{briefError}</p>
          ) : brief ? (
            <BriefCard brief={brief} entry={selectedEntry} />
          ) : null}
        </section>
      </div>
    </div>
  );
}

// ── Queue Row ───────────────────────────────────────────────────────────────

function QueueRow({
  entry,
  isSelected,
  isCalling,
  onSelect,
  onCallIn,
}: {
  entry: QueueEntry;
  isSelected: boolean;
  isCalling: boolean;
  onSelect: () => void;
  onCallIn: (e: React.MouseEvent) => void;
}) {
  const level = entry.urgency_level as UrgencyLevel;
  const color = URGENCY_COLORS[level];
  const bg = URGENCY_BG[level];

  const rowStyle: CSSProperties = {
    ...styles.queueRow,
    background: isSelected ? `${color}22` : bg,
    borderLeft: `3px solid ${color}`,
    transform: entry.animating ? "translateX(4px)" : "translateX(0)",
    opacity: entry.isNew ? 0 : 1,
    animation: entry.isNew
      ? "slideIn 0.4s ease-out forwards"
      : entry.animating
        ? "pulse 0.6s ease-in-out"
        : "none",
    transition: "transform 0.3s ease, opacity 0.3s ease, background 0.2s ease",
  };

  return (
    <div style={rowStyle} onClick={onSelect}>
      <div style={styles.rowLeft}>
        <span style={{ ...styles.positionBadge, background: color }}>
          #{entry.position}
        </span>
        <div>
          <div style={styles.patientId}>
            {entry.patient_id.slice(0, 8)}...
          </div>
          <div style={styles.complaint}>
            {entry.chief_complaint || "No complaint recorded"}
          </div>
        </div>
      </div>
      <div style={styles.rowRight}>
        <div style={styles.scoreContainer}>
          <span style={{ ...styles.scoreBadge, color }}>{entry.urgency_score}</span>
          <span style={{ ...styles.levelLabel, color }}>{level}</span>
        </div>
        <button
          style={{
            ...styles.callButton,
            opacity: isCalling ? 0.5 : 1,
          }}
          onClick={onCallIn}
          disabled={isCalling}
        >
          {isCalling ? "Calling..." : "Call In"}
        </button>
      </div>
    </div>
  );
}

// ── Brief Card ──────────────────────────────────────────────────────────────

function BriefCard({
  brief,
  entry,
}: {
  brief: ParsedBrief;
  entry: QueueEntry | null;
}) {
  return (
    <div style={styles.briefContent}>
      {entry && (
        <div
          style={{
            ...styles.briefHeader,
            borderColor: URGENCY_COLORS[entry.urgency_level as UrgencyLevel],
          }}
        >
          <span
            style={{
              ...styles.briefUrgency,
              color: URGENCY_COLORS[entry.urgency_level as UrgencyLevel],
            }}
          >
            {entry.urgency_level} — Score {entry.urgency_score}
          </span>
        </div>
      )}

      <div style={styles.briefSection}>
        <h3 style={styles.briefLabel}>Summary</h3>
        <p style={styles.briefText}>{brief.brief_summary}</p>
      </div>

      {brief.priority_flags.length > 0 && (
        <div style={styles.briefSection}>
          <h3 style={styles.briefLabel}>Priority Flags</h3>
          <div style={styles.flagContainer}>
            {brief.priority_flags.map((flag, i) => (
              <span key={i} style={styles.flag}>
                {flag}
              </span>
            ))}
          </div>
        </div>
      )}

      <div style={styles.briefSection}>
        <h3 style={styles.briefLabel}>History Context</h3>
        <p style={styles.briefText}>{brief.context_from_history}</p>
      </div>

      {brief.suggested_opening_questions.length > 0 && (
        <div style={styles.briefSection}>
          <h3 style={styles.briefLabel}>Suggested Questions</h3>
          <ul style={styles.questionList}>
            {brief.suggested_opening_questions.map((q, i) => (
              <li key={i} style={styles.questionItem}>
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      {brief.watch_for && (
        <div style={styles.briefSection}>
          <h3 style={styles.briefLabel}>Watch For</h3>
          <p style={{ ...styles.briefText, color: "#f0883e" }}>
            {brief.watch_for}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Brief Skeleton ──────────────────────────────────────────────────────────

function BriefSkeleton() {
  return (
    <div style={styles.briefContent}>
      {[100, 60, 80, 40].map((w, i) => (
        <div
          key={i}
          style={{
            ...styles.skeletonBlock,
            width: `${w}%`,
          }}
        />
      ))}
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const styles: Record<string, CSSProperties> = {
  root: {
    minHeight: "100vh",
    background: "#080c12",
    color: "#e6edf3",
    fontFamily: "'Inter', system-ui, sans-serif",
    position: "relative",
  },

  // Alert banners
  alertContainer: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 100,
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  alertBanner: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "12px 20px",
    background: "linear-gradient(90deg, #3b1018 0%, #1a0a0e 100%)",
    borderBottom: "1px solid rgba(248, 81, 73, 0.3)",
    cursor: "pointer",
    animation: "slideDown 0.3s ease-out",
  },
  pulseDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: "#f85149",
    boxShadow: "0 0 8px #f85149",
    animation: "pulseDotAnim 1.5s infinite",
  },
  alertLabel: {
    fontSize: "11px",
    fontWeight: 700,
    letterSpacing: "0.1em",
    color: "#f85149",
    fontFamily: "'JetBrains Mono', monospace",
  },
  alertText: {
    flex: 1,
    fontSize: "14px",
    color: "#e6edf3",
  },
  alertDismiss: {
    fontSize: "18px",
    color: "#8b949e",
    padding: "0 4px",
  },

  // Header
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "24px 32px 16px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
  },
  title: {
    fontSize: "24px",
    fontWeight: 700,
    color: "#e6edf3",
    margin: 0,
  },
  subtitle: {
    fontSize: "13px",
    color: "#8b949e",
    margin: "4px 0 0",
  },
  liveIndicator: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontSize: "13px",
    color: "#3fb950",
    fontFamily: "'JetBrains Mono', monospace",
  },
  liveDot: {
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    background: "#3fb950",
    boxShadow: "0 0 6px #3fb950",
    animation: "pulseDotAnim 2s infinite",
  },

  // Layout
  content: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "0",
    height: "calc(100vh - 85px)",
  },

  // Queue panel
  queuePanel: {
    padding: "20px 24px",
    borderRight: "1px solid rgba(255, 255, 255, 0.06)",
    overflowY: "auto",
  },
  sectionTitle: {
    fontSize: "14px",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.08em",
    color: "#8b949e",
    marginBottom: "16px",
  },
  queueList: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
  },
  queueRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    borderRadius: "8px",
    cursor: "pointer",
  },
  rowLeft: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  positionBadge: {
    width: "32px",
    height: "32px",
    borderRadius: "6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "12px",
    fontWeight: 700,
    color: "#fff",
    fontFamily: "'JetBrains Mono', monospace",
    flexShrink: 0,
  },
  patientId: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#e6edf3",
    fontFamily: "'JetBrains Mono', monospace",
  },
  complaint: {
    fontSize: "12px",
    color: "#8b949e",
    marginTop: "2px",
    maxWidth: "280px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
  rowRight: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
  },
  scoreContainer: {
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "flex-end",
  },
  scoreBadge: {
    fontSize: "20px",
    fontWeight: 800,
    fontFamily: "'JetBrains Mono', monospace",
  },
  levelLabel: {
    fontSize: "10px",
    fontWeight: 600,
    letterSpacing: "0.05em",
  },
  callButton: {
    padding: "6px 14px",
    borderRadius: "6px",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    background: "rgba(255, 255, 255, 0.05)",
    color: "#e6edf3",
    fontSize: "12px",
    fontWeight: 600,
    cursor: "pointer",
    transition: "background 0.15s ease",
    whiteSpace: "nowrap" as const,
  },

  // Brief panel
  briefPanel: {
    padding: "20px 24px",
    overflowY: "auto",
  },
  briefContent: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "16px",
  },
  briefHeader: {
    paddingBottom: "12px",
    borderBottom: "2px solid",
  },
  briefUrgency: {
    fontSize: "14px",
    fontWeight: 700,
    fontFamily: "'JetBrains Mono', monospace",
  },
  briefSection: {
    paddingBottom: "12px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
  },
  briefLabel: {
    fontSize: "11px",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.08em",
    color: "#8b949e",
    margin: "0 0 8px",
  },
  briefText: {
    fontSize: "14px",
    lineHeight: 1.6,
    color: "#c9d1d9",
    margin: 0,
  },
  flagContainer: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "6px",
  },
  flag: {
    padding: "4px 10px",
    borderRadius: "12px",
    background: "rgba(248, 81, 73, 0.12)",
    color: "#f85149",
    fontSize: "12px",
    fontWeight: 600,
  },
  questionList: {
    margin: 0,
    paddingLeft: "18px",
    display: "flex",
    flexDirection: "column" as const,
    gap: "6px",
  },
  questionItem: {
    fontSize: "13px",
    color: "#c9d1d9",
    lineHeight: 1.5,
  },

  // Loading states
  emptyText: {
    color: "#484f58",
    fontSize: "14px",
    textAlign: "center" as const,
    padding: "40px 0",
  },
  skeleton: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
  },
  skeletonRow: {
    height: "56px",
    borderRadius: "8px",
    background: "rgba(255, 255, 255, 0.04)",
    animation: "shimmer 1.5s infinite",
  },
  skeletonBlock: {
    height: "20px",
    borderRadius: "4px",
    background: "rgba(255, 255, 255, 0.04)",
    animation: "shimmer 1.5s infinite",
  },
};
