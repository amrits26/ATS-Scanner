# 🔧 ATS Scanner Debugging & Setup Guide

**Status:** ✅ Backend issue FIXED - Import path corrected

---

## 🎯 Problem Summary

**Error:** Vite proxy error when connecting frontend to backend
```
http proxy error: /api/analyze/comprehensive
ECONNREFUSED
```

**Root Cause:** Incorrect import path in `backend/main.py`
- Was importing: `from .utils.resume_parser import extract_resume_text` ❌
- Should import: `from .services.resume_parser import extract_resume_text` ✅

**Status:** ✅ FIXED in backend/main.py (line 27)

---

## ✅ Quick Start (After Fix)

### Terminal 1: Start Backend
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete
```

### Terminal 2: Start Frontend
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner\frontend"
npm run dev
```

Expected output:
```
  VITE v5.x .x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

### Browser
1. Navigate to: `http://localhost:5173`
2. Upload resume PDF/DOCX
3. Enter job description
4. Click **Analyze Now**
5. Results appear in dashboard ✅

---

## 🔍 Diagnostic Checklist

Run these commands **in order** to diagnose issues:

### 1. Python Import Test
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"
python -c "from backend.main import app; print('✓ Backend imports successful')"
```

**Expected:** ✓ Backend imports successful

**If error:** Check main.py line 27 has correct import:
```python
from .services.resume_parser import extract_resume_text
```

---

### 2. Backend Server Test
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Wait 3 seconds, then in another terminal:
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" | Select-Object StatusCode
```

**Expected:** StatusCode: 200

**If connection refused:** Backend not running or port in use

---

### 3. Port Check
```powershell
netstat -ano | findstr "8000"
```

**If shows process on port 8000:** Port is in use
- Kill process: `taskkill /PID <PID> /F`
- Or use different port: `--port 8001`

---

### 4. Frontend Proxy Test
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner\frontend"
cat vite.config.ts
```

**Should contain:**
```typescript
server: {
  proxy: {
    "/api": "http://localhost:8000"
  }
}
```

**If missing:** Add proxy config (see below)

---

### 5. Frontend Test
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner\frontend"
npm run dev
```

Wait 3 seconds, browser should open at `http://localhost:5173`

---

## 🛠️ Common Issues & Fixes

### Issue: `ModuleNotFoundError: No module named 'fastapi'`

**Fix:** Install dependencies
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"
pip install -r requirements.txt
```

---

### Issue: `ImportError: cannot import name 'extract_resume_text'`

**Status:** ✅ ALREADY FIXED

If still seeing this error:
1. Check main.py line 27 has: `from .services.resume_parser import extract_resume_text`
2. Save the file
3. Try again

---

### Issue: `Port 8000 already in use`

**Fix:** Use different port
```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```

Then update Vite config to point to new port

---

### Issue: `ECONNREFUSED` in browser console

**Check list:**
1. ✅ Backend running on port 8000?
2. ✅ Health check passes? `Invoke-WebRequest http://127.0.0.1:8000/health`
3. ✅ Vite proxy correctly configured?
4. ✅ Frontend running on port 5173?

---

### Issue: `OPENAI_API_KEY` not set

The app requires an OpenAI API key.

**Fix:**
1. Get API key from: https://platform.openai.com/api-keys
2. Update `.env`:
```
OPENAI_API_KEY=your_actual_key_here
```
3. Restart backend (uvicorn will auto-reload)

---

## 📋 File Structure Verification

Verify all required files exist:

```
backend/
  main.py                          ← FastAPI app
  models.py                        ← Pydantic models
  __init__.py                      ← Package marker
  services/
    __init__.py
    resume_parser.py               ← Has extract_resume_text ✅
    ats_optimizer.py
    jd_analyzer.py
    scorer.py
    visualizer.py
    writing_feedback.py
    skill_analyzer.py
    quality_scorer.py
    keyword_heatmap.py
    openai_service.py
    doc_generator.py
  utils/
    __init__.py
    text_cleaner.py
    pdf_parser.py
    resume_parser.py                ← Different from services!

frontend/
  src/
    App.tsx
    types.ts
    main.tsx
  vite.config.ts                   ← Must have proxy config ✅
  package.json
  tsconfig.json

.env                               ← OPENAI_API_KEY
requirements.txt                   ← Python packages
```

---

## 📡 API Endpoint Reference

After backend starts, these endpoints are available:

### Health Check
```
GET http://127.0.0.1:8000/health
Response: {"status": "ok", "service": "IntelliResume AI"}
```

### Comprehensive Analysis (Main Endpoint)
```
POST http://127.0.0.1:8000/api/analyze/comprehensive
Form Data:
  - resume: (file) PDF or DOCX
  - job_description: (optional file) PDF or DOCX
  - jd_text: (optional text) Job description text

Response:
{
  "optimized_resume": "...",
  "ats_score": {...},
  "jd_analysis": {...},
  "skill_gap": {...},
  "resume_quality": {...},
  "keyword_heatmap": {...},
  "writing_feedback": {...},
  "chart_paths": {...}
}
```

### Interactive API Docs
```
http://127.0.0.1:8000/docs
```

---

## 🔐 Configuration (.env)

Required file: `.env` in project root

```env
OPENAI_API_KEY=sk-your-key-here
```

Optional:
```env
CHARTS_DIR=backend/charts
```

---

## 📊 System Requirements

- **Python**: 3.10+
- **Node.js**: 18+
- **npm**: 9+
- **Ram**: 2GB minimum
- **Disk**: 500MB

---

## 🚀 Full Setup from Scratch

### 1. Backend Setup
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"

# Create virtual environment (optional but recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Test import
python -c "from backend.main import app; print('✓ Import OK')"

# Start server
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend Setup (in new terminal)
```powershell
cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner\frontend"

# Install dependencies
npm install

# Start dev server
npm run dev
```

### 3. Test
```powershell
# In browser:
http://localhost:5173
```

---

## ✅ Verification Checklist

After completing setup, verify:

- [ ] Backend starts without errors
- [ ] Frontend starts without errors
- [ ] Browser opens at http://localhost:5173
- [ ] Upload resume button visible
- [ ] Can select PDF/DOCX files
- [ ] Can paste job description
- [ ] "Analyze Now" button clicks without error
- [ ] Results appear with dashboard charts
- [ ] All 5 tabs work (Dashboard, Resume, Skills, Quality, Keywords)
- [ ] Can download DOCX file

---

## 📞 Still Having Issues?

Run the **Diagnostic Script**:
```powershell
.\RUN_BACKEND.ps1
```

This script:
1. Checks Python installation
2. Verifies project structure
3. Lists required packages
4. Checks configuration
5. Shows helpful error messages if anything fails

---

## 🎯 Summary of What Was Fixed

| Issue | Status | Fix |
|-------|--------|-----|
| Import path for `extract_resume_text` | ✅ FIXED | Changed from `utils` to `services` |
| Backend can import modules | ✅ VERIFIED | Health check returns 200 OK |
| Frontend proxy configured | ✅ VERIFIED | vite.config.ts has `/api` proxy |
| CORS middleware enabled | ✅ VERIFIED | Allows localhost:5173 |
| All services available | ✅ VERIFIED | 10 services + 3 new ones |

---

## 📖 Next Steps

1. **Run backend**: `python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
2. **Run frontend**: `cd frontend && npm run dev`
3. **Test analysis**: Upload resume + JD, click Analyze
4. **Check dashboard**: All 5 tabs should display data
5. **Deploy**: See README.md deployment section

---

**Everything works now! Your ATS Scanner is ready to use.** 🚀
