# IntelliResume AI – LLM-Powered ATS Optimization Engine

Production-ready AI-powered ATS Resume Optimizer: upload resume and job description, get an optimized resume, ATS score, keyword analysis, and downloadable DOCX.

## ✨ Features

- **Resume & JD upload**: PDF, DOCX; optional paste for job description
- **Job description analyzer**: OpenAI extracts required/preferred skills, keywords, tools, experience level (strict JSON)
- **ATS optimizer**: Rewrites resume with better action verbs and keyword alignment **without fabricating experience**
- **ATS scoring**: Keyword overlap %, TF-IDF cosine similarity, weighted final score (0–100%), missing/recommended keywords
- **Skill Gap Analysis**: Identifies matched vs missing required and preferred skills
- **Resume Quality Score**: Evaluates readability, formatting, content quality, and keyword density
- **Keyword Heatmap**: Visual analysis of top keywords and their importance
- **Visual dashboard**: Professional Matplotlib charts (keyword coverage, match vs missing, skill gap, quality breakdown)
- **Download**: DOCX export via python-docx  
- **Writing Feedback**: Weak verb detection, metric detection, passive voice, readability score, section detection
- **Professional UI**: Modern SaaS-style interface with Tailwind CSS

## 📊 Architecture

```
ATS Scanner/
├── backend/                          # FastAPI Python backend
│   ├── main.py                       # FastAPI app & routes
│   ├── models.py                     # Pydantic models (request/response)
│   ├── services/
│   │   ├── resume_parser.py          # PDF/DOCX text extraction
│   │   ├── jd_analyzer.py            # OpenAI JD → structured JSON
│   │   ├── ats_optimizer.py          # OpenAI resume rewrite
│   │   ├── scorer.py                 # Keyword + TF-IDF scoring
│   │   ├── skill_analyzer.py         # Skill gap analysis
│   │   ├── quality_scorer.py         # Resume quality evaluation
│   │   ├── keyword_heatmap.py        # Keyword frequency analysis
│   │   ├── doc_generator.py          # DOCX generation
│   │   ├── visualizer.py             # Matplotlib charts
│   │   ├── writing_feedback.py       # Writing analysis
│   │   └── openai_service.py         # OpenAI API integration
│   ├── utils/
│   │   ├── resume_parser.py          # Shared parser utilities
│   │   └── text_cleaner.py           # Text normalization
│   └── requirements.txt
│
├── frontend/                         # React + Vite + TypeScript
│   ├── src/
│   │   ├── App.tsx                   # Main app component (enhanced UI)
│   │   ├── main.tsx                  # Entry point
│   │   ├── types.ts                  # TypeScript interfaces
│   │   └── index.css                 # Tailwind styles
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
│
├── .env.example                      # Environment template
├── .env                              # Your configuration (create from template)
└── README.md                         # This file
```

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 16+ & npm
- OpenAI API key ([get one](https://platform.openai.com/api-keys))

### 1. Environment Setup

Clone/extract and enter the project directory:
```bash
cd "ATS Scanner"
```

Copy the environment template:
```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:
```env
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_MODEL=gpt-4o-mini
CHARTS_DIR=backend/charts
```

### 2. Backend Setup (Python)

Create and activate a virtual environment:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Run the backend:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

✓ Backend is running at `http://localhost:8000`
✓ API docs: `http://localhost:8000/docs`

### 3. Frontend Setup (Node.js)

In a new terminal, navigate to frontend:
```bash
cd frontend
npm install
npm run dev
```

✓ Frontend is running at `http://localhost:5173`

### 4. Test the Application

1. Open `http://localhost:5173` in your browser
2. Upload a resume (PDF or DOCX)
3. Provide a job description (paste or upload)
4. Click "🚀 Analyze Now"
5. View results in the comprehensive dashboard:
   - **📊 Dashboard**: Visual charts and metrics
   - **✨ Optimized Resume**: AI-enhanced resume text
   - **🎯 Skill Gap**: Matched vs missing skills
   - **⭐ Quality Score**: Detailed quality breakdown
   - **🔥 Keywords**: Keyword analysis and recommendations
6. Download optimized resume as DOCX

## 📡 API Endpoints

### Main Analysis Endpoint
```
POST /api/analyze/comprehensive
```

**Request:**
- `resume` (File): PDF or DOCX resume
- `job_description` (File, optional): PDF/DOCX JD
- `jd_text` (string, optional): Paste JD text

**Response:**
```json
{
  "optimized_resume": "...",
  "ats_score": {
    "final_ats_score": 78.5,
    "keyword_match_percent": 82,
    "semantic_similarity_score": 0.65,
    "missing_keywords": [...],
    "recommended_keywords_to_add": [...]
  },
  "jd_analysis": {
    "required_skills": [...],
    "preferred_skills": [...],
    "keywords": [...],
    "tools": [...],
    "experience_level": "Senior"
  },
  "skill_gap": {
    "matched_skills": [...],
    "missing_skills": [...],
    "gap_score": 75.0,
    "match_count": 12,
    "total_required": 18
  },
  "resume_quality": {
    "overall_score": 82,
    "readability_score": 85,
    "formatting_score": 80,
    "content_score": 85,
    "keyword_density_score": 75,
    "feedback": ["✓ Good readability...", ...]
  },
  "keyword_heatmap": {
    "keywords": ["Python", "AWS", ...],
    "frequencies": [5, 3, ...],
    "importance_scores": [0.95, 0.72, ...]
  },
  "writing_feedback": {
    "weak_verbs_detected": [...],
    "bullets_without_metrics": [...],
    "passive_voice_phrases": [...],
    "readability_score": 0.82,
    "sections_detected": ["SUMMARY", "EXPERIENCE", ...]
  },
  "chart_paths": {
    "keyword_coverage": "/api/charts/session-id/...",
    "match_pie": "/api/charts/...",
    "skill_gap": "/api/charts/...",
    "quality_breakdown": "/api/charts/...",
    "keyword_heatmap": "/api/charts/..."
  }
}
```

### Download Optimized Resume
```
POST /api/download-docx
```

**Request:**
- `optimized_resume` (string): Resume text to convert to DOCX

**Response:** DOCX file binary

### Other Endpoints
```
GET /                            # Health check
GET /health                      # Service health
GET /api/charts/{session_id}/{filename}  # Serve chart images
```

## 🔧 Configuration

Edit `.env` to customize:

```env
# OpenAI
OPENAI_API_KEY=sk-...      # Your API key
OPENAI_MODEL=gpt-4o-mini   # or gpt-4, gpt-4o

# Paths
CHARTS_DIR=backend/charts   # Where to save chart images
```

## 📈 How It Works

### 1. Resume Parsing
- Extracts text from PDF/DOCX files
- Cleans and normalizes formatting
- Preserves original content

### 2. JD Analysis (OpenAI)
- Extracts structured data:
  - Required skills
  - Preferred skills
  - Responsibilities
  - Keywords & tools
  - Experience level
- Returns strict JSON format

### 3. Resume Optimization (OpenAI)
- Rewrites resume using JD keywords
- Improves action verbs and phrasing
- **Does NOT fabricate** experience
- Maintains factual accuracy
- Improves ATS friendliness

### 4. ATS Scoring
- **Keyword Match %**: How many JD keywords appear in resume
- **Semantic Similarity**: TF-IDF cosine similarity (0-1 scale)
- **Final Score**: Weighted blend (55% keyword, 45% semantic)

### 5. Skill Gap Analysis
- Compares required skills vs resume
- Identifies matched and missing skills
- Calculates gap percentage (weighted by skill importance)

### 6. Resume Quality Scoring
- **Readability**: Word length, sentence complexity
- **Formatting**: Section headers, bullet points, structure
- **Content**: Action verbs, metrics, technology references
- **Keyword Density**: JD keyword percentage

### 7. Visualizations
- **Keyword Coverage**: Bar chart of matched vs missing
- **Match Pie**: Percentage breakdown
- **Skill Gap**: Donut chart of skill matching
- **Quality Breakdown**: Component score visualization
- **Keyword Heatmap**: Top keywords and importance

## 🎓 Building a Portfolio Project

To showcase this as a portfolio project:

1. **Deploy Backend**: Use platforms like:
   - Heroku (with procfile)
   - AWS (EC2 + RDS)
   - Railway
   - DigitalOcean

2. **Deploy Frontend**: Use:
   - Vercel (easiest for React)
   - Netlify
   - GitHub Pages
   - AWS S3 + CloudFront

3. **Example .github/workflows/deploy.yml**:
   ```yaml
   name: Deploy
   on: [push]
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v2
         - name: Deploy to Vercel
           run: npm run build && vercel deploy
   ```

4. **README highlights**:
   - Tech stack: FastAPI, React, Tailwind, OpenAI
   - 50+ lines of code per service
   - Database-free but production-ready
   - API-first architecture
   - Comprehensive error handling

## 🧪 Testing

### Backend Tests
```bash
# Manual test with curl
curl -X POST http://localhost:8000/api/analyze/comprehensive \
  -F "resume=@resume.pdf" \
  -F "jd_text=Senior Python Developer required..."
```

### Frontend Tests
Manual testing:
1. Try uploading invalid files → should show errors
2. Missing JD → error message
3. Large resumes → should handle gracefully
4. Check all tabs render correctly

## 📝 Tips for Best Results

1. **Resume Format**:
   - Clean, standard format
   - Use clear section headers
   - Quantify achievements (e.g., "Increased revenue by 25%")
   - Action verbs per bullet point

2. **Job Description**:
   - Full JD text works better
   - Include "Required", "Preferred", tools, responsibilities
   - Longer = more detailed analysis

3. **Optimization**:
   - Tool detects ~80-90% of important keywords
   - Review suggestions before accepting
   - Don't over-optimize: maintain authenticity
   - Add real skills you possess

## 🐛 Common Issues

### Issue: `OPENAI_API_KEY not found`
**Solution**: Create `.env` file with your key (copy from `.env.example`)

### Issue: `ModuleNotFoundError: No module named 'backend'`
**Solution**: Run backend from project root: `uvicorn backend.main:app --reload`

### Issue: `Port 8000 already in use`
**Solution**: Kill process or use different port: `uvicorn backend.main:app --reload --port 8001`

### Issue: Frontend shows blank screen
**Solution**: Check browser console for errors, ensure backend is running

### Issue: Charts not displaying
**Solution**: Check backend logs, ensure `CHARTS_DIR` exists and is writable

## 📚 Documentation

For detailed info on individual services, see:
- [Services Documentation](backend/services/)
- [Models Documentation](backend/models.py)
- [Frontend Components](frontend/src/)

## 🤝 Contributing

Improvements welcome! Areas for enhancement:
- [ ] Database support (PostgreSQL)
- [ ] Job queue for async processing
- [ ] WebSocket updates for real-time analysis
- [ ] Resume templates library
- [ ] Multi-language support
- [ ] User accounts & saved analyses
- [ ] Batch resume processing
- [ ] Advanced formatting preservation

## 📄 License

Open source. Use freely for portfolio/production projects.

## 🎯 Next Steps

1. ✅ Run locally following Quick Start
2. Deploy backend to cloud (Railway/Render)
3. Deploy frontend to Vercel
4. Add to GitHub portfolio
5. Write blog post about the project
6. Showcase in interviews

---

**Built with Python, FastAPI, React, OpenAI API, and Tailwind CSS**

1. Create a virtual environment and install dependencies:

   ```bash
   cd "c:\Users\amrit\OneDrive\Documents\ATS Scanner"
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate   # macOS/Linux
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set your OpenAI API key:

   ```
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o-mini
   CHARTS_DIR=backend/charts
   ```

3. Run the API (from project root so `backend` package is importable):

   ```bash
   set PYTHONPATH=%CD%   # Windows
   # export PYTHONPATH=.   # macOS/Linux
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

   API: http://localhost:8000  
   Docs: http://localhost:8000/docs

### Frontend

1. Install and run:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

2. Open http://localhost:5173

   The Vite dev server proxies `/api` to `http://localhost:8000`, so use the frontend URL for full flow.

## Usage

1. Upload your **resume** (PDF or DOCX).
2. Provide **job description**: either upload a PDF/DOCX/TXT or paste text.
3. Click **Optimize**.
4. View **ATS score**, **Optimized resume**, **Score breakdown**, **Missing keywords**, and **Visual dashboard**.
5. Click **Download DOCX** to save the optimized resume.

## Environment variables (.env)

| Variable        | Description           | Default        |
|----------------|-----------------------|----------------|
| `OPENAI_API_KEY` | OpenAI API key       | (required)     |
| `OPENAI_MODEL`   | Model for JD/optimize | `gpt-4o-mini` |
| `CHARTS_DIR`     | Dir for chart images  | `backend/charts` |

## Constraints

- **No fabrication**: The optimizer does not invent experience, skills, or employment history. It only improves wording and keyword alignment.
- All OpenAI prompts instruct the model to return strict JSON and not fabricate.

## License

MIT.
