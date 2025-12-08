import React, { useEffect, useState } from "react";
import { EmailCard } from "../components/EmailCard";
import { Card } from "../components/Card";
import { LoadingSpinner } from "../components/LoadingSpinner";

type JunkEmail = {
  id: number;
  email_id?: number;
  subject: string | null;
  sender?: string | null;
  date?: string | null;
  snippet?: string | null;
  body?: string | null;
  gmail_message_id?: string | null;
  raw_json?: string | null;
  unsubscribe_url?: string | null;
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

  const handleHideEmail = async (emailId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await fetch(`/api/hide-email/${emailId}`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        throw new Error("Failed to hide email");
      }
      // Remove from local state immediately
      setData(data.filter((email) => email.email_id !== emailId && email.id !== emailId));
    } catch (error) {
      console.error("Error hiding email:", error);
      alert("Failed to hide email. Please try again.");
    }
  };

  if (loading) return <LoadingSpinner message="Loading inbox hygiene..." />;
  if (error) return <Card><div className="error">Error: {error}</div></Card>;

  return (
    <Card>
      <header className="section-header">
        <div>
          <h2 style={{ color: "white", margin: 0 }}>Inbox Hygiene</h2>
          <p style={{ margin: "0.5rem 0 0 0", color: "var(--color-text-secondary)" }}>
            Newsletters & junk Pare thinks you can safely ignore or unsubscribe
          </p>
        </div>
      </header>
      <div className="scrollable-content">
        {data.map((email) => (
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
              showUnsubscribe={!!email.unsubscribe_url}
              unsubscribeUrl={email.unsubscribe_url || null}
            />
          ))}
        {data.length === 0 && (
          <div className="list-empty">No junk or newsletters detected yet. Inbox looks clean.</div>
        )}
      </div>
    </Card>
  );
};


