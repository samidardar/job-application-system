#!/usr/bin/env python3
"""
Unified Dashboard - Job System + File Browser for Deployment
"""
import os
import sys
import json
import logging
import mimetypes
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template_string, send_from_directory, request, jsonify

# Setup paths
WORKSPACE_DIR = Path("/data/.openclaw/workspace")
JOB_SYSTEM_DIR = WORKSPACE_DIR / "job_application_system"

# Add job system to path
sys.path.insert(0, str(JOB_SYSTEM_DIR))

# Import job system modules
try:
    from utils.database import DatabaseManager
    from utils.config import get_config
    from orchestrator import JobApplicationOrchestrator
    JOB_SYSTEM_AVAILABLE = True
except ImportError:
    JOB_SYSTEM_AVAILABLE = False

# Setup Flask app
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize job system if available
if JOB_SYSTEM_AVAILABLE:
    try:
        config = get_config()
        db = DatabaseManager(config.get_database_path())
    except:
        db = None
else:
    db = None

# ============== UNIFIED HTML TEMPLATE ==============
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 Workspace Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117; 
            color: #c9d1d9;
            line-height: 1.6;
        }
        .header { 
            background: linear-gradient(135deg, #1f6feb 0%, #58a6ff 100%);
            padding: 1.5rem 2rem;
            color: white;
        }
        .header h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
        .nav-tabs {
            display: flex;
            background: #161b22;
            border-bottom: 1px solid #30363d;
            padding: 0 2rem;
        }
        .nav-tab {
            padding: 1rem 1.5rem;
            color: #8b949e;
            text-decoration: none;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
            cursor: pointer;
        }
        .nav-tab:hover, .nav-tab.active {
            color: #58a6ff;
            border-bottom-color: #58a6ff;
        }
        .container { padding: 2rem; max-width: 1400px; margin: 0 auto; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        /* Job Dashboard Styles */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .stat-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 1.5rem;
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        .stat-icon { font-size: 2rem; }
        .stat-content h3 { font-size: 2rem; color: #58a6ff; }
        .stat-content p { color: #8b949e; }
        
        .pipeline {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #161b22;
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
            gap: 1rem;
        }
        .pipeline-step {
            text-align: center;
            flex: 1;
            min-width: 100px;
        }
        .step-icon { font-size: 2rem; margin-bottom: 0.5rem; }
        .step-count { font-size: 1.5rem; font-weight: bold; color: #58a6ff; }
        .pipeline-arrow { font-size: 1.5rem; color: #30363d; }
        
        .btn {
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.2s;
        }
        .btn-primary { background: #238636; color: white; }
        .btn-primary:hover { background: #2ea043; }
        .btn-secondary { background: #1f6feb; color: white; }
        .btn-secondary:hover { background: #388bfd; }
        
        /* File Browser Styles */
        .file-list { list-style: none; }
        .file-item { 
            display: flex; 
            align-items: center; 
            padding: 0.75rem 1rem;
            border-bottom: 1px solid #21262d;
            transition: background 0.2s;
        }
        .file-item:hover { background: #161b22; }
        .file-icon { width: 24px; text-align: center; margin-right: 1rem; font-size: 1.2rem; }
        .file-name { 
            flex: 1; 
            color: #c9d1d9;
            text-decoration: none;
        }
        .file-name:hover { color: #58a6ff; }
        .file-name.folder { color: #58a6ff; font-weight: 500; }
        .file-meta { color: #8b949e; font-size: 0.85rem; font-family: monospace; }
        .breadcrumb { padding: 1rem 0; color: #8b949e; }
        .breadcrumb a { color: #58a6ff; text-decoration: none; margin: 0 0.5rem; }
        
        .preview-panel {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 1rem;
            margin-top: 1rem;
            max-height: 500px;
            overflow: auto;
        }
        .preview-content {
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.85rem;
            white-space: pre-wrap;
            word-break: break-all;
        }
        
        h2 { margin-bottom: 1rem; color: #c9d1d9; }
        .section { margin-bottom: 2rem; }
        
        /* Deployment info */
        .deploy-info {
            background: #238636;
            color: white;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Workspace Dashboard</h1>
        <p>Job Application System + File Browser</p>
    </div>
    
    <div class="nav-tabs">
        <div class="nav-tab active" onclick="showTab('jobs')">📊 Job System</div>
        <div class="nav-tab" onclick="showTab('files')">📁 Files</div>
        <div class="nav-tab" onclick="showTab('deploy')">🚀 Deploy</div>
    </div>
    
    <div class="container">
        <!-- Jobs Tab -->
        <div id="jobs" class="tab-content active">
            <div class="section">
                <h2>📊 Statistics</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-icon">📋</div>
                        <div class="stat-content">
                            <h3 id="totalJobs">{{ stats.total_jobs }}</h3>
                            <p>Jobs Scraped</p>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">✉️</div>
                        <div class="stat-content">
                            <h3 id="totalApps">{{ stats.total_apps }}</h3>
                            <p>Applications</p>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">⭐</div>
                        <div class="stat-content">
                            <h3 id="shortlisted">{{ stats.shortlisted }}</h3>
                            <p>Shortlisted</p>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">📈</div>
                        <div class="stat-content">
                            <h3 id="responseRate">{{ stats.response_rate }}%</h3>
                            <p>Response Rate</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>🔄 Pipeline</h2>
                <div class="pipeline">
                    <div class="pipeline-step">
                        <div class="step-icon">🔍</div>
                        <div class="step-count">{{ pipeline.scraped }}</div>
                        <div>Scraped</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step">
                        <div class="step-icon">🤖</div>
                        <div class="step-count">{{ pipeline.analyzed }}</div>
                        <div>Analyzed</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step">
                        <div class="step-icon">✅</div>
                        <div class="step-count">{{ pipeline.shortlisted }}</div>
                        <div>Selected</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step">
                        <div class="step-icon">📤</div>
                        <div class="step-count">{{ pipeline.applied }}</div>
                        <div>Applied</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <button class="btn btn-primary" onclick="runWorkflow()">▶ Run Workflow</button>
                <button class="btn btn-secondary" onclick="location.reload()">↻ Refresh</button>
                <span id="status"></span>
            </div>
        </div>
        
        <!-- Files Tab -->
        <div id="files" class="tab-content">
            <h2>📁 File Browser</h2>
            <div class="breadcrumb">
                <a href="/files">🏠 Home</a>
                {% for part in breadcrumbs %}
                    / <a href="/files/{{ part.path }}">{{ part.name }}</a>
                {% endfor %}
            </div>
            <ul class="file-list">
                {% if path %}
                <li class="file-item">
                    <span class="file-icon">⬆️</span>
                    <a href="/files/{{ parent }}" class="file-name folder">..</a>
                </li>
                {% endif %}
                {% for item in files %}
                <li class="file-item">
                    <span class="file-icon">{{ item.icon }}</span>
                    {% if item.is_dir %}
                        <a href="/files/{{ item.path }}" class="file-name folder">{{ item.name }}</a>
                    {% else %}
                        <a href="/view/{{ item.path }}" class="file-name">{{ item.name }}</a>
                    {% endif %}
                    <span class="file-meta" style="margin-left: auto;">{{ item.size }}</span>
                </li>
                {% endfor %}
            </ul>
            {% if preview %}
            <div class="preview-panel">
                <h3>👁️ {{ preview_name }}</h3>
                <pre class="preview-content">{{ preview }}</pre>
            </div>
            {% endif %}
        </div>
        
        <!-- Deploy Tab -->
        <div id="deploy" class="tab-content">
            <h2>🚀 Deploy to Render.com (Free)</h2>
            
            <div class="deploy-info">
                <strong>✅ Ready for deployment!</strong>
            </div>
            
            <div class="section">
                <h3>Steps:</h3>
                <ol style="margin-left: 2rem; line-height: 2;">
                    <li>Go to <a href="https://render.com" target="_blank" style="color: #58a6ff;">render.com</a> and sign up</li>
                    <li>Click "New +" → "Web Service"</li>
                    <li>Connect your GitHub repo OR use "Deploy from image"</li>
                    <li>Set these values:
                        <ul style="margin-left: 2rem; margin-top: 0.5rem;">
                            <li><strong>Name:</strong> job-system</li>
                            <li><strong>Runtime:</strong> Python 3</li>
                            <li><strong>Build Command:</strong> <code>pip install -r requirements.txt</code></li>
                            <li><strong>Start Command:</strong> <code>gunicorn wsgi:app</code></li>
                        </ul>
                    </li>
                    <li>Click "Create Web Service" (Free tier)</li>
                </ol>
            </div>
            
            <div class="section">
                <h3>Files created for deployment:</h3>
                <ul style="margin-left: 2rem; line-height: 2;">
                    <li>✅ <code>wsgi.py</code> - Entry point</li>
                    <li>✅ <code>requirements.txt</code> - Dependencies</li>
                    <li>✅ <code>render.yaml</code> - Render config</li>
                </ul>
            </div>
        </div>
    </div>
    
    <script>
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
        }
        
        function runWorkflow() {
            document.getElementById('status').innerHTML = '⏳ Running...';
            fetch('/api/run', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    document.getElementById('status').innerHTML = '✅ Done!';
                    setTimeout(() => location.reload(), 1000);
                })
                .catch(e => {
                    document.getElementById('status').innerHTML = '❌ Error: ' + e;
                });
        }
    </script>
</body>
</html>
'''

# ============== HELPER FUNCTIONS ==============

def get_icon(name, is_dir):
    if is_dir:
        return '📁'
    ext = Path(name).suffix.lower()
    icons = {
        '.py': '🐍', '.js': '📜', '.ts': '🔷', '.html': '🌐', '.css': '🎨',
        '.json': '📋', '.yaml': '📋', '.yml': '📋', '.md': '📝', '.txt': '📄',
        '.sql': '🗄️', '.db': '🗄️', '.log': '📋', '.sh': '⚡',
    }
    return icons.get(ext, '📄')

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != 'B' else f"{size} B"
        size /= 1024
    return f"{size:.1f} TB"

def get_files(path=''):
    full_path = WORKSPACE_DIR / path if path else WORKSPACE_DIR
    if not full_path.exists():
        return [], '', []
    
    items = []
    try:
        for entry in sorted(full_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            stat = entry.stat()
            is_dir = entry.is_dir()
            rel_path = str(entry.relative_to(WORKSPACE_DIR))
            
            items.append({
                'name': entry.name,
                'path': rel_path,
                'is_dir': is_dir,
                'icon': get_icon(entry.name, is_dir),
                'size': format_size(stat.st_size) if not is_dir else '--'
            })
    except:
        pass
    
    # Build breadcrumbs
    breadcrumbs = []
    current = ''
    for part in Path(path).parts:
        if part == '.' or not part:
            continue
        current = f"{current}/{part}" if current else part
        breadcrumbs.append({'name': part, 'path': current})
    
    parent = str(Path(path).parent) if path and path != '.' else ''
    
    return items, parent, breadcrumbs

def get_stats():
    if not db:
        return {'total_jobs': 0, 'total_apps': 0, 'shortlisted': 0, 'response_rate': 0}
    
    try:
        import sqlite3
        conn = sqlite3.connect(str(JOB_SYSTEM_DIR / 'database/job_application.db'))
        cursor = conn.cursor()
        
        total_jobs = cursor.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        total_apps = cursor.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        shortlisted = cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'shortlisted'").fetchone()[0]
        responses = cursor.execute("SELECT COUNT(*) FROM applications WHERE status IN ('interview', 'offer', 'rejected')").fetchone()[0]
        
        conn.close()
        
        response_rate = round((responses / total_apps * 100), 1) if total_apps > 0 else 0
        
        return {
            'total_jobs': total_jobs,
            'total_apps': total_apps,
            'shortlisted': shortlisted,
            'response_rate': response_rate
        }
    except:
        return {'total_jobs': 0, 'total_apps': 0, 'shortlisted': 0, 'response_rate': 0}

def get_pipeline():
    if not db:
        return {'scraped': 0, 'analyzed': 0, 'shortlisted': 0, 'applied': 0}
    
    try:
        import sqlite3
        conn = sqlite3.connect(str(JOB_SYSTEM_DIR / 'database/job_application.db'))
        cursor = conn.cursor()
        
        return {
            'scraped': cursor.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            'analyzed': cursor.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('analyzed', 'shortlisted', 'applied')").fetchone()[0],
            'shortlisted': cursor.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('shortlisted', 'applied')").fetchone()[0],
            'applied': cursor.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        }
    except:
        return {'scraped': 0, 'analyzed': 0, 'shortlisted': 0, 'applied': 0}

# ============== ROUTES ==============

@app.route('/')
def index():
    stats = get_stats()
    pipeline = get_pipeline()
    files, parent, breadcrumbs = get_files('')
    
    return render_template_string(DASHBOARD_HTML,
        stats=stats,
        pipeline=pipeline,
        files=files,
        parent=parent,
        breadcrumbs=breadcrumbs,
        path='',
        preview=None,
        preview_name=None
    )

@app.route('/files/')
@app.route('/files/<path:path>')
def files(path=''):
    stats = get_stats()
    pipeline = get_pipeline()
    files, parent, breadcrumbs = get_files(path)
    
    return render_template_string(DASHBOARD_HTML,
        stats=stats,
        pipeline=pipeline,
        files=files,
        parent=parent,
        breadcrumbs=breadcrumbs,
        path=path,
        preview=None,
        preview_name=None
    )

@app.route('/view/<path:path>')
def view(path):
    full_path = WORKSPACE_DIR / path
    if not full_path.exists() or not full_path.is_file():
        return "File not found", 404
    
    preview = None
    try:
        size = full_path.stat().st_size
        if size < 100000:  # Max 100KB
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                preview = f.read()
        else:
            preview = f"[File too large: {format_size(size)}]"
    except:
        preview = "[Cannot preview this file]"
    
    stats = get_stats()
    pipeline = get_pipeline()
    files, parent, breadcrumbs = get_files(str(full_path.parent.relative_to(WORKSPACE_DIR)) if full_path.parent != WORKSPACE_DIR else '')
    
    return render_template_string(DASHBOARD_HTML,
        stats=stats,
        pipeline=pipeline,
        files=files,
        parent=parent,
        breadcrumbs=breadcrumbs,
        path=str(full_path.parent.relative_to(WORKSPACE_DIR)) if full_path.parent != WORKSPACE_DIR else '',
        preview=preview,
        preview_name=full_path.name
    )

@app.route('/api/run', methods=['POST'])
def run_workflow():
    """Trigger workflow run"""
    if not JOB_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Job system not available'}), 500
    
    try:
        orchestrator = JobApplicationOrchestrator()
        results = orchestrator.run_full_workflow(dry_run=True)
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        logger.error(f"Workflow error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())

# ============== MAIN ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
