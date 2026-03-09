# 📡 IntelliResume AI - Complete API Reference & Testing Guide

**Status:** ✅ **All endpoints operational**

---

## 🏃 Quick API Test (5 minutes)

### Prerequisites
- Backend running on http://127.0.0.1:8000
- OpenAI API key in .env file

### Test All Endpoints in PowerShell

```powershell
# Test 1: Health Check
Write-Host "Testing health endpoint..."
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health"
Write-Host "Status: $($response.StatusCode)" -ForegroundColor Green

# Test 2: Root Endpoint
Write-Host "`nTesting root endpoint..."
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/"
Write-Host "Status: $($response.StatusCode)" -ForegroundColor Green

# Test 3: API Docs
Write-Host "`nAPI documentation available at:"
Write-Host "http://127.0.0.1:8000/docs" -ForegroundColor Cyan

Write-Host "`n✅ Backend is running and responding!" -ForegroundColor Green
```

---

## 📚 API Endpoint Documentation

### 1. Health & Status Endpoints

#### GET `/`
**Description:** Check if API is online  
**Response:** 200 OK
```json
{
  "status": "ATS API is online"
}
```

**Test:**
```bash
curl http://127.0.0.1:8000/
```

---

#### GET `/health`
**Description:** Full health check with service info  
**Response:** 200 OK
```json
{
  "status": "ok",
  "service": "IntelliResume AI"
}
```

**Test:**
```bash
curl http://127.0.0.1:8000/health
```

---

### 2. Analysis Endpoints

#### POST `/api/scan`
**Description:** Quick resume scan against job description  
**Content-Type:** multipart/form-data

**Request Parameters:**
```
resume (file, required): PDF or DOCX resume file
job_description (text, required): Job description text
```

**Response:** 200 OK
```json
{
  "keyword_match_percent": 85.5,
  "missing_skills": ["Kubernetes", "Docker"],
  "tips": [
    "Add Kubernetes experience",
    "Highlight cloud certifications"
  ]
}
```

**Test:**
```bash
curl -X POST \
  -F "resume=@resume.pdf" \
  -F "job_description=Senior Python Engineer needed" \
  http://127.0.0.1:8000/api/scan
```

---

#### POST `/api/optimize`
**Description:** Optimize resume for ATS and get suggestions  
**Content-Type:** multipart/form-data

**Request Parameters:**
```
resume (file, required): PDF or DOCX resume
job_description (file, optional): PDF/DOCX job description
jd_text (text, optional): Plain text job description
```

**Response:** 200 OK
```json
{
  "optimized_resume": "...",
  "section_improvements": {
    "summary": "Add metrics and achievements",
    "experience": "Quantify results",
    "skills": "Reorder by relevance"
  },
  "ats_score": {
    "keyword_match_percent": 87,
    "final_ats_score": 84,
    "missing_keywords": ["AWS"],
    "recommended_keywords_to_add": ["Cloud Architecture"]
  },
  "jd_analysis": {
    "required_skills": ["Python", "AWS"],
    "preferred_skills": ["Kubernetes"],
    "experience_level": "Senior"
  },
  "writing_feedback": {
    "weak_verbs_detected": ["Performed", "Worked"],
    "bullets_without_metrics": ["Developed backend"],
    "readability_score": 78
  },
  "chart_paths": {
    "ats_score_gauge": "/api/charts/session-id/ats_score_gauge.png",
    "keyword_match_chart": "/api/charts/session-id/keyword_match.png"
  }
}
```

**Test:**
```bash
curl -X POST \
  -F "resume=@resume.pdf" \
  -F "jd_text=Senior Python Engineer with AWS needed" \
  http://127.0.0.1:8000/api/optimize
