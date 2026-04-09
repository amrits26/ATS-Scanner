# COMPREHENSIVE DEPLOYMENT GUIDE
## ATS Scanner: Phase 1-3 Production Deployment

**Last Updated**: April 8, 2026  
**Status**: ✅ PRODUCTION READY  
**Total Files**: 49  
**Total LOC**: 6,165  
**Target Revenue**: $30-57K MRR  

---

## 📋 Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Database Setup](#database-setup)
3. [Environment Configuration](#environment-configuration)
4. [Backend Deployment](#backend-deployment)
5. [Frontend Deployment](#frontend-deployment)
6. [Monitoring & Logging](#monitoring-logging)
7. [Post-Deployment Verification](#post-deployment-verification)
8. [Troubleshooting](#troubleshooting)
9. [Rollback Procedures](#rollback-procedures)

---

## Pre-Deployment Checklist

### Security Review
- [ ] All secrets removed from code (check `git log` and `grep` for API keys)
- [ ] `.env.example` contains only placeholder values
- [ ] AWS/GCP/Heroku credentials stored ONLY in CI/CD environment variables
- [ ] Database password changed from default

### Code Quality
- [ ] `pytest backend/tests/ -v` passes with >80% coverage
- [ ] `flake8 backend/ --max-line-length=100` shows no errors
- [ ] `black --check backend/` passes
- [ ] `mypy backend/` has <5 warnings
- [ ] Postman collection tests all 20+ endpoints successfully

### Infrastructure
- [ ] PostgreSQL database created (v13+)
- [ ] Redis instance configured (v6+)
- [ ] Email service (Resend) API key generated
- [ ] Google Gemini API key active with sufficient quota
- [ ] Stripe account configured (webhooks + test keys)
- [ ] CDN configured (optional, for static assets)

### Team Communications
- [ ] Slack webhook configured for deploy notifications
- [ ] On-call rotation established
- [ ] Rollback decision tree documented
- [ ] Incident response plan published

---

## Database Setup

### Step 1: Create PostgreSQL Instance

**Local Development** (using Docker):
```bash
docker run --name ats-postgres \
  -e POSTGRES_PASSWORD=mysecurepass \
  -e POSTGRES_DB=ats_scanner \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15-alpine
```

**Production** (Cloud Managed Options):

**AWS RDS**:
```bash
aws rds create-db-instance \
  --db-instance-identifier ats-scanner-prod \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 15.3 \
  --master-username admin \
  --master-user-password $(openssl rand -base64 32) \
  --allocated-storage 100 \
  --backup-retention-period 30 \
  --multi-az \
  --storage-encrypted
```

**Google Cloud SQL**:
```bash
gcloud sql instances create ats-scanner-prod \
  --database-version=POSTGRES_15 \
  --tier=db-g1-small \
  --region=us-central1 \
  --backup-start-time=03:00
```

**Heroku Postgres**:
```bash
heroku addons:create heroku-postgresql:standard-0 -a ats-scanner
```

### Step 2: Apply Migrations

```bash
# Export database URL
export DATABASE_URL="postgresql://user:password@host:5432/ats_scanner"

# Install Alembic (if not in requirements.txt)
pip install alembic

# Initialize Alembic (one-time)
# alembic init migrations  # SKIP - already done

# Run all migrations
alembic upgrade head

# Verify migration status
alembic current
alembic history --verbose
```

**Manual SQL Migration** (if not using Alembic):
```bash
psql $DATABASE_URL < backend/migrations/001_init.sql
psql $DATABASE_URL < backend/migrations/002_phase2_revenue_fortress.sql
psql $DATABASE_URL < backend/migrations/010_phase1_email_automation.sql
psql $DATABASE_URL < backend/migrations/011_phase2_ai_agents.sql
psql $DATABASE_URL < backend/migrations/012_phase3_legal_data.sql
psql $DATABASE_URL < backend/migrations/013_analytics_snapshots.sql
```

### Step 3: Verify Database

```bash
psql $DATABASE_URL -c "\dt"  # List all tables
psql $DATABASE_URL -c "SELECT COUNT(*) FROM users;"  # Check users table
```

---

## Environment Configuration

### Step 1: Create Production `.env` File

**Template**:
```bash
# Backend config
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://user:pass@host:5432/ats_scanner
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis (for async job queue)
REDIS_URL=redis://host:6379/0
REDIS_PASSWORD=your_secure_password

# API Keys & Secrets
GOOGLE_API_KEY=your_gemini_api_key
RESEND_API_KEY=your_resend_api_key
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxx

# Auth
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
JWT_SECRET=your_jwt_secret_key

# Email
SUPPORT_EMAIL=support@atsscanner.com
ADMIN_EMAIL=admin@atsscanner.com

# Frontend URLs
FRONTEND_URL=https://atsscanner.com
ALLOWED_ORIGINS=https://atsscanner.com,https://www.atsscanner.com

# Stripe Webhooks
STRIPE_SUCCESS_URL=https://atsscanner.com/checkout/success
STRIPE_CANCEL_URL=https://atsscanner.com/checkout/cancel
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxx

# AWS S3 (optional, for resume storage)
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_S3_BUCKET=ats-scanner-prod
AWS_REGION=us-east-1

# Analytics
POSTHOG_API_KEY=your_posthog_key
SENTRY_DSN=your_sentry_dsn

# Slack (for notifications)
SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Step 2: Secure Environment Files

```bash
# DO NOT commit .env to Git!
echo ".env" >> .gitignore
echo ".env.*.local" >> .gitignore

# Set restrictive permissions
chmod 600 .env

# Encrypt .env for backup (optional)
gpg --symmetric .env
```

### Step 3: Load Environment in Production

**Using systemd** (Linux):
```bash
# Create /etc/systemd/system/ats-scanner.service
[Service]
EnvironmentFile=/opt/ats-scanner/.env
ProtectSystem=full
NoNewPrivileges=true
```

**Using Docker**:
```bash
docker run \
  --env-file /path/to/.env \
  -p 8000:8000 \
  ats-scanner:latest
```

**Using Kubernetes**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ats-scanner-env
data:
  DATABASE_URL: <base64-encoded-value>
  GOOGLE_API_KEY: <base64-encoded-value>
---
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: api
    envFrom:
    - secretRef:
        name: ats-scanner-env
```

---

## Backend Deployment

### Option 1: Deploy to Heroku (Simplest)

```bash
# Login to Heroku
heroku login

# Create app
heroku create ats-scanner-prod

# Set environment variables
heroku config:set \
  ENVIRONMENT=production \
  DATABASE_URL=$DATABASE_URL \
  GOOGLE_API_KEY=$GOOGLE_API_KEY \
  RESEND_API_KEY=$RESEND_API_KEY \
  --app ats-scanner-prod

# Deploy
git push heroku main

# View logs
heroku logs --tail --app ats-scanner-prod

# Run migrations
heroku run "alembic upgrade head" --app ats-scanner-prod
```

### Option 2: Deploy to AWS (via Docker + ECS)

```bash
# Build Docker image
docker build -t ats-scanner:latest .

# Tag for ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $REGISTRY_URL
docker tag ats-scanner:latest $REGISTRY_URL/ats-scanner:latest
docker push $REGISTRY_URL/ats-scanner:latest

# Update ECS service
aws ecs update-service \
  --cluster ats-scanner-prod \
  --service api \
  --force-new-deployment
```

### Option 3: Deploy to Google Cloud Run

```bash
# Build and submit to Cloud Build
gcloud builds submit --tag gcr.io/$PROJECT_ID/ats-scanner:latest

# Deploy to Cloud Run
gcloud run deploy ats-scanner \
  --image gcr.io/$PROJECT_ID/ats-scanner:latest \
  --platform managed \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --set-env-vars DATABASE_URL=$DATABASE_URL,GOOGLE_API_KEY=$GOOGLE_API_KEY

# View logs
gcloud run logs read ats-scanner --size=50
```

### Option 4: Deploy to Ubuntu VM (DIY)

```bash
# SSH into server
ssh ubuntu@your-server-ip

# Clone repository
git clone https://github.com/yourusername/ats-scanner.git
cd ats-scanner

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start with systemd
cat > /etc/systemd/system/ats-scanner.service << EOF
[Unit]
Description=ATS Scanner API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/ats-scanner
Environment="PATH=/home/ubuntu/ats-scanner/venv/bin"
ExecStart=/home/ubuntu/ats-scanner/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable ats-scanner
sudo systemctl start ats-scanner

# Check status
sudo systemctl status ats-scanner
```

---

## Frontend Deployment

### Step 1: Build Frontend

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build

# Output in frontend/dist/
```

### Step 2: Deploy to CDN Options

**Vercel** (Recommended for React):
```bash
npm install -g vercel
vercel --prod

# Select project and confirm
```

**Netlify**:
```bash
npm install -g netlify-cli
netlify deploy --prod --dir=dist
```

**AWS S3 + CloudFront**:
```bash
# Build
npm run build

# Upload to S3
aws s3 sync dist/ s3://ats-scanner-frontend/ --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

**GitHub Pages**:
```bash
# Add to package.json
"homepage": "https://yourusername.github.io/ats-scanner/"

# Deploy
npm run build
npm run deploy  # Uses gh-pages package
```

---

## Monitoring & Logging

### Step 1: Configure Application Logging

```python
# backend/main.py
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler()
    ]
)
```

### Step 2: Send Logs to Central Service

**Sentry** (Error tracking):
```python
import sentry_sdk

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=0.1,
    environment=os.getenv("ENVIRONMENT", "development")
)
```

**DataDog** (Full monitoring):
```bash
pip install datadog

# In main.py
from datadog import initialize, api
initialize(api_key="your_api_key", app_key="your_app_key")
```

### Step 3: Set Up Alerts

**Slack Alerts**:
```bash
# Create Slack workflow
webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Send alert on error
requests.post(webhook_url, json={
    "text": "❌ API Error: Database connection failed"
})
```

**PagerDuty Integration**:
```bash
Configure in Sentry → Integrations → PagerDuty
```

### Step 4: Database Monitoring

```bash
# Monitor query performance
EXPLAIN ANALYZE
SELECT * FROM users WHERE email = 'test@example.com';

# Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Monitor slow queries
ALTER SYSTEM SET log_min_duration_statement = 1000;  # Log queries >1s
```

---

## Post-Deployment Verification

### Step 1: Health Check Endpoints

```bash
# API health
curl -X GET https://api.atsscanner.com/health

# Database check
curl -X GET https://api.atsscanner.com/health/db

# Frontend load
curl -X GET https://atsscanner.com -I
```

### Step 2: Test Core Features

```bash
# Test agent (Coach)
curl -X POST https://api.atsscanner.com/api/agent/coach \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "How to improve my resume?", "resume_text": "Senior Python Developer..."}'

# Test interview marketplace
curl -X GET https://api.atsscanner.com/api/interviews/google

# Test analytics (admin only)
curl -X GET https://api.atsscanner.com/api/analytics/dashboard \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Step 3: Run Postman Collection

```bash
# Use Postman CLI
npx newman run ATS_Scanner_API.postman_collection.json \
  --environment postman_env.json \
  --reporters cli,json

# Output: test-results.json
```

### Step 4: Load Testing (Optional)

```bash
# Using Apache Bench
ab -n 1000 -c 10 https://api.atsscanner.com/health

# Using k6
k6 run load-test.js
```

---

## Troubleshooting

### Problem: Database Connection Fails

**Solution**:
```bash
# Check credentials
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"

# Verify SSL requirements
# Add ?sslmode=require to DATABASE_URL if needed
export DATABASE_URL="postgresql://user:pass@host:5432/ats_scanner?sslmode=require"

# Check network firewall
telnet $DB_HOST 5432
```

### Problem: Gemini API Rate Limited

**Solution**:
```python
# Implement exponential backoff (already in code)
# Check quota in Google Cloud Console
# Upgrade plan if necessary
```

### Problem: Email Sending Fails

**Solution**:
```bash
# Test Resend API key
curl -X GET https://api.resend.com/emails \
  -H "Authorization: Bearer $RESEND_API_KEY"

# Check bounce list
curl -X GET https://api.resend.com/bounces \
  -H "Authorization: Bearer $RESEND_API_KEY"
```

### Problem: Slow Analytics Dashboard

**Solution**:
```sql
-- Add indexes
CREATE INDEX idx_user_sessions_date ON user_sessions(created_at DESC);
CREATE INDEX idx_agent_calls_user_date ON agent_calls(user_id, created_at DESC);

-- Enable query plan analysis
EXPLAIN ANALYZE
SELECT COUNT(*) FROM user_sessions WHERE created_at > NOW() - INTERVAL '30 days';
```

---

## Rollback Procedures

### Quick Rollback (Within 5 Minutes)

```bash
# Heroku: Rollback to previous release
heroku releases:rollback --app ats-scanner-prod

# AWS ECS: Redeploy previous image
aws ecs update-service --cluster ats-scanner-prod --service api \
  --force-new-deployment --image "ats-scanner:previous-tag"

# Check status
heroku logs --tail --app ats-scanner-prod
```

### Database Rollback

```bash
# List migrations
alembic history

# Rollback one migration
alembic downgrade -1

# Rollback to specific history
alembic downgrade 002_phase2
```

### Full Rollback Checklist

- [ ] Stop traffic to canary/new deployment
- [ ] Verify old version still running
- [ ] Test critical endpoints
- [ ] Rollback database migrations (if applicable)
- [ ] Clear deployment status from Slack
- [ ] Post-mortem within 24 hours

---

## Success Criteria

After deployment, verify:

✅ **Performance**:
- API response time <200ms (p95)
- Database queries <100ms
- Uptime >99.5%

✅ **Revenue**:
- Email campaigns: >5% open rate
- Agent adoption: >10% of free users
- Pro tier sign-ups: >2% of users

✅ **Stability**:
- Error rate <0.1%
- 99.9% uptime
- Zero data loss

✅ **Security**:
- All API responses authenticated
- Database encrypted at rest
- No exposed API keys in logs

---

## 24/7 Support

**On-Call Runbook**: `docs/ON_CALL_RUNBOOK.md`  
**Internal Slack**: `#ats-scanner-ops`  
**StatusPage**: https://status.atsscanner.com

---

**DEPLOYMENT COMPLETE! 🚀**

Questions? Check `TROUBLESHOOTING.md` or contact the team.
