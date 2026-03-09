# Setup Guide - IntelliResume AI

Complete step-by-step guide to run IntelliResume AI locally.

## Prerequisites Check

Verify you have:
- [Python 3.10+](https://www.python.org/downloads/)
- [Node.js 16+](https://nodejs.org/)
- [OpenAI API Key](https://platform.openai.com/api-keys)

Verify installations:
```bash
python --version        # Should be 3.10+
node --version         # Should be 16+
npm --version          # Should be 8+
```

## Step 1: Environment Setup

### 1.1 Clone/Extract Project
```bash
cd "ATS Scanner"
```

### 1.2 Create .env File
**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS/Linux:**
```bash
cp .env.example .env
```

### 1.3 Edit .env with Your API Key
Open `.env` in your editor and replace:
```env
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_MODEL=gpt-4o-mini
CHARTS_DIR=backend/charts
```

Get your API key from: https://platform.openai.com/api-keys

⚠️ **Never commit `.env`** – it's in `.gitignore` for security

## Step 2: Backend Setup (Python)

### 2.1 Create Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the start of your terminal prompt.

### 2.2 Install Dependencies
```bash
pip install -r requirements.txt
```

This installs:
- fastapi
- uvicorn
- python-multipart
- openai
- pdfplumber
- python-docx
- pydantic
- scikit-learn
- matplotlib
- python-dotenv

### 2.3 Start Backend Server
```bash
uvicorn backend.main:app --reload
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

✓ Backend is ready at: http://localhost:8000
✓ API docs at: http://localhost:8000/docs

**Keep this terminal open!**

## Step 3: Frontend Setup (Node.js)

### 3.1 Open New Terminal (Keep Backend Running)

Open a second terminal in the same project directory.

### 3.2 Navigate to Frontend
```bash
cd frontend
```

### 3.3 Install Dependencies
```bash
npm install
```

### 3.4 Start Development Server
```bash
npm run dev
```

Expected output:
```
  VITE v5.0.0  ready in 234 ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

✓ Frontend is ready at: http://localhost:5173

## Step 4: Test the Application

### 4.1 Open Application
1. Open browser and go to: http://localhost:5173
2. You should see the IntelliResume AI interface

### 4.2 Run a Test Analysis

Prepare:
- A resume file (PDF or DOCX)
- A job description (can paste in the form)

Steps:
1. **Upload Resume**: Click on resume upload area and select your resume
2. **Add Job Description**: Either upload a file or paste text in the textarea
3. **Click "🚀 Analyze Now"**
4. **Wait 10-30 seconds** for OpenAI API calls to complete
5. **Review Results**:
   - 📊 Dashboard: Charts and visualizations
   - ✨ Optimized Resume: AI-enhanced version
   - 🎯 Skill Gap: Matched vs missing skills
   - ⭐ Quality Score: Detailed quality metrics
   - 🔥 Keywords: Keyword analysis
6. **Download DOCX**: Click "⬇️ Download Optimized Resume"

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'backend'`
**Solution**: Make sure you're running the command from the project root (same level as `backend/` folder)

### Issue: `OPENAI_API_KEY not found in environment variables`
**Solution**: 
1. Check `.env` file exists (not `.env.example`)
2. Verify `OPENAI_API_KEY=sk-...` is filled in
3. Restart backend: `Ctrl+C` then run `uvicorn backend.main:app --reload` again

### Issue: `Port 8000 already in use`
**Solution**: Use a different port:
```bash
uvicorn backend.main:app --reload --port 8001
```
Then update frontend's `vite.config.ts` proxy to port 8001

### Issue: `Port 5173 already in use`
**Solution**: 
```bash
npm run dev -- --port 5174
```

### Issue: Frontend shows blank screen / 404
**Solution**:
1. Check browser console (F12) for errors
2. Verify backend is running (`http://localhost:8000/health`)
3. Check frontend console for network errors
4. Clear browser cache: `Ctrl+Shift+Delete`

### Issue: OpenAI API returns 401 error
**Solution**:
1. Verify API key is correct and valid
2. Check you have API credits: https://platform.openai.com/account/billing/overview
3. Make sure you didn't paste quotes around the key

### Issue: Charts not displaying
**Solution**:
1. Check backend logs for matplotlib errors
2. Verify `CHARTS_DIR` folder exists: `backend/charts/`
3. Check disk space
4. Try running a simple request first

### Issue: PDF/DOCX upload fails silently
**Solution**:
1. Ensure file is under 10MB
2. Try opening file locally first to verify it's not corrupted
3. Check backend logs for pdfplumber/docx errors
4. Try a different PDF/DOCX file

## Development Tips

### Reloading Code
- **Backend**: Auto-reloads with `--reload` flag
- **Frontend**: Auto-reloads on file changes

### Debugging
- Backend: Check server terminal for detailed error messages
- Frontend: Open DevTools (F12) → Console for JS errors

### API Testing
Use the interactive API docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Test manually:
```bash
curl -X POST http://localhost:8000/api/analyze/comprehensive \
  -F "resume=@path/to/resume.pdf" \
  -F "jd_text=Senior Python Developer required..."
```

### Performance
- First request might take 20-30s (OpenAI API calls)
- Subsequent requests cached locally
- Charts generate in ~2-5 seconds

## Production Build

### Build Frontend
```bash
cd frontend
npm run build
```

Creates optimized build in `frontend/dist/`

### Run Backend in Production
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Deploy
See deployment guides:
- Backend: Railway, Render, Heroku, AWS
- Frontend: Vercel, Netlify, AWS S3

## Next Steps

1. ✅ Follow steps 1-4 above
2. 📚 Read main README.md for feature details
3. 🧪 Run test analyses with different resumes
4. 💻 Explore the code in `backend/` and `frontend/src/`
5. 🚀 Deploy to cloud (see README.md)
6. 📝 Add to portfolio/GitHub

## Quick Reference

```bash
# Start Backend
cd "ATS Scanner"
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
uvicorn backend.main:app --reload

# Start Frontend (in new terminal)
cd frontend
npm install
npm run dev

# When done
# Press Ctrl+C in both terminals
deactivate  # Exit virtual environment
```

## Still Need Help?

1. Check the main [README.md](README.md)
2. Review error messages in terminal/console carefully
3. Ensure all prerequisites are installed
4. Verify `.env` file setup
5. Try a simple file first (smaller PDF/DOCX)

Good luck! 🚀
