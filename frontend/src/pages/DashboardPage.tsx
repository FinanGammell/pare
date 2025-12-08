import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { EmailCard } from "../components/EmailCard";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { LoadingSpinner } from "../components/LoadingSpinner";

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
  sender?: string | null;
  snippet?: string | null;
  date?: string | null;
  gmail_message_id?: string | null;
  body?: string | null;
  raw_json?: string | null;
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
    return <LoadingSpinner message="Loading dashboard..." />;
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
  
  // Ensure we have valid numbers for the progress calculation
  const totalEmails = sync_stats?.total_emails ?? 0;
  const processedEmails = sync_stats?.processed_emails ?? 0;
  const processedPct =
    totalEmails > 0
      ? Math.round((processedEmails / totalEmails) * 100)
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
      <Card className="span-2" delay={0}>
        <header className="section-header">
          <h2>Sync Status</h2>
          <span className="pill">
            {totalEmails} emails • {processedEmails} processed
          </span>
        </header>
        <div className="progress-bar-premium">
          <div
            className="progress-bar-inner-premium"
            style={{ width: `${Math.max(0, Math.min(100, processedPct))}%` }}
          />
        </div>
        <div className="stats-row">
          <div>
            <label>New</label>
            <span>{sync_stats?.new_count ?? 0}</span>
          </div>
          <div>
            <label>Pending</label>
            <span>{sync_stats?.unprocessed_emails ?? 0}</span>
          </div>
          <div>
            <label>Newly processed</label>
            <span>{sync_stats?.newly_processed ?? 0}</span>
          </div>
        </div>
      </Card>

      <Card delay={0.1}>
        <header className="section-header">
          <h2>Meetings</h2>
        </header>
        <div>
          {meetings.slice(0, 5).map((m) => (
            <EmailCard
              key={m.id}
              id={m.id}
              emailId={m.email_id}
              subject={m.subject}
              sender={m.sender}
              date={m.date}
              snippet={m.snippet}
              body={m.body}
              rawJson={m.raw_json}
              gmailMessageId={m.gmail_message_id}
              onDelete={m.email_id ? handleHideEmail : undefined}
              onClick={() => navigate("/meetings")}
            />
          ))}
          {meetings.length === 0 && (
            <div className="list-empty">No meetings detected yet.</div>
          )}
        </div>
      </Card>

      <Card delay={0.15}>
        <header className="section-header">
          <h2>Tasks</h2>
        </header>
        <div>
          {tasks.slice(0, 5).map((t) => (
            <EmailCard
              key={t.id}
              id={t.id}
              emailId={t.email_id}
              subject={t.subject}
              sender={t.sender}
              date={t.date}
              snippet={t.snippet}
              body={t.body}
              rawJson={t.raw_json}
              gmailMessageId={t.gmail_message_id}
              onDelete={t.email_id ? handleHideEmail : undefined}
              onClick={() => navigate("/tasks")}
            />
          ))}
          {tasks.length === 0 && (
            <div className="list-empty">No tasks detected yet.</div>
          )}
        </div>
      </Card>

      <Card className="span-2" delay={0.2}>
        <header className="section-header">
          <h2>Inbox Analytics</h2>
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
      </Card>

      <Card className="span-2" delay={0.25}>
        <header className="section-header">
          <h2>Junk & Newsletters</h2>
        </header>
        <div>
          {junk_emails.slice(0, 5).map((email) => (
            <EmailCard
              key={email.id}
              id={email.id}
              emailId={email.email_id || email.id}
              subject={email.subject}
              sender={email.sender}
              date={email.date}
              snippet={email.snippet}
              body={email.body}
              rawJson={email.raw_json}
              gmailMessageId={email.gmail_message_id}
              onDelete={handleHideEmail}
              onClick={() => navigate("/junk")}
            />
          ))}
          {junk_emails.length === 0 && (
            <div className="list-empty">No junk or newsletters detected.</div>
          )}
        </div>
      </Card>
    </div>
  );
};


