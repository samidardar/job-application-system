/**
 * Job Application System - Dashboard JavaScript
 */

// API Base URL
const API_BASE = '/api';

// Chart instances
let activityChart = null;
let platformChart = null;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeDashboard();
    setupEventListeners();
    loadDashboardData();
});

/**
 * Initialize dashboard components
 */
function initializeDashboard() {
    // Initialize charts
    initActivityChart();
    initPlatformChart();
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Refresh button
    document.getElementById('refreshBtn').addEventListener('click', function() {
        loadDashboardData();
        showNotification('Données actualisées', 'success');
    });
    
    // Run workflow button
    document.getElementById('runWorkflowBtn').addEventListener('click', function() {
        runWorkflow();
    });
    
    // Save settings button
    document.getElementById('saveSettings').addEventListener('click', function() {
        saveSettings();
    });
}

/**
 * Load all dashboard data
 */
async function loadDashboardData() {
    try {
        // Load main dashboard data
        const response = await fetch(`${API_BASE}/dashboard`);
        const data = await response.json();
        
        updateStats(data);
        updatePipeline(data.pipeline);
        updateCharts(data);
        updateTopOpportunities(data.recent_jobs);
        updateRecentApplications(data.recent_applications);
        updateActivityLog(data.recent_activity);
        
        // Update last refresh time
        document.getElementById('lastUpdate').textContent = new Date().toLocaleString('fr-FR');
        
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showNotification('Erreur lors du chargement des données', 'error');
    }
}

/**
 * Update statistics cards
 */
function updateStats(data) {
    document.getElementById('totalJobs').textContent = data.total_jobs || 0;
    document.getElementById('totalApplications').textContent = data.total_applications || 0;
    document.getElementById('shortlistedCount').textContent = (data.pipeline && data.pipeline.analyzed) || 0;
    
    // Calculate response rate
    const responseRate = data.total_applications > 0 
        ? ((data.pipeline && data.pipeline.responded) || 0) / data.total_applications * 100 
        : 0;
    document.getElementById('responseRate').textContent = responseRate.toFixed(1) + '%';
}

/**
 * Update pipeline visualization
 */
function updatePipeline(pipeline) {
    if (!pipeline) return;
    
    document.getElementById('pipelineScraped').textContent = pipeline.scraped || 0;
    document.getElementById('pipelineAnalyzed').textContent = pipeline.analyzed || 0;
    document.getElementById('pipelineShortlisted').textContent = pipeline.shortlisted || 0;
    document.getElementById('pipelineApplied').textContent = pipeline.applied || 0;
    document.getElementById('pipelineResponded').textContent = pipeline.responded || 0;
}

/**
 * Update charts with data
 */
function updateCharts(data) {
    // Update activity chart
    if (data.daily_stats && activityChart) {
        const labels = data.daily_stats.map(d => d.date);
        const scrapedData = data.daily_stats.map(d => d.scraped || 0);
        const appliedData = data.daily_stats.map(d => d.applied || 0);
        
        activityChart.data.labels = labels;
        activityChart.data.datasets[0].data = scrapedData;
        activityChart.data.datasets[1].data = appliedData;
        activityChart.update();
    }
    
    // Update platform chart
    if (data.platform_distribution && platformChart) {
        const platforms = Object.keys(data.platform_distribution);
        const counts = Object.values(data.platform_distribution);
        
        platformChart.data.labels = platforms;
        platformChart.data.datasets[0].data = counts;
        platformChart.update();
    }
}

/**
 * Initialize activity chart
 */
