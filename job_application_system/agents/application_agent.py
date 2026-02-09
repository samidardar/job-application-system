"""
Agent 4: Application Agent
Handles auto-filling and submitting job applications
"""
import re
import time
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

from utils.database import DatabaseManager
from utils.config import get_config
from utils.logging_utils import ActivityLogger
from utils.anti_detection import AntiDetectionManager, SessionConfig

logger = logging.getLogger(__name__)

class ApplicationAgent:
    """Agent responsible for submitting job applications"""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.config = get_config()
        self.db = db_manager or DatabaseManager(self.config.get_database_path())
        self.activity_logger = ActivityLogger("ApplicationAgent", self.db)
        
        session_config = SessionConfig(
            delay_min=self.config.get('anti_detection.apply_delay_min', 5),
            delay_max=self.config.get('anti_detection.apply_delay_max', 12)
        )
        self.anti_detect = AntiDetectionManager(config=session_config)
        
        self.user_profile = self.config.get_user_profile()
        self.daily_limit = self.config.get_daily_limit()
        self.auto_apply = self.config.get('application.auto_apply', False)
    
    def run(self, dry_run: bool = True) -> Dict[str, int]:
        """
        Run application process for shortlisted jobs
        
        Args:
            dry_run: If True, only simulate applications without actually submitting
        """
        self.activity_logger.info(
            "Starting application run",
            f"Dry run: {dry_run}, Auto-apply: {self.auto_apply}"
        )
        
        # Check daily limit
        if not dry_run:
            todays_count = self._get_todays_application_count()
            if todays_count >= self.daily_limit:
                self.activity_logger.warning(
                    "Daily limit reached",
                    f"Already applied to {todays_count} jobs today"
                )
                return {'submitted': 0, 'skipped': 0, 'errors': 0, 'reason': 'daily_limit_reached'}
        
        # Get jobs to apply to
        jobs_to_apply = self._get_jobs_to_apply()
        
        logger.info(f"Found {len(jobs_to_apply)} jobs to apply to")
        
        results = {'submitted': 0, 'skipped': 0, 'errors': 0, 'pending_review': 0}
        
        for job in jobs_to_apply:
            try:
                # Check if we've hit daily limit
                if not dry_run and self._get_todays_application_count() >= self.daily_limit:
                    logger.info("Daily application limit reached")
                    break
                
                # Determine if we should auto-apply or manual review
                relevance_score = job.get('relevance_score', 0)
                auto_apply_threshold = self.config.get('application.auto_apply_threshold', 8.0)
                
                if not self.auto_apply or relevance_score < auto_apply_threshold:
                    # Mark for manual review
                    self._mark_for_review(job)
                    results['pending_review'] += 1
                    continue
                
                # Attempt application
                success = self.apply_to_job(job, dry_run=dry_run)
                
                if success:
                    results['submitted'] += 1
                    self.activity_logger.info(
                        f"Applied to {job['company']} - {job['title']}",
                        f"Platform: {job['platform']}"
                    )
                else:
                    results['errors'] += 1
                    
                # Add delay between applications
                self.anti_detect.human_like_delay("submit")
                
            except Exception as e:
                logger.error(f"Error applying to job {job['id']}: {e}")
                self.activity_logger.error(f"Applying to job {job['id']}", str(e))
                results['errors'] += 1
        
        self.activity_logger.info(
            "Application run complete",
            f"Results: {results}"
        )
        
        return results
    
    def _get_todays_application_count(self) -> int:
        """Get number of applications sent today"""
        stats = self.db.get_application_stats()
        return stats.get('today_applications', 0)
    
    def _get_jobs_to_apply(self) -> List[Dict]:
        """Get list of jobs ready for application"""
        # Get shortlisted jobs
        min_score = self.config.get_min_relevance_score()
        shortlisted = self.db.get_shortlisted_jobs(min_score, limit=self.daily_limit * 2)
        
        # Filter out jobs that already have applications
        jobs_to_apply = []
        for job in shortlisted:
            with self.db._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM applications WHERE job_id = ?",
                    (job['id'],)
                )
                if not cursor.fetchone():
                    jobs_to_apply.append(job)
        
        return jobs_to_apply[:self.daily_limit]
    
    def _mark_for_review(self, job: Dict):
        """Mark a job for manual review before application"""
        self.db.update_job_status(job['id'], 'pending_review')
        logger.info(f"Job {job['id']} marked for manual review")
    
    def apply_to_job(self, job: Dict, dry_run: bool = True) -> bool:
        """
        Apply to a specific job
        
        Returns:
            True if successful, False otherwise
        """
        platform = job.get('platform')
        
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would apply to: {job['title']} at {job['company']}")
                return True
            
            # Route to platform-specific application method
            if platform == 'linkedin':
                return self._apply_linkedin(job)
            elif platform == 'indeed':
                return self._apply_indeed(job)
            elif platform == 'welcometothejungle':
                return self._apply_wttj(job)
            else:
                logger.warning(f"Unknown platform: {platform}")
                return False
                
        except Exception as e:
            logger.error(f"Error in apply_to_job: {e}")
            return False
    
    def _apply_linkedin(self, job: Dict) -> bool:
        """Apply to a LinkedIn job"""
        logger.info(f"Applying to LinkedIn job: {job['title']}")
        
        # LinkedIn Easy Apply would require browser automation
        # For now, we'll track it as a manual application
        
        application_data = {
            'status': 'pending',
            'application_method': 'linkedin_easy_apply',
            'notes': 'LinkedIn Easy Apply - requires manual completion or browser automation'
        }
        
        self.db.insert_application(job['id'], application_data)
        return True
    
    def _apply_indeed(self, job: Dict) -> bool:
        """Apply to an Indeed job"""
        logger.info(f"Applying to Indeed job: {job['title']}")
        
        application_data = {
            'status': 'pending',
            'application_method': 'indeed',
            'notes': 'Indeed application - requires manual completion or browser automation'
        }
        
        self.db.insert_application(job['id'], application_data)
        return True
    
    def _apply_wttj(self, job: Dict) -> bool:
        """Apply to a Welcome to the Jungle job"""
        logger.info(f"Applying to WTTJ job: {job['title']}")
        
        application_data = {
            'status': 'pending',
            'application_method': 'welcometothejungle',
            'notes': 'WTTJ application - requires manual completion or browser automation'
        }
        
        self.db.insert_application(job['id'], application_data)
        return True
    
    def prepare_application_package(self, job: Dict) -> Dict:
        """Prepare all documents needed for an application"""
        package = {
            'job_id': job['id'],
            'cover_letter': None,
            'resume': None,
            'application_data': self._prepare_form_data(job)
        }
        
        # Get cover letter
        with self.db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT file_path FROM cover_letters WHERE job_id = ? ORDER BY generated_at DESC LIMIT 1",
                (job['id'],)
            )
            row = cursor.fetchone()
            if row:
                package['cover_letter'] = row[0]
        
        # Get resume
        language = 'fr'  # Default
        if job.get('title', '').lower().count(' ') < 3:  # Simple heuristic for English jobs
            language = 'en'
        
        if language == 'en' and self.config.get('application.cv_english_path'):
            package['resume'] = self.config.get('application.cv_english_path')
        else:
            package['resume'] = self.config.get('application.cv_path')
        
        return package
    
    def _prepare_form_data(self, job: Dict) -> Dict:
        """Prepare form data for auto-filling applications"""
        user = self.user_profile
        
        form_data = {
            'first_name': user.get('full_name', '').split()[0] if user.get('full_name') else '',
            'last_name': ' '.join(user.get('full_name', '').split()[1:]) if user.get('full_name') else '',
            'email': user.get('email', ''),
            'phone': user.get('phone', ''),
            'linkedin_url': user.get('linkedin_url', ''),
            'portfolio_url': user.get('portfolio_url', ''),
            'github_url': user.get('github_url', ''),
            'cover_letter_text': self._get_cover_letter_text(job),
        }
        
        return form_data
    
    def _get_cover_letter_text(self, job: Dict) -> str:
        """Get cover letter text for a job"""
        with self.db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT content FROM cover_letters WHERE job_id = ? ORDER BY generated_at DESC LIMIT 1",
                (job['id'],)
            )
            row = cursor.fetchone()
            if row:
                return row[0]
        
        return ""
    
    def track_follow_ups(self):
        """Check for applications needing follow-up"""
        follow_up_days = self.config.get('application.follow_up_days', 7)
        applications = self.db.get_applications_needing_followup(follow_up_days)
        
        logger.info(f"Found {len(applications)} applications needing follow-up")
        
        for app in applications:
            logger.info(f"Follow-up needed: {app['company']} - {app['title']}")
            # In a full implementation, this would send follow-up emails
    
    def get_application_status(self, job_id: int) -> Optional[str]:
        """Get the application status for a job"""
        with self.db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM applications WHERE job_id = ? ORDER BY application_date DESC LIMIT 1",
                (job_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    
    def update_application_status(self, application_id: int, status: str, notes: Optional[str] = None):
        """Update the status of an application"""
        self.db.update_application_status(application_id, status, notes)

if __name__ == "__main__":
    agent = ApplicationAgent()
    # Run in dry mode by default
    results = agent.run(dry_run=True)
    print(f"Application run complete: {results}")
    
    # Check follow-ups
    agent.track_follow_ups()
