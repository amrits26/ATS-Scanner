"""
SerpAPI Job Scraper Service - Legal, White-Hat Job Data Acquisition

Uses Google Jobs API via SerpAPI to legally aggregate jobs from:
- LinkedIn (via Google's cache)
- Indeed
- Glassdoor  
- Monster
- ZipRecruiter
- And 100+ other sources

No direct scraping. No IP bans. No legal issues. Just clean JSON.

Setup:
1. Sign up at https://serpapi.com (free tier: 100 searches/month)
2. Set SERPAPI_KEY environment variable
"""

import logging
import os
from typing import List, Dict, Optional
import httpx
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JobListingSerpAPI(BaseModel):
    """Job listing from SerpAPI"""
    id: str
    title: str
    company: str
    location: str
    country_code: str = "US"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    jd_text: str
    url: str
    source: str
    visa_sponsorship: bool = False
    remote: bool = False
    posted_date: Optional[str] = None


class SerpAPIJobScraper:
    """
    Scrapes jobs from Google Jobs via SerpAPI.
    Legal, fast, and scales to millions of jobs.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SERPAPI_KEY")
        
        if not self.api_key:
            logger.warning("[SERPAPI] SERPAPI_KEY not set. Job search will be limited.")
        
        self.base_url = "https://serpapi.com/search"
        self.session = None
        
        logger.info("[SERPAPI] SerpAPI Job Scraper initialized")

    async def search_jobs(
        self,
        query: str,
        location: str = "USA",
        pages: int = 1,
        filters: Optional[Dict] = None
    ) -> List[JobListingSerpAPI]:
        """
        Search for jobs using Google Jobs API.
        
        Args:
            query: Job title/keywords (e.g., "Senior Android Engineer")
            location: Location (e.g., "Sydney, Australia")
            pages: Number of pages (each page = 10 jobs)
            filters: Optional dict with keys:
              - visa_sponsorship: bool
              - remote: bool
              - salary_min: int (annually in thousands)
              - salary_max: int
        
        Returns: List of JobListingSerpAPI objects
        """
        if not self.api_key:
            logger.warning("[SERPAPI] No API key - returning empty results")
            return []
        
        try:
            logger.info(f"[SERPAPI] Searching: '{query}' in {location}")
            
            jobs = []
            
            for page in range(pages):
                try:
                    # Construct search parameters
                    params = {
                        "engine": "google_jobs",
                        "q": query,
                        "location": location,
                        "api_key": self.api_key,
                        "start": page * 10,  # Pagination
                    }
                    
                    # Add filters to query string
                    if filters:
                        if filters.get("visa_sponsorship"):
                            params["q"] += " visa sponsorship"
                        if filters.get("remote"):
                            params["q"] += " remote"
                    
                    logger.debug(f"[SERPAPI] Fetching page {page}...")
                    
                    # Make request
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(self.base_url, params=params)
                        response.raise_for_status()
                        data = response.json()
                    
                    # Parse jobs from response
                    jobs_data = data.get("jobs_results", [])
                    
                    if not jobs_data:
                        logger.debug(f"[SERPAPI] No jobs on page {page}")
                        break
                    
                    for job_data in jobs_data:
                        try:
                            job = self._parse_job_result(job_data)
                            
                            # Apply filters
                            if filters:
                                if filters.get("visa_sponsorship") and not job.visa_sponsorship:
                                    continue
                                if filters.get("remote") and not job.remote:
                                    continue
                                if filters.get("salary_min") and job.salary_max and job.salary_max < filters["salary_min"]:
                                    continue
                            
                            jobs.append(job)
                            
                        except Exception as e:
                            logger.debug(f"[SERPAPI] Failed to parse job: {e}")
                            continue
                    
                except Exception as e:
                    logger.warning(f"[SERPAPI] Page {page} failed: {e}")
                    break
            
            logger.info(f"[SERPAPI] Retrieved {len(jobs)} jobs")
            return jobs
            
        except Exception as e:
            logger.error(f"[SERPAPI] Search failed: {e}")
            return []

    def _parse_job_result(self, job_data: Dict) -> JobListingSerpAPI:
        """Parse a single job result from SerpAPI response"""
        
        # Extract salary range
        salary_min = None
        salary_max = None
        
        if "salary" in job_data and isinstance(job_data["salary"], dict):
            salary_str = job_data["salary"].get("from") or job_data["salary"].get("to")
            if salary_str:
                # Parse "$80,000" or "80,000"
                import re
                match = re.search(r'[\d,]+', str(salary_str))
                if match:
                    val = int(match.group().replace(",", "")) // 1000  # Convert to thousands
                    if "from" in job_data["salary"]:
                        salary_min = val
                    else:
                        salary_max = val
        
        # Detect visa sponsorship from description
        visa_keywords = ["h-1b", "visa sponsorship", "work visa", "sponsor", "immigration support"]
        description = (job_data.get("description") or "").lower()
        visa_sponsorship = any(kw in description for kw in visa_keywords)
        
        # Detect remote
        remote = job_data.get("job_type", "").lower() == "remote" or "remote" in description
        
        # Get country code from location
        country_code = self._infer_country_code(job_data.get("location", ""))
        
        job = JobListingSerpAPI(
            id=job_data.get("job_id", f"serpapi_{hash(job_data.get('title'))}"),
            title=job_data.get("title", ""),
            company=job_data.get("company_name", ""),
            location=job_data.get("location", ""),
            country_code=country_code,
            salary_min=salary_min,
            salary_max=salary_max,
            jd_text=job_data.get("description", "")[:5000],
            url=job_data.get("link", ""),
            source=self._infer_source(job_data.get("via", "")),
            visa_sponsorship=visa_sponsorship,
            remote=remote,
            posted_date=job_data.get("posted_at"),
        )
        
        return job

    def _infer_source(self, via_text: str) -> str:
        """Infer job source from 'via' field"""
        via_lower = via_text.lower()
        
        if "linkedin" in via_lower:
            return "linkedin"
        elif "indeed" in via_lower:
            return "indeed"
        elif "glassdoor" in via_lower:
            return "glassdoor"
        elif "ziprecruiter" in via_lower:
            return "ziprecruiter"
        elif "monster" in via_lower:
            return "monster"
        else:
            return "google_jobs"

    def _infer_country_code(self, location: str) -> str:
        """Infer country code from location string"""
        location_upper = location.upper()
        
        # Country detection
        country_map = {
            "AUSTRALIA": "AU",
            "SYDNEY": "AU",
            "MELBOURNE": "AU",
            "CANADA": "CA",
            "TORONTO": "CA",
            "VANCOUVER": "CA",
            "UK": "GB",
            "LONDON": "GB",
            "INDIA": "IN",
            "BANGALORE": "IN",
            "MUMBAI": "IN",
            "SINGAPORE": "SG",
            "HONG KONG": "HK",
            "NEW ZEALAND": "NZ",
            "AUCKLAND": "NZ",
        }
        
        for city, code in country_map.items():
            if city in location_upper:
                return code
        
        return "US"  # Default

    async def get_job_details(self, job_url: str) -> Optional[str]:
        """
        Fetch full job description from URL.
        Uses trafilatura for HTML extraction.
        """
        try:
            import trafilatura
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(job_url)
                response.raise_for_status()
                
                # Extract text from HTML
                extracted = trafilatura.extract(response.text)
                return extracted if extracted else ""
                
        except Exception as e:
            logger.debug(f"[SERPAPI] Failed to fetch details from {job_url}: {e}")
            return None


def get_serp_scraper() -> SerpAPIJobScraper:
    """Get or create singleton SerpAPIJobScraper instance"""
    return SerpAPIJobScraper()
