import React, { useEffect, useState } from "react";

type Analytics = {
  total_emails: number;
  processed_emails: number;
  meeting_count: number;
  task_count: number;
  junk_count?: number;
  category_counts?: Record<string, number>;
};

export const AnalyticsPage: React.FC = () => {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/api/analytics", { credentials: "include" });
        if (res.status === 401) {
          setError("Please log in to view analytics");
          return;
        }
        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.error || `HTTP ${res.status}`);
        }
        const json = (await res.json()) as { analytics: Analytics; summary?: any };
        setAnalytics(json.analytics);
      } catch (e: any) {
        setError(e.message ?? "Failed to load analytics");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) return <div className="card skeleton">Loading analytics…</div>;
  if (error || !analytics)
    return <div className="card error">Error: {error ?? "Unknown error"}</div>;

  const { total_emails, processed_emails, meeting_count, task_count, junk_count, category_counts } =
    analytics;

  const processedPct =
    total_emails > 0 ? Math.round((processed_emails / total_emails) * 100) : 0;

  return (
    <div>
      <div className="card">
        <header className="section-header">
          <h2>Analytics</h2>
          <p>High-level metrics about your inbox.</p>
        </header>
        <div className="analytics-grid">
          <div className="analytics-card">
            <label>Total emails</label>
            <span>{total_emails ?? 0}</span>
          </div>
          <div className="analytics-card">
            <label>Processed emails</label>
            <span>{processed_emails ?? 0}</span>
          </div>
          <div className="analytics-card">
            <label>Processing rate</label>
            <span>{processedPct}%</span>
          </div>
          <div className="analytics-card">
            <label>Meetings</label>
            <span>{meeting_count ?? 0}</span>
          </div>
          <div className="analytics-card">
            <label>Tasks</label>
            <span>{task_count ?? 0}</span>
          </div>
          <div className="analytics-card">
            <label>Junk & Newsletters</label>
            <span>{junk_count ?? 0}</span>
          </div>
        </div>
      </div>

      {category_counts && Object.keys(category_counts).length > 0 && (
        <div className="card" style={{ marginTop: "1.5rem" }}>
          <header className="section-header">
            <h2>Category Breakdown</h2>
          </header>
          <div className="analytics-grid">
            {Object.entries(category_counts).map(([category, count]) => (
              <div key={category} className="analytics-card">
                <label style={{ textTransform: "capitalize" }}>{category}</label>
                <span>{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};


