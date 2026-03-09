# 🚀 IntelliResume AI - Complete Setup & Run Guide

**Status:** ✅ All issues fixed and ready to run

---

## ⚡ TL;DR - Quick Start (3 Steps)

### Terminal 1: Backend
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Terminal 2: Frontend
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner\frontend"
npm run dev
```

### Browser
Go to http://localhost:5173 and start analyzing resumes!

---

## 📝 What Was Fixed

### Issue
Frontend showed: `http proxy error: /api/analyze/comprehensive ECONNREFUSED`

### Root Cause
Backend main.py had incorrect import path for `extract_resume_text`

### The Fix
Changed line 27 in `backend/main.py`:
```python
# Before (WRONG)
from .utils.resume_parser import extract_resume_text

# After (CORRECT)
from .services.resume_parser import extract_resume_text
```

### Proof
✅ Backend imports successfully  
✅ Server starts on port 8000  
✅ Health endpoint returns 200 OK  
✅ Frontend proxy can connect  

---

## 🎯 Prerequisites

### Verify You Have
```powershell
# Check Python 3.10+
python --version

# Check Node.js 18+
node --version

# Check npm 9+
npm --version
```

All should be ≥ the versions above.

---

## 🔧 First Time Setup

Only needed once.

### Step 1: Install Python Dependencies
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"
pip install -r requirements.txt
```

Expected output ends with:
```
Successfully installed [package list]
```

### Step 2: Configure .env File
```powershell
# Open .env file
notepad .env
```

Update the file with your OpenAI API key:
```env
OPENAI_API_KEY=sk-your-actual-key-here
```

Get your key from: https://platform.openai.com/api-keys

### Step 3: Install Frontend Dependencies
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner\frontend"
npm install
```

Expected output ends with:
```
added XXX packages in Xs
```

Done! You only need to do this once.

---

## ▶️ Running the System

### Every Time You Start

Open 2 PowerShell terminals side by side.

#### Terminal 1 - Backend Server
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Wait for this message:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

✅ Backend is ready!

#### Terminal 2 - Frontend Server (in a NEW terminal)
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner\frontend"
npm run dev
```

Wait for this message:
```
➜  Local:   http://localhost:5173/
```

✅ Frontend is ready!

#### Browser
Automatically opens to http://localhost:5173 or manually go there.

---

## 📖 Using the Application

### Step 1: Upload Resume
1. Click the resume upload box
2. Select a PDF or DOCX resume file
3. File appears in the upload area

### Step 2: Add Job Description
Choose one:

**Option A - Paste Text:**
1. Click in the "Paste Job Description" text box
2. Paste the job description text
3. Done!

**Option B - Upload File:**
1. Click the JD upload box
2. Select a PDF, DOCX, or TXT file
3. File appears in the upload area

### Step 3: Analyze
1. Click the **Analyze Now** button
2. Wait 10-30 seconds (depends on OpenAI response)
3. See loading indicator

### Step 4: View Results
View results in 5 tabs:

**📊 Dashboard**
- ATS Score
- 7 professional charts
- Key metrics

**✨ Optimized Resume**
- Revised resume text
- Ready to copy/paste
- Download as DOCX

**🎯 Skill Gap**
- Matched skills (green)
- Missing skills (orange)
- Gap percentage

**⭐ Quality Score**
- Readability score
- Formatting score
- Content score
- Keyword density score
- Tips for improvement

**🔥 Keywords**
- Top keywords found
- Required skills needed
- Recommended tools

### Step 5: Download
1. Click **Download DOCX** button
2. Save the file
3. Open in Word to format further

---

## 🔍 Troubleshooting

### Backend Won't Start

**Error: ModuleNotFoundError: No module named 'fastapi'**
```powershell
pip install -r requirements.txt
```

**Error: Port 8000 already in use**
```powershell
# Find what's using port 8000
netstat -ano | findstr ":8000"

# Kill it (replace XXXX with PID)
taskkill /PID XXXX /F

# Or use a different port
python -m uvicorn backend.main:app --port 8001
```
Then update frontend proxy in `frontend/vite.config.ts`

**Error: ImportError in backend/main.py**
```powershell
# Check line 27 has:
findstr "from .services.resume_parser import extract_resume_text" backend\main.py

# If not, manually fix it
```

---

### Frontend Won't Start

**Error: npm command not found**
```powershell
# Install Node.js from https://nodejs.org
# Choose LTS version
# Then restart PowerShell
```

**Error: missing node_modules**
```powershell
cd frontend
npm install
```

---

### Connection Errors

