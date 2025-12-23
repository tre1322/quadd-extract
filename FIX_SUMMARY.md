# Railway Deployment Issues - Fixed

## Issues Identified and Resolved

### Issue 1: App Fails to Start After init_auth.py Runs

**Root Cause:**
- The start command ran `python init_auth.py; uvicorn ...` as two separate processes
- init_auth.py created the admin user in a separate Python process, then exited
- The container was stopping after init_auth.py completed instead of continuing to uvicorn
- This was likely due to process management issues in the Railway environment

**Fix:**
- **Moved admin user creation into the FastAPI lifespan function**
- Admin user is now created during app startup, in the same process as uvicorn
- Removed `python init_auth.py;` from all start commands (Procfile, railway.json, nixpacks.toml)
- Added comprehensive logging to track initialization progress

**Files Changed:**
- `src/api/main.py` - Added `init_default_admin()` function and called it in `lifespan()`
- `Procfile` - Removed init_auth.py call
- `railway.json` - Removed init_auth.py call
- `nixpacks.toml` - Removed init_auth.py call

### Issue 2: Login Returns 401 Even When Password is Correct

**Root Cause:**
- Multiple database files existed in different locations:
  - `./quadd_extract.db` (root directory)
  - `./data/processors.db`
  - `./data/quadd.db`
- When DATABASE_PATH environment variable wasn't set consistently:
  - init_auth.py created user in one database
  - FastAPI app queried a different database
  - Result: User not found → 401 error
- Lack of database path logging made this impossible to debug

**Fix:**
- **Added explicit database path logging** in the lifespan function
- Database path is now logged on startup: `Initializing database at: {db_path}`
- Admin user initialization happens in the same database connection as the app
- Added comprehensive error logging in login endpoint:
  - Checks if database is initialized before attempting login
  - Logs which specific check failed (user not found vs invalid password)
  - Returns 503 if database not initialized

**Files Changed:**
- `src/api/main.py` - Enhanced logging in lifespan and login endpoint

## How to Deploy the Fix

1. **Commit and push these changes to your repository:**
   ```bash
   git add src/api/main.py Procfile railway.json nixpacks.toml
   git commit -m "Fix: Move auth initialization to app lifespan, remove separate init_auth.py call"
   git push
   ```

2. **Railway will automatically redeploy**

3. **Expected deployment logs:**
   ```
   Starting Quadd Extract API...
   Initializing database at: /app/data/quadd_extract.db
   Database initialized successfully at: /app/data/quadd_extract.db
   Initializing authentication system...
   Creating default admin user...
   ✓ Default admin user created successfully!
   DEFAULT ADMIN CREDENTIALS
   Email:    admin@quadd.com
   Password: changeme123
   ...
   Quadd Extract API started successfully
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ```

4. **Verify the fix:**
   - App should start successfully (uvicorn will be running)
   - Login with admin@quadd.com / changeme123 should return 200 with token
   - Check Railway logs to confirm database path is correct

## Environment Variables Required

Ensure these are set in Railway:

- `DATABASE_PATH=/app/data/quadd_extract.db` ✓ (Critical - ensures consistent DB path)
- `ANTHROPIC_API_KEY=sk-ant-...` ✓ (Already set)
- `JWT_SECRET=<random-secret>` (Optional but recommended for production)
- `ALLOWED_ORIGINS=<your-domain>` (Optional, defaults to *)

## What Was NOT Changed

- `init_auth.py` - Left as-is (can still be run manually if needed)
- Database schema or models
- Authentication logic
- Password hashing/verification

## Testing Performed

✅ Admin user creation works correctly
✅ Password verification returns True
✅ Database initialization succeeds
✅ All changes are backward compatible

## Benefits of This Fix

1. **Single process execution** - Everything runs in uvicorn, no process coordination issues
2. **Guaranteed database consistency** - Admin user created in the same DB instance the app uses
3. **Better error handling** - Clear logging shows exactly what's happening
4. **Easier debugging** - Database path is logged on startup
5. **Simpler deployment** - One command instead of two sequential processes

## Rollback Plan

If needed, revert by restoring old start commands:
```bash
git revert HEAD
git push
```

However, this fix addresses the root cause and should be more reliable than the previous approach.
