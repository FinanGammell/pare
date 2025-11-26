# Pare Email Suite

Starter scaffold for the Pare Flask application.

## Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Set the required environment variables (optional defaults exist), especially `OPENAI_API_KEY` for AI classification:
   - `SECRET_KEY`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI`
   - `OPENAI_API_KEY`
3. (Optional) Initialize/verify the SQLite schema manually:

   ```bash
   flask --app app:create_app shell -c "from models import ensure_tables; ensure_tables()"
   ```
4. Run the dev server (tables will be created automatically on first run):

   ```bash
   flask --app app:create_app run --debug
   ```

## Next Steps

- Connect OpenAI classification in `services/classifier.py`.
- Expand dashboards with real metrics and add authentication/session handling.
- Trigger the `/process` route after syncing to enrich emails with meetings, tasks, and unsubscribe data.
