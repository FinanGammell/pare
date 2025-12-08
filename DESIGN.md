## Architecture Overview

Pare Email Suite organizes Gmail inboxes by turning raw email text into clear categories you can act on. The system has a Flask backend and a React frontend, but in production they run as one service on Railway. Flask serves both the API routes and the built frontend, which keeps deployment simple and ensures the OAuth callback always hits the backend. When you connect your Gmail, the app downloads your messages, classifies them through GPT-4o-mini, stores the results, and shows them in the UI. Email processing runs in the background, so you can use the app right away without waiting for the sync to complete.

## OAuth Implementation and Security

OAuth lives entirely in the backend to keep your tokens safe. When you click “Sign in,” the frontend sends you to /login, where Flask creates the Google OAuth request and stores a random state token in your session. Google sends you back to /oauth2callback, where Flask checks the state and exchanges the authorization code for access and refresh tokens. Early in development, the frontend intercepted the callback route and broke the flow, so we shifted all static-file serving to Flask to guarantee the backend owns that path. Session cookies follow strict rules: HttpOnly and Secure in production, and environment-specific SameSite settings to ensure the Google redirect works.

## Database Design

The database uses SQLite because it’s simple and reliable for a single user. SQLite reduces complexity for a single-user tool. The in-memory job queue avoids external services but loses state on restarts. The DB has tables for users, tokens, emails, and classification results. Each email entry stores the full Gmail JSON payload, which lets us extract fields later without guessing formats. Parsed data—such as subjects, dates, and bodies—lives in well-structured columns. Classification results link back to their emails and drive downstream features such as meeting extraction and task creation.

## AI Classification System

A batch processor sends groups of emails to GPT-4o-mini with strict instructions to return clean JSON and consistent time formats. GPT-4o-mini trades a small accuracy difference for much faster and cheaper performance. This improves speed and avoids malformed output. Threaded processing handles up to 25 emails at a time without blocking the main application. The system validates every result before writing to the database. If one email fails, the rest continue. This approach cuts cost, speeds up classification, and keeps the system stable during large inbox syncs. 

## Frontend and Backend Integration

During development, React runs on port 5173 and proxies backend traffic to Flask on 5001. In production, React builds to static files that Flask serves directly. Flask uses a catch-all route for client-side navigation but never serves the React app for /oauth2callback. This prevents OAuth loops and keeps routing predictable. The unified setup removes the need for separate hosting and avoids complex networking issues.

## Background Processing

Email syncing and classification run in background threads so the UI stays responsive. An in-memory job queue tracks status and progress. This avoids the overhead of Redis or Celery while still giving you live updates through API polling. Thread locks prevent two jobs for the same user from running at once. If the server restarts, jobs disappear, but you can trigger a new sync with one click.

## Security Considerations

OAuth tokens stay in the backend and never touch the frontend. Cookies are HttpOnly and Secure in production. Input is validated before database use, and email HTML is cleaned before rendering. These steps protect against SQL injection and session theft. The system rejects malformed OAuth callbacks and invalid AI responses to keep state consistent.

## Future Improvements

Railway deployment in production would be an ideal next step to move away from local hosting. This is unfortunately not a possibility due to the restrictions Google Cloud API places on tools that are not developer-approved. I was not able to deploy this application in a non-local hosted setting for this reason, despite many hours of trying to.

The accuracy of meeting imports is not always the best. For implicit times, the AI inferences are not always the best. Improving this will be a goal. 

Moreover, if I had more time I would try to create an auto import feature for tasks. I believe there exists a Google Keep API that could help me achieve this.

# Thanksssss
Thanks for a wonderful semester Mo +all CS50 teaching staff!
`:)`