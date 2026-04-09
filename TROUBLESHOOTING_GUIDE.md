# Phase 1 & 2: Comprehensive Troubleshooting Guide

**For Questions About**: Email automation, AI agents, cost tracking, database issues

---

## 🔴 CRITICAL ERRORS & SOLUTIONS

### Error: `ModuleNotFoundError: No module named 'trafilatura'`

**When**: Starting backend or calling `/api/agent/tailor`

**Root Cause**: Missing dependencies not installed

**Solution**:
```bash
# Option 1: Install all at once
pip install -r requirements.txt

# Option 2: Install specific packages
pip install trafilatura>=1.12.0 fake-useragent>=1.4.0 beautifulsoup4>=4.12.0 pytz>=2024.1

# Verify:
python -c "import trafilatura; print('✓ trafilatura installed')"
```

**Prevention**: Always run `pip install -r requirements.txt` after git pull

---

### Error: `ValueError: GOOGLE_API_KEY not configured`

**When**: Calling any agent endpoint (`/api/agent/coach`, `/api/agent/tailor`, `/api/agent/interview-prep`)

**Root Cause**: Missing or empty `GOOGLE_API_KEY` in `.env`

**Solution**:
```bash
# Check if .env exists:
ls .env

# If missing, create it:
cp .env.example .env

# Check if GOOGLE_API_KEY is set:
grep GOOGLE_API_KEY .env

# If empty, add your key (get from Google AI Studio):
# Edit .env and add:
# GOOGLE_API_KEY=sk-proj-XXXXXXXXXXXXX
```

**Prevention**: Add `.env` to `.gitignore` BEFORE committing (already done)

---

### Error: `psycopg2.errors.UndefinedTable: relation "nudge_tracking" does not exist`

**When**: Calling email service or checking email analytics

**Root Cause**: Database migrations not applied

**Solution**:
```bash
# Apply Phase 1 migration:
psql $DATABASE_URL < backend/migrations/010_phase1_email_automation.sql

# Apply Phase 2 migration:
psql $DATABASE_URL < backend/migrations/011_phase2_ai_agents.sql

# Verify tables exist:
psql $DATABASE_URL -c "SELECT tablename FROM pg_tables WHERE schemaname='public';"

# Should see:
# nudge_tracking
# gemini_cost_log
# agent_executions
# agent_subscriptions
# job_description_cache
```

**Quick Fix**:
```bash
# If using Supabase, copy-paste migrations into SQL Editor:
# 1. supabase.com → Project → SQL Editor
# 2. Paste content of 010_phase1_email_automation.sql
# 3. Paste content of 011_phase2_ai_agents.sql
# 4. Execute each
```

---

### Error: `google.generativeai.types.generation_types.StopReasonError: Response blocked by safety filter`

**When**: Calling agent endpoint with resume containing sensitive data

**Root Cause**: Gemini safety filters blocked the content

**Solution**:
```bash
# Option 1: Retry with slightly different wording in request
# Option 2: Add safety instruction to agent prompt
# Option 3: Use different Gemini model (though not recommended)

# Add to agent_base.py after Gemini initialization:
client.safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    }
]
```

**Prevention**: This is rare. Test with real resume data beforehand.

---

## 🟡 PERFORMANCE ISSUES

### Issue: Agent Endpoint Takes >30 Seconds

**Observation**: `/api/agent/coach` or `/api/agent/tailor` takes 30-60+ seconds

**Root Causes** (in order of likelihood):
1. Gemini API is slow/overloaded
2. Too many tools being called
3. Database query is slow
4. Network latency to Resend/trafilatura

**Diagnosis**:
```python
# Add debug logging to agent_base.py:
import time

async def execute(self):
    t0 = time.time()
    print(f"[{self.agent_type}] START")
    
    result = await self.think()
    print(f"[{self.agent_type}] THINK: {time.time() - t0:.2f}s")
    
    result = await self.act()
    print(f"[{self.agent_type}] ACT: {time.time() - t0:.2f}s")
    
    result = await self.reflect()
    print(f"[{self.agent_type}] REFLECT: {time.time() - t0:.2f}s")
    
    return result
```

**Solutions**:

