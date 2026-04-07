# Monitoring & Alerting Configuration
## ATS Scanner v2.0 - Production Ready

### Overview
Critical metrics and alert rules for production monitoring. Configure with your monitoring system (Datadog, New Relic, CloudWatch, etc.).

---

## Critical Metrics & Thresholds

### API Availability & Performance

| Metric | Target | Warning | Critical | Check Frequency |
|--------|--------|---------|----------|-----------------|
| API Health Check | 200 OK | N/A | No response for 2 min | Every 30s |
| Error Rate (all endpoints) | <0.5% | >1% for 5 min | >5% for 5 min | Every 1 min |
| Response Time (p95) | <500ms | >1000ms avg | >2000ms avg | Every 1 min |
| Response Time (p99) | <1000ms | >2000ms avg | >5000ms avg | Every 1 min |
| Successful Requests | >99% | <98% | <95% | Every 5 min |

### Analysis Pipeline

| Metric | Target | Warning | Critical | Action |
|--------|--------|---------|----------|--------|
| Analysis Submission Success | >99% | <98% | <95% | Check backend logs, database connection |
| Analysis Completion Time | <5s median | >10s | >30s | Check Gemini API quota, database slow queries |
| Fallback Activation Rate | <5% | >10% | >20% | Monitor Gemini API availability |
| Queue Depth (pending analyses) | <100 | >500 | >1000 | Scale backend workers |

### Database Performance

| Metric | Target | Warning | Critical | Resolution |
|--------|--------|---------|----------|------------|
| Active Connections | <50 | >70 | >90 (of 100) | Increase connection pool, check for leaks |
| Connection Pool Exhaustion | 0 | Any event | Immediate | Emergency: Scale database or reduce connections |
| Query Latency (p95) | <50ms | >100ms | >500ms | Check for slow queries, index missing |
| Replication Lag | <1s | >5s | >30s | Check network, database load |
| Disk Space Free | >20% | <15% | <5% | Immediate cleanup or increase storage |

### Backend Infrastructure

| Metric | Target | Warning | Critical | Action |
|--------|--------|---------|----------|--------|
| CPU Usage | <50% | >70% | >90% | Scale horizontally (add instances) |
| Memory Usage | <60% | >80% | >95% | Restart workers, check for leaks |
| Disk I/O | <70% | >85% | >95% | Optimize queries, check for runaway processes |
| Network I/O | <50% available | >70% | >90% | Check for DDoS, optimize payload size |
| Uptime | 100% | Any downtime | Immediate | Alert on-call, start incident response |

### Payment Processing

| Metric | Target | Warning | Critical | Action |
|--------|--------|---------|----------|--------|
| Stripe Webhook Success Rate | >99.5% | >99% | <99% | Check webhook handler, retry queue |
| Webhook Processing Latency | <500ms | >1000ms | >5000ms | Optimize tier update logic |
| Payment Success Rate | >99.5% | 99% | <99% | Check Stripe API, review recent failures |
| Refund Processing Time | <24h | >48h | Never | Review Stripe dashboard |
| Failed Charges | 0 | Any | Immediate | Investigate with Stripe support |

### Frontend

| Metric | Target | Warning | Critical | Action |
|--------|--------|---------|----------|--------|
| Page Load Time | <2s | >3s | >5s | Check CDN, optimize assets |
| JavaScript Errors | 0 | >5 per hour | >20 per hour | Check browser console logs, review deployment |
| Core Web Vitals (LCP) | <2.5s | >3s | >5s | Optimize image loading, reduce JS |
| Core Web Vitals (CLS) | <0.1 | >0.1 | >0.25 | Check for layout shifts, lazy loading |
| 404 Errors | 0 | >1 per hour | >5 per hour | Check for missing assets, review CDN |

---

## Alert Rules (By Severity)

### CRITICAL (Immediate Action Required - Page On-Call)

