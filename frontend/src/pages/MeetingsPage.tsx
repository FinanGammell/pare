import React, { useEffect, useState } from "react";

type Meeting = {
  id: number;
  email_id?: number;
  subject: string | null;
  email_date?: string | null;
  sender?: string | null;
  gmail_message_id?: string | null;
};

export const MeetingsPage: React.FC = () => {
  const [data, setData] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/api/meetings", { credentials: "include" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as Meeting[];
        setData(json);
      } catch (e: any) {
        setError(e.message ?? "Failed to load meetings");
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
      setData(data.filter((m) => m.email_id !== emailId));
    } catch (error) {
      console.error("Error hiding email:", error);
      alert("Failed to hide email. Please try again.");
    }
  };

  if (loading) return <div className="card skeleton">Loading meetings…</div>;
  if (error) return <div className="card error">Error: {error}</div>;

  return (
    <div className="card">
      <header className="section-header">
        <h2>Meetings</h2>
        <p>AI-detected meetings with structured metadata.</p>
      </header>
      <div>
        {data.map((m) => (
          <div key={m.id} className="email-ticket">
            <div className="email-ticket-content">
              <div className="email-ticket-info">
                <div className="email-ticket-title">
                  {m.subject ?? "Untitled meeting"}
                </div>
                {m.sender && (
                  <div className="email-ticket-meta">From {m.sender}</div>
                )}
                {m.email_date && (
                  <div className="email-ticket-meta">{m.email_date}</div>
                )}
              </div>
              <div className="email-ticket-actions">
                {m.email_id && (
                  <button
                    className="hide-button"
                    onClick={() => handleHideEmail(m.email_id!)}
                    title="Hide this email"
                  >
                    ×
                  </button>
                )}
                <button
                  className="small-button"
                  onClick={() => openEmail(m.gmail_message_id)}
                >
                  Open email
                </button>
              </div>
            </div>
          </div>
        ))}
        {data.length === 0 && (
          <div className="list-empty" style={{ padding: "1rem", textAlign: "center" }}>
            No meetings have been detected yet.
          </div>
        )}
      </div>
    </div>
  );
};


