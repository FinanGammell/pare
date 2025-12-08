import React, { useEffect, useState } from "react";
import { EmailCard } from "../components/EmailCard";
import { Card } from "../components/Card";
import { LoadingSpinner } from "../components/LoadingSpinner";

type Task = {
  id: number;
  email_id?: number;
  subject: string | null;
  sender?: string | null;
  date?: string | null;
  status?: string | null;
  gmail_message_id?: string | null;
  snippet?: string | null;
  body?: string | null;
  raw_json?: string | null;
  description?: string | null;
  due_date?: string | null;
  unsubscribe_url?: string | null;
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
      setData(data.filter((t) => t.email_id !== emailId));
    } catch (error) {
      console.error("Error hiding email:", error);
      alert("Failed to hide email. Please try again.");
    }
  };

  if (loading) return <LoadingSpinner message="Loading tasks..." />;
  if (error) return <Card><div className="error">Error: {error}</div></Card>;

  return (
    <Card>
      <header className="section-header">
        <div>
          <h2 style={{ color: "white", margin: 0 }}>Tasks</h2>
          <p style={{ margin: "0.5rem 0 0 0", color: "var(--color-text-secondary)" }}>
            Inbox-derived tasks ready to action
          </p>
        </div>
      </header>
      <div className="scrollable-content">
        {data.map((task) => (
            <EmailCard
              key={task.id}
              id={task.id}
              emailId={task.email_id}
              subject={task.subject}
              sender={task.sender}
              date={task.date}
              snippet={task.snippet}
              body={task.body}
              rawJson={task.raw_json}
              gmailMessageId={task.gmail_message_id}
              onDelete={task.email_id ? handleHideEmail : undefined}
              showAddToKeep={true}
              taskData={{
                description: task.description || task.subject,
                dueDate: task.due_date || task.date,
              }}
              showUnsubscribe={!!task.unsubscribe_url}
              unsubscribeUrl={task.unsubscribe_url || null}
            />
          ))}
        {data.length === 0 && (
          <div className="list-empty">No tasks detected yet.</div>
        )}
      </div>
    </Card>
  );
};