```
1. API is Down
   Rule: /health endpoint fails for 2+ minutes
   Condition: No 200 response
   Action: Page on-call, start incident
   Notification: PagerDuty, Slack #incidents, SMS

2. Database Connection Pool Exhausted
   Rule: Active connections > 90 (of 100)
   Condition: Sustained for 1 minute
   Action: Page DBA, stop new backend instances
   Notification: PagerDuty, Slack, SMS

3. Payment Processing Down
   Rule: Stripe API communication fails for 5+ minutes
   Condition: All Stripe calls returning errors
   Action: Page payments team, notify customers
   Notification: PagerDuty, Slack #payments, SMS

4. Data Loss Risk
   Rule: Database logs show unexpected deletes/truncates
   Condition: Any table with >10x normal delete rate
   Action: Immediate: Stop all writes, page DBA
   Notification: PagerDuty, all executives, SMS

5. Security Issue
   Rule: Unusual authentication failures (50+ in 1 min)
   Condition: Brute force attempt detected
   Action: Page security team, rate limit attacker
   Notification: PagerDuty, Slack #security

6. Disk Running Out
   Rule: Free disk space <5%
   Condition: Sustained for 5 minutes
   Action: Page ops, emergency cleanup
   Notification: PagerDuty, Slack, SMS
```

### HIGH (Action Required Within 15 Minutes)

```
1. High Error Rate
   Rule: API errors >5% for 5+ minutes
   Condition: Any endpoint returning >5% errors
   Action: Review logs, check recent deployments
   Notification: Slack #incidents, ops-team

2. Slow Responses
   Rule: p95 response time >2 seconds
   Condition: Sustained for 10+ minutes
   Action: Check database, review slow queries
   Notification: Slack #incidents

3. Memory Leak
   Rule: Memory usage grows >2% per minute
   Condition: Sustained for 15+ minutes
   Action: Identify process, plan restart
   Notification: Slack #incidents

4. Analysis Pipeline Slow
   Rule: Analysis completion time >30 seconds
   Condition: >3 analyses affected
   Action: Check Gemini API, scale workers
   Notification: Slack #incidents

5. High Queue Depth
   Rule: Pending analyses >1000
   Condition: Sustained for 5+ minutes
   Action: Scale backend workers
   Notification: Slack #incidents
```

### MEDIUM (Action Required Within 1 Hour)

```
1. Elevated Error Rate
   Rule: API errors >1% for 5+ minutes
   Condition: Below critical threshold
   Action: Monitor, review logs
   Notification: Slack #incidents

2. Database Slow
   Rule: p95 query time >100ms
   Condition: Sustained for 10+ minutes
   Action: Review slow query log
   Notification: Slack #backend

3. Disk Space Low
   Rule: Free disk <15%
   Condition: Sustained for 5 minutes
   Action: Plan cleanup or expansion
   Notification: Slack #ops

4. Certificate Expiring
   Rule: SSL certificate expires in <30 days
   Condition: One-time check daily
   Action: Renew certificate
   Notification: Slack #ops (reminder task)

5. Fallback Rate High
   Rule: Gemini fallback >10% of analyses
   Condition: Sustained for 30+ minutes
   Action: Investigate Gemini API issues
   Notification: Slack #backend
```

### LOW (Monitor Trend)

```
1. High CPU Usage
   Rule: CPU >70% average
   Condition: Sustained for 30+ minutes
   Action: Monitor, plan scaling
   Notification: Daily summary report

2. High Memory Usage
   Rule: Memory >80% average
   Condition: Sustained for 30+ minutes
   Action: Monitor, plan restart
   Notification: Daily summary report

3. Slow Webhook Processing
   Rule: Webhook latency >1 second
   Condition: >3 consecutive webhooks
   Action: Review webhook handler
   Notification: Weekly report only
```

---

## Alert Notification Routing

### By Severity & Component:

| Severity | Channels | Response Time |
|----------|----------|----------------|
| CRITICAL | PagerDuty + SMS + Slack + Call | Immediate (5 min) |
| HIGH | PagerDuty + Slack | 15 minutes |
| MEDIUM | Slack channel | 1 hour |
| LOW | Daily digest email | Next business day |