function initActivityChart() {
    const ctx = document.getElementById('activityChart').getContext('2d');
    
    activityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Offres scrapées',
                    data: [],
                    borderColor: '#4f46e5',
                    backgroundColor: 'rgba(79, 70, 229, 0.1)',
                    tension: 0.4,
                    fill: true
                },
                {
                    label: 'Candidatures envoyées',
                    data: [],
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    tension: 0.4,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

/**
 * Initialize platform distribution chart
 */
function initPlatformChart() {
    const ctx = document.getElementById('platformChart').getContext('2d');
    
    platformChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    '#4f46e5',
                    '#10b981',
                    '#f59e0b',
                    '#3b82f6'
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

/**
 * Update top opportunities list
 */
function updateTopOpportunities(jobs) {
    const container = document.getElementById('topOpportunities');
    
    if (!jobs || jobs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <p>Aucune opportunité pour le moment</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = jobs.map(job => `
        <div class="job-card">
            <div class="job-header">
                <div>
                    <div class="job-title">${escapeHtml(job.title)}</div>
                    <div class="job-company">${escapeHtml(job.company)}</div>
                </div>
                <div class="job-score ${getScoreClass(job.relevance_score)}">${job.relevance_score ? job.relevance_score.toFixed(1) : '-'}/10</div>
            </div>
            <div class="job-meta">
                <span>📍 ${escapeHtml(job.location || 'Non spécifié')}</span>
                <span>🏢 ${escapeHtml(job.platform)}</span>
            </div>
            <div class="job-actions">
                <button class="btn btn-small btn-primary" onclick="viewJob(${job.id})">Voir</button>
                <button class="btn btn-small btn-success" onclick="applyToJob(${job.id})">Postuler</button>
            </div>
        </div>
    `).join('');
}

/**
 * Update recent applications list
 */
function updateRecentApplications(applications) {
    const container = document.getElementById('recentApplications');
    
    if (!applications || applications.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <p>Aucune candidature pour le moment</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = applications.map(app => `
        <div class="application-card">
            <div class="application-header">
                <div>
                    <div class="application-title">${escapeHtml(app.title)}</div>
                    <div class="application-company">${escapeHtml(app.company)}</div>
                </div>
                <span class="status-badge status-${app.status}">${formatStatus(app.status)}</span>
            </div>
            <div class="application-meta">
                <span>📅 ${formatDate(app.application_date)}</span>
                <span>🔗 ${escapeHtml(app.application_method || 'N/A')}</span>
            </div>
        </div>
    `).join('');
}

/**
 * Update activity log
 */
function updateActivityLog(activities) {
    const container = document.getElementById('activityLog');
    
    if (!activities || activities.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>Aucune activité récente</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = activities.map(activity => `
        <div class="activity-item">
            <div class="activity-icon ${activity.status}">
                ${getActivityIcon(activity.status)}
            </div>
            <div class="activity-content">
                <div class="activity-title">${escapeHtml(activity.agent)} - ${escapeHtml(activity.action)}</div>
                <div class="activity-time">${formatDate(activity.time)}</div>
            </div>
        </div>
    `).join('');
}

/**
 * Run the full workflow
 */
async function runWorkflow() {
    const btn = document.getElementById('runWorkflowBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="icon">⏳</span> En cours...';
    
    showNotification('Workflow démarré...', 'info');
    
    try {
        const response = await fetch(`${API_BASE}/run-workflow`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ dry_run: true })
        });
        
        const result = await response.json();
        
        showNotification('Workflow terminé avec succès!', 'success');
        loadDashboardData(); // Refresh data
        
    } catch (error) {
        console.error('Error running workflow:', error);
        showNotification('Erreur lors du workflow', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="icon">▶</span> Lancer Workflow';
    }
}

/**
 * View job details
 */
function viewJob(jobId) {
    window.open(`/job/${jobId}`, '_blank');
}

/**
 * Apply to a job
 */
async function applyToJob(jobId) {
    try {
        const response = await fetch(`${API_BASE}/apply/${jobId}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Candidature envoyée!', 'success');
            loadDashboardData();
        } else {
            showNotification('Erreur lors de la candidature', 'error');
        }
        
    } catch (error) {
        console.error('Error applying to job:', error);
        showNotification('Erreur lors de la candidature', 'error');
    }
}

/**
 * Save settings
 */
async function saveSettings() {
    const dailyLimit = document.getElementById('dailyLimit').value;
    const minScore = document.getElementById('minScore').value;
    const autoApply = document.getElementById('autoApply').checked;
    
    try {
        const response = await fetch(`${API_BASE}/settings`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                daily_application_limit: parseInt(dailyLimit),
                min_relevance_score: parseFloat(minScore),
                auto_apply_enabled: autoApply
            })
        });
        
        if (response.ok) {
            showNotification('Paramètres sauvegardés', 'success');
        } else {
            showNotification('Erreur lors de la sauvegarde', 'error');
        }
        
    } catch (error) {
        console.error('Error saving settings:', error);
        showNotification('Erreur lors de la sauvegarde', 'error');
    }
}

/**
 * Show notification
 */
function showNotification(message, type = 'info') {
    const container = document.getElementById('notificationContainer');
    
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <span class="icon">${getNotificationIcon(type)}</span>
        <span>${escapeHtml(message)}</span>
    `;
    
    container.appendChild(notification);
    
    // Remove after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

/**
 * Utility: Escape HTML
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Utility: Get score class
 */
function getScoreClass(score) {
    if (score >= 8) return 'high';
    if (score >= 6) return 'medium';
    return 'low';
}

/**
 * Utility: Format status
 */
function formatStatus(status) {
    const statusMap = {
        'pending': 'En attente',
        'submitted': 'Envoyée',
        'viewed': 'Vue',
        'interview_scheduled': 'Entretien',
        'offer_received': 'Offre reçue',
        'rejected': 'Refusée'
    };
    return statusMap[status] || status;
}

/**
 * Utility: Format date
 */
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('fr-FR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Utility: Get activity icon
 */
function getActivityIcon(status) {
    const icons = {
        'success': '✓',
        'error': '✗',
        'warning': '!',
        'info': 'i'
    };
    return icons[status] || '•';
}

/**
 * Utility: Get notification icon
 */
function getNotificationIcon(type) {
    const icons = {
        'success': '✓',
        'error': '✗',
        'warning': '⚠',
        'info': 'ℹ'
    };
    return icons[type] || '•';
}

// Auto-refresh every 5 minutes
setInterval(loadDashboardData, 300000);
