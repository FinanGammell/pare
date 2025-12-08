import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

// CRITICAL: Prevent React from loading if we're on /oauth2callback
// This route must be handled exclusively by the backend Flask server
// If React loads here, it means the server incorrectly served index.html
if (window.location.pathname === "/oauth2callback") {
  // Don't render React - let the backend handle this route
  // This should never happen if server is configured correctly,
  // but serves as a safety measure
  console.warn(
    "WARNING: /oauth2callback reached React app. This should be handled by the backend server."
  );
  // Try to preserve query params and redirect to backend
  const fullUrl = window.location.href;
  window.location.replace(fullUrl);
} else {
  ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>
  );
}


