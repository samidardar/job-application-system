#!/bin/bash
# ============================================================
# OpenClaw MCP Servers & Skills Installer
# Comprehensive setup for AI agent capabilities
# ============================================================

echo "🚀 Installing OpenClaw MCP Servers & Skills..."
echo ""

# Create directories
mkdir -p ~/.config/openclaw
mkdir -p ~/.openclaw/mcp-servers
mkdir -p ~/.openclaw/skills

# ============================================================
# 1. OFFICIAL MCP SERVERS (Model Context Protocol)
# ============================================================

echo "📦 Installing Official MCP Servers..."

# Filesystem access - allows AI to read/write files
npm install -g @modelcontextprotocol/server-filesystem

# SQLite database access
npm install -g @modelcontextprotocol/server-sqlite

# PostgreSQL database access  
npm install -g @modelcontextprotocol/server-postgres

# Web scraping with Puppeteer
npm install -g @modelcontextprotocol/server-puppeteer

# Brave Search API
npm install -g @modelcontextprotocol/server-brave-search

# Fetch/HTTP requests
npm install -g @modelcontextprotocol/server-fetch

# Git operations
npm install -g @modelcontextprotocol/server-git

# GitHub integration
npm install -g @modelcontextprotocol/server-github

# Sequential thinking (for complex reasoning)
npm install -g @modelcontextprotocol/server-sequential-thinking

# Memory server (persistent conversations)
npm install -g @modelcontextprotocol/server-memory

# Google Drive
npm install -g @modelcontextprotocol/server-gdrive

# Slack integration
npm install -g @modelcontextprotocol/server-slack

echo "✅ Official MCP servers installed!"
echo ""

# ============================================================
# 2. COMMUNITY MCP SERVERS
# ============================================================

echo "📦 Installing Community MCP Servers..."

# Gmail
npm install -g @gmail/mcp-server-gmail

# Notion
npm install -g @suekou/mcp-notion-server

# Obsidian
npm install -g @mcp-servers/obsidian

# Discord
npm install -g @modelcontextprotocol/server-discord

# Weather
npm install -g @modelcontextprotocol/server-weather

# YouTube transcript
npm install -g @mcp-servers/youtube-transcript

# Browser automation
npm install -g @browserbase/mcp-server-browserbase

# Stripe
npm install -g @stripe/mcp-server-stripe

# Twilio
npm install -g @twilio-labs/mcp-server-twilio

# AWS
npm install -g @awslabs/mcp-server-aws

# Docker
npm install -g @modelcontextprotocol/server-docker

# Kubernetes
npm install -g @modelcontextprotocol/server-kubernetes

echo "✅ Community MCP servers installed!"
echo ""

# ============================================================
# 3. OPENCLAW SKILLS FROM skills.sh / ClawHub
# ============================================================

echo "📦 Installing OpenClaw Skills..."

# Job-related skills
clawhub install job-auto-apply
clawhub install job-search-mcp-jobspy

# Vercel skills (React, patterns)
npx skills add vercel-labs/agent-skills -y

echo "✅ OpenClaw skills installed!"
echo ""

# ============================================================
# 4. PYTHON-BASED MCP SERVERS
# ============================================================

echo "📦 Installing Python MCP Servers..."

pip install mcp-server-fetch
pip install mcp-server-filesystem
pip install mcp-server-web-search

echo "✅ Python MCP servers installed!"
echo ""

echo "🎉 Installation Complete!"
echo ""
echo "Next steps:"
echo "1. Configure API keys in ~/.config/openclaw/config.json"
echo "2. Restart OpenClaw to load new servers"
echo ""
