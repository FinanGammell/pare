import React, { useEffect, useRef, useState } from "react";
import DOMPurify from "dompurify";

export interface EmailViewerProps {
  subject?: string | null;
  sender?: string | null;
  date?: string | null;
  htmlBody?: string | null;
  rawJson?: string | null;
  plainTextBody?: string | null;
  snippet?: string | null;
  gmailMessageId?: string | null;
  showHeader?: boolean;
}

/**
 * EmailViewer - Renders emails with full HTML fidelity, exactly as they appear in Gmail.
 * Uses an iframe for complete CSS isolation while preserving all formatting.
 */
export const EmailViewer: React.FC<EmailViewerProps> = ({
  subject,
  sender,
  date,
  htmlBody,
  rawJson,
  plainTextBody,
  snippet,
  gmailMessageId,
  showHeader = true,
}) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [htmlContent, setHtmlContent] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);

  // Extract HTML from raw_json if available
  const extractHtmlFromRawJson = (): string | null => {
    if (htmlBody) return htmlBody;
    if (!rawJson) return null;

    try {
      const parsed = typeof rawJson === "string" ? JSON.parse(rawJson) : rawJson;
      const payload = parsed?.payload;
      if (!payload) return null;

      // Recursively extract HTML from payload
      const extractHtml = (part: any): { html: string | null; text: string | null } => {
        if (!part) return { html: null, text: null };

        const mimeType = part.mimeType || "";
        const partBody = part.body || {};
        const data = partBody.data;

        const decodeBase64 = (data: string): string | null => {
          try {
            // Decode base64url (Gmail uses URL-safe base64)
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
            console.warn("Failed to decode base64:", e);
            return null;
          }
        };

        // If this part is HTML, decode and return it
        if (mimeType.startsWith("text/html") && data) {
          const decoded = decodeBase64(data);
          if (decoded) {
            return { html: decoded, text: null };
          }
        }

        // If this part is plain text, decode it
        if (mimeType.startsWith("text/plain") && data) {
          const decoded = decodeBase64(data);
          if (decoded) {
            return { html: null, text: decoded };
          }
        }

        // Check nested parts (multipart messages)
        const parts = part.parts || [];
        let htmlContent = null;
        let textContent = null;

        for (const p of parts) {
          const result = extractHtml(p);
          if (result.html) {
            htmlContent = result.html;
          } else if (result.text && !textContent) {
            textContent = result.text;
          }
        }

        // Prefer HTML over plain text
        return { html: htmlContent, text: textContent };
      };

      const result = extractHtml(payload);
      return result.html || result.text;

      return extractHtml(payload);
    } catch (e) {
      console.warn("Failed to parse raw_json:", e);
      return null;
    }
  };

  // Format date for display
  const formatDate = (dateStr: string | null | undefined): string => {
    if (!dateStr) return "";
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

      if (diffDays === 0) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      } else if (diffDays === 1) {
        return "Yesterday";
      } else if (diffDays < 7) {
        return `${diffDays} days ago`;
      } else {
        return date.toLocaleDateString([], { month: "short", day: "numeric", year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined });
      }
    } catch {
      return dateStr;
    }
  };

  // Sanitize HTML with DOMPurify - preserve all safe styles and formatting
  const sanitizeHtml = (html: string): string => {
    // Configure DOMPurify to be permissive for email HTML while still being safe
    return DOMPurify.sanitize(html, {
      // Allow all safe HTML tags commonly used in emails
      ALLOWED_TAGS: [
        "p", "div", "span", "br", "hr", "a", "img", "table", "tbody", "thead", "tfoot", "tr", "td", "th",
        "ul", "ol", "li", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
        "strong", "b", "em", "i", "u", "s", "strike", "del", "ins", "sub", "sup",
        "blockquote", "pre", "code", "kbd", "samp", "var", "abbr", "acronym", "address",
        "cite", "q", "dfn", "time", "mark", "small", "big", "font", "center",
        "style", "link", "meta", "title", "head", "body", "html", "section", "article",
        "header", "footer", "nav", "aside", "main", "figure", "figcaption"
      ],
      // Allow all safe attributes including style for email formatting
      ALLOWED_ATTR: [
        "href", "src", "alt", "title", "width", "height", "align", "valign",
        "colspan", "rowspan", "cellpadding", "cellspacing", "border", "bgcolor",
        "color", "face", "size", "style", "class", "id", "target", "rel",
        "border", "frameborder", "marginwidth", "marginheight", "scrolling",
        "background", "dir", "lang", "type", "media"
      ],
      // Allow data URIs for embedded images
      ALLOW_DATA_ATTR: true,
      // Keep relative URLs
      KEEP_CONTENT: true,
      // Allow style attributes (critical for email formatting)
      ADD_TAGS: ["style"],
      ADD_ATTR: ["style"],
      // Only forbid truly dangerous tags
      FORBID_TAGS: ["script", "iframe", "object", "embed", "form", "input", "button", "textarea", "select"],
      // Only forbid dangerous event handlers
      FORBID_ATTR: ["onerror", "onload", "onclick", "onmouseover", "onmouseout", "onfocus", "onblur", "onchange", "onsubmit"],
      // Return DOM instead of string to preserve more formatting
      RETURN_DOM: false,
      RETURN_DOM_FRAGMENT: false,
    });
  };

  // Prepare HTML content for iframe
  useEffect(() => {
    const prepareContent = () => {
      setIsLoading(true);
      
      // Try to get HTML content
      let html = extractHtmlFromRawJson();
      
      if (!html && plainTextBody) {
        // Fallback to plain text - convert to HTML
        html = `<pre style="font-family: inherit; white-space: pre-wrap; word-wrap: break-word;">${DOMPurify.sanitize(plainTextBody)}</pre>`;
      } else if (!html && snippet) {
        // Last resort - use snippet
        html = `<p>${DOMPurify.sanitize(snippet)}</p>`;
      }

      if (html) {
        // Sanitize the HTML
        const sanitized = sanitizeHtml(html);
        
        // Create a complete HTML document with proper styling
        // Use minimal base styles to avoid interfering with email CSS
        const fullHtml = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    /* Minimal base styles - let email CSS take precedence */
    body {
      margin: 0;
      padding: 16px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      color: #333;
      background: #fff;
      word-wrap: break-word;
      overflow-wrap: break-word;
    }
    /* Responsive images - only if not already styled */
    img:not([style*="width"]):not([style*="max-width"]) {
      max-width: 100%;
      height: auto;
    }
    /* Responsive tables - only if not already styled */
    table:not([style*="width"]):not([style*="max-width"]) {
      max-width: 100%;
    }
    /* Default link styling - only if not already styled */
    a:not([style*="color"]) {
      color: #1a73e8;
    }
    /* Preserve email-specific box-sizing */
    *, *::before, *::after {
      box-sizing: border-box;
    }
  </style>
</head>
<body>
  ${sanitized}
</body>
</html>`;
        
        setHtmlContent(fullHtml);
      } else {
        setHtmlContent(`
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {
      margin: 0;
      padding: 16px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #666;
    }
  </style>
</head>
<body>
  <p>No email content available.</p>
</body>
</html>`);
      }
      
      setIsLoading(false);
    };

    prepareContent();
  }, [htmlBody, rawJson, plainTextBody, snippet]);

  // Load content into iframe
  useEffect(() => {
    if (iframeRef.current && htmlContent) {
      const iframe = iframeRef.current;
      const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
      
      if (iframeDoc) {
        iframeDoc.open();
        iframeDoc.write(htmlContent);
        iframeDoc.close();
        
        // Ensure images load
        const images = iframeDoc.querySelectorAll("img");
        images.forEach((img) => {
          img.loading = "lazy";
          // Force reload if image failed
          img.onerror = () => {
            const src = img.getAttribute("src");
            if (src) {
              img.src = src;
            }
          };
        });
      }
    }
  }, [htmlContent]);

  const formattedDate = date ? formatDate(date) : "";
  const displaySubject = subject || "No subject";
  const displaySender = sender ? sender.replace(/<[^>]+>/g, "").trim() : "Unknown sender";

  return (
    <div className="email-viewer">
      {showHeader && (subject || sender || date) && (
        <div className="email-viewer-header">
          <div className="email-viewer-subject">{displaySubject}</div>
          <div className="email-viewer-meta">
            <span className="email-viewer-sender">{displaySender}</span>
            {formattedDate && <span className="email-viewer-date">{formattedDate}</span>}
          </div>
        </div>
      )}
      
      <div className="email-viewer-body-container">
        {isLoading ? (
          <div className="email-viewer-loading">Loading email content...</div>
        ) : (
          <iframe
            ref={iframeRef}
            className="email-viewer-iframe"
            title="Email content"
            sandbox="allow-same-origin"
            scrolling="yes"
          />
        )}
      </div>
      
      {gmailMessageId && (
        <div className="email-viewer-actions">
          <button
            className="email-viewer-open-button"
            onClick={() => {
              const url = `/open_email/${gmailMessageId}`;
              // Open in a new tab without giving the new page access to the opener
              window.open(url, "_blank", "noopener,noreferrer");
            }}
          >
            Open email in Gmail
          </button>
        </div>
      )}
    </div>
  );
};

