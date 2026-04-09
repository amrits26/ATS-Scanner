# ATS Scanner Phase 1 & Phase 2 Implementation Checklist

**Date Generated**: April 8, 2026  
**Status**: ✅ ALL CODE FILES GENERATED  
**Expected Timeline**: 2 hours to deploy, 1 day to test end-to-end

---

## 📋 PRE-DEPLOYMENT (30 minutes)

### Step 1: Install Dependencies
```bash
# From project root:
pip install -r requirements.txt

# New packages added:
# - trafilatura (job scraping)
# - fake-useragent (web scraping)
# - beautifulsoup4 (HTML parsing)
# - pytz (timezone handling)
```

**Verify installation:**
```bash
python -c "import trafilatura, pytz, google.generativeai; print('✓ All deps installed')"
```

---

### Step 2: Copy .env Configuration

1. **Copy template to actual .env**:
```bash
cp .env.example .env
```

2. **Fill in CRITICAL variables** (items marked 🔴 below):

#### 🔴 REQUIRED for Phase 1:
- `RESEND_API_KEY` – Get from [resend.com/api-keys](https://resend.com/api-keys)
- `RESEND_FROM_EMAIL` – e.g., `noreply@intelliresume.ai`
- Create 3 email templates in Resend dashboard:
  - Template ID: `fear-email-24h-v1`
  - Template ID: `abandoned-scan-72h-v1`
  - Template ID: `weekly-digest-v1`

#### 🔴 REQUIRED for Phase 2:
- `GOOGLE_API_KEY` – Already have this (used by existing code)

#### 🟡 OPTIONAL (defaults provided):
- `AGENT_COST_MONTHLY_LIMIT_CENTS` – Default: $100/month
- `COACH_PRICE_MONTHLY_CENTS` – Default: $9.99/month

---

### Step 3: Apply Database Migrations

```bash
# List all migrations:
ls backend/migrations/

# You should see:
# - 001_init.sql through 009_... (existing)
# - 010_phase1_email_automation.sql (NEW)
# - 011_phase2_ai_agents.sql (NEW)

# Apply migrations to your PostgreSQL database:
# Option A: Using psql directly
psql $DATABASE_URL < backend/migrations/010_phase1_email_automation.sql
psql $DATABASE_URL < backend/migrations/011_phase2_ai_agents.sql

# Option B: Using Supabase dashboard
# Go to: supabase.com → Project → SQL Editor
# Copy-paste contents of each migration file and execute
```

**Verify migrations applied:**
```bash
# Connect to your database and check tables exist:
psql $DATABASE_URL
\dt nudge_tracking          # Should return table info
\dt agent_executions        # Should return table info
\dt gemini_cost_log         # Should return table info
\q
```

---

## 🚀 DEPLOYMENT (30 minutes)

### Step 4: Start Backend Server

```bash
# From project root:
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     [STARTUP] Creating database tables...
INFO:     [STARTUP] [OK] Database tables created/verified
```

If you see Uvicorn errors re: imports, troubleshoot:
```bash
python -c "from backend.services.agent_base import AIAgent; print('✓ Agent base imports correctly')"
python -c "from backend.services.email_nudge_service import NudgeEngine; print('✓ Email service imports correctly')"
```

---

### Step 5: Start ARQ Worker (Optional, for background jobs)

In a **separate terminal**:
```bash
# Enable scheduled email nudges (every 15 minutes):
python -m arq backend.jobs.WorkerSettings

# OR: Use the provided startup script:
.\start-arq-worker.ps1  # Windows
bash start-arq-worker.sh # Mac/Linux
```

---

### Step 6: Verify API Endpoints Are Live

```bash
# Test health check:
curl http://localhost:8000/health
# Expected: {"status": "ok"}

# Test agent endpoints (requires auth token):
# These will fail with 401 Unauthorized without a valid JWT,
# which is expected. We're just checking the endpoints exist.

curl -X POST http://localhost:8000/api/agent/coach \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test_token" \
  -d '{"question": "test", "resume_text": "test"}'

# Expected: 401 Unauthorized (or detailed error message)
# This means the endpoint exists and auth is working correctly.
```

---

## ✅ TESTING (1-2 hours for full end-to-end)

### Test 1: Email Nudge Service (Phase 1)

**Without Resend API key configured**, this will log to DLQ safely:

```python
# backend/test_nudge_service.py (create this file)
import asyncio
from sqlalchemy.ext.asyncio import AsyncSessionLocal
from backend.services.email_nudge_service import NudgeEngine

async def test_nudge():
    db = AsyncSessionLocal()
    engine = NudgeEngine(db)
    
    # Test email copy generation (uses Gemini)
    subject, preview = await engine._generate_fear_email_copy(72, ["Python", "AWS", "Docker"])
    print(f"✓ Fear email subject: {subject}")
    print(f"✓ Fear email preview: {preview}")
    
    await db.close()

asyncio.run(test_nudge())
```

**Run test:**
```bash
python backend/test_nudge_service.py

# Expected output:
# ✓ Fear email subject: ⚠️ Your score: 72/100 (upgrade for +20 points)
# ✓ Fear email preview: Your resume scored 72/100. Missing: Python. Upgrade now →
```

---

### Test 2: Agent Base Infrastructure (Phase 2)

```python
# backend/test_agent_base.py
import asyncio
from backend.services.agent_coach import ResumeCoachAgent
from backend.services.agent_telemetry import AgentTelemetry

async def test_agent():
    # Initialize agent
    coach = ResumeCoachAgent(user_id="test_user_123")
    print(f"✓ Agent initialized: {coach.agent_type}")
    
    # Check tools are registered
    print(f"✓ Tools available: {list(coach.tools.keys())}")
    
    # Expected tools: strength_analyzer, gap_detector, bullet_rewriter, ...

asyncio.run(test_agent())
```

**Run test:**
```bash
python backend/test_agent_base.py

# Expected output:
# ✓ Agent initialized: coach
# ✓ Tools available: ['strength_analyzer', 'gap_detector', 'bullet_rewriter', 'industry_benchmark', 'action_plan_generator']
```

---

### Test 3: Agent API Endpoints (Full Stack)

**Create authenticated test user first:**

```bash
# Using Supabase CLI or manual signup, get a valid JWT token
# Store in environment variable:
export AUTH_TOKEN="your_valid_jwt_token_here"
```

**Test Resume Coach endpoint:**
```bash
curl -X POST http://localhost:8000/api/agent/coach \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d '{
    "question": "How do I improve my resume for data science roles?",
    "resume_text": "Software Engineer at Google. Worked on ML infrastructure. Led team of 5."
  }'

# Expected response (200 OK):
{
  "session_id": "uuid-here",
  "status": "completed",
  "response": {
    "response": "Your resume has strong technical bullets...",
    "action_items": ["Add metrics to bullets", "Include power verbs"],
    "confidence": 85,
    "follow_up": "Next, consider..."
  },
  "execution_time_seconds": 8.5,
  "gemini_cost_cents": 3
}
```

**Test Auto-Tailor endpoint:**
```bash
curl -X POST http://localhost:8000/api/agent/tailor \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d '{
    "resume_text": "Senior Software Engineer...",
    "jd_text": "We are looking for a Senior ML Engineer with Python, TensorFlow..."
  }'

# Expected response (200 OK):
{
  "session_id": "uuid-here",
  "status": "completed",
  "rewritten_resume": "Senior Software Engineer with 7+ years in ML/AI...",
  "key_alignments": ["Added TensorFlow emphasis", "Reordered ML projects first"],
  "match_score": 87,
  "execution_time_seconds": 12.3,
  "gemini_cost_cents": 5
}
```

**Test Interview Prep endpoint:**
```bash
curl -X POST http://localhost:8000/api/agent/interview-prep \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d '{
    "job_title": "Senior Software Engineer",
    "company": "Google",
    "resume_text": "Led ML infrastructure team..."
  }'

# Expected response (200 OK):
{
  "session_id": "uuid-here",
  "status": "completed",
  "questions": {
    "technical": ["Design a recommendation system", ...],
    "behavioral": ["Tell me about a time you led a team", ...],
    "culture_fit": [...],
    "resume_specific": [...]
  },
  "execution_time_seconds": 10.2,
  "gemini_cost_cents": 4
}
```

---

## 🚨 TROUBLESHOOTING

### Issue: `ModuleNotFoundError: No module named 'trafilatura'`
**Solution**: Run `pip install -r requirements.txt` again, or manual:
```bash
pip install trafilatura fake-useragent beautifulsoup4 pytz
```

---

### Issue: `GOOGLE_API_KEY not configured` when calling agents
**Solution**: Check `.env` file has `GOOGLE_API_KEY` set:
```bash
grep GOOGLE_API_KEY .env
# Should print your key
```

---

### Issue: Gemini API rate limits errors during testing
**Solution**: This is expected if calling 3+ agents in quick succession. Wait 60 seconds between calls, or:
```bash
# Use lower cost models (replace in code if needed)
GEMINI_MODEL="gemini-1.5-flash"  # Cheaper & faster
```

---

### Issue: Database migration fails with `relation "X" already exists`
**Solution**: You already applied the migration. This is safe to ignore. Check:
```bash
psql $DATABASE_URL -c "\dt nudge_tracking"
# If table exists, migration is good.
```

---

### Issue: Agent takes >60 seconds to execute
**Solution**: Gemini API might be throttled or overloaded. Check:
```bash
# In logs, look for:
# "[AGENT] THINK: Decided to call 3 tools"
# "[AGENT] ACT: Calling tool 1/3: strength_analyzer"

# If tools take >30s each, Gemini is slow. Retry or contact Google support.
```

---

## 📊 MONITORING

### Check Gemini Costs

```python
# Quick cost check script:
import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSessionLocal
from backend.db_models import GeminiCostLog
from datetime import datetime, timedelta

async def check_costs():
    db = AsyncSessionLocal()
    
    # Get today's costs
    today = datetime.utcnow().date()
    result = await db.execute(
        select(func.sum(GeminiCostLog.cost_cents)).where(
            func.date(GeminiCostLog.created_at) == today
        )
    )
    total_cents = result.scalar() or 0
    print(f"Today's Gemini spend: ${total_cents/100:.2f}")
    
    await db.close()

asyncio.run(check_costs())
```

---

### View Email Delivery Status

```sql
-- Check scheduled nudges:
SELECT count(*), nudge_type, sent_at IS NOT NULL as sent
FROM nudge_tracking
GROUP BY nudge_type, sent;

-- Check pending nudges (not yet sent):
SELECT * FROM nudge_tracking
WHERE sent_at IS NULL
ORDER BY scheduled_at ASC;
```

---

## 📈 NEXT STEPS AFTER SUCCESSFUL DEPLOYMENT

1. **Phase 1 Revenue**: Enable fear emails in your free tier
   - Update `backend/jobs.py` → `run_analysis_job` to call nudge scheduler after free scan
   
2. **Phase 2 Monetization**: Add agent access tiers
   - Create `/api/subscribe/agent-coach` endpoint (charge $9.99/mo)
   - Check `agent_subscriptions` table before executing agents

3. **Legal Data Stack** (Optional, as discussed):
   - Implement user-generated interview questions (UGC)
   - Scrape Hacker News "Who is Hiring" thread
   - Start collecting salary data from public sources

---

## 📞 SUPPORT

- **Gemini API docs**: https://ai.google.dev/docs
- **Resend email guides**: https://resend.com/docs
- **FastAPI documentation**: https://fastapi.tiangolo.com
- **SQLAlchemy async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

---

## ✨ SUCCESS CRITERIA

You'll know everything is working when:

- ✅ All 3 agent endpoints return 200 OK with valid JSON responses
- ✅ Gemini cost logs are populated in `gemini_cost_log` table
- ✅ Agent executions are saved to `agent_executions` table
- ✅ No errors in backend logs for >30 minutes of normal usage
- ✅ Email templates are created in Resend (even if not sending yet)
- ✅ All database tables exist and have correct schemas

**Estimated time to success: 2-3 hours from start of this checklist.**
