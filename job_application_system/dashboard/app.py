"""
Dashboard Flask Application
Web-based dashboard for the job application system
"""
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request, send_from_directory

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import DatabaseManager
from utils.config import get_config
from orchestrator import JobApplicationOrchestrator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
template_dir = Path(__file__).parent / 'templates'
static_dir = Path(__file__).parent / 'static'

app = Flask(__name__, 
            template_folder=str(template_dir),
            static_folder=str(static_dir))

# Initialize database and config
config = get_config()
db = DatabaseManager(config.get_database_path())

# ============== Routes ==============

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory(static_dir, path)

# ============== API Routes ==============

@app.route('/api/dashboard')
def get_dashboard_data():
    """Get all dashboard data"""
    try:
        data = db.get_dashboard_data()
        
        # Get application stats
        app_stats = db.get_application_stats()
        
        # Format response
        response = {
            'total_jobs': data.get('total_jobs', 0),
            'total_applications': data.get('total_applications', 0),
            'pipeline': {
                'scraped': data.get('pipeline', {}).get('scraped', 0),
                'analyzed': data.get('pipeline', {}).get('analyzed', 0),
                'shortlisted': len(data.get('recent_jobs', [])),
                'applied': data.get('pipeline', {}).get('applied', 0),
                'responded': app_stats.get('by_status', {}).get('interview_scheduled', 0) + 
                            app_stats.get('by_status', {}).get('offer_received', 0)
            },
            'recent_jobs': data.get('recent_jobs', []),
            'recent_applications': data.get('recent_applications', []),
            'platform_distribution': data.get('platform_distribution', {}),
            'daily_stats': data.get('daily_stats', []),
            'recent_activity': db.get_recent_activity(20)
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """Get system statistics"""
    try:
        app_stats = db.get_application_stats()
        
        with db._get_connection() as conn:
            # Jobs by status
            cursor = conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
            jobs_by_status = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Total jobs
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            total_jobs = cursor.fetchone()[0]
        
        return jsonify({
            'applications': app_stats,
            'jobs': {
                'total': total_jobs,
                'by_status': jobs_by_status
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs')
def get_jobs():
    """Get jobs list with optional filtering"""
    try:
        status = request.args.get('status')
        platform = request.args.get('platform')
        limit = int(request.args.get('limit', 50))
        
        with db._get_connection() as conn:
            query = "SELECT * FROM jobs WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            if platform:
                query += " AND platform = ?"
                params.append(platform)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            jobs = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(jobs)
        
    except Exception as e:
        logger.error(f"Error getting jobs: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/job/<int:job_id>')
def get_job(job_id):
    """Get single job details"""
    try:
        with db._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            job = cursor.fetchone()
            
            if not job:
                return jsonify({'error': 'Job not found'}), 404
            
            job_dict = dict(job)
            
            # Get associated cover letters
            cursor = conn.execute(
                "SELECT * FROM cover_letters WHERE job_id = ?",
                (job_id,)
            )
            job_dict['cover_letters'] = [dict(row) for row in cursor.fetchall()]
            
            # Get associated applications
            cursor = conn.execute(
                "SELECT * FROM applications WHERE job_id = ?",
                (job_id,)
            )
            job_dict['applications'] = [dict(row) for row in cursor.fetchall()]
            
            return jsonify(job_dict)
            
    except Exception as e:
        logger.error(f"Error getting job: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/applications')
def get_applications():
    """Get applications list"""
    try:
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        
        with db._get_connection() as conn:
            query = """
                SELECT a.*, j.title, j.company, j.platform
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE 1=1
            """
            params = []
            
            if status:
                query += " AND a.status = ?"
                params.append(status)
            
            query += " ORDER BY a.application_date DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            applications = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(applications)
        
    except Exception as e:
        logger.error(f"Error getting applications: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/activity')
def get_activity():
    """Get recent activity log"""
    try:
        limit = int(request.args.get('limit', 50))
        activities = db.get_recent_activity(limit)
        return jsonify(activities)
        
    except Exception as e:
        logger.error(f"Error getting activity: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    """Get or update settings"""
    if request.method == 'GET':
        try:
            settings = db.get_settings()
            return jsonify(settings)
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return jsonify({'error': str(e)}), 500
    
    else:  # POST
        try:
            data = request.json
            db.update_settings(data)
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return jsonify({'error': str(e)}), 500

# ============== Action Routes ==============

@app.route('/api/run-workflow', methods=['POST'])
def run_workflow():
    """Run the full workflow"""
    try:
        data = request.json or {}
        dry_run = data.get('dry_run', True)
        
        orchestrator = JobApplicationOrchestrator()
        results = orchestrator.run_full_workflow(dry_run=dry_run)
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error running workflow: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scrape', methods=['POST'])
def run_scrape():
    """Run scraping only"""
    try:
        orchestrator = JobApplicationOrchestrator()
        results = orchestrator.run_scraping_only()
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error running scrape: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def run_analyze():
    """Run analysis only"""
    try:
        orchestrator = JobApplicationOrchestrator()
        results = orchestrator.run_analysis_only()
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error running analysis: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-letters', methods=['POST'])
def generate_letters():
    """Generate cover letters"""
    try:
        data = request.json or {}
        job_id = data.get('job_id')
        
        orchestrator = JobApplicationOrchestrator()
        results = orchestrator.cover_letter_agent.run(job_id)
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error generating letters: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/apply/<int:job_id>', methods=['POST'])
def apply_to_job(job_id):
    """Apply to a specific job"""
    try:
        with db._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            job = cursor.fetchone()
            
            if not job:
                return jsonify({'error': 'Job not found'}), 404
        
        orchestrator = JobApplicationOrchestrator()
        success = orchestrator.application_agent.apply_to_job(dict(job), dry_run=True)
        
        return jsonify({
            'success': success
        })
        
    except Exception as e:
        logger.error(f"Error applying to job: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/followups')
def get_followups():
    """Get applications needing follow-up"""
    try:
        follow_up_days = config.get('application.follow_up_days', 7)
        applications = db.get_applications_needing_followup(follow_up_days)
        return jsonify(applications)
        
    except Exception as e:
        logger.error(f"Error getting followups: {e}")
        return jsonify({'error': str(e)}), 500

# ============== Report Routes ==============

@app.route('/api/report/daily')
def daily_report():
    """Generate daily report"""
    try:
        orchestrator = JobApplicationOrchestrator()
        report = orchestrator.generate_daily_report()
        return jsonify(report)
        
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(
        host=config.get('dashboard.host', '127.0.0.1'),
        port=config.get('dashboard.port', 5000),
        debug=config.get('dashboard.debug', False)
    )
