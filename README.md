# Job Application System

Multi-agent job application system with AI-powered scraping, analysis, and cover letter generation.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/samidardar/job-application-system)

## Features

- **4 AI Agents:** Scraping, Analysis, Cover Letter, Application
- **Multi-platform:** LinkedIn, Indeed, Welcome to the Jungle
- **Anti-detection:** Random delays, user-agent rotation
- **Dashboard:** Real-time job tracking
- **Auto-apply:** With dry-run safety mode

## Quick Start

### Deploy to Render (Free)

1. Click the **"Deploy to Render"** button above
2. Create a free Render account
3. The service will auto-deploy

### Local Development

```bash
git clone https://github.com/samidardar/job-application-system.git
cd job-application-system
pip install -r requirements.txt
python unified_dashboard.py
```

## Configuration

Edit `job_application_system/config/config.yaml`:
- User profile (name, email, skills)
- Job search filters
- Platform settings
- Application limits

## Dashboard

Access the web dashboard at `/` after deployment.

## License

MIT
