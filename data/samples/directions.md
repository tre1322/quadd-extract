I'm deploying quadd-extract to Railway and login doesn't work - always "Invalid email or password".

The app runs fine locally at localhost:8000. Railway deployment starts successfully but the database has no users.

**The problem:** init_auth.py should create admin@quadd.com with password "changeme123" but it's not working on Railway.

**What I need you to do:**

1. Check if init_auth.py actually runs - look at the Railway deploy logs or add debug output
2. Check the database.py to see how DATABASE_PATH is used and if the path matches the Railway volume mount (/app/data)
3. Verify the volume is mounted correctly - Railway volume should be at /app/data and DATABASE_PATH should be /app/data/quadd_extract.db
4. Check if there's a mismatch between where init_auth.py writes vs where main.py reads the database
5. Look at how the local setup works (it uses start_ui.bat) and make Railway work the same way

**Key files to check:**
- init_auth.py (creates admin user)
- src/db/database.py (database connection)
- src/api/main.py (app startup)
- Procfile (Railway start command)
- railway.json (Railway config)

**Railway environment variables set:**
- ANTHROPIC_API_KEY
- JWT_SECRET  
- DATABASE_PATH=/app/data/quadd_extract.db

**Railway volume:** mounted at /app/data

Find why the admin user isn't being created or isn't being found, and fix it.

