import React, { useEffect, useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

type Analytics = {
  total_emails: number;
  processed_emails: number;
  meeting_count: number;
  task_count: number;
  junk_count?: number;
  category_counts?: Record<string, number>;
};

const COLORS = {
  meeting: "#6366f1",
  task: "#22c55e",
  junk: "#ef4444",
  newsletter: "#f59e0b",
  other: "#94a3b8",
};

const getCategoryColor = (category: string): string => {
  const lower = category.toLowerCase();
  if (lower.includes("meeting")) return COLORS.meeting;
  if (lower.includes("task")) return COLORS.task;
  if (lower.includes("junk")) return COLORS.junk;
  if (lower.includes("newsletter")) return COLORS.newsletter;
  return COLORS.other;
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
  const unprocessed_emails = total_emails - processed_emails;

  // Prepare data for charts
  const categoryData = category_counts
    ? Object.entries(category_counts).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value,
        color: getCategoryColor(name),
      }))
    : [];

  const processingData = [
    { name: "Processed", value: processed_emails, color: "#22c55e" },
    { name: "Unprocessed", value: unprocessed_emails, color: "#64748b" },
  ];

  const actionItemsData = [
    { name: "Meetings", count: meeting_count, color: COLORS.meeting },
    { name: "Tasks", count: task_count, color: COLORS.task },
    { name: "Junk & Newsletters", count: junk_count || 0, color: COLORS.junk },
  ].filter((item) => item.count > 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Key Metrics Cards */}
      <div className="card">
        <header className="section-header">
          <h2>Overview</h2>
        </header>
        <div className="analytics-grid">
          <div className="analytics-card">
            <label>Total emails</label>
            <span style={{ fontSize: "2rem", fontWeight: 600 }}>{total_emails ?? 0}</span>
          </div>
          <div className="analytics-card">
            <label>Processed</label>
            <span style={{ fontSize: "2rem", fontWeight: 600, color: "#22c55e" }}>
              {processed_emails ?? 0}
            </span>
          </div>
          <div className="analytics-card">
            <label>Processing rate</label>
            <span style={{ fontSize: "2rem", fontWeight: 600, color: "#6366f1" }}>
              {processedPct}%
            </span>
          </div>
          <div className="analytics-card">
            <label>Action items</label>
            <span style={{ fontSize: "2rem", fontWeight: 600 }}>
              {(meeting_count || 0) + (task_count || 0)}
            </span>
          </div>
        </div>
      </div>

      {/* Charts Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        {/* Category Distribution Pie Chart */}
        {categoryData.length > 0 && (
          <div className="card">
            <header className="section-header">
              <h2>Email Categories</h2>
              <p style={{ fontSize: "0.875rem", color: "rgba(148, 163, 184, 0.7)" }}>
                Distribution of email types
              </p>
            </header>
            <div style={{ height: "300px", marginTop: "1rem" }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categoryData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(15, 23, 42, 0.95)",
                      border: "1px solid rgba(51, 65, 85, 0.5)",
                      borderRadius: "8px",
                      color: "#e2e8f0",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Processing Status Donut Chart */}
        {total_emails > 0 && (
          <div className="card">
            <header className="section-header">
              <h2>Processing Status</h2>
              <p style={{ fontSize: "0.875rem", color: "rgba(148, 163, 184, 0.7)" }}>
                Processed vs unprocessed emails
              </p>
            </header>
            <div style={{ height: "300px", marginTop: "1rem" }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={processingData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {processingData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(15, 23, 42, 0.95)",
                      border: "1px solid rgba(51, 65, 85, 0.5)",
                      borderRadius: "8px",
                      color: "#e2e8f0",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      {/* Action Items Bar Chart */}
      {actionItemsData.length > 0 && (
        <div className="card">
          <header className="section-header">
            <h2>Action Items</h2>
            <p style={{ fontSize: "0.875rem", color: "rgba(148, 163, 184, 0.7)" }}>
              Meetings, tasks, and items requiring attention
            </p>
          </header>
          <div style={{ height: "300px", marginTop: "1rem" }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={actionItemsData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(51, 65, 85, 0.3)" />
                <XAxis
                  dataKey="name"
                  stroke="#94a3b8"
                  style={{ fontSize: "0.875rem" }}
                />
                <YAxis stroke="#94a3b8" style={{ fontSize: "0.875rem" }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(15, 23, 42, 0.95)",
                    border: "1px solid rgba(51, 65, 85, 0.5)",
                    borderRadius: "8px",
                    color: "#e2e8f0",
                  }}
                />
                <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                  {actionItemsData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Category Breakdown Table */}
      {categoryData.length > 0 && (
        <div className="card">
          <header className="section-header">
            <h2>Category Breakdown</h2>
          </header>
          <div style={{ marginTop: "1rem" }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "1rem",
              }}
            >
              {categoryData.map((item) => (
                <div
                  key={item.name}
                  style={{
                    padding: "1rem",
                    background: "rgba(30, 41, 59, 0.5)",
                    border: "1px solid rgba(51, 65, 85, 0.5)",
                    borderRadius: "8px",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                  }}
                >
                  <div
                    style={{
                      width: "12px",
                      height: "12px",
                      borderRadius: "50%",
                      backgroundColor: item.color,
                    }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "0.875rem", color: "rgba(148, 163, 184, 0.7)" }}>
                      {item.name}
                    </div>
                    <div style={{ fontSize: "1.5rem", fontWeight: 600, marginTop: "0.25rem" }}>
                      {item.value}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
