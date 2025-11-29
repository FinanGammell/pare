# Pare Phase 1 Deployment Checklist

## ✅ Critical Issues Fixed

All critical issues identified in the audit have been resolved:

1. ✅ **OAuth Redirect URI** - Updated to match `/oauth2callback` route
2. ✅ **OpenAI Model Name** - Changed from invalid `gpt-4.1-mini` to `gpt-4o-mini`
3. ✅ **Flask Deprecated Decorator** - Removed `before_first_request` (tables created in app.py)
4. ✅ **SECRET_KEY Validation** - Added warning for dev key usage
5. ✅ **OAuth Error Handling** - Added try/except in callback route

---

## Pre-Deployment Checklist

### Environment Variables (Required)

```bash
# Security
export SECRET_KEY="<generate-strong-random-key>"

# Google OAuth
export GOOGLE_CLIENT_ID="<your-client-id>"
export GOOGLE_CLIENT_SECRET="<your-client-secret>"
export GOOGLE_REDIRECT_URI="https://your-domain.com/oauth2callback"

# OpenAI
export OPENAI_API_KEY="<your-openai-key>"
```

**Generate SECRET_KEY:**
```python
import secrets
print(secrets.token_hex(32))
```

### Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** → **Credentials**
3. Edit your OAuth 2.0 Client ID
4. Add **Authorized redirect URIs**:
   - Development: `http://localhost:5001/oauth2callback`
   - Production: `https://pare.up.railway.app/oauth2callback`
5. Verify **Authorized JavaScript origins**:
   - Development: `http://localhost:5001`
   - Production: `https://pare.up.railway.app`

### Verify OAuth Scopes

Ensure these scopes are enabled:
- `https://www.googleapis.com/auth/userinfo.email`
- `https://www.googleapis.com/auth/userinfo.profile`
- `https://www.googleapis.com/auth/gmail.readonly`

### Database

- SQLite database will be created automatically at `pare.sqlite3`
- Ensure write permissions in deployment directory
- For Phase 2, plan migration to PostgreSQL/MySQL

### Production Server Setup

**Using Gunicorn (recommended):**

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"
```

**Environment:**
```bash
export FLASK_ENV=production
export FLASK_DEBUG=0
```

### HTTPS Requirement

⚠️ **CRITICAL:** OAuth requires HTTPS in production. Ensure:
- SSL certificate configured
- All redirect URIs use `https://`
- HSTS headers enabled

### Testing Checklist

- [ ] OAuth login flow works end-to-end
- [ ] Gmail sync fetches emails correctly
- [ ] OpenAI classification processes emails
- [ ] All routes render without errors
- [ ] Flash messages display correctly
- [ ] Database persists data across restarts
- [ ] Token refresh works when tokens expire

### Monitoring

Add logging for:
- OAuth errors
- Gmail API failures
- OpenAI API errors
- Database connection issues

---

## Deployment Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (use .env file or export)
export SECRET_KEY="..."
export GOOGLE_CLIENT_ID="..."
# ... etc

# Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"

# Or with Flask dev server (development only)
flask --app app:create_app run --host=0.0.0.0 --port=8000
```

---

## Post-Deployment Verification

1. Visit homepage - should load without errors
2. Click "Connect Gmail" - should redirect to Google
3. Complete OAuth - should redirect back and show dashboard
4. Click "Sync" - should fetch emails from Gmail
5. Click "Process" - should classify emails with OpenAI
6. Navigate to Meetings/Tasks/Junk/Analytics - all should render

---

## Known Limitations (Phase 1)

- SQLite database (single-user, file-based)
- No user authentication middleware (session-based only)
- No rate limiting on API endpoints
- No background job queue (sync/process run synchronously)
- No email body truncation for very large emails (may hit OpenAI token limits)

These will be addressed in Phase 2.

---

## Support

If deployment issues occur:
1. Check `AUDIT_REPORT.md` for detailed issue analysis
2. Verify all environment variables are set
3. Check Google Cloud Console OAuth settings
4. Review application logs for errors
5. Ensure HTTPS is properly configured

---

**Status: READY FOR DEPLOYMENT** ✅

All critical issues have been resolved. Proceed to Lovable deployment.

