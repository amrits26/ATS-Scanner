"""
Job Scraper Service - Fetches job listings from multiple sources

Supports:
- Indeed job search
- LinkedIn job cards (basic)
- Hacker News jobs (if available)

Returns structured Job objects suitable for AI Job Hunter resume tailoring.
"""

import logging
from typing import Optional
from datetime import datetime
from dataclasses import dataclass
import trafilatura
import requests
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

# Data class for job postings
@dataclass
class JobListing:
    id: str
    title: str
    company: str
    location: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    jd_text: str = ""
    url: str = ""
    source: str = "indeed"  # indeed, linkedin, hackernews
    visa_sponsorship: bool = False
    posted_date: Optional[str] = None
    country_code: str = "US"  # US, CA, AU etc
    
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary_range": f"${self.salary_min}k - ${self.salary_max}k" if self.salary_min else None,
            "url": self.url,
            "source": self.source,
            "visa_sponsorship": self.visa_sponsorship,
            "posted_date": self.posted_date,
            "country_code": self.country_code,
        }


class JobScraperService:
    """Scrapes job listings for the Job Hunter feature"""
    
    INDEED_BASE_URL = "https://www.indeed.com/jobs"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Visa sponsorship keywords to detect
    VISA_KEYWORDS = [
        "H-1B", "H1B", "visa sponsorship", "visa support",
        "work visa", "immigration support", "green card",
        "TN visa", "L1 visa", "sponsorship available"
    ]
    
    # Salary regex patterns
    SALARY_REGEX = r"\$(\d+[,\d]*)\s*(?:k|-)\s*\$?(\d+[,\d]*)\s*k?"

    async def search_jobs(self, query: str, location: str = "USA", 
                         pages: int = 1) -> list[JobListing]:
        """
        Search for jobs using parameters
        
        Args:
            query: Job title/keywords (e.g. "Software Engineer")
            location: Location filter (e.g. "San Francisco, CA" or "USA")
            pages: Number of pages to scrape (1-3 recommended)
            
        Returns:
            List of JobListing objects
        """
        logger.info(f"[SCRAPER] Searching for '{query}' in {location} ({pages} pages)")
        
        jobs = []
        try:
            # For now, return mock data since real scraping needs proxy handling
            # Production would need:
            # - Proxy rotation (Bright Data, ScraperAPI)
            # - Rate limiting
            # - Caching (Redis)
            # - Error retry logic
            
            jobs = await self._scrape_indeed(query, location, pages)
            
            logger.info(f"[SCRAPER] Found {len(jobs)} jobs")
            return jobs
            
        except Exception as e:
            logger.error(f"[SCRAPER] Search failed: {e}")
            raise

    async def _scrape_indeed(self, query: str, location: str, 
                            pages: int) -> list[JobListing]:
        """Scrape Indeed with basic HTML parsing"""
        jobs = []
        
        try:
            # Indeed URL with search params
            for page in range(pages):
                start = page * 10
                url = f"{self.INDEED_BASE_URL}?q={query}&l={location}&start={start}"
                
                logger.debug(f"[SCRAPER] Fetching {url}")
                
                response = requests.get(url, headers=self.HEADERS, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"[SCRAPER] Indeed returned {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find job cards – Indeed uses .job_seen_beacon or similar
                job_cards = soup.find_all('div', class_=re.compile('job_seen_beacon|resultContent'))
                
                for card in job_cards:
                    try:
                        # Extract title
                        title_elem = card.find('h2', class_=re.compile('jobTitle'))
                        title = title_elem.get_text(strip=True) if title_elem else "N/A"
                        
                        # Extract company
                        company_elem = card.find('span', class_='companyName')
                        company = company_elem.get_text(strip=True) if company_elem else "N/A"
                        
                        # Extract location
                        location_elem = card.find('div', class_=re.compile('companyLocation'))
                        job_location = location_elem.get_text(strip=True) if location_elem else location
                        
                        # Extract job URL
                        link_elem = card.find('a', class_='jcs-JobTitle')
                        job_url = link_elem['href'] if link_elem and link_elem.has_attr('href') else ""
                        if job_url and not job_url.startswith('http'):
                            job_url = f"https://indeed.com{job_url}"
                        
                        # Extract salary if visible
                        salary_text = card.get_text()
                        salary_match = re.search(self.SALARY_REGEX, salary_text)
                        salary_min, salary_max = None, None
                        if salary_match:
                            salary_min = int(salary_match.group(1).replace(',', ''))
                            salary_max = int(salary_match.group(2).replace(',', ''))
                        
                        # Check visa sponsorship keywords in snippet
                        snippet = card.get_text()
                        visa_sponsorship = any(kw.lower() in snippet.lower() for kw in self.VISA_KEYWORDS)
                        
                        # Fetch full JD via trafilatura if URL available
                        jd_text = ""
                        if job_url:
                            try:
                                jd_response = requests.get(job_url, headers=self.HEADERS, timeout=10)
                                extracted = trafilatura.extract(jd_response.text)
                                jd_text = extracted or ""
                            except Exception as e:
                                logger.debug(f"[SCRAPER] Couldn't extract JD from {job_url}: {e}")
                        
                        # Create JobListing
                        job = JobListing(
                            id=f"indeed_{len(jobs)}_{hash(title)}",
                            title=title,
                            company=company,
                            location=job_location,
                            salary_min=salary_min,
                            salary_max=salary_max,
                            jd_text=jd_text[:5000],  # Truncate to avoid huge payloads
                            url=job_url,
                            source="indeed",
                            visa_sponsorship=visa_sponsorship,
                            country_code=self._infer_country(job_location)
                        )
                        
                        jobs.append(job)
                        logger.debug(f"[SCRAPER] Scraped: {title} at {company} ({job_location})")
                        
                    except Exception as e:
                        logger.debug(f"[SCRAPER] Skipped job card: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"[SCRAPER] Indeed scraping failed: {e}")
        
        return jobs

    def _infer_country(self, location: str) -> str:
        """Infer country code from location string"""
        location_upper = location.upper()
        
        if any(x in location_upper for x in ["CANADA", "ON", "BC", "TORONTO"]):
            return "CA"
        elif any(x in location_upper for x in ["AUSTRALIA", "SYDNEY", "MELBOURNE"]):
            return "AU"
        elif any(x in location_upper for x in ["UK", "LONDON", "ENGLAND"]):
            return "GB"
        elif any(x in location_upper for x in ["INDIA", "BANGALORE", "MUMBAI"]):
            return "IN"
        
        return "US"  # Default to US


# Singleton instance
_scraper = None


def get_scraper():
    """Get or create scraper instance"""
    global _scraper
    if _scraper is None:
        _scraper = JobScraperService()
    return _scraper
