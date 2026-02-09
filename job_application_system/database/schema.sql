-- Job Application System Database Schema
-- SQLite database for multi-agent job application system

-- Jobs table: Stores scraped job listings
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,  -- Platform-specific job ID
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    company_size TEXT,
    location TEXT,
    description TEXT,
    requirements TEXT,
    salary_range TEXT,
    job_type TEXT,  -- alternance, stage, CDI, CDD
    experience_level TEXT,
    post_date DATETIME,
    application_url TEXT,
    platform TEXT NOT NULL,  -- linkedin, indeed, welcometothejungle
    raw_data TEXT,  -- JSON blob of raw scraped data
    status TEXT DEFAULT 'scraped',  -- scraped, analyzed, shortlisted, applied, rejected, interview, offer
    relevance_score REAL,
    match_details TEXT,  -- JSON blob with detailed match scores
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Applications table: Tracks applications sent
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    application_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending',  -- pending, submitted, viewed, rejected, interview_scheduled, offer_received
    cover_letter_path TEXT,
    resume_path TEXT,
    application_method TEXT,  -- linkedin_easy_apply, company_page, indeed, wttj
    follow_up_date DATETIME,
    follow_up_sent BOOLEAN DEFAULT 0,
    notes TEXT,
    response_date DATETIME,
    response_type TEXT,  -- rejection, interview_request, offer
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- Cover Letters table: Stores generated cover letters
CREATE TABLE IF NOT EXISTS cover_letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT,  -- fr, en
    content TEXT,
    keywords_used TEXT,  -- JSON array
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- Activity Log table: Tracks all system activities
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,  -- success, error, warning
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Platform Stats table: Daily statistics per platform
CREATE TABLE IF NOT EXISTS platform_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    platform TEXT NOT NULL,
    jobs_scraped INTEGER DEFAULT 0,
    jobs_analyzed INTEGER DEFAULT 0,
    jobs_shortlisted INTEGER DEFAULT 0,
    applications_sent INTEGER DEFAULT 0,
    responses_received INTEGER DEFAULT 0,
    UNIQUE(date, platform)
);

-- Company table: Track companies for follow-up management
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    website TEXT,
    linkedin_url TEXT,
    industry TEXT,
    size TEXT,
    location TEXT,
    notes TEXT,
    priority_score INTEGER DEFAULT 5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- User Profile table: Sami's profile data
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    portfolio_url TEXT,
    skills TEXT,  -- JSON array
    experience TEXT,  -- JSON object
    education TEXT,  -- JSON object
    preferred_locations TEXT,  -- JSON array
    preferred_roles TEXT,  -- JSON array
    languages TEXT,  -- JSON array
    cv_path TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Settings table: System configuration
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    daily_application_limit INTEGER DEFAULT 30,
    min_relevance_score REAL DEFAULT 6.0,
    preferred_platforms TEXT,  -- JSON array
    auto_apply_enabled BOOLEAN DEFAULT 0,
    follow_up_days INTEGER DEFAULT 7,
    notification_email TEXT,
    browser_headless BOOLEAN DEFAULT 1,
    delay_min_seconds INTEGER DEFAULT 3,
    delay_max_seconds INTEGER DEFAULT 8,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Scraping Sessions table: Track scraping sessions for anti-detection
CREATE TABLE IF NOT EXISTS scraping_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    session_start DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_end DATETIME,
    requests_count INTEGER DEFAULT 0,
    user_agent TEXT,
    proxy_used TEXT,
    status TEXT DEFAULT 'active'  -- active, completed, failed, rate_limited
);

-- Insert default user profile
INSERT OR IGNORE INTO user_profile (id, full_name) VALUES (1, 'Sami');

-- Insert default settings
INSERT OR IGNORE INTO settings (id) VALUES (1);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_platform ON jobs(platform);
CREATE INDEX IF NOT EXISTS idx_jobs_relevance ON jobs(relevance_score);
CREATE INDEX IF NOT EXISTS idx_jobs_post_date ON jobs(post_date);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_follow_up ON applications(follow_up_date);
CREATE INDEX IF NOT EXISTS idx_activity_log_agent ON activity_log(agent_name);
CREATE INDEX IF NOT EXISTS idx_activity_log_date ON activity_log(created_at);
