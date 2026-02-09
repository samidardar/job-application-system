"""
Agent 2: Analysis Agent
Analyzes scraped jobs, scores relevance, and creates shortlist
"""
import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import Counter

from utils.database import DatabaseManager
from utils.config import get_config
from utils.logging_utils import ActivityLogger

logger = logging.getLogger(__name__)

class AnalysisAgent:
    """Agent responsible for analyzing job listings and scoring relevance"""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.config = get_config()
        self.db = db_manager or DatabaseManager(self.config.get_database_path())
        self.activity_logger = ActivityLogger("AnalysisAgent", self.db)
        
        # Load keywords for matching
        self.keywords = self.config.get_search_keywords()
        self.high_priority_keywords = [k.lower() for k in self.keywords.get('high_priority', [])]
        self.medium_priority_keywords = [k.lower() for k in self.keywords.get('medium_priority', [])]
        self.exclude_keywords = [k.lower() for k in self.keywords.get('exclude', [])]
        
        # Load user profile for matching
        self.user_profile = self.config.get_user_profile()
        self.user_skills = self._extract_user_skills()
    
    def _extract_user_skills(self) -> List[str]:
        """Extract all user skills from profile"""
        skills = []
        technical_skills = self.user_profile.get('skills', {}).get('technical', [])
        soft_skills = self.user_profile.get('skills', {}).get('soft', [])
        
        skills.extend([s.lower() for s in technical_skills])
        skills.extend([s.lower() for s in soft_skills])
        
        return skills
    
    def run(self) -> Dict[str, int]:
        """Run analysis on all unanalyzed jobs"""
        self.activity_logger.info("Starting analysis job", "Beginning job analysis run")
        
        # Get jobs to analyze
        jobs_to_analyze = self.db.get_jobs_for_analysis(
            limit=self.config.get('search.max_jobs_per_run', 100)
        )
        
        logger.info(f"Found {len(jobs_to_analyze)} jobs to analyze")
        
        analyzed_count = 0
        shortlisted_count = 0
        rejected_count = 0
        
        for job in jobs_to_analyze:
            try:
                score, match_details = self.analyze_job(job)
                
                # Determine status based on score
                min_score = self.config.get_min_relevance_score()
                
                if score >= min_score:
                    status = 'analyzed'
                    shortlisted_count += 1
                else:
                    status = 'rejected_low_score'
                    rejected_count += 1
                
                # Update job in database
                self.db.update_job_status(job['id'], status, score)
                
                # Store match details
                with self.db._get_connection() as conn:
                    conn.execute(
                        "UPDATE jobs SET match_details = ? WHERE id = ?",
                        (json.dumps(match_details), job['id'])
                    )
                
                analyzed_count += 1
                
                # Update platform stats
                self.db.update_platform_stats(job['platform'], 'jobs_analyzed')
                
            except Exception as e:
                logger.error(f"Error analyzing job {job.get('id')}: {e}")
                self.activity_logger.error(f"Analyzing job {job.get('id')}", str(e))
                continue
        
        self.activity_logger.info(
            "Analysis complete", 
            f"Analyzed: {analyzed_count}, Shortlisted: {shortlisted_count}, Rejected: {rejected_count}"
        )
        
        return {
            'analyzed': analyzed_count,
            'shortlisted': shortlisted_count,
            'rejected': rejected_count
        }
    
    def analyze_job(self, job: Dict) -> Tuple[float, Dict]:
        """
        Analyze a single job and return relevance score and match details
        
        Returns:
            Tuple of (score: float, match_details: dict)
        """
        text_to_analyze = self._get_combined_text(job)
        text_lower = text_to_analyze.lower()
        
        match_details = {
            'keyword_matches': [],
            'skill_matches': [],
            'exclude_matches': [],
            'job_type_match': False,
            'experience_match': False,
            'location_match': False,
            'individual_scores': {}
        }
        
        # Calculate individual component scores
        scores = {}
        
        # 1. Keyword matching (max 4 points)
        keyword_score, keyword_matches = self._calculate_keyword_score(text_lower)
        scores['keywords'] = keyword_score
        match_details['keyword_matches'] = keyword_matches
        
        # 2. Skills matching (max 3 points)
        skill_score, skill_matches = self._calculate_skill_score(text_lower)
        scores['skills'] = skill_score
        match_details['skill_matches'] = skill_matches
        
        # 3. Job type matching (max 1 point)
        job_type_score, job_type_match = self._calculate_job_type_score(job)
        scores['job_type'] = job_type_score
        match_details['job_type_match'] = job_type_match
        
        # 4. Experience level matching (max 1 point)
        experience_score, experience_match = self._calculate_experience_score(job)
        scores['experience'] = experience_score
        match_details['experience_match'] = experience_match
        
        # 5. Location matching (max 0.5 point)
        location_score, location_match = self._calculate_location_score(job)
        scores['location'] = location_score
        match_details['location_match'] = location_match
        
        # 6. Recency bonus (max 0.5 point)
        recency_score = self._calculate_recency_score(job)
        scores['recency'] = recency_score
        
        # Check for exclusion keywords (negative scoring)
        exclude_penalty, exclude_matches = self._check_exclusions(text_lower)
        scores['exclusion_penalty'] = exclude_penalty
        match_details['exclude_matches'] = exclude_matches
        
        # Calculate total score
        total_score = sum(scores.values()) - exclude_penalty
        total_score = max(0, min(10, total_score))  # Clamp between 0-10
        
        match_details['individual_scores'] = scores
        match_details['total_score'] = round(total_score, 2)
        
        return round(total_score, 2), match_details
    
    def _get_combined_text(self, job: Dict) -> str:
        """Combine all job text fields for analysis"""
        fields = [
            job.get('title', ''),
            job.get('description', ''),
            job.get('requirements', ''),
            job.get('company', ''),
            job.get('location', '')
        ]
        return ' '.join(filter(None, fields))
    
    def _calculate_keyword_score(self, text: str) -> Tuple[float, List[str]]:
        """
        Calculate keyword matching score
        High priority keywords: 0.4 points each (max 2.4)
        Medium priority keywords: 0.2 points each (max 1.6)
        """
        matches = []
        score = 0.0
        
        # Check high priority keywords
        for keyword in self.high_priority_keywords:
            if keyword in text:
                matches.append(f"HIGH:{keyword}")
                score += 0.4
        
        # Check medium priority keywords
        for keyword in self.medium_priority_keywords:
            if keyword in text:
                matches.append(f"MEDIUM:{keyword}")
                score += 0.2
        
        return min(4.0, score), matches
    
    def _calculate_skill_score(self, text: str) -> Tuple[float, List[str]]:
        """
        Calculate skills matching score
        Each matched skill: 0.3 points (max 3 points)
        """
        matches = []
        score = 0.0
        
        for skill in self.user_skills:
            # Use word boundaries for more accurate matching
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(skill)
                score += 0.3
        
        return min(3.0, score), matches
    
    def _calculate_job_type_score(self, job: Dict) -> Tuple[float, bool]:
        """
        Check if job type matches what user is looking for
        Alternance/Stage preferred for students
        """
        job_type = (job.get('job_type') or '').lower()
        title = (job.get('title') or '').lower()
        description = (job.get('description') or '').lower()
        
        preferred_types = [t.lower() for t in self.user_profile.get('role_types', [])]
        
        # Check explicit job type field
        if job_type:
            for pref_type in preferred_types:
                if pref_type in job_type:
                    return 1.0, True
        
        # Check title and description
        combined_text = title + ' ' + description
        for pref_type in preferred_types:
            if pref_type in combined_text:
                return 1.0, True
        
        # Check for explicit CDI mentions (may not be suitable for alternance-seekers)
        if 'cdi' in combined_text and 'alternance' not in preferred_types:
            return 0.3, False
        
        return 0.5, False  # Neutral score if unclear
    
    def _calculate_experience_score(self, job: Dict) -> Tuple[float, bool]:
        """
        Check if experience level is appropriate
        Penalize senior-level positions for students/junior seekers
        """
        title = (job.get('title') or '').lower()
        description = (job.get('description') or '').lower()
        experience_level = (job.get('experience_level') or '').lower()
        
        combined_text = title + ' ' + description + ' ' + experience_level
        
        # Senior indicators
        senior_indicators = [
            'senior', 'confirmé', 'expert', 'lead', 'principal',
            '5+ years', '5 ans', '6 ans', '7 ans', '8 ans', '10 ans',
            '10+ years', '15 years', '15 ans'
        ]
        
        for indicator in senior_indicators:
            if indicator in combined_text:
                return 0.0, False  # Not suitable
        
        # Junior/entry-level indicators (positive)
        junior_indicators = [
            'junior', 'débutant', 'entry level', 'graduate',
            '0-2 years', '1-2 ans', '2-3 ans', 'alternance',
            'stage', 'apprentissage', 'première expérience'
        ]
        
        for indicator in junior_indicators:
            if indicator in combined_text:
                return 1.0, True
        
        # If no clear indicators, neutral score
        return 0.7, True
    
    def _calculate_location_score(self, job: Dict) -> Tuple[float, bool]:
        """Check if location is acceptable"""
        location = (job.get('location') or '').lower()
        
        preferred_locations = [l.lower() for l in self.user_profile.get('locations', {}).get('preferred', [])]
        acceptable_locations = [l.lower() for l in self.user_profile.get('locations', {}).get('acceptable', [])]
        
        # Check preferred locations
        for pref in preferred_locations:
            if pref in location:
                return 0.5, True
        
        # Check acceptable locations
        for acc in acceptable_locations:
            if acc in location:
                return 0.3, True
        
        # Remote work is usually acceptable
        if any(word in location for word in ['remote', 'télétravail', 'full remote', 'hybride']):
            return 0.4, True
        
        return 0.1, False
    
    def _calculate_recency_score(self, job: Dict) -> float:
        """Give bonus points for recent postings"""
        post_date = job.get('post_date')
        
        if not post_date:
            return 0.25  # Neutral if unknown
        
        try:
            if isinstance(post_date, str):
                post_date = datetime.fromisoformat(post_date.replace('Z', '+00:00'))
            
            days_old = (datetime.now() - post_date).days
            
            if days_old <= 1:
                return 0.5  # Posted today
            elif days_old <= 3:
                return 0.4  # Posted within 3 days
            elif days_old <= 7:
                return 0.3  # Posted within a week
            elif days_old <= 14:
                return 0.2  # Posted within 2 weeks
            else:
                return 0.1  # Older posting
                
        except Exception as e:
            logger.warning(f"Error calculating recency score: {e}")
            return 0.25
    
    def _check_exclusions(self, text: str) -> Tuple[float, List[str]]:
        """
        Check for exclusion keywords that indicate the job is not suitable
        Returns penalty score and list of matched exclusions
        """
        matches = []
        penalty = 0.0
        
        for exclude_keyword in self.exclude_keywords:
            if exclude_keyword in text:
                matches.append(exclude_keyword)
                penalty += 2.0  # Heavy penalty for exclusions
        
        return min(5.0, penalty), matches
    
    def get_shortlist(self, min_score: Optional[float] = None, limit: int = 30) -> List[Dict]:
        """Get the current shortlist of jobs for application"""
        min_score = min_score or self.config.get_min_relevance_score()
        return self.db.get_shortlisted_jobs(min_score, limit)
    
    def generate_analysis_report(self) -> Dict:
        """Generate a report of the analysis results"""
        with self.db._get_connection() as conn:
            # Score distribution
            cursor = conn.execute("""
                SELECT 
                    CASE 
                        WHEN relevance_score >= 8 THEN '8-10'
                        WHEN relevance_score >= 6 THEN '6-8'
                        WHEN relevance_score >= 4 THEN '4-6'
                        ELSE '0-4'
                    END as score_range,
                    COUNT(*) as count
                FROM jobs
                WHERE relevance_score IS NOT NULL
                GROUP BY score_range
            """)
            score_distribution = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Top matching skills
            cursor = conn.execute("""
                SELECT match_details FROM jobs 
                WHERE match_details IS NOT NULL
            """)
            all_skill_matches = []
            for row in cursor.fetchall():
                try:
                    details = json.loads(row[0])
                    all_skill_matches.extend(details.get('skill_matches', []))
                except:
                    continue
            
            skill_counts = Counter(all_skill_matches).most_common(10)
            
            return {
                'score_distribution': score_distribution,
                'top_matching_skills': skill_counts,
                'total_analyzed': sum(score_distribution.values())
            }

if __name__ == "__main__":
    agent = AnalysisAgent()
    results = agent.run()
    print(f"Analysis complete: {results}")
    
    # Generate and print report
    report = agent.generate_analysis_report()
    print(f"\nAnalysis Report: {report}")