**"http proxy error: /api/analyze/comprehensive" in browser console**

1. Check backend is running:
```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
# Should show StatusCode: 200
```

2. Check proxy in vite.config.ts:
```powershell
cat "frontend\vite.config.ts"
# Should show: proxy: { "/api": "http://localhost:8000" }
```

3. Restart both servers:
   - Stop backend (Ctrl+C)
   - Stop frontend (Ctrl+C)  
   - Start backend again
   - Start frontend again

---

### Analysis Returns Error

**"OPENAI_API_KEY error" or "rate limited"**

1. Check .env file:
```powershell
type .env
# Should show: OPENAI_API_KEY=sk-...
```

2. If not set:
```powershell
notepad .env
# Add: OPENAI_API_KEY=sk-your-key-here
# Save and close
```

3. Restart backend to reload .env:
   - Stop backend (Ctrl+C)
   - Start backend again

---

### Browser Shows Blank Page

Press F12 to open Developer Console and check for errors.

Common fixes:
1. Clear browser cache: Ctrl+Shift+Delete
2. Refresh page: F5 or Ctrl+R
3. Hard refresh: Ctrl+Shift+R
4. Check frontend is running on port 5173
5. Check backend is running on port 8000

---

## 📊 System Architecture

```
User's Browser
    ↓ (http://localhost:5173)
    ↓
React Frontend (Vite)
    ↓ (proxied to localhost:8000)
    ↓
FastAPI Backend
    ├─ Resume Parser (extract text)
    ├─ JD Analyzer (OpenAI parse job description)
    ├─ ATS Optimizer (OpenAI rewrite resume)
    ├─ Scorer (calculate ATS match)
    ├─ Skill Analyzer (skill gap)
    ├─ Quality Scorer (resume quality)
    ├─ Keyword Heatmap (important keywords)
    ├─ Visualizer (generate charts)
    ├─ Writing Feedback (improve writing)
    └─ Doc Generator (export DOCX)
    ↓
OpenAI API (gpt-4o-mini)
    ↓
Results returned to React
    ↓
Dashboard displays with charts
```

---

## 🔑 Configuration

### .env File
Location: `c:\Users\amrit\OneDrive\Documents\ATS Scanner\.env`

Required:
```env
OPENAI_API_KEY=sk-proj-your-key-here
```

Get from: https://platform.openai.com/api-keys

Optional:
```env
CHARTS_DIR=backend/charts
```

### vite.config.ts
Location: `frontend/vite.config.ts`

Should have:
```typescript
server: {
  proxy: {
    "/api": "http://localhost:8000"
  }
}
```

This tells frontend to send `/api/*` requests to backend on port 8000.

---

## 📱 Testing the API Directly

### Health Check
```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
# Returns: {"status": "ok", "service": "IntelliResume AI"}
```

### Interactive API Docs
Go to: http://127.0.0.1:8000/docs

Try endpoints with Swagger UI:
- `/health` - Server status
- `/api/analyze/comprehensive` - Main analysis
- `/api/download-docx` - Export DOCX

---

## 🚀 Production Deployment

When ready to deploy:

1. **Backend** - Deploy to:
   - Railway.app
   - Render.com
   - AWS
   - Or your own server

2. **Frontend** - Deploy to:
   - Vercel.com
   - Netlify.com
   - GitHub Pages

See `README.md` for detailed deployment instructions.

---

## 📞 Need Help?

### Check These Files
- `DEBUGGING_GUIDE.md` - Detailed troubleshooting
- `BACKEND_FIX_REPORT.md` - What was fixed
- `README.md` - Full project documentation
- `FEATURES.md` - All features explained

### Run This Script
```powershell
.\RUN_BACKEND.ps1
# Checks dependencies and starts with helpful messages
```

---

## ✅ Verification Checklist

After starting both servers, verify:

- [ ] Backend starts without errors
- [ ] Frontend starts without errors
- [ ] Can access http://localhost:5173
- [ ] Resume upload works
- [ ] Job description input works
- [ ] "Analyze Now" button responds
- [ ] Dashboard shows with charts
- [ ] All 5 tabs display
- [ ] Can download DOCX
- [ ] No console errors (F12)

If all checked ✅, your system is working perfectly!

---

## 🎉 You're Ready!

**Summary:**
1. Backend fixed ✅
2. Frontend configured ✅
3. All dependencies installed ✅
4. Ready to analyze resumes! 🚀

**Start using it:**
```powershell
# Terminal 1
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend && npm run dev

# Browser
http://localhost:5173
```

Enjoy! 🎊
