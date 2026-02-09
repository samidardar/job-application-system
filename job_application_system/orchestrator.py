"""
Main Orchestrator - Coordinates all agents for the job application system
"""
import logging
import argparse
from datetime import datetime
from typing import Dict, Optional

from utils.database import DatabaseManager
from utils.config import get_config
from utils.logging_utils import setup_logging
from agents.scraping_agent import ScrapingAgent
from agents.analysis_agent import AnalysisAgent
from agents.cover_letter_agent import CoverLetterAgent
from agents.application_agent import ApplicationAgent

logger = logging.getLogger(__name__)

class JobApplicationOrchestrator:
    """Orchestrates the entire job application workflow"""
    
    def __init__(self):
        self.config = get_config()
        self.db = DatabaseManager(self.config.get_database_path())
        
        # Initialize agents
        self.scraping_agent = ScrapingAgent(self.db)
        self.analysis_agent = AnalysisAgent(self.db)
        self.cover_letter_agent = CoverLetterAgent(self.db)
        self.application_agent = ApplicationAgent(self.db)
    
    def run_full_workflow(self, dry_run: bool = True) -> Dict:
        """Run the complete workflow: scrape → analyze → generate → apply"""
        logger.info("="*60)
        logger.info("STARTING FULL WORKFLOW")
        logger.info("="*60)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'scraping': {},
            'analysis': {},
            'cover_letters': {},
            'applications': {}
        }
        
        # Step 1: Scrape jobs
        logger.info("\n[STEP 1/4] Scraping jobs...")
        scraping_results = self.scraping_agent.run()
        results['scraping'] = scraping_results
        logger.info(f"Scraping complete: {scraping_results}")
        
        # Step 2: Analyze jobs
        logger.info("\n[STEP 2/4] Analyzing jobs...")
        analysis_results = self.analysis_agent.run()
        results['analysis'] = analysis_results
        logger.info(f"Analysis complete: {analysis_results}")
        
        # Step 3: Generate cover letters
        logger.info("\n[STEP 3/4] Generating cover letters...")
        cover_letter_results = self.cover_letter_agent.run()
        results['cover_letters'] = cover_letter_results
        logger.info(f"Cover letter generation complete: {cover_letter_results}")
        
        # Step 4: Apply to jobs
        logger.info("\n[STEP 4/4] Submitting applications...")
        application_results = self.application_agent.run(dry_run=dry_run)
        results['applications'] = application_results
        logger.info(f"Application submission complete: {application_results}")
        
        logger.info("\n" + "="*60)
        logger.info("FULL WORKFLOW COMPLETE")
        logger.info("="*60)
        
        return results
    
    def run_scraping_only(self) -> Dict:
        """Run only the scraping agent"""
        logger.info("Running scraping agent only...")
        return self.scraping_agent.run()
    
    def run_analysis_only(self) -> Dict:
        """Run only the analysis agent"""
        logger.info("Running analysis agent only...")
        return self.analysis_agent.run()
    
    def run_cover_letters_only(self) -> Dict:
        """Run only the cover letter generation agent"""
        logger.info("Running cover letter agent only...")
        return self.cover_letter_agent.run()
    
    def run_applications_only(self, dry_run: bool = True) -> Dict:
        """Run only the application agent"""
        logger.info("Running application agent only...")
        return self.application_agent.run(dry_run=dry_run)
    
    def generate_daily_report(self) -> Dict:
        """Generate a daily activity report"""
        logger.info("Generating daily report...")
        
        # Get application stats
        app_stats = self.db.get_application_stats()
        
        # Get recent activity
        recent_activity = self.db.get_recent_activity(20)
        
        # Get platform stats
        platform_stats = self.db.get_platform_stats(7)
        
        # Get shortlist
        shortlist = self.db.get_shortlisted_jobs(
            self.config.get_min_relevance_score(),
            limit=10
        )
        
        report = {
            'date': datetime.now().isoformat(),
            'summary': {
                'total_jobs_in_system': self._get_total_jobs(),
                'total_applications_sent': app_stats.get('total_applications', 0),
                'todays_applications': app_stats.get('today_applications', 0),
                'response_rate': f"{app_stats.get('response_rate', 0):.1f}%",
            },
            'pipeline': {
                'scraped': len(self.db.get_jobs_by_status('scraped')),
                'analyzed': len(self.db.get_jobs_by_status('analyzed')),
                'shortlisted': len(shortlist),
                'applied': len(self.db.get_jobs_by_status('applied')),
            },
            'top_opportunities': [
                {
                    'title': job['title'],
                    'company': job['company'],
                    'score': job['relevance_score'],
                    'platform': job['platform']
                }
                for job in shortlist[:5]
            ],
            'recent_activity': [
                {
                    'agent': act['agent_name'],
                    'action': act['action'],
                    'status': act['status'],
                    'time': act['created_at']
                }
                for act in recent_activity[:10]
            ]
        }
        
        return report
    
    def _get_total_jobs(self) -> int:
        """Get total number of jobs in the system"""
        with self.db._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            return cursor.fetchone()[0]

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Job Application System')
    parser.add_argument(
        'command',
        choices=['full', 'scrape', 'analyze', 'letters', 'apply', 'report'],
        help='Command to run'
    )
    parser.add_argument(
        '--no-dry-run',
        action='store_true',
        help='Actually submit applications (default is dry run)'
    )
    parser.add_argument(
        '--config',
        default='config/config.yaml',
        help='Path to configuration file'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(
        level='INFO',
        log_file='logs/system.log',
        log_to_console=True
    )
    
    # Initialize orchestrator
    orchestrator = JobApplicationOrchestrator()
    
    # Execute command
    dry_run = not args.no_dry_run
    
    if args.command == 'full':
        results = orchestrator.run_full_workflow(dry_run=dry_run)
        print(f"\nWorkflow Results:\n{results}")
    
    elif args.command == 'scrape':
        results = orchestrator.run_scraping_only()
        print(f"\nScraping Results:\n{results}")
    
    elif args.command == 'analyze':
        results = orchestrator.run_analysis_only()
        print(f"\nAnalysis Results:\n{results}")
    
    elif args.command == 'letters':
        results = orchestrator.run_cover_letters_only()
        print(f"\nCover Letter Results:\n{results}")
    
    elif args.command == 'apply':
        results = orchestrator.run_applications_only(dry_run=dry_run)
        print(f"\nApplication Results:\n{results}")
    
    elif args.command == 'report':
        report = orchestrator.generate_daily_report()
        import json
        print(f"\nDaily Report:\n{json.dumps(report, indent=2, default=str)}")

if __name__ == "__main__":
    main()
