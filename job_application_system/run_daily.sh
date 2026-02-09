#!/bin/bash
#
# Job Application System - Daily Run Script
# Run this script daily to execute the full workflow
#

set -e  # Exit on error

# Configuration
PROJECT_DIR="/data/.openclaw/workspace/job_application_system"
PYTHON="$PROJECT_DIR/venv/bin/python"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$PROJECT_DIR/logs/daily_${TIMESTAMP}.log"

# Create logs directory if not exists
mkdir -p "$PROJECT_DIR/logs"

# Change to project directory
cd "$PROJECT_DIR"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========================================"
log "Job Application System - Daily Workflow"
log "Started at $(date)"
log "========================================"
log ""

# Step 1: Scraping
log "[STEP 1/4] Starting job scraping..."
if $PYTHON orchestrator.py scrape >> "$LOG_FILE" 2>&1; then
    log "✓ Scraping completed successfully"
else
    log "✗ Scraping failed"
fi
log ""

# Step 2: Analysis
log "[STEP 2/4] Starting job analysis..."
if $PYTHON orchestrator.py analyze >> "$LOG_FILE" 2>&1; then
    log "✓ Analysis completed successfully"
else
    log "✗ Analysis failed"
fi
log ""

# Step 3: Cover Letter Generation
log "[STEP 3/4] Generating cover letters..."
if $PYTHON orchestrator.py letters >> "$LOG_FILE" 2>&1; then
    log "✓ Cover letter generation completed successfully"
else
    log "✗ Cover letter generation failed"
fi
log ""

# Step 4: Applications (DRY-RUN MODE - Safe)
log "[STEP 4/4] Processing applications (DRY-RUN mode)..."
if $PYTHON orchestrator.py apply >> "$LOG_FILE" 2>&1; then
    log "✓ Application processing completed successfully"
else
    log "✗ Application processing failed"
fi
log ""

# Generate daily report
log "Generating daily report..."
$PYTHON orchestrator.py report >> "$LOG_FILE" 2>&1

log ""
log "========================================"
log "Workflow completed at $(date)"
log "Log file: $LOG_FILE"
log "========================================"

# Optional: Send notification (uncomment and configure as needed)
# python -c "from utils.notifications import send_notification; send_notification('Daily workflow completed')"

exit 0