**If THINK is slow (>10s)**:
- Gemini API is bottleneck
- Wait and retry (transient issue)
- Contact Google Cloud support

**If ACT is slow (>5s)**:
- Tool execution is slow
- Check if scraping JD from internet (trafilatura can take 3-5s)
- Consider using pre-fetched JD instead of URL

**If REFLECT is slow (>5s)**:
- Second Gemini call is slow
- Disable reflect step for faster responses (edit `agent_base.py`)

---

### Issue: High Gemini API Costs ($10+/day)

**Observation**: `gemini_cost_log` shows unexpectedly high daily costs

**Root Causes**:
1. User calling agents 1000+ times
2. Prompts are too long (many tools listed)
3. Bug causing infinite loops in tool calls

**Diagnosis**:
```sql
-- Check daily spend over last 7 days
SELECT 
  DATE(created_at) as date,
  SUM(cost_cents) as total_cents,
  COUNT(*) as calls,
  SUM(cost_cents)::float / COUNT(*) as avg_cost_cents_per_call
FROM gemini_cost_log
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Check which agent is most expensive
SELECT 
  agent_type,
  COUNT(*) as calls,
  SUM(cost_cents) as total_cents,
  SUM(cost_cents)::float / COUNT(*) as avg_cost_cents
FROM agent_executions
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY agent_type
ORDER BY total_cents DESC;
```

**Solutions**:

**If cost per call is very high (>10 cents)**:
- Prompts are too long
- Reduce number of tools in tool registry
- Use cheaper model (e.g., gemini-1.5-flash instead of gemini-pro)

**If total calls are very high (>10K/day)**:
- User is abusing the system
- Implement rate limiting (`/api/agent/*/rate-limit`)
- Add charge per call

**If suspect retry loops**:
- Check `agent_executions.error_message` for "max retries exceeded"
- Add log: `print(f"Tool call retry {attempt}/3")` in AIAgent.act()

---

### Issue: Database Query Performance (Agent Endpoints Taking 5+s Just for DB)

**Observation**: `execution_time_seconds` in response is >5s, most time is DB

**Root Cause**: Missing indexes on agent_executions table

**Solution**:
```sql
-- Check if indexes exist:
SELECT * FROM pg_indexes WHERE tablename = 'agent_executions';

-- Should see at least these:
-- - agent_executions_user_id_idx
-- - agent_executions_created_at_idx
-- - agent_executions_agent_type_idx

-- If missing, create manually:
CREATE INDEX agent_executions_user_id_idx ON agent_executions(user_id);
CREATE INDEX agent_executions_created_at_idx ON agent_executions(created_at DESC);
CREATE INDEX agent_executions_agent_type_idx ON agent_executions(agent_type);
```

---

## 🟡 FUNCTIONALITY ISSUES

### Issue: Email Not Sending (Nudge Emails Go to Void)

**Observation**: `nudge_tracking` shows `sent_at = NULL` for scheduled emails

**Root Causes**:
1. ARQ worker not running
2. Resend API key invalid/not configured
3. Email template IDs don't match deployed templates

**Diagnosis**:
```bash
# Check if ARQ worker is running:
ps aux | grep arq

# If not running, start it:
python -m arq backend.jobs.WorkerSettings

# Check Resend API key:
grep RESEND_API_KEY .env
# Should show: RESEND_API_KEY=re_XXXXXXXXXXXXX

# Check Resend templates exist:
curl https://api.resend.com/templates \
  -H "Authorization: Bearer $RESEND_API_KEY"

# Should see: fear-email-24h-v1, abandoned-scan-72h-v1, weekly-digest-v1
```

**Solutions**:

**If ARQ not running**:
```bash
# Start ARQ worker in background:
python -m arq backend.jobs.WorkerSettings &
# Or use provided script:
.\start-arq-worker.ps1
```

**If Resend API key invalid**:
```bash
# Get new key from resend.com/api-keys:
# 1. Go to resend.com
# 2. Click "API Keys"
# 3. Create new key
# 4. Copy and paste into .env
# 5. Restart backend (Uvicorn will reload .env)
```

