"""
Agent 1: Scraping Agent
Scrapes job listings from LinkedIn, Indeed, and Welcome to the Jungle
"""
import requests
import re
import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from utils.database import DatabaseManager
from utils.config import get_config
from utils.logging_utils import ActivityLogger
from utils.anti_detection import AntiDetectionManager, get_random_delay_range

logger = logging.getLogger(__name__)

class ScrapingAgent:
    """Agent responsible for scraping job listings from multiple platforms"""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.config = get_config()
        self.db = db_manager or DatabaseManager(self.config.get_database_path())
        self.activity_logger = ActivityLogger("ScrapingAgent", self.db)
        
        self.platforms = {
            'linkedin': self.scrape_linkedin,
            'indeed': self.scrape_indeed,
            'welcometothejungle': self.scrape_welcometothejungle
        }
    
    def run(self) -> Dict[str, int]:
        """Run scraping for all enabled platforms"""
        self.activity_logger.info("Starting scraping job", "Beginning scraping run for all enabled platforms")
        
        results = {}
        enabled_platforms = self.config.get_enabled_platforms()
        
        for platform in enabled_platforms:
            try:
                count = self.scrape_platform(platform)
                results[platform] = count
                self.activity_logger.info(f"Scraped {platform}", f"Found {count} new jobs")
            except Exception as e:
                logger.error(f"Error scraping {platform}: {e}")
                self.activity_logger.error(f"Scraping {platform}", str(e))
                results[platform] = 0
        
        self.activity_logger.info("Scraping complete", f"Results: {results}")
        return results
    
    def scrape_platform(self, platform: str) -> int:
        """Scrape jobs from a specific platform"""
        if platform not in self.platforms:
            logger.error(f"Unknown platform: {platform}")
            return 0
        
        scraper_func = self.platforms[platform]
        return scraper_func()
    
    def _get_session(self, platform: str) -> requests.Session:
        """Create a configured session for scraping"""
        session = requests.Session()
        
        # Get anti-detection config
        anti_detect = AntiDetectionManager()
        
        # Set headers
        headers = {
            'User-Agent': anti_detect.get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
        session.headers.update(headers)
        
        return session
    
    def scrape_linkedin(self) -> int:
        """Scrape jobs from LinkedIn"""
        logger.info("Scraping LinkedIn...")
        platform_config = self.config.get_platform_config('linkedin')
        
        session = self._get_session('linkedin')
        anti_detect = AntiDetectionManager()
        
        new_jobs_count = 0
        search_urls = platform_config.get('search_urls', [])
        max_jobs = platform_config.get('max_jobs_per_session', 50)
        
        for search_url in search_urls:
            try:
                delay = anti_detect.random_delay(3, 7)
                logger.info(f"Fetching: {search_url}")
                
                response = session.get(search_url, timeout=30)
                
                if response.status_code != 200:
                    logger.warning(f"LinkedIn returned status {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # LinkedIn job cards
                job_cards = soup.find_all('div', class_=re.compile('base-card'))
                
                for card in job_cards[:max_jobs // len(search_urls)]:
                    try:
                        job_data = self._parse_linkedin_job(card, search_url)
                        if job_data and not self.db.job_exists(job_data['job_id'], 'linkedin'):
                            self.db.insert_job(job_data)
                            new_jobs_count += 1
                            
                            # Update platform stats
                            self.db.update_platform_stats('linkedin', 'jobs_scraped')
                        
                        # Check session limit
                        if anti_detect.check_session_limit():
                            break
                            
                        anti_detect.random_delay(2, 4)
                        
                    except Exception as e:
                        logger.error(f"Error parsing LinkedIn job card: {e}")
                        continue
                
                # Longer delay between search URLs
                anti_detect.random_delay(5, 10)
                
            except Exception as e:
                logger.error(f"Error scraping LinkedIn search URL: {e}")
                continue
        
        logger.info(f"LinkedIn scraping complete. New jobs: {new_jobs_count}")
        return new_jobs_count
    
    def _parse_linkedin_job(self, card, source_url: str) -> Optional[Dict]:
        """Parse a LinkedIn job card"""
        try:
            # Extract job ID from URL
            link_elem = card.find('a', class_=re.compile('base-card__full-link'))
            if not link_elem:
                return None
            
            job_url = link_elem.get('href', '')
            job_id_match = re.search(r'/jobs/view/(\d+)', job_url)
            job_id = job_id_match.group(1) if job_id_match else None
            
            if not job_id:
                return None
            
            # Extract title
            title_elem = card.find('h3', class_=re.compile('base-search-card__title'))
            title = title_elem.text.strip() if title_elem else "Unknown"
            
            # Extract company
            company_elem = card.find('a', class_=re.compile('hidden-nested-link'))
            company = company_elem.text.strip() if company_elem else "Unknown"
            
            # Extract location
            location_elem = card.find('span', class_=re.compile('job-search-card__location'))
            location = location_elem.text.strip() if location_elem else "Unknown"
            
            # Extract post date
            time_elem = card.find('time')
            post_date = None
            if time_elem and time_elem.get('datetime'):
                try:
                    post_date = datetime.fromisoformat(time_elem['datetime'].replace('Z', '+00:00'))
                except:
                    post_date = datetime.now()
            
            job_data = {
                'job_id': f"linkedin_{job_id}",
                'title': title,
                'company': company,
                'company_size': None,
                'location': location,
                'description': None,  # Would need to fetch detail page
                'requirements': None,
                'salary_range': None,
                'job_type': self._detect_job_type(title),
                'experience_level': self._detect_experience_level(title),
                'post_date': post_date,
                'application_url': job_url,
                'platform': 'linkedin',
                'raw_data': {'html': str(card)},
                'status': 'scraped'
            }
            
            return job_data
            
        except Exception as e:
            logger.error(f"Error parsing LinkedIn job: {e}")
            return None
    
    def scrape_indeed(self) -> int:
        """Scrape jobs from Indeed France"""
        logger.info("Scraping Indeed...")
        platform_config = self.config.get_platform_config('indeed')
        
        session = self._get_session('indeed')
        anti_detect = AntiDetectionManager()
        
        new_jobs_count = 0
        search_urls = platform_config.get('search_urls', [])
        max_jobs = platform_config.get('max_jobs_per_session', 50)
        
        for search_url in search_urls:
            try:
                logger.info(f"Fetching: {search_url}")
                anti_detect.random_delay(2, 5)
                
                response = session.get(search_url, timeout=30)
                
                if response.status_code != 200:
                    logger.warning(f"Indeed returned status {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Indeed job cards - updated selectors
                job_cards = soup.find_all('div', {'data-testid': 'job-title'})
                if not job_cards:
                    # Fallback to older selectors
                    job_cards = soup.find_all('div', class_=re.compile('job_seen_beacon|slider_container'))
                
                for card in job_cards[:max_jobs // len(search_urls)]:
                    try:
                        job_data = self._parse_indeed_job(card, search_url)
                        if job_data and not self.db.job_exists(job_data['job_id'], 'indeed'):
                            self.db.insert_job(job_data)
                            new_jobs_count += 1
                            
                            self.db.update_platform_stats('indeed', 'jobs_scraped')
                        
                        if anti_detect.check_session_limit():
                            break
                            
                        anti_detect.random_delay(2, 4)
                        
                    except Exception as e:
                        logger.error(f"Error parsing Indeed job card: {e}")
                        continue
                
                anti_detect.random_delay(5, 10)
                
            except Exception as e:
                logger.error(f"Error scraping Indeed: {e}")
                continue
        
        logger.info(f"Indeed scraping complete. New jobs: {new_jobs_count}")
        return new_jobs_count
    
    def _parse_indeed_job(self, card, source_url: str) -> Optional[Dict]:
        """Parse an Indeed job card"""
        try:
            # Find parent container
            parent = card
            if card.name != 'div' or 'job_seen_beacon' not in str(card.get('class', [])):
                parent = card.find_parent('div', class_=re.compile('job_seen_beacon|slider_container'))
            
            if not parent:
                parent = card
            
            # Extract job ID
            job_id = parent.get('data-jk', '') or parent.get('id', '').replace('job_', '')
            if not job_id:
                return None
            
            # Extract title
            title_elem = parent.find(['h2', 'a'], class_=re.compile('jcs-JobTitle|jobTitle'))
            if not title_elem:
                title_elem = parent.find('span', {'title': True})
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            
            # Extract company
            company_elem = parent.find(['span', 'a'], class_=re.compile('companyName|company'))
            company = company_elem.get_text(strip=True) if company_elem else "Unknown"
            
            # Extract location
            location_elem = parent.find(['div', 'span'], class_=re.compile('companyLocation|location'))
            location = location_elem.get_text(strip=True) if location_elem else "Unknown"
            
            # Extract salary if available
            salary_elem = parent.find('div', class_=re.compile('salary-snippet-container|estimated-salary'))
            salary = salary_elem.get_text(strip=True) if salary_elem else None
            
            # Extract snippet/summary
            snippet_elem = parent.find('div', class_=re.compile('job-snippet|summary'))
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else None
            
            job_data = {
                'job_id': f"indeed_{job_id}",
                'title': title,
                'company': company,
                'company_size': None,
                'location': location,
                'description': snippet,
                'requirements': None,
                'salary_range': salary,
                'job_type': self._detect_job_type(title + ' ' + (snippet or '')),
                'experience_level': self._detect_experience_level(title),
                'post_date': datetime.now(),
                'application_url': f"https://fr.indeed.com/viewjob?jk={job_id}",
                'platform': 'indeed',
                'raw_data': {'html': str(parent)},
                'status': 'scraped'
            }
            
            return job_data
            
        except Exception as e:
            logger.error(f"Error parsing Indeed job: {e}")
            return None
    
    def scrape_welcometothejungle(self) -> int:
        """Scrape jobs from Welcome to the Jungle"""
        logger.info("Scraping Welcome to the Jungle...")
        platform_config = self.config.get_platform_config('welcometothejungle')
        
        session = self._get_session('welcometothejungle')
        anti_detect = AntiDetectionManager()
        
        new_jobs_count = 0
        search_urls = platform_config.get('search_urls', [])
        max_jobs = platform_config.get('max_jobs_per_session', 40)
        
        headers = {
            'Accept': 'application/json',
            'Referer': 'https://www.welcometothejungle.com/',
            'X-Requested-With': 'XMLHttpRequest'
        }
        session.headers.update(headers)
        
        for search_url in search_urls:
            try:
                logger.info(f"Fetching: {search_url}")
                anti_detect.random_delay(4, 8)
                
                response = session.get(search_url, timeout=30)
                
                if response.status_code != 200:
                    logger.warning(f"WTTJ returned status {response.status_code}")
                    continue
                
                # WTTJ uses API-based job loading
                try:
                    data = response.json()
                    jobs = data.get('jobs', []) if isinstance(data, dict) else []
                except:
                    # Fallback to HTML parsing
                    soup = BeautifulSoup(response.content, 'html.parser')
                    job_cards = soup.find_all('a', href=re.compile('/jobs/'))
                    jobs = [{'html': str(card)} for card in job_cards]
                
                for job in jobs[:max_jobs // len(search_urls)]:
                    try:
                        job_data = self._parse_wttj_job(job)
                        if job_data and not self.db.job_exists(job_data['job_id'], 'welcometothejungle'):
                            self.db.insert_job(job_data)
                            new_jobs_count += 1
                            
                            self.db.update_platform_stats('welcometothejungle', 'jobs_scraped')
                        
                        if anti_detect.check_session_limit():
                            break
                            
                        anti_detect.random_delay(3, 6)
                        
                    except Exception as e:
                        logger.error(f"Error parsing WTTJ job: {e}")
                        continue
                
                anti_detect.random_delay(6, 12)
                
            except Exception as e:
                logger.error(f"Error scraping WTTJ: {e}")
                continue
        
        logger.info(f"Welcome to the Jungle scraping complete. New jobs: {new_jobs_count}")
        return new_jobs_count
    
    def _parse_wttj_job(self, job: Dict) -> Optional[Dict]:
        """Parse a Welcome to the Jungle job"""
        try:
            if isinstance(job, dict) and 'id' in job:
                # API response format
                job_id = job.get('id', '')
                title = job.get('name', 'Unknown')
                
                organization = job.get('organization', {})
                company = organization.get('name', 'Unknown')
                company_size = organization.get('size', {}).get('name') if isinstance(organization.get('size'), dict) else None
                
                location_data = job.get('location', {})
                if isinstance(location_data, dict):
                    location = location_data.get('city', location_data.get('name', 'Unknown'))
                else:
                    location = str(location_data)
                
                description = job.get('description', '')
                
                # Extract requirements from description
                requirements = self._extract_requirements(description)
                
                # Get salary info
                salary = job.get('salary', {})
                salary_range = None
                if isinstance(salary, dict):
                    min_salary = salary.get('min', '')
                    max_salary = salary.get('max', '')
                    currency = salary.get('currency', 'EUR')
                    if min_salary and max_salary:
                        salary_range = f"{min_salary} - {max_salary} {currency}"
                
                job_data = {
                    'job_id': f"wttj_{job_id}",
                    'title': title,
                    'company': company,
                    'company_size': company_size,
                    'location': location,
                    'description': description,
                    'requirements': requirements,
                    'salary_range': salary_range,
                    'job_type': job.get('contract', {}).get('type', 'Alternance') if isinstance(job.get('contract'), dict) else 'Alternance',
                    'experience_level': job.get('experienceLevel', {}).get('name') if isinstance(job.get('experienceLevel'), dict) else None,
                    'post_date': datetime.now(),  # WTTJ doesn't always provide this
                    'application_url': f"https://www.welcometothejungle.com/jobs/{job_id}",
                    'platform': 'welcometothejungle',
                    'raw_data': job,
                    'status': 'scraped'
                }
                
                return job_data
            
            elif 'html' in job:
                # HTML parsing fallback
                soup = BeautifulSoup(job['html'], 'html.parser')
                # Would implement HTML parsing here
                return None
            
        except Exception as e:
            logger.error(f"Error parsing WTTJ job: {e}")
            return None
    
    def _detect_job_type(self, text: str) -> Optional[str]:
        """Detect job type from text"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['alternance', 'apprentissage', 'apprenti']):
            return 'Alternance'
        elif any(word in text_lower for word in ['stage', 'internship', 'stagiaire']):
            return 'Stage'
        elif 'cdi' in text_lower:
            return 'CDI'
        elif 'cdd' in text_lower:
            return 'CDD'
        
        return None
    
    def _detect_experience_level(self, text: str) -> Optional[str]:
        """Detect experience level from text"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['senior', 'confirmé', '5+ years', '5 ans']):
            return 'Senior'
        elif any(word in text_lower for word in ['junior', 'débutant', 'entry level', '0-2 years']):
            return 'Junior'
        elif any(word in text_lower for word in ['intermediate', 'intermédiaire', '2-5 years']):
            return 'Intermédiaire'
        
        return None
    
    def _extract_requirements(self, description: str) -> Optional[str]:
        """Extract requirements section from description"""
        if not description:
            return None
        
        # Look for requirements sections
        patterns = [
            r'(?:Profil recherché|Requirements?|Qualifications?|Compétences?)[\s:]*(.*?)(?:\n\n|\Z)',
            r'(?:Ce que nous cherchons|What we look for)[\s:]*(.*?)(?:\n\n|\Z)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()[:2000]  # Limit length
        
        return None

if __name__ == "__main__":
    agent = ScrapingAgent()
    results = agent.run()
    print(f"Scraping complete: {results}")
