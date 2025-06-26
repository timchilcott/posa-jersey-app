# POSA Jersey App

This FastAPI application manages player registrations and jersey assignments for POSA sports. It now includes a simple session-based authentication system.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**
   - `DATABASE_URL` – SQLAlchemy connection string to your database
   - `SECRET_KEY` – secret used for session cookies
   - `ADMIN_EMAIL` – email for the initial admin account (optional)
   - `ADMIN_PASSWORD` – password for the initial admin account (optional)

3. **Run the app**
   ```bash
   uvicorn app.main:app --reload
   ```

An admin user is created on first start if no users exist. Additional users can be invited from the "Invite User" link once logged in.

## Testing

Run the unit tests with:

```bash
pytest -q
```

### Debugging inbound emails

When using the `/email/receive` endpoint in development, inbound messages are saved to timestamped files like `captured_email_20240101_123456.txt` in the project root. This helps inspect the raw email content for troubleshooting.

