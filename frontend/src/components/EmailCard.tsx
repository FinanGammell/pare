import React, { useState } from "react";
import { EmailViewer } from "./EmailViewer";

// Helper to determine if a date is in Eastern Daylight Time (DST)
// DST: 2nd Sunday in March to 1st Sunday in November
function _isEasternDST(year: number, month: number, day: number): boolean {
  // Month is 0-indexed in JS Date
  if (month < 2 || month > 10) return false; // Jan, Feb, Nov, Dec are always EST
  if (month > 2 && month < 10) return true; // Apr-Oct are always EDT
  
  // March: check if after 2nd Sunday
  if (month === 2) {
    const secondSunday = _getNthSunday(year, 2, 2);
    return day >= secondSunday;
  }
  
  // November: check if before 1st Sunday
  if (month === 10) {
    const firstSunday = _getNthSunday(year, 10, 1);
    return day < firstSunday;
  }
  
  return false;
}

function _getNthSunday(year: number, month: number, n: number): number {
  // Find the nth Sunday of the month
  let count = 0;
  for (let day = 1; day <= 31; day++) {
    const date = new Date(year, month, day);
    if (date.getMonth() !== month) break; // Month overflow
    if (date.getDay() === 0) { // Sunday
      count++;
      if (count === n) return day;
    }
  }
  return 31; // Fallback
}

export interface EmailCardProps {
  id: number;
  emailId?: number;
  subject: string | null;
  sender?: string | null;
  date?: string | null;
  snippet?: string | null;
  body?: string | null;
  htmlBody?: string | null;
  rawJson?: string | null;
  gmailMessageId?: string | null;
  onDelete?: (emailId: number, e: React.MouseEvent) => void;
  onClick?: () => void;
  // Action buttons
  showAddToCalendar?: boolean;
  meetingData?: {
    title?: string | null;
    startTime?: string | null;
    endTime?: string | null;
    location?: string | null;
    attendees?: string[] | null;
  };
  showAddToKeep?: boolean;
  taskData?: {
    description?: string | null;
    dueDate?: string | null;
  };
  showUnsubscribe?: boolean;
  unsubscribeUrl?: string | null;
}

