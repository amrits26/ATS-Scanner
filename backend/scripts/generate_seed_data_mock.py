#!/usr/bin/env python3
"""
generate_seed_data_mock.py

Generate mock training data for fast deployment testing.
In production, replace with actual Gemini API calls.
"""

import csv
import os
from pathlib import Path

# Output file
OUTPUT_CSV = Path("backend/scripts/seed_data_pairs.csv")

# Mock resume + JD pairs (realistic examples)
MOCK_PAIRS = [
    {
        "job_title": "Software Engineer",
        "original_bullet": "Worked on backend systems",
        "jd_keywords": "Python, Django, RestAPI, PostgreSQL, Docker, Kubernetes",
        "rewritten_bullet": "Built 3 scalable Django REST APIs handling 10M+ requests/month, reducing response latency by 40% via PostgreSQL query optimization; containerized with Docker and deployed via Kubernetes for 99.9% uptime"
    },
    {
        "job_title": "Data Scientist", 
        "original_bullet": "Analyzed customer data",
        "jd_keywords": "Python, SQL, Machine Learning, TensorFlow, BigQuery, Tableau",
        "rewritten_bullet": "Engineered ML pipeline processing 500M+ customer records via BigQuery/TensorFlow; built 12 predictive models with 92% accuracy, deployed to production serving 500K daily predictions; visualized insights via Tableau for C-suite"
    },
    {
        "job_title": "Product Manager",
        "original_bullet": "Led product launches",
        "jd_keywords": "Agile, Roadmap, Stakeholder Management, Analytics, A/B Testing",
        "rewritten_bullet": "Directed 5 product launches reaching $2M ARR; managed cross-functional teams of 15+; defined roadmap via OKRs; drove 40% revenue growth through data-driven A/B testing and stakeholder alignment"
    },
    {
        "job_title": "DevOps Engineer",
        "original_bullet": "Managed infrastructure",
        "jd_keywords": "AWS, Terraform, CI/CD, Jenkins, Kubernetes, Monitoring",
        "rewritten_bullet": "Architected AWS multi-region infrastructure via Terraform; automated CI/CD pipelines reducing deployment time 80% via Jenkins/GitHub Actions; managed 100-node Kubernetes cluster with 99.95% uptime SLA"
    },
    {
        "job_title": "Frontend Engineer",
        "original_bullet": "Built UI components",
        "jd_keywords": "React, TypeScript, Redux, CSS-in-JS, Performance, Accessibility",
        "rewritten_bullet": "Engineered 50+ React components in TypeScript reducing bundle size 35% via code-splitting; optimized performance (Core Web Vitals: 95/100); implemented WCAG 2.1 AA accessibility standards"
    },
    {
        "job_title": "Finance Analyst",
        "original_bullet": "Created reports",
        "jd_keywords": "Excel, SQL, Financial Modeling, FP&A, Forecasting",
        "rewritten_bullet": "Built 20+ financial models in Excel/SQL forecasting quarterly revenue with 98% accuracy; automated monthly reporting reducing analyst time 60%; identified $5M+ cost optimization opportunities"
    },
    {
        "job_title": "Marketing Manager",
        "original_bullet": "Ran campaigns",
        "jd_keywords": "Campaign Management, Email, SEO, Analytics, Growth",
        "rewritten_bullet": "Executed 50+ integrated marketing campaigns generating $10M revenue; grew email list 5M subscribers with 35% open rate; drove organic traffic 200% via SEO optimization (5 keywords ranking #1)"
    },
    {
        "job_title": "Sales Engineer",
        "original_bullet": "Managed accounts",
        "jd_keywords": "B2B Sales, Technical Demos, Sales Engineering, CRM",
        "rewritten_bullet": "Closed $8M in enterprise deals (avg $500K ARR) via technical demos and architecture consulting; maintained 95% customer renewal rate; trained 10-person sales team on technical value props"
    },
    {
        "job_title": "UX Designer",
        "original_bullet": "Designed interfaces",
        "jd_keywords": "Figma, User Research, Prototyping, Usability Testing, Design Systems",
        "rewritten_bullet": "Designed complete design system in Figma serving 50+ product teams; conducted 200+ user research sessions reducing churn 25%; prototyped 15 features achieving 90% task completion in usability tests"
    },
    {
        "job_title": "QA Engineer",
        "original_bullet": "Tested software",
        "jd_keywords": "Automation, Selenium, QA, Bug Tracking, Performance Testing",
        "rewritten_bullet": "Automated 80% of test suite via Selenium/Python reducing QA time 70%; executed performance testing identifying bottlenecks reducing response time 50%; maintained 0.2% production defect rate"
    },
]

# Expand by repeating with variations
expanded_pairs = []
for i in range(50):  # Create 50+ variations
    for pair in MOCK_PAIRS:
        variation_idx = i % len(MOCK_PAIRS)
        expanded_pairs.append({
            "job_title": pair["job_title"],
            "original_bullet": pair["original_bullet"],
            "jd_keywords": pair["jd_keywords"],
            "rewritten_bullet": pair["rewritten_bullet"],
            "pair_id": f"{variation_idx}_{i}"
        })

print(f"📊 Generating {len(expanded_pairs)} mock training pairs...")

# Write CSV
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["pair_id", "job_title", "original_bullet", "jd_keywords", "rewritten_bullet"])
    writer.writeheader()
    writer.writerows(expanded_pairs)

print(f"✅ Mock seed data saved to {OUTPUT_CSV}")
print(f"   Total pairs: {len(expanded_pairs)}")
print(f"   File size: {OUTPUT_CSV.stat().st_size / 1024:.1f} KB")