**If templates don't match**:
```python
# In backend/services/email_nudge_service.py, check these lines:
# Line ~45: FEAR_EMAIL_TEMPLATE_ID = "fear-email-24h-v1"
# Line ~46: ABANDONED_EMAIL_TEMPLATE_ID = "abandoned-scan-72h-v1"
# Line ~47: DIGEST_EMAIL_TEMPLATE_ID = "weekly-digest-v1"

# Make sure these match what you created in Resend dashboard
```

---

### Issue: Agent Returns Incomplete Response (Empty Action Items)

**Observation**: `/api/agent/coach` returns `response: {action_items: []}`

**Root Cause**: Gemini response parsing failed

**Solution**:
```python
# Check logs for JSON parsing error:
# Look for: "[REFLECT] Failed to parse Gemini response"

# Debug by calling agent directly:
import asyncio
from backend.services.agent_coach import ResumeCoachAgent

async def test():
    coach = ResumeCoachAgent(user_id="test")
    response = await coach.execute(
        question="How do I improve?",
        resume_text="Senior Engineer..."
    )
    print(response)

asyncio.run(test())

# If response is malformed, Gemini response handling needs debug
# Check agent_base.py reflect() method for JSON parsing logic
```

**Prevention**:
- Add try-except around `json.loads()` in reflect()
- Return graceful error message if parsing fails
- Log raw Gemini response for debugging

---

### Issue: Job Scraper Returns Empty Text

**Observation**: `/api/agent/tailor` with `jd_url` returns error "JD text too short"

**Root Cause**: trafilatura couldn't extract text from URL

**Solution**:
```python
# Test scraper directly:
from backend.services.job_scraper import scrape_job_description

import asyncio
async def test():
    text = await scrape_job_description("https://jobs.example.com/123")
    print(f"Scraped: {len(text)} chars")
    print(f"Content: {text[:500]}")  # First 500 chars

asyncio.run(test())

# If returns empty or <100 chars:
# 1. URL might be behind login (auth required)
# 2. Website blocks trafilatura
# 3. Content is JavaScript-rendered (trafilatura doesn't run JS)

# Solution: Use Playwright instead of trafilatura
pip install playwright
python -m playwright install
```

---

## 🟢 MINOR ISSUES

### Issue: Cost Calculation is Off (Charges Don't Match Gemini Billing)

**When**: Comparing `gemini_cost_log.cost_cents` with actual Gemini bill

**Root Cause**: Token counting formula differs from Google's exact calculation

**Why It Happens**:
- We estimate tokens based on prompt length
- Google counts tokens precisely after processing
- Difference is usually 5-10%

**Solution**:
```python
# For accuracy, use Google's TokenCounter (requires tokenizers package):
pip install google-generativeai-tokencount

# In agent_base.py, replace:
estimated_tokens = len(prompt_text) / 4  # Rough estimate

# With:
from google.generativeai import tokencount
estimated_tokens = tokencount.count_tokens(prompt_text)
```

---

### Issue: Agent Subscription Tier Not Being Enforced

**Observation**: Free user can call `/api/agent/coach` unlimited times

**Root Cause**: Tier check in `agents.py` is missing or commented out

**Solution**:
```python
# In backend/routes/agents.py, add before agent execution:

from backend.services.agent_telemetry import AgentTelemetry

@router.post("/agent/coach")
async def coach_endpoint(...):
    # Check tier
    telemetry = AgentTelemetry(db=db)
    tier = await telemetry.get_user_subscription_tier(current_user.id)
    
    if tier == "free":
        return {"error": "Upgrade to Pro to use Coach", "status": 403}
    
    # Continue with agent execution
    ...
```

---

## 🔧 DEBUG UTILITIES

### Quick Test: Agent System is Working

```python
# Run this in Python REPL:
import asyncio
from sqlalchemy.ext.asyncio import AsyncSessionLocal
from backend.services.agent_coach import ResumeCoachAgent

async def test_full_stack():
    db = AsyncSessionLocal()
    
    try:
        agent = ResumeCoachAgent(user_id="test_user_123", db=db)
        print(f"✓ Agent created: {agent.agent_type}")
        
        result = await agent.execute(
            question="How do I improve my resume?",
            resume_text="Software Engineer at Google. Worked on ML infrastructure. Led team of 5."
        )
        
        print(f"✓ Execution completed in {result.get('execution_time_seconds')}s")
        print(f"✓ Gemini cost: ${result.get('gemini_cost_cents')/100:.4f}")
        print(f"✓ Status: {result.get('status')}")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        await db.close()

success = asyncio.run(test_full_stack())
print(f"\nOverall: {'✓ PASS' if success else '✗ FAIL'}")
```

