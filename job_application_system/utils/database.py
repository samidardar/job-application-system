"""
Database Manager - Handles all database operations for the job application system
"""
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages SQLite database operations for the job application system"""
    
    def __init__(self, db_path: str = "database/job_application.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database with schema"""
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                schema = f.read()
            
            with self._get_connection() as conn:
                conn.executescript(schema)
            logger.info("Database initialized successfully")
    
    # ==================== Job Operations ====================
    
    def insert_job(self, job_data: Dict[str, Any]) -> int:
        """Insert a new job listing"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO jobs 
                (job_id, title, company, company_size, location, description, 
                 requirements, salary_range, job_type, experience_level, 
                 post_date, application_url, platform, raw_data, status, 
                 relevance_score, match_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_data.get('job_id'),
                job_data.get('title'),
                job_data.get('company'),
                job_data.get('company_size'),
                job_data.get('location'),
                job_data.get('description'),
                job_data.get('requirements'),
                job_data.get('salary_range'),
                job_data.get('job_type'),
                job_data.get('experience_level'),
                job_data.get('post_date'),
                job_data.get('application_url'),
                job_data.get('platform'),
                json.dumps(job_data.get('raw_data', {})),
                job_data.get('status', 'scraped'),
                job_data.get('relevance_score'),
                json.dumps(job_data.get('match_details', {}))
            ))
            return cursor.lastrowid
    
    def update_job_status(self, job_id: int, status: str, relevance_score: Optional[float] = None):
        """Update job status and optionally relevance score"""
        with self._get_connection() as conn:
            if relevance_score is not None:
                conn.execute("""
                    UPDATE jobs SET status = ?, relevance_score = ?, updated_at = ?
                    WHERE id = ?
                """, (status, relevance_score, datetime.now(), job_id))
            else:
                conn.execute("""
                    UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?
                """, (status, datetime.now(), job_id))
    
    def get_jobs_by_status(self, status: str, limit: Optional[int] = None) -> List[Dict]:
        """Get jobs by status"""
        with self._get_connection() as conn:
            query = "SELECT * FROM jobs WHERE status = ? ORDER BY post_date DESC"
            params = [status]
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_jobs_for_analysis(self, limit: int = 100) -> List[Dict]:
        """Get jobs that need analysis (scraped but not analyzed)"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM jobs 
                WHERE status = 'scraped' 
                AND (relevance_score IS NULL OR relevance_score = 0)
                ORDER BY post_date DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_shortlisted_jobs(self, min_score: float = 6.0, limit: int = 30) -> List[Dict]:
        """Get shortlisted jobs for application"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM jobs 
                WHERE status = 'analyzed' 
                AND relevance_score >= ?
                AND status != 'applied'
                ORDER BY relevance_score DESC, post_date DESC
                LIMIT ?
            """, (min_score, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def job_exists(self, job_id: str, platform: str) -> bool:
        """Check if a job already exists"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM jobs WHERE job_id = ? AND platform = ?",
                (job_id, platform)
            )
            return cursor.fetchone() is not None
    
    # ==================== Application Operations ====================
    
    def insert_application(self, job_id: int, application_data: Dict) -> int:
        """Record a new application"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO applications 
                (job_id, status, cover_letter_path, resume_path, 
                 application_method, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                application_data.get('status', 'pending'),
                application_data.get('cover_letter_path'),
                application_data.get('resume_path'),
                application_data.get('application_method'),
                application_data.get('notes')
            ))
            
            # Update job status
            conn.execute(
                "UPDATE jobs SET status = 'applied', updated_at = ? WHERE id = ?",
                (datetime.now(), job_id)
            )
            
            return cursor.lastrowid
    
    def update_application_status(self, application_id: int, status: str, notes: Optional[str] = None):
        """Update application status"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE applications 
                SET status = ?, notes = COALESCE(?, notes), 
                    response_date = CASE WHEN ? IN ('rejected', 'interview_scheduled', 'offer_received') THEN ? ELSE response_date END
                WHERE id = ?
            """, (status, notes, status, datetime.now(), application_id))
    
    def get_applications_needing_followup(self, days: int = 7) -> List[Dict]:
        """Get applications needing follow-up"""
        follow_up_date = datetime.now() - timedelta(days=days)
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT a.*, j.title, j.company, j.platform
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE a.status = 'submitted'
                AND a.application_date <= ?
                AND (a.follow_up_sent = 0 OR a.follow_up_sent IS NULL)
            """, (follow_up_date,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_application_stats(self) -> Dict:
        """Get application statistics"""
        with self._get_connection() as conn:
            stats = {}
            
            # Total applications
            cursor = conn.execute("SELECT COUNT(*) FROM applications")
            stats['total_applications'] = cursor.fetchone()[0]
            
            # Applications by status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count 
                FROM applications 
                GROUP BY status
            """)
            stats['by_status'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Today's applications
            cursor = conn.execute("""
                SELECT COUNT(*) FROM applications 
                WHERE DATE(application_date) = DATE('now')
            """)
            stats['today_applications'] = cursor.fetchone()[0]
            
            # Response rate
            cursor = conn.execute("""
                SELECT COUNT(*) FROM applications 
                WHERE response_date IS NOT NULL
            """)
            responded = cursor.fetchone()[0]
            stats['response_rate'] = (responded / stats['total_applications'] * 100) if stats['total_applications'] > 0 else 0
            
            return stats
    
    # ==================== Activity Log ====================
    
    def log_activity(self, agent_name: str, action: str, status: str, details: Optional[str] = None):
        """Log agent activity"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO activity_log (agent_name, action, status, details)
                VALUES (?, ?, ?, ?)
            """, (agent_name, action, status, details))
    
    def get_recent_activity(self, limit: int = 50) -> List[Dict]:
        """Get recent activity log"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM activity_log 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== Platform Stats ====================
    
    def update_platform_stats(self, platform: str, field: str, increment: int = 1):
        """Update platform statistics for today"""
        today = datetime.now().date()
        with self._get_connection() as conn:
            # Try to update existing record
            cursor = conn.execute(f"""
                UPDATE platform_stats 
                SET {field} = {field} + ?
                WHERE date = ? AND platform = ?
            """, (increment, today, platform))
            
            # If no record exists, insert one
            if cursor.rowcount == 0:
                conn.execute(f"""
                    INSERT INTO platform_stats (date, platform, {field})
                    VALUES (?, ?, ?)
                """, (today, platform, increment))
    
    def get_platform_stats(self, days: int = 30) -> List[Dict]:
        """Get platform statistics for the last N days"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM platform_stats 
                WHERE date >= DATE('now', '-{} days')
                ORDER BY date DESC, platform
            """.format(days))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== Settings ====================
    
    def get_settings(self) -> Dict:
        """Get system settings"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM settings WHERE id = 1")
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    def update_settings(self, settings: Dict):
        """Update system settings"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE settings SET
                    daily_application_limit = ?,
                    min_relevance_score = ?,
                    updated_at = ?
                WHERE id = 1
            """, (
                settings.get('daily_application_limit', 30),
                settings.get('min_relevance_score', 6.0),
                datetime.now()
            ))
    
    # ==================== Cover Letters ====================
    
    def insert_cover_letter(self, job_id: int, file_path: str, language: str, content: str, keywords: List[str]):
        """Store generated cover letter"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO cover_letters (job_id, file_path, language, content, keywords_used)
                VALUES (?, ?, ?, ?, ?)
            """, (job_id, file_path, language, content, json.dumps(keywords)))
    
    # ==================== Dashboard Data ====================
    
    def get_dashboard_data(self) -> Dict:
        """Get all data needed for the dashboard"""
        with self._get_connection() as conn:
            data = {}
            
            # Pipeline counts
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count FROM jobs GROUP BY status
            """)
            data['pipeline'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Total counts
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            data['total_jobs'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM applications")
            data['total_applications'] = cursor.fetchone()[0]
            
            # Recent jobs
            cursor = conn.execute("""
                SELECT * FROM jobs 
                ORDER BY created_at DESC 
                LIMIT 10
            """)
            data['recent_jobs'] = [dict(row) for row in cursor.fetchall()]
            
            # Recent applications
            cursor = conn.execute("""
                SELECT a.*, j.title, j.company 
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                ORDER BY a.application_date DESC
                LIMIT 10
            """)
            data['recent_applications'] = [dict(row) for row in cursor.fetchall()]
            
            # Platform distribution
            cursor = conn.execute("""
                SELECT platform, COUNT(*) as count 
                FROM jobs 
                GROUP BY platform
            """)
            data['platform_distribution'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Daily stats (last 7 days)
            cursor = conn.execute("""
                SELECT date, SUM(jobs_scraped) as scraped, 
                       SUM(applications_sent) as applied
                FROM platform_stats
                WHERE date >= DATE('now', '-7 days')
                GROUP BY date
                ORDER BY date
            """)
            data['daily_stats'] = [dict(row) for row in cursor.fetchall()]
            
            return data
