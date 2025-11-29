import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

type SyncStats = {
  total_emails: number;
  processed_emails: number;
  unprocessed_emails: number;
  new_count: number;
  synced_count: number;
  newly_processed: number;
};

type Analytics = {
  total_emails: number;
  processed_emails: number;
  meeting_count: number;
  task_count: number;
};

type EmailSummary = {
  id: number;
  email_id?: number;
  subject: string | null;
  snippet?: string | null;
  date?: string | null;
};

type DashboardPayload = {
  sync_stats: SyncStats;
  analytics: Analytics;
  meetings: EmailSummary[];
  tasks: EmailSummary[];
  junk_emails: EmailSummary[];
};

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/api/dashboard", { credentials: "include" });
        if (res.status === 401) {
          setError("Please log in to view your dashboard");
          return;
        }
        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.error || `HTTP ${res.status}`);
        }
        const json = (await res.json()) as DashboardPayload;
        setData(json);
      } catch (e: any) {
        setError(e.message || "Failed to load dashboard");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return <div className="card skeleton">Loading dashboard…</div>;
  }

  if (error || !data) {
    const isAuthError = error?.includes("log in") || error?.includes("401") || error?.includes("403");
    return (
      <div className="card error">
        <h2>{isAuthError ? "Authentication Required" : "Error"}</h2>
        <p>{error || "Failed to load dashboard data"}</p>
        {isAuthError && (
          <button
            className="primary-button"
            onClick={() => {
              window.location.href = "/login";
            }}
            style={{ marginTop: "1rem" }}
          >
            Connect Gmail
          </button>
        )}
      </div>
    );
  }

  const { sync_stats, analytics, meetings, tasks, junk_emails } = data;
  const processedPct =
    sync_stats.total_emails > 0
      ? Math.round(
          (sync_stats.processed_emails / sync_stats.total_emails) * 100
        )
      : 0;

  const handleHideEmail = async (emailId: number, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation();
    }
    if (!emailId) {
      console.error("No email_id provided");
      alert("Cannot hide email: missing email ID");
      return;
    }
    try {
      console.log("Hiding email with ID:", emailId);
      const res = await fetch(`/api/hide-email/${emailId}`, {
        method: "POST",
        credentials: "include",
      });
      const data = await res.json().catch(() => ({}));
      console.log("Hide email response:", res.status, data);
      if (!res.ok) {
        const errorMsg = data.error || `HTTP ${res.status}: Failed to hide email`;
        console.error("Hide email failed:", errorMsg);
        throw new Error(errorMsg);
      }
      // Reload data to reflect the change
      window.location.reload();
    } catch (error: any) {
      console.error("Error hiding email:", error);
      alert(error.message || "Failed to hide email. Please try again.");
    }
  };

  return (
    <div className="grid grid-dashboard">
      <section className="card span-2">
        <header className="section-header">
          <h2>Sync status</h2>
          <span className="pill">
            {sync_stats.total_emails} emails • {sync_stats.processed_emails}{" "}
            processed
          </span>
        </header>
        <div className="progress-bar">
          <div
            className="progress-bar-inner"
            style={{ width: `${processedPct}%` }}
          />
        </div>
        <div className="stats-row">
          <div>
            <label>New</label>
            <span>{sync_stats.new_count}</span>
          </div>
          <div>
            <label>Pending</label>
            <span>{sync_stats.unprocessed_emails}</span>
          </div>
          <div>
            <label>Newly processed</label>
            <span>{sync_stats.newly_processed}</span>
          </div>
        </div>
      </section>

      <section className="card">
        <header className="section-header">
          <h2>Meetings</h2>
        </header>
        <div>
          {meetings.slice(0, 5).map((m) => (
            <div 
              key={m.id} 
              className="email-ticket clickable-ticket"
              onClick={() => navigate("/meetings")}
            >
              <div className="email-ticket-content">
                <div className="email-ticket-info">
                  <div className="email-ticket-title">{m.subject ?? "Untitled meeting"}</div>
                  {m.date && <div className="email-ticket-meta">{m.date}</div>}
                </div>
                {m.email_id ? (
                  <button
                    className="hide-button"
                    onClick={(e) => handleHideEmail(m.email_id!, e)}
                    title="Hide this email"
                  >
                    ×
                  </button>
                ) : (
                  <span style={{ fontSize: "0.75rem", color: "rgba(148, 163, 184, 0.5)" }}>
                    (no email_id)
                  </span>
                )}
              </div>
            </div>
          ))}
          {meetings.length === 0 && (
            <div className="list-empty" style={{ padding: "1rem", textAlign: "center" }}>
              No meetings detected yet.
            </div>
          )}
        </div>
      </section>

      <section className="card">
        <header className="section-header">
          <h2>Tasks</h2>
        </header>
        <div>
          {tasks.slice(0, 5).map((t) => (
            <div 
              key={t.id} 
              className="email-ticket clickable-ticket"
              onClick={() => navigate("/tasks")}
            >
              <div className="email-ticket-content">
                <div className="email-ticket-info">
                  <div className="email-ticket-title">{t.subject ?? "Untitled task"}</div>
                  {t.date && <div className="email-ticket-meta">{t.date}</div>}
                </div>
                {t.email_id ? (
                  <button
                    className="hide-button"
                    onClick={(e) => handleHideEmail(t.email_id!, e)}
                    title="Hide this email"
                  >
                    ×
                  </button>
                ) : (
                  <span style={{ fontSize: "0.75rem", color: "rgba(148, 163, 184, 0.5)" }}>
                    (no email_id)
                  </span>
                )}
              </div>
            </div>
          ))}
          {tasks.length === 0 && (
            <div className="list-empty" style={{ padding: "1rem", textAlign: "center" }}>
              No tasks detected yet.
            </div>
          )}
        </div>
      </section>

      <section className="card span-2">
        <header className="section-header">
          <h2>Inbox analytics</h2>
        </header>
        <div className="analytics-grid">
          <div className="analytics-card">
            <label>Total emails</label>
            <span>{analytics.total_emails ?? 0}</span>
          </div>
          <div className="analytics-card">
            <label>Processed</label>
            <span>{analytics.processed_emails ?? 0}</span>
          </div>
          <div className="analytics-card">
            <label>Meetings</label>
            <span>{analytics.meeting_count ?? 0}</span>
          </div>
          <div className="analytics-card">
            <label>Tasks</label>
            <span>{analytics.task_count ?? 0}</span>
          </div>
        </div>
      </section>

      <section className="card span-2">
        <header className="section-header">
          <h2>Junk & newsletters</h2>
        </header>
        <div>
          {junk_emails.slice(0, 5).map((email) => (
            <div 
              key={email.id} 
              className="email-ticket clickable-ticket"
              onClick={() => navigate("/junk")}
            >
              <div className="email-ticket-content">
                <div className="email-ticket-info">
                  <div className="email-ticket-title">{email.subject ?? "No subject"}</div>
                  {email.snippet && <div className="email-ticket-meta">{email.snippet}</div>}
                </div>
                <button
                  className="hide-button"
                  onClick={(e) => handleHideEmail(email.id, e)}
                  title="Hide this email"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
          {junk_emails.length === 0 && (
            <div className="list-empty" style={{ padding: "1rem", textAlign: "center" }}>
              No junk or newsletters detected.
            </div>
          )}
        </div>
      </section>
    </div>
  );
};


