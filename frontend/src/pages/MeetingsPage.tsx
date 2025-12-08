import React, { useEffect, useState } from "react";
import { EmailCard } from "../components/EmailCard";
import { Card } from "../components/Card";
import { LoadingSpinner } from "../components/LoadingSpinner";

type Meeting = {
  id: number;
  email_id?: number;
  subject: string | null;
  email_date?: string | null;
  sender?: string | null;
  gmail_message_id?: string | null;
  snippet?: string | null;
  body?: string | null;
  raw_json?: string | null;
  title?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  location?: string | null;
  attendees_json?: { attendees?: string[] } | null;
  unsubscribe_url?: string | null;
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
      setData(data.filter((m) => m.email_id !== emailId));
    } catch (error) {
      console.error("Error hiding email:", error);
      alert("Failed to hide email. Please try again.");
    }
  };

  if (loading) return <LoadingSpinner message="Loading meetings..." />;
  if (error) return <Card><div className="error">Error: {error}</div></Card>;

  return (
    <Card>
      <header className="section-header">
        <div>
          <h2 style={{ color: "white", margin: 0 }}>Meetings</h2>
          <p style={{ margin: "0.5rem 0 0 0", color: "var(--color-text-secondary)" }}>
            AI-detected meetings with structured metadata
          </p>
        </div>
      </header>
      <div className="scrollable-content">
        {data.map((meeting, index) => (
            <EmailCard
              key={meeting.id}
              id={meeting.id}
              emailId={meeting.email_id}
              subject={meeting.subject}
              sender={meeting.sender}
              date={meeting.email_date}
              snippet={meeting.snippet}
              body={meeting.body}
              rawJson={meeting.raw_json}
              gmailMessageId={meeting.gmail_message_id}
              onDelete={meeting.email_id ? handleHideEmail : undefined}
              showAddToCalendar={true}
              meetingData={{
                title: meeting.title || meeting.subject,
                startTime: meeting.start_time || meeting.email_date,
                endTime: meeting.end_time,
                location: meeting.location,
                attendees: meeting.attendees_json?.attendees || null,
              }}
              showUnsubscribe={!!meeting.unsubscribe_url}
              unsubscribeUrl={meeting.unsubscribe_url || null}
            />
          ))}
        {data.length === 0 && (
          <div className="list-empty">No meetings have been detected yet.</div>
        )}
      </div>
    </Card>
  );
};