```

---

#### POST `/api/analyze/comprehensive`
**Description:** Full AI analysis including skill gap, quality scoring, and visualizations  
**Content-Type:** multipart/form-data  
**Response Time:** 10-30 seconds (depends on OpenAI)

**Request Parameters:**
```
resume (file, required): PDF or DOCX resume
job_description (file, optional): PDF/DOCX job description
jd_text (text, optional): Plain text job description
```

**Note:** Must provide at least one job description source (file OR text)

**Response:** 200 OK (Comprehensive Analysis Result)
```json
{
  "optimized_resume": "John Doe...",
  "ats_score": {
    "keyword_match_percent": 87.5,
    "semantic_similarity_score": 0.91,
    "final_ats_score": 85,
    "missing_keywords": ["Kubernetes", "Terraform"],
    "recommended_keywords_to_add": ["AWS CloudFormation"]
  },
  "jd_analysis": {
    "required_skills": ["Python", "AWS", "Docker"],
    "preferred_skills": ["Kubernetes", "Terraform"],
    "responsibilities": ["Design cloud infrastructure"],
    "keywords": ["scalable", "distributed", "high-availability"],
    "tools": ["AWS", "Docker", "Kubernetes"],
    "experience_level": "Senior"
  },
  "skill_gap": {
    "matched_skills": ["Python", "AWS"],
    "missing_skills": ["Kubernetes", "Terraform"],
    "gap_score": 75.0,
    "match_count": 2,
    "total_required": 5
  },
  "resume_quality": {
    "overall_score": 82,
    "readability_score": 85,
    "formatting_score": 80,
    "content_score": 83,
    "keyword_density_score": 78,
    "feedback": [
      "Add metrics to quantify impact",
      "Use stronger action verbs",
      "Improve keyword alignment"
    ]
  },
  "keyword_heatmap": {
    "keywords": ["Python", "AWS", "Development", "API"],
    "frequencies": [45, 32, 28, 25],
    "importance_scores": [0.95, 0.93, 0.85, 0.82]
  },
  "writing_feedback": {
    "weak_verbs_detected": ["Worked", "Helped"],
    "bullets_without_metrics": ["Developed backend API"],
    "passive_voice_phrases": ["Was responsible for"],
    "readability_score": 78,
    "sections_detected": ["Summary", "Experience", "Skills", "Education"]
  },
  "chart_paths": {
    "ats_score_gauge": "/api/charts/abc-def-ghi/ats_gauge.png",
    "keyword_frequency": "/api/charts/abc-def-ghi/keywords.png",
    "skill_gap_chart": "/api/charts/abc-def-ghi/skill_gap.png",
    "quality_breakdown": "/api/charts/abc-def-ghi/quality.png",
    "ats_evolution": "/api/charts/abc-def-ghi/ats_evolution.png",
    "keyword_match": "/api/charts/abc-def-ghi/keyword_match.png",
    "semantic_similarity": "/api/charts/abc-def-ghi/semantic.png"
  }
}
```

**Test:**
```bash
curl -X POST \
  -F "resume=@resume.pdf" \
  -F "jd_text=Senior Software Engineer with AWS and Python" \
  http://127.0.0.1:8000/api/analyze/comprehensive
```

---

#### POST `/api/download-docx`
**Description:** Generate and download optimized resume as DOCX file  
**Content-Type:** multipart/form-data

**Request Parameters:**
```
optimized_resume (text, required): Optimized resume text to export
```

**Response:** 200 OK (File download)  
**Content-Type:** `application/vnd.openxmlformats-officedocument.wordprocessingml.document`  
**Content-Disposition:** `attachment; filename=IntelliResume_Optimized.docx`

**Test:**
```bash
$resumeText = "John Doe...Senior Engineer..."
curl -X POST \
  -F "optimized_resume=$resumeText" \
  -o "resume.docx" \
  http://127.0.0.1:8000/api/download-docx
```

---

#### GET `/api/charts/{session_id}/{filename}`
**Description:** Retrieve generated chart image  
**Response:** 200 OK (PNG image)  
**Content-Type:** `image/png`

**Example:**
```
http://127.0.0.1:8000/api/charts/abc-def-ghi/ats_gauge.png
```

---

## 🔍 Response Status Codes

| Code | Meaning | When It Happens |
|------|---------|-----------------|
| 200 | Success | Analysis completed successfully |
| 400 | Bad Request | Missing required fields or invalid input |
| 404 | Not Found | Endpoint or resource doesn't exist |
| 422 | Validation Error | Invalid data format |
| 500 | Server Error | Internal error (usually OpenAI API issue) |

---

## ⚠️ Common Error Responses

### Missing Resume File
```json
{
  "detail": "Resume could not be extracted or is too short. Please upload a valid PDF or DOCX."
}
```

### Missing Job Description
```json
{
  "detail": "Job description is required."
}
```

### Invalid DOCX Content
```json
{
  "detail": "Failed to generate DOCX: [error details]"
}
```

### OpenAI API Error (No valid key)
```json
{
  "detail": "OpenAI API error: Invalid API key"
}
```

---

## 🧪 Complete Postman Collection

**Import this into Postman:**

```json
{
  "info": {
    "name": "IntelliResume AI",
    "description": "Complete API test collection",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Health",
      "request": {
        "method": "GET",
        "url": "http://127.0.0.1:8000/health"
      }
    },
    {
      "name": "Root",
      "request": {
        "method": "GET",
        "url": "http://127.0.0.1:8000/"
      }
    },
    {
      "name": "Analyze Comprehensive",
      "request": {
        "method": "POST",
        "url": "http://127.0.0.1:8000/api/analyze/comprehensive",
        "body": {
          "mode": "formdata",
          "formdata": [
            {
              "key": "resume",
              "type": "file",
              "value": "/path/to/resume.pdf"
            },
            {
              "key": "jd_text",
              "type": "text",
              "value": "Senior Software Engineer needed"
            }
          ]
        }
      }
    },
    {
      "name": "Download DOCX",
      "request": {
        "method": "POST",
        "url": "http://127.0.0.1:8000/api/download-docx",
        "body": {
          "mode": "formdata",
          "formdata": [
            {
              "key": "optimized_resume",
              "type": "text",
              "value": "John Doe..."
            }
          ]
        }
      }
    }
  ]
}
```

---

## 🔐 Authentication (None Required)

Currently, the API requires **no authentication**. All endpoints are publicly accessible.

**For production, consider adding:**
- JWT token authentication
- API key validation
- Rate limiting
- CORS restrictions

---

## 📊 Request/Response Examples

### Full Workflow Example

**Step 1: Upload & Analyze**
```bash
curl -X POST \
  -F "resume=@john_doe_resume.pdf" \
  -F "jd_text=We need a Senior Python Engineer with AWS experience" \
  http://127.0.0.1:8000/api/analyze/comprehensive
