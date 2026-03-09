# Quick Start - Windows PowerShell

Fast setup for Windows users.

## Install OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key (copy it!)
3. Keep it safe - you'll need it

## Step 1: Setup Environment (2 min)

Open PowerShell and navigate to project:

```powershell
cd "ATS Scanner"

# Copy template
Copy-Item .env.example .env

# Edit .env - replace with your API key
notepad .env
```

Edit `.env`:
```env
OPENAI_API_KEY=sk-your-key-here
```

Save and close.

## Step 2: Start Backend (2 min)

```powershell
# Create venv
python -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1

# Install
pip install -r requirements.txt

# Start server
uvicorn backend.main:app --reload
```

Wait for:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

✅ Leave this PowerShell window OPEN

## Step 3: Start Frontend (2 min)

Open NEW PowerShell window:

```powershell
cd "ATS Scanner\frontend"

npm install

npm run dev
```

Wait for:
```
➜  Local:   http://localhost:5173/
```

## Step 4: Test (2 min)

1. Open http://localhost:5173 in browser
2. Upload resume (PDF or DOCX)
3. Paste a job description
4. Click "🚀 Analyze Now"
5. Wait 15-30 seconds
6. View dashboard

Done! 🎉

## First Run Times

- First analysis: 20-30 seconds (OpenAI API calls)
- Subsequent: 5-10 seconds
- Charts: 2-5 seconds

## When Done

Stop both PowerShell windows: `Ctrl+C`

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `OPENAI_API_KEY not found` | Check `.env` file has your key |
| `Port 8000 already in use` | Change to `--port 8001` in backend command |
| `Port 5173 already in use` | Use `npm run dev -- --port 5174` |
| Blank frontend | Check browser console (F12), refresh page |
| Upload fails | Try smaller PDF/DOCX file |

## File Locations

- Backend: Current folder / `backend/`
- Frontend: Current folder / `frontend/`
- Config: `.env` (create from `.env.example`)
- Logs: PowerShell windows console

## What You Need

- ✅ Python 3.10+ (check: `python --version`)
- ✅ Node.js 16+ (check: `node --version`)
- ✅ OpenAI API key (free credits available)

---

That's it! Questions? Check `SETUP.md` or `README.md`.
