import React, { useEffect, useState } from "react";

type JunkEmail = {
  id: number;
  subject: string | null;
  snippet?: string | null;
  gmail_message_id?: string | null;
};

export const JunkPage: React.FC = () => {
  const [data, setData] = useState<JunkEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/api/junk", { credentials: "include" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as JunkEmail[];
        setData(json);
      } catch (e: any) {
        setError(e.message ?? "Failed to load junk mail");
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
      setData(data.filter((e) => e.id !== emailId));
    } catch (error) {
      console.error("Error hiding email:", error);
      alert("Failed to hide email. Please try again.");
    }
  };

  if (loading) return <div className="card skeleton">Loading…</div>;
  if (error) return <div className="card error">Error: {error}</div>;

  return (
    <div className="card">
      <header className="section-header">
        <h2>Inbox hygiene</h2>
        <p>Newsletters & junk Pare thinks you can safely ignore or unsubscribe.</p>
      </header>
      <div>
        {data.map((e) => (
          <div key={e.id} className="email-ticket">
            <div className="email-ticket-content">
              <div className="email-ticket-info">
                <div className="email-ticket-title">{e.subject ?? "No subject"}</div>
                {e.snippet && <div className="email-ticket-meta">{e.snippet}</div>}
              </div>
              <div className="email-ticket-actions">
                <button
                  className="hide-button"
                  onClick={() => handleHideEmail(e.id)}
                  title="Hide this email"
                >
                  ×
                </button>
                <button
                  className="small-button"
                  onClick={() => openEmail(e.gmail_message_id)}
                >
                  Open email
                </button>
              </div>
            </div>
          </div>
        ))}
        {data.length === 0 && (
          <div className="list-empty" style={{ padding: "1rem", textAlign: "center" }}>
            No junk or newsletters detected yet. Inbox looks clean.
          </div>
        )}
      </div>
    </div>
  );
};