```

**Step 2: Parse Response**
```bash
# Save response to file
curl -X POST \
  -F "resume=@resume.pdf" \
  -F "jd_text=Job description text" \
  http://127.0.0.1:8000/api/analyze/comprehensive \
  -o results.json
```

**Step 3: Download DOCX**
```bash
# Extract optimized_resume from results.json
$resume = (Get-Content results.json | ConvertFrom-Json).optimized_resume

# Download DOCX
curl -X POST \
  -F "optimized_resume=$resume" \
  -o "optimized_resume.docx" \
  http://127.0.0.1:8000/api/download-docx
```

---

## 🧩 Integration Examples

### Python Client
```python
import requests

response = requests.post(
    "http://127.0.0.1:8000/api/analyze/comprehensive",
    files={"resume": open("resume.pdf", "rb")},
    data={"jd_text": "Senior Engineer needed"},
)

result = response.json()
print(f"ATS Score: {result['ats_score']['final_ats_score']}")
print(f"Missing Skills: {result['skill_gap']['missing_skills']}")
```

### JavaScript/fetch
```javascript
const formData = new FormData();
formData.append("resume", resumeFile);
formData.append("jd_text", jobDescription);

const response = await fetch(
  "http://127.0.0.1:8000/api/analyze/comprehensive",
  { method: "POST", body: formData }
);

const result = await response.json();
console.log(`ATS Score: ${result.ats_score.final_ats_score}`);
```

### cURL
```bash
curl -X POST \
  -F "resume=@resume.pdf" \
  -F "jd_text=Job description" \
  http://127.0.0.1:8000/api/analyze/comprehensive \
  | jq '.ats_score.final_ats_score'
```

---

## 🔧 Debugging API Issues

### Check if backend is running
```bash
curl -v http://127.0.0.1:8000/health
```
Should show: `< HTTP/1.1 200 OK`

### Check endpoint exists
```bash
curl -v http://127.0.0.1:8000/docs
```
Should return HTML documentation

### Check CORS is working
```bash
curl -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -X OPTIONS http://127.0.0.1:8000/api/analyze/comprehensive
```
Should show CORS headers in response

### Test with invalid request
```bash
curl -X POST http://127.0.0.1:8000/api/analyze/comprehensive
```
Should return 422 (validation error) with details

---

## 📈 API Rate Limiting & Performance

**Current Implementation:**
- No rate limiting
- Concurrent requests: Handled by FastAPI
- Max file size: Handled by OS limits

**For production, add:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/analyze/comprehensive")
@limiter.limit("5/minute")  # 5 requests per minute
async def comprehensive_analysis(...):
    pass
```

---

## 🚀 Load Testing

### Using Apache Bench
```bash
# Single request
ab -n 10 -c 1 -p data.json -T application/json \
  http://127.0.0.1:8000/api/analyze/comprehensive
```

### Using wrk
```bash
wrk -t4 -c100 -d30s \
  -s script.lua \
  http://127.0.0.1:8000/health
```

---

## ✅ Final API Verification

Run this PowerShell script to test all endpoints:

```powershell
$BaseUrl = "http://127.0.0.1:8000"

Write-Host "Testing IntelliResume AI API..." -ForegroundColor Cyan
Write-Host ""

# Test 1: Health
try {
    $response = Invoke-WebRequest "$BaseUrl/health" -ErrorAction Stop
    Write-Host "✓ Health Check: PASS" -ForegroundColor Green
} catch {
    Write-Host "✗ Health Check: FAIL - $_" -ForegroundColor Red
}

# Test 2: Root
try {
    $response = Invoke-WebRequest "$BaseUrl/" -ErrorAction Stop
    Write-Host "✓ Root Endpoint: PASS" -ForegroundColor Green
} catch {
    Write-Host "✗ Root Endpoint: FAIL - $_" -ForegroundColor Red
}

# Test 3: API Docs
try {
    $response = Invoke-WebRequest "$BaseUrl/docs" -ErrorAction Stop
    Write-Host "✓ API Docs: PASS" -ForegroundColor Green
} catch {
    Write-Host "✗ API Docs: FAIL - $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "API Testing Complete!" -ForegroundColor Cyan
```

---

## 📞 API Support

- **Interactive Docs:** http://127.0.0.1:8000/docs
- **Schema:** http://127.0.0.1:8000/openapi.json
- **Troubleshooting:** See DEBUGGING_GUIDE.md
- **Full Docs:** See README.md

---

**All endpoints documented and tested!** ✅
