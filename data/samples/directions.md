Prepare the project for secure Railway deployment using Nixpacks. Review and create/update all necessary files.
1.	CHECK AND UPDATE railway.json:
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "nixpacks"
  },
  "deploy": {
    "startCommand": "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}",
    "restartPolicyType": "on_failure",
    "restartPolicyMaxRetries": 3
  }
}
```

2. CHECK AND UPDATE Procfile:
```
web: uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
CREATE nixpacks.toml for build configuration:
[phases.setup]
nixPkgs = ["python311", "tesseract", "poppler_utils"]

[phases.install]
cmds = ["pip install -r requirements.txt"]

[start]
cmd = "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
```

4. CHECK requirements.txt includes ALL dependencies:
- fastapi
- uvicorn
- python-multipart
- anthropic
- pyjwt
- bcrypt
- pdf2image
- pytesseract
- pillow
- python-docx
- openpyxl
- pandas
- aiofiles
- jinja2

5. UPDATE src/api/main.py for production security:
- Ensure CORS is configured properly for production (allow your Railway domain)
- Ensure JWT_SECRET is loaded from environment variable (not hardcoded)
- Ensure ANTHROPIC_API_KEY is loaded from environment variable
- Ensure database path works with Railway volume (/app/data/ if volume mounted)

6. CREATE .env.example showing required environment variables:
```
JWT_SECRET=your-secure-random-string-here
ANTHROPIC_API_KEY=sk-ant-your-key-here
PORT=8000
DATABASE_PATH=/app/data/quadd_extract.db
```

7. UPDATE database path in code:
- Check src/db/database.py
- Database should use environment variable DATABASE_PATH or default to /app/data/quadd_extract.db for Railway
- Ensure the data directory is created if it doesn't exist

8. CHECK .gitignore excludes:
- .env (never commit secrets)
- *.db (database files)
- __pycache__/
- venv/

9. SECURITY CHECK:
- No hardcoded passwords anywhere in code
- No API keys in code
- No default credentials visible in frontend
- JWT secret loaded from environment only

10. CREATE runtime.txt specifying Python version:
```
python-3.11.0
Report back what files were created, updated, or already correct. List any security issues found.