export const EmailCard: React.FC<EmailCardProps> = ({
  id,
  emailId,
  subject,
  sender,
  date,
  snippet,
  body,
  htmlBody,
  rawJson,
  gmailMessageId,
  onDelete,
  onClick,
  showAddToCalendar,
  meetingData,
  showAddToKeep,
  taskData,
  showUnsubscribe,
  unsubscribeUrl,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleCardClick = (e: React.MouseEvent) => {
    // Don't expand if clicking on delete button or its container
    if ((e.target as HTMLElement).closest(".email-card-delete")) {
      return;
    }
    setIsExpanded(!isExpanded);
    if (onClick) {
      onClick();
    }
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete && emailId) {
      onDelete(emailId, e);
    }
  };

  const handleOpenEmail = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (gmailMessageId) {
      window.open(`/open_email/${gmailMessageId}`, "_blank", "noopener,noreferrer");
    }
  };

  const handleAddToCalendar = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!meetingData) return;

    const title = meetingData.title || subject || "Meeting";
    const location = meetingData.location || "";
    const attendees = meetingData.attendees || [];

    // Convert Eastern Time (from classifier) to UTC for Google Calendar
    const formatDateForCalendar = (dateStr: string | null | undefined): string => {
      if (!dateStr || dateStr.trim() === "") {
        return new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
      }

      try {
        const cleanDateStr = dateStr.trim();
        let date = new Date(cleanDateStr);

        if (isNaN(date.getTime())) {
          throw new Error("Invalid date");
        }

        // Check if date has timezone info
        const hasTimezone = cleanDateStr.includes("Z") || cleanDateStr.match(/[+-]\d{2}:?\d{2}$/);
        
        if (!hasTimezone) {
          // Date is in Eastern Time (naive), convert to UTC
          const year = date.getFullYear();
          const month = date.getMonth();
          const day = date.getDate();
          const hours = date.getHours();
          const minutes = date.getMinutes();
          const seconds = date.getSeconds();

          // Determine if DST using proper calculation
          // DST in US Eastern Time: 2nd Sunday in March to 1st Sunday in November
          const isDST = _isEasternDST(year, month, day);
          const offsetHours = isDST ? 4 : 5; // EDT is UTC-4, EST is UTC-5
          
          // Create UTC date by adding offset
          date = new Date(Date.UTC(year, month, day, hours + offsetHours, minutes, seconds));
        }

        // Format as UTC for Google Calendar (YYYYMMDDTHHmmssZ)
        return date.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
      } catch {
        return new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
      }
    };

    // Use start_time from meeting data, fallback to email date
    let startTime = meetingData.startTime;
    if (!startTime || startTime.trim() === "") {
      startTime = date || new Date().toISOString();
    }

    const start = formatDateForCalendar(startTime);

    // Calculate end time: use end_time if provided, otherwise add 1 hour
    let end: string;
    if (meetingData.endTime && meetingData.endTime.trim() !== "") {
      end = formatDateForCalendar(meetingData.endTime);
    } else {
      // Default to 1 hour duration
      try {
        const startDate = new Date(startTime);
        if (!isNaN(startDate.getTime())) {
          const endDate = new Date(startDate.getTime() + 3600000); // Add 1 hour
          end = formatDateForCalendar(endDate.toISOString());
        } else {
          const now = new Date();
          end = formatDateForCalendar(new Date(now.getTime() + 3600000).toISOString());
        }
      } catch {
        const now = new Date();
        end = formatDateForCalendar(new Date(now.getTime() + 3600000).toISOString());
      }
    }

    // Build Google Calendar URL
    const params = new URLSearchParams({
      action: "TEMPLATE",
      text: title,
      dates: `${start}/${end}`,
    });

    if (location) {
      params.append("location", location);
    }

    if (attendees && attendees.length > 0) {
      params.append("add", attendees.join(","));
    }

    const calendarUrl = `https://calendar.google.com/calendar/render?${params.toString()}`;
    window.open(calendarUrl, "_blank", "noopener,noreferrer");
  };


  const handleAddToKeep = (e: React.MouseEvent) => {
    e.stopPropagation();
    // Simply redirect to Google Keep
    window.open("https://keep.google.com", "_blank", "noopener,noreferrer");
  };

  const handleUnsubscribe = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!unsubscribeUrl) {
      console.warn("No unsubscribe URL available");
      return;
    }

    // Validate and clean the URL
    let url = unsubscribeUrl.trim();
    
    // Ensure URL has a protocol
    if (!url.match(/^https?:\/\//i)) {
      // If it starts with //, add https:
      if (url.startsWith("//")) {
        url = "https:" + url;
      } else if (url.startsWith("/")) {
        // Relative URL - this shouldn't happen but handle it
        console.warn("Relative unsubscribe URL detected:", url);
        return;
      } else {
        // Assume https if no protocol
        url = "https://" + url;
      }
    }

    // Validate it's a proper URL
    try {
      const urlObj = new URL(url);
      // Only allow http and https protocols
      if (!["http:", "https:"].includes(urlObj.protocol)) {
        console.warn("Invalid unsubscribe URL protocol:", url);
        return;
      }
      
      // Open the validated URL
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      console.error("Invalid unsubscribe URL:", url, err);
      alert(`Invalid unsubscribe URL: ${url}`);
    }
  };

  // Format date for display - always include time
  const formatDate = (dateStr: string | null | undefined): string => {
    if (!dateStr) return "";
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
      const timeStr = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

      if (diffDays === 0) {
        return timeStr;
      } else if (diffDays === 1) {
        return `Yesterday ${timeStr}`;
      } else if (diffDays < 7) {
        return `${diffDays} days ago ${timeStr}`;
      } else {
        const dateStr = date.toLocaleDateString([], { month: "short", day: "numeric" });
        return `${dateStr} ${timeStr}`;
      }
    } catch {
      return dateStr;
    }
  };

  // Clean email body: remove HTML, CSS, and long links
  const cleanBody = (text: string | null | undefined): string => {
    if (!text) return "";
    
    let cleaned = text;
    
    // Remove HTML tags
    cleaned = cleaned.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "");
    cleaned = cleaned.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "");
    cleaned = cleaned.replace(/<[^>]+>/g, "");
    
    // Decode HTML entities
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = cleaned;
    cleaned = tempDiv.textContent || tempDiv.innerText || cleaned;
    
    // Remove or truncate long URLs
    // Match URLs (http, https, www, or email-like patterns)
    cleaned = cleaned.replace(/https?:\/\/[^\s<>"']{40,}/g, (url) => {
      // Truncate very long URLs to 40 chars
      if (url.length > 40) {
        return url.substring(0, 35) + "...";
      }
      return url;
    });
    
    // Remove standalone long strings that look like URLs without protocol
    cleaned = cleaned.replace(/\b(www\.[^\s<>"']{35,}|[a-zA-Z0-9.-]+\.(com|org|net|io|co|gov|edu)[^\s<>"']{25,})/g, (match) => {
      if (match.length > 35) {
        return match.substring(0, 30) + "...";
      }
      return match;
    });
    
    // Remove very long tracking parameters and query strings
    cleaned = cleaned.replace(/[?&][a-zA-Z0-9_]+=[a-zA-Z0-9_-]{30,}/g, "");
    
    // Remove email addresses that are very long (likely tracking pixels)
    cleaned = cleaned.replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\?[^\s]{20,}/g, "");
    
    // Clean up whitespace (balanced approach - remove excessive but preserve paragraphs)
    // First, normalize all line breaks
    cleaned = cleaned.replace(/\r\n/g, "\n");
    cleaned = cleaned.replace(/\r/g, "\n");
    
    // Remove unicode whitespace characters (non-breaking spaces, etc.)
    cleaned = cleaned.replace(/[\u00A0\u1680\u2000-\u200B\u202F\u205F\u3000\uFEFF]/g, " ");
    
    // Replace tabs with spaces
    cleaned = cleaned.replace(/\t/g, " ");
    
    // Remove lines that are only whitespace (but keep lines with content)
    cleaned = cleaned.replace(/^[ \t]+$/gm, "");
    
    // Collapse multiple spaces/tabs to single space (but preserve newlines)
    cleaned = cleaned.replace(/[ \t]{2,}/g, " ");
    
    // Remove spaces at the start/end of lines (but keep the line breaks)
    cleaned = cleaned.replace(/^[ \t]+/gm, "");
    cleaned = cleaned.replace(/[ \t]+$/gm, "");
    
    // Limit consecutive blank lines to maximum of 2 (preserve paragraph breaks)
    cleaned = cleaned.replace(/\n{4,}/g, "\n\n\n");
    
    // Remove excessive blank lines at the start and end (but keep one if it exists)
    cleaned = cleaned.replace(/^\n{3,}/, "\n");
    cleaned = cleaned.replace(/\n{3,}$/, "\n");
    
    // Remove very long sequences of spaces (formatting artifacts, but keep normal spacing)
    cleaned = cleaned.replace(/ {5,}/g, " ");
    
    // Final trim
    cleaned = cleaned.trim();
    
    return cleaned;
  };

  // Extract HTML from raw_json if available
  const extractHtmlFromRawJson = (): string | null => {
    if (htmlBody) return htmlBody;
    if (!rawJson) return null;
    
    try {
      const parsed = typeof rawJson === "string" ? JSON.parse(rawJson) : rawJson;
      const payload = parsed?.payload;
      if (!payload) return null;
      
      // Try to extract HTML from payload
      const extractHtml = (part: any): string | null => {
        if (!part) return null;
        
        const mimeType = part.mimeType || "";
        const partBody = part.body || {};
        const data = partBody.data;
        
        // If this part is HTML, return it
        if (mimeType.startsWith("text/html") && data) {
          try {
            // Decode base64url (Gmail uses URL-safe base64)
            // Replace URL-safe characters and add padding if needed
            let base64 = data.replace(/-/g, "+").replace(/_/g, "/");
            const padding = 4 - (base64.length % 4);
            if (padding !== 4) {
              base64 += "=".repeat(padding);
            }
            // Use atob to decode base64, then decode as UTF-8
            const binaryString = atob(base64);
            // Convert binary string to Uint8Array
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
              bytes[i] = binaryString.charCodeAt(i);
            }
            // Decode as UTF-8 using TextDecoder
            const decoder = new TextDecoder("utf-8", { fatal: false });
            return decoder.decode(bytes);
          } catch (e) {
            console.warn("Failed to decode HTML from raw_json:", e);
            return null;
          }
        }
        
        // Check nested parts
        const parts = part.parts || [];
        for (const p of parts) {
          const html = extractHtml(p);
          if (html) return html;
        }
        
        return null;
      };
      
      return extractHtml(payload);
    } catch (e) {
      console.warn("Failed to parse raw_json:", e);
      return null;
    }
  };

  // Sanitize HTML for safe rendering (aggressive sanitization to prevent style leakage)
  const sanitizeHtml = (html: string): string => {
    // Create a temporary DOM element to parse and clean the HTML
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = html;
    
    // Remove script tags
    const scripts = tempDiv.querySelectorAll("script");
    scripts.forEach(script => script.remove());
    
    // Remove style tags (they can affect global styles)
    const styles = tempDiv.querySelectorAll("style");
    styles.forEach(style => style.remove());
    
    // Remove only truly empty elements (no text, no images, no links, no children)
    const removeEmptyElements = (element: Element) => {
      const children = Array.from(element.children);
      children.forEach(child => {
        if (child instanceof Element) {
          removeEmptyElements(child);
          const text = child.textContent?.trim() || "";
          const hasImages = child.querySelector("img");
          const hasLinks = child.querySelector("a");
          const hasContent = text.length > 0 || hasImages || hasLinks;
          // Only remove if completely empty and has no meaningful children
          if (!hasContent && child.children.length === 0 && child.tagName !== "BR" && child.tagName !== "HR") {
            child.remove();
          }
        }
      });
    };
    removeEmptyElements(tempDiv);
    
    // Remove all event handlers and dangerous attributes
    const allElements = tempDiv.querySelectorAll("*");
    allElements.forEach(el => {
      // Remove all event handlers
      Array.from(el.attributes).forEach(attr => {
        if (attr.name.startsWith("on") || attr.name === "javascript") {
          el.removeAttribute(attr.name);
        }
        // Remove class attributes (prevent external CSS from affecting)
        if (attr.name === "class") {
          el.removeAttribute("class");
        }
        // Remove id attributes (prevent JS from targeting)
        if (attr.name === "id") {
          el.removeAttribute("id");
        }
      });
      
      // For images, add safe attributes
      if (el.tagName === "IMG") {
        el.setAttribute("loading", "lazy");
        const existingStyle = el.getAttribute("style") || "";
        el.setAttribute("style", `max-width: 100%; height: auto; display: block; ${existingStyle}`);
      }
      
      // Clean inline styles - remove dangerous ones but keep safe formatting
      if (el.hasAttribute("style")) {
        const style = el.getAttribute("style") || "";
        // Remove dangerous styles
        let cleanedStyle = style
          .replace(/position\s*:\s*(absolute|fixed|sticky)[^;]*;?/gi, "")
          .replace(/z-index[^;]*;?/gi, "")
          .replace(/transform[^;]*;?/gi, "")
          .replace(/height\s*:\s*0(px)?[^;]*;?/gi, "")
          .replace(/min-height\s*:\s*0(px)?[^;]*;?/gi, "")
          // Limit excessive margins/padding but don't remove all
          .replace(/margin[^;]*:\s*(\d{3,}px|\d{3,}em)[^;]*;?/gi, "")
          .replace(/padding[^;]*:\s*(\d{3,}px|\d{3,}em)[^;]*;?/gi, "")
          .trim();
        
        // Clean up multiple semicolons
        cleanedStyle = cleanedStyle.replace(/;+/g, ";").replace(/^;|;$/g, "");
        
        if (cleanedStyle.length > 0) {
          el.setAttribute("style", cleanedStyle);
        } else {
          el.removeAttribute("style");
        }
      }
    });
    
    // Remove leading/trailing empty divs and whitespace
    let cleaned = tempDiv.innerHTML;
    // Remove empty divs at the start
    cleaned = cleaned.replace(/^(\s*<div[^>]*>\s*<\/div>\s*)+/i, "");
    // Remove empty divs at the end
    cleaned = cleaned.replace(/(\s*<div[^>]*>\s*<\/div>\s*)+$/i, "");
    // Remove multiple consecutive empty divs
    cleaned = cleaned.replace(/(<div[^>]*>\s*<\/div>\s*){2,}/gi, "");
    
    return cleaned;
  };

  const formattedDate = formatDate(date);
  const displaySubject = subject || "No subject";

  return (
    <div
      className={`email-card ${isExpanded ? "email-card-expanded" : ""}`}
      onClick={handleCardClick}
    >
      <div className="email-card-header">
        <div className="email-card-actions">
          {gmailMessageId && (
            <button
              className="email-card-action-btn"
              onClick={handleOpenEmail}
              title="Open in Gmail"
              aria-label="Open in Gmail"
            >
              📧
            </button>
          )}
          {showAddToCalendar && meetingData && (
            <button
              className="email-card-action-btn"
              onClick={handleAddToCalendar}
              title="Add to Google Calendar"
              aria-label="Add to Google Calendar"
            >
              📅
            </button>
          )}
          {showAddToKeep && taskData && (
            <button
              className="email-card-action-btn"
              onClick={handleAddToKeep}
              title="Add to Google Keep"
              aria-label="Add to Google Keep"
            >
              📝
            </button>
          )}
          {showUnsubscribe && unsubscribeUrl && (
            <button
              className="email-card-action-btn"
              onClick={handleUnsubscribe}
              title="Unsubscribe"
              aria-label="Unsubscribe"
            >
              🚫
            </button>
          )}
        </div>
        <div className="email-card-main">
          <div className="email-card-subject">{displaySubject}</div>
          <div className="email-card-meta">
            {sender && (
              <span className="email-card-sender">
                {sender.replace(/<[^>]+>/g, "").trim() || sender}
              </span>
            )}
            {formattedDate && (
              <span className="email-card-date">{formattedDate}</span>
            )}
          </div>
        </div>
        {emailId && onDelete && (
          <button
            className="email-card-delete"
            onClick={handleDelete}
            title="Hide this email"
            aria-label="Hide email"
          >
            ×
          </button>
        )}
      </div>

      {isExpanded && (
        <div className="email-card-expanded-content">
          <EmailViewer
            subject={null}
            sender={null}
            date={null}
            htmlBody={htmlBody}
            rawJson={rawJson}
            plainTextBody={body}
            snippet={snippet}
            gmailMessageId={gmailMessageId}
            showHeader={false}
          />
        </div>
      )}
    </div>
  );
};

