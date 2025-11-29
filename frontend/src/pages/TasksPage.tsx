import React, { useEffect, useState } from "react";

type Task = {
  id: number;
  email_id?: number;
  subject: string | null;
  status?: string | null;
  gmail_message_id?: string | null;
};

export const TasksPage: React.FC = () => {
  const [data, setData] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/api/tasks", { credentials: "include" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as Task[];
        setData(json);
      } catch (e: any) {
        setError(e.message ?? "Failed to load tasks");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const openEmail = (gmailMessageId?: string | null) => {
    if (!gmailMessageId) return;
    window.location.href = `/open_email/${gmailMessageId}`;
  };

  const handleHideEmail = async (emailId: number) => {
    try {
      const res = await fetch(`/api/hide-email/${emailId}`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        throw new Error("Failed to hide email");
      }
      // Remove from local state immediately
      setData(data.filter((t) => t.email_id !== emailId));
    } catch (error) {
      console.error("Error hiding email:", error);
      alert("Failed to hide email. Please try again.");
    }
  };

  if (loading) return <div className="card skeleton">Loading tasks…</div>;
  if (error) return <div className="card error">Error: {error}</div>;

  return (
    <div className="card">
      <header className="section-header">
        <h2>Tasks</h2>
        <p>Inbox-derived tasks ready to action.</p>
      </header>
      <div>
        {data.map((t) => (
          <div key={t.id} className="email-ticket">
            <div className="email-ticket-content">
              <div className="email-ticket-info">
                <div className="email-ticket-title">{t.subject ?? "Untitled task"}</div>
                {t.status && <div className="email-ticket-meta">{t.status}</div>}
              </div>
              <div className="email-ticket-actions">
                {t.email_id && (
                  <button
                    className="hide-button"
                    onClick={() => handleHideEmail(t.email_id!)}
                    title="Hide this email"
                  >
                    ×
                  </button>
                )}
                <button
                  className="small-button"
                  onClick={() => openEmail(t.gmail_message_id)}
                >
                  Open email
                </button>
              </div>
            </div>
          </div>
        ))}
        {data.length === 0 && (
          <div className="list-empty" style={{ padding: "1rem", textAlign: "center" }}>
            No tasks detected yet.
          </div>
        )}
      </div>
    </div>
  );
};


