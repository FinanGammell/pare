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
import { Card } from "../components/Card";
import { LoadingSpinner } from "../components/LoadingSpinner";

// Custom Tooltip Components
const CustomPieTooltip = ({ active, payload }: any) => {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0];
  const { name, value, color, total } = data.payload || {};
  const totalValue = total || payload.reduce((sum: number, p: any) => sum + (p.value || 0), 0);
  const percentage = totalValue > 0 ? ((value / totalValue) * 100).toFixed(1) : "0.0";

  return (
    <div
      style={{
        backgroundColor: "rgba(15, 23, 42, 0.98)",
        border: "1px solid rgba(99, 102, 241, 0.5)",
        borderRadius: "8px",
        padding: "12px 16px",
        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.4)",
        minWidth: "140px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
        <div
          style={{
            width: "12px",
            height: "12px",
            borderRadius: "50%",
            backgroundColor: color,
          }}
        />
        <span style={{ color: "#e2e8f0", fontSize: "0.95rem", fontWeight: 700 }}>
          {name}
        </span>
      </div>
      <div style={{ color: color, fontSize: "1.75rem", fontWeight: 800, marginBottom: "4px" }}>
        {value.toLocaleString()}
      </div>
      <div style={{ color: "#64748b", fontSize: "0.85rem", fontWeight: 600 }}>
        {percentage}% of {totalValue.toLocaleString()} emails
      </div>
    </div>
  );
};

const CustomBarTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0];
  const { count, color } = data.payload;

  return (
    <div
      style={{
        backgroundColor: "rgba(15, 23, 42, 0.98)",
        border: "1px solid rgba(99, 102, 241, 0.5)",
        borderRadius: "8px",
        padding: "12px 16px",
        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.4)",
        minWidth: "140px",
      }}
    >
      <div style={{ color: "#94a3b8", fontSize: "0.75rem", marginBottom: "6px" }}>
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <div
          style={{
            width: "12px",
            height: "12px",
            borderRadius: "4px",
            backgroundColor: color,
          }}
        />
        <span style={{ color: "#e2e8f0", fontSize: "0.875rem", fontWeight: 600 }}>
          Count:
        </span>
        <span style={{ color: color, fontSize: "1.25rem", fontWeight: 700 }}>
          {count.toLocaleString()}
        </span>
      </div>
    </div>
  );
};