---

### Check All Database Tables

```bash
# Connect to database and list all tables:
psql $DATABASE_URL

# List tables:
\dt

# Expected output should include:
# nudge_tracking
# gemini_cost_log
# agent_executions
# agent_subscriptions
# job_description_cache

# Check table schemas:
\d nudge_tracking
\d agent_executions

# Exit:
\q
```

---

### Monitor Gemini API in Real-Time

```bash
# Watch Gemini costs as they accumulate:
watch -n 5 'psql $DATABASE_URL -c "SELECT SUM(cost_cents) as total_cents, COUNT(*) as calls FROM gemini_cost_log WHERE created_at > NOW() - INTERVAL '\''1 hour'\''"'

# Reset costs (careful!):
DELETE FROM gemini_cost_log WHERE created_at < NOW() - INTERVAL '30 days';
```

---

## 📞 ESCALATION PATH

**Issue Persists After Trying Above Solutions?**

1. **Check logs first**:
   ```bash
   # Backend logs:
   tail -f VSCODE_TARGET_SESSION_LOG  # Check session debug log
   
   # Database logs (if using Supabase):
   supabase.com → Project → Logs → Postgres
   ```

2. **Enable debug mode**:
   ```python
   # In backend/main.py:
   import logging
   logging.basicConfig(level=logging.DEBUG)
   
   # Restart Uvicorn
   ```

3. **Post to GitHub Issues** with:
   - Error message (exact)
   - Steps to reproduce
   - `/api/` endpoint called
   - Request body example
   - Logs from past 2 minutes

---

## 🎓 COMMON GOTCHAS

### Gotcha 1: `.env` Not Re-Loaded After Restart
**Problem**: You edit `.env` but changes don't take effect

**Solution**: 
- Uvicorn DOES auto-reload `.env` if you use `--reload` flag
- If not, restart: `CTRL+C` then `uvicorn backend.main:app --reload`

### Gotcha 2: Agent Subscription Tier Always "free"
**Problem**: All users get tier="free" even if they should be "pro"

**Solution**: 
- Make sure `agent_subscriptions` table has entries for users
- Run: `INSERT INTO agent_subscriptions (user_id, tier) VALUES ('user_123', 'pro');`

### Gotcha 3: Gemini Returns Different Results Each Time
**Problem**: Agent called twice with same input returns different outputs

**Solution**: This is NORMAL. Gemini is probabilistic (temperature=1.0).
- Add `temperature=0.0` to Gemini calls for deterministic output
- Or accept variation as feature (more creative responses)

### Gotcha 4: Rate Limiting Blocks Legitimate Requests
**Problem**: Calling agents too fast (>5 requests/second) gets 429 errors

**Solution**:
- Implement exponential backoff on client side
- Or increase rate limit in code (max 60 req/minute per user)

---

## 🆘 EMERGENCY SHUTDOWN PROCEDURES

**If System is Broken and You Need to Stop It Fast:**

```bash
# 1. Kill backend:
pkill -f uvicorn

# 2. Kill ARQ worker:
pkill -f arq

# 3. Kill any rogue Gemini calls (optional):
pkill -f "google.generativeai"

# 4. Check what's running:
ps aux | grep python
```

**If Database is Corrupted:**

```bash
# Make a backup first:
pg_dump $DATABASE_URL > backup_$(date +%s).sql

# Then restore from previous backup (if available):
# In Supabase: Database → Backups → Restore
```

---

## 📋 SUPPORT RESOURCES

- **Google Gemini Docs**: https://ai.google.dev/docs
- **FastAPI Guide**: https://fastapi.tiangolo.com
- **SQLAlchemy Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Resend Email Docs**: https://resend.com/docs
- **trafilatura Docs**: https://trafilatura.readthedocs.io/

---

**Last Updated**: April 8, 2026  
**Version**: 1.0 (Initial deployment guide)