### By Category:

| Category | Primary | Backup | Escalation |
|----------|---------|--------|------------|
| Infrastructure | #ops | PagerDuty | VP Eng |
| Backend | #backend | PagerDuty | Tech Lead |
| Database | #database + DBA | PagerDuty | Infrastructure Lead |
| Payments | #payments | Stripe Support | CFO |
| Security | #security | CISO | Legal |
| Frontend | #frontend | PagerDuty | Product Lead |

---

## Monitoring Dashboard Queries

### Backend Health Dashboard

```sql
-- Query 1: Request Success Rate (Last 1 hour)
SELECT 
  timestamp,
  COUNT(*) as total_requests,
  SUM(CASE WHEN status_code < 400 THEN 1 ELSE 0 END) as successful,
  ROUND(100.0 * SUM(CASE WHEN status_code < 400 THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM api_logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY timestamp ORDER BY timestamp DESC;

-- Query 2: Average Response Time by Endpoint (Last 1 hour)
SELECT 
  endpoint,
  COUNT(*) as hits,
  ROUND(AVG(response_time_ms), 2) as avg_time,
  ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms), 2) as p95,
  MAX(response_time_ms) as max_time
FROM api_logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY endpoint
ORDER BY p95 DESC;

-- Query 3: Error Distribution (Last 1 hour)
SELECT 
  status_code,
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM api_logs WHERE timestamp > NOW() - INTERVAL '1 hour'), 2) as percentage
FROM api_logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY status_code
ORDER BY count DESC;
```

### Database Performance Dashboard

```sql
-- Query 1: Active Connection Count
SELECT 
  datname,
  COUNT(*) as active_connections,
  MAX(state_change) as latest_activity
FROM pg_stat_activity
WHERE datname = 'intelliresume_prod'
GROUP BY datname;

-- Query 2: Slow Queries (>100ms)
SELECT 
  query,
  calls,
  ROUND(total_exec_time / calls, 2) as avg_time,
  total_exec_time
FROM pg_stat_statements
WHERE total_exec_time > 100000
ORDER BY avg_time DESC
LIMIT 20;

-- Query 3: Table Sizes
SELECT 
  schemaname,
  tablename,
  ROUND(pg_total_relation_size(schemaname || '.' || tablename) / 1024 / 1024, 2) as size_mb
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;
```

### Analysis Pipeline Dashboard

```sql
-- Query: Analysis Status Distribution (Last 24 hours)
SELECT 
  status,
  COUNT(*) as count,
  ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))), 2) as avg_duration_sec
FROM analysis_results
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY status
ORDER BY count DESC;
```

---

## Incident Response Playbooks

### BrokenAPI Endpoint
1. Check `/health` - is backend alive?
2. Review backend logs for errors
3. Check database connectivity
4. Check API rate limiting
5. If recent deployment: View code changes, consider rollback

### Slow Analysis Processing
1. Check Gemini API status page
2. Check database slow query log
3. Monitor queue depth
4. Check worker process count
5. Scale workers if queue>500

### Database Connection Issues
1. Check active connection count (`pgAdmin` or SQL query)
2. Check for long-running queries
3. Kill idle connections if safe
4. Check connection pool settings
5. Restart backend if pool remains exhausted

### Payment Failures
1. Check Stripe API status
2. Review webhook event log (Stripe dashboard)
3. Check webhook handler logs
4. Verify webhook signing key
5. Contact Stripe support if API down

---

## Post-Incident Review Checklist

After any alert fires:
- [ ] Log incident start time, severity, impact
- [ ] Document root cause
- [ ] Record resolution time and steps
- [ ] Identify preventive measures
- [ ] Create ticket for improvements
- [ ] Update runbooks if needed
- [ ] Share learnings in team meeting

---

**Last Updated:** 2025-04-07
**Version:** 2.0.0
**Status:** Ready for Production
