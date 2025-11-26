# Railway Deployment Guide for Pare

## Quick Start

1. **Connect Repository to Railway**
   - Go to [Railway](https://railway.app)
   - Create new project
   - Connect your GitHub repository

2. **Set Environment Variables**
   In Railway dashboard → Variables tab, add:

   ```
   FLASK_SECRET_KEY=<generate-strong-random-key>
   GOOGLE_CLIENT_ID=<your-google-client-id>
   GOOGLE_CLIENT_SECRET=<your-google-client-secret>
   OPENAI_API_KEY=<your-openai-api-key>
   ```

   **Note:** `GOOGLE_REDIRECT_URI` is automatically constructed from your Railway domain.

3. **Deploy**
   - Railway will automatically detect the `Procfile` and deploy
   - The app will be available at `https://your-app-name.up.railway.app`

4. **Configure Google OAuth**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Edit your OAuth 2.0 Client ID
   - Add authorized redirect URI:
     ```
     https://your-app-name.up.railway.app/oauth2callback
     ```

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `FLASK_SECRET_KEY` | ✅ Yes | Strong random key for Flask sessions (generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `GOOGLE_CLIENT_ID` | ✅ Yes | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | ✅ Yes | Google OAuth client secret |
| `OPENAI_API_KEY` | ✅ Yes | OpenAI API key for email classification |
| `GOOGLE_REDIRECT_URI` | ❌ No | Auto-constructed from Railway domain (override if needed) |
| `RAILWAY_PUBLIC_DOMAIN` | ❌ No | Auto-set by Railway (used as fallback) |
| `PORT` | ❌ No | Auto-set by Railway |
| `DATABASE_URL` | ❌ No | Optional PostgreSQL URL (SQLite used by default) |

## How It Works

- **Procfile**: Tells Railway to run Gunicorn with the Flask app
- **Port Binding**: Railway sets `PORT` env var, Gunicorn binds to `0.0.0.0:$PORT`
- **OAuth Redirect**: Automatically uses `url_for('oauth2callback', _external=True)` to get the correct domain
- **Database**: SQLite file is created automatically (persists in Railway's filesystem)

## Troubleshooting

### OAuth Redirect URI Mismatch
- Ensure Google Cloud Console has the exact Railway domain URL
- Check that `GOOGLE_REDIRECT_URI` env var matches (or leave unset for auto-detection)

### App Won't Start
- Check Railway logs for errors
- Verify all required environment variables are set
- Ensure `requirements.txt` includes all dependencies

### Database Issues
- SQLite file is created at `pare.sqlite3` in the project root
- For production, consider migrating to PostgreSQL (set `DATABASE_URL`)

## Local Development

The app still works locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FLASK_SECRET_KEY="dev-key"
export GOOGLE_CLIENT_ID="..."
# ... etc

# Run locally
python app.py
# or
flask --app app:create_app run --debug
```

## Production Notes

- Gunicorn runs with 1 worker by default (increase in Procfile if needed)
- Timeout set to 120 seconds for long-running sync/process operations
- Debug mode is disabled in production (controlled by `FLASK_DEBUG` env var)