const CustomDonutTooltip = ({ active, payload }: any) => {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0];
  const { name, value, color } = data.payload;
  const total = payload.reduce((sum: number, p: any) => sum + p.value, 0);
  const percentage = ((value / total) * 100).toFixed(1);

  return (
    <div
      style={{
        backgroundColor: "rgba(15, 23, 42, 0.98)",
        border: "1px solid rgba(99, 102, 241, 0.5)",
        borderRadius: "8px",
        padding: "12px 16px",
        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.4)",
        minWidth: "160px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
        <div
          style={{
            width: "12px",
            height: "12px",
            borderRadius: "50%",
            backgroundColor: color,
          }}
        />
        <span style={{ color: "#e2e8f0", fontSize: "0.875rem", fontWeight: 600 }}>
          {name}
        </span>
      </div>
      <div style={{ color: color, fontSize: "1.5rem", fontWeight: 700, marginBottom: "4px" }}>
        {value.toLocaleString()}
      </div>
      <div style={{ color: "#64748b", fontSize: "0.75rem" }}>
        {percentage}% of {total.toLocaleString()} emails
      </div>
    </div>
  );
};

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

  if (loading) return <LoadingSpinner message="Loading analytics..." />;
  if (error || !analytics)
    return <Card><div className="error">Error: {error ?? "Unknown error"}</div></Card>;

  const { total_emails, processed_emails, meeting_count, task_count, junk_count, category_counts } =
    analytics;

  const processedPct =
    total_emails > 0 ? Math.round((processed_emails / total_emails) * 100) : 0;
  const unprocessed_emails = total_emails - processed_emails;

  // Prepare data for charts
  const categoryData = category_counts
    ? Object.entries(category_counts)
        .map(([name, value]) => ({
          name: name.charAt(0).toUpperCase() + name.slice(1),
          value,
          color: getCategoryColor(name),
          total: Object.values(category_counts).reduce((sum, v) => sum + v, 0),
          originalName: name.toLowerCase(),
        }))
        .sort((a, b) => {
          // Explicit sort order for both legend and breakdown cards:
          // Newsletter, Meeting, Task, Junk, Other
          const orderMap: Record<string, number> = {
            newsletter: 0,
            meeting: 1,
            task: 2,
            junk: 3,
            other: 4,
          };

          const aOrder = orderMap[a.originalName] ?? 999;
          const bOrder = orderMap[b.originalName] ?? 999;
          return aOrder - bOrder;
        })
        .map(({ originalName, ...rest }) => rest) // Remove originalName after sorting
    : [];

  const processingData = [
    { name: "Processed", value: processed_emails, color: "#22c55e", total: total_emails },
    { name: "Unprocessed", value: unprocessed_emails, color: "#64748b", total: total_emails },
  ];

  const actionItemsData = [
    { name: "Meetings", count: meeting_count, color: COLORS.meeting },
    { name: "Tasks", count: task_count, color: COLORS.task },
    { name: "Junk & Newsletters", count: junk_count || 0, color: COLORS.junk },
  ].filter((item) => item.count > 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Key Metrics Cards */}
      <Card delay={0.1}>
        <header className="section-header">
          <div>
            <h2 style={{ color: "white", margin: 0 }}>Analytics</h2>
            <p style={{ margin: "0.5rem 0 0 0", color: "var(--color-text-secondary)" }}>
              Comprehensive insights into your email organization
            </p>
          </div>
        </header>
        <div className="analytics-grid" style={{ marginTop: "var(--spacing-md)" }}>
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
      </Card>

      {/* Charts Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
          {/* Category Distribution Pie Chart */}
          {categoryData.length > 0 && (
            <Card delay={0.2}>
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
                    label={false}
                    outerRadius={90}
                    innerRadius={30}
                    paddingAngle={3}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomPieTooltip />} />
                  <Legend
                    verticalAlign="bottom"
                    height={60}
                    iconType="circle"
                    wrapperStyle={{ paddingTop: "1rem" }}
                    formatter={(value, entry: any) => {
                      const percent = entry.payload.total > 0 
                        ? ((entry.payload.value / entry.payload.total) * 100).toFixed(0)
                        : "0";
                      return (
                        <span style={{ color: "#f9fafb", fontSize: "0.95rem", fontWeight: 600 }}>
                          {value} <span style={{ color: "#94a3b8", fontWeight: 600 }}>({percent}%)</span>
                        </span>
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            </Card>
          )}

          {/* Processing Status Donut Chart */}
          {total_emails > 0 && (
            <Card delay={0.25}>
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
                    labelLine={false}
                    label={false}
                    dataKey="value"
                  >
                    {processingData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomDonutTooltip />} />
                  <Legend
                    verticalAlign="bottom"
                    height={60}
                    iconType="circle"
                    wrapperStyle={{ paddingTop: "1rem" }}
                    formatter={(value, entry: any) => {
                      const percent = entry.payload.total > 0 
                        ? ((entry.payload.value / entry.payload.total) * 100).toFixed(0)
                        : "0";
                      return (
                        <span style={{ color: "#f9fafb", fontSize: "0.95rem", fontWeight: 600 }}>
                          {value} <span style={{ color: "#94a3b8", fontWeight: 600 }}>({percent}%)</span>
                        </span>
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            </Card>
          )}
        </div>

        {/* Action Items Bar Chart */}
        {actionItemsData.length > 0 && (
          <Card delay={0.3}>
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
                <Tooltip content={<CustomBarTooltip />} />
                <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                  {actionItemsData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Category Breakdown Table */}
      {categoryData.length > 0 && (
        <Card delay={0.35}>
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
        </Card>
      )}
    </div>
  );
};
