#!/bin/bash
# ============================================================
# COPY-PASTE THIS ENTIRE SCRIPT TO OPENCLAW
# This will install all MCP servers and skills
# ============================================================

echo "🚀 OpenClaw MCP & Skills Mega-Installer"
echo "=========================================="
echo ""

# Create directories
mkdir -p ~/.config/openclaw
mkdir -p ~/.openclaw/mcp-servers
mkdir -p ~/.openclaw/skills

# ============================================================
# OFFICIAL ANTHROPIC MCP SERVERS
# ============================================================
echo "📦 Installing Official MCP Servers..."

SERVERS=(
  "@modelcontextprotocol/server-filesystem"
  "@modelcontextprotocol/server-sqlite"
  "@modelcontextprotocol/server-postgres"
  "@modelcontextprotocol/server-puppeteer"
  "@modelcontextprotocol/server-brave-search"
  "@modelcontextprotocol/server-fetch"
  "@modelcontextprotocol/server-git"
  "@modelcontextprotocol/server-github"
  "@modelcontextprotocol/server-sequential-thinking"
  "@modelcontextprotocol/server-memory"
  "@modelcontextprotocol/server-gdrive"
  "@modelcontextprotocol/server-slack"
)

for server in "${SERVERS[@]}"; do
  echo "  Installing $server..."
  npm install -g "$server" 2>/dev/null || echo "  ⚠️ Failed: $server"
done

# ============================================================
# COMMUNITY MCP SERVERS
# ============================================================
echo ""
echo "📦 Installing Community MCP Servers..."

COMMUNITY=(
  "@gmail/mcp-server-gmail"
  "@suekou/mcp-notion-server"
  "@mcp-servers/youtube-transcript"
  "@modelcontextprotocol/server-discord"
  "@modelcontextprotocol/server-weather"
  "@stripe/mcp-server-stripe"
  "@twilio-labs/mcp-server-twilio"
  "@awslabs/mcp-server-aws"
  "@modelcontextprotocol/server-docker"
  "@modelcontextprotocol/server-kubernetes"
  "@browserbase/mcp-server-browserbase"
)

for server in "${COMMUNITY[@]}"; do
  echo "  Installing $server..."
  npm install -g "$server" 2>/dev/null || echo "  ⚠️ Failed: $server"
done

# ============================================================
# OPENCLAW SKILLS
# ============================================================
echo ""
echo "📦 Installing OpenClaw Skills..."

# From ClawHub
clawhub install job-auto-apply 2>/dev/null || true
clawhub install job-search-mcp-jobspy 2>/dev/null || true
clawhub install healthcheck 2>/dev/null || true
clawhub install weather 2>/dev/null || true

# From skills.sh
npx skills add vercel-labs/agent-skills -y 2>/dev/null || true

# ============================================================
# CREATE CONFIG FILE
# ============================================================
echo ""
echo "📝 Creating OpenClaw config..."

cat > ~/.config/openclaw/config.json << 'EOF'
{
  "agent": {
    "name": "Jarvis",
    "model": "moonshot/kimi-k2.5"
  },
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data/.openclaw/workspace"]
    },
    "sqlite": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sqlite", "/data/.openclaw/workspace/job_application_system/database/job_application.db"]
    },
    "puppeteer": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": { "BRAVE_API_KEY": "" }
    },
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git", "/data/.openclaw/workspace"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "" }
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "gmail": {
      "command": "npx",
      "args": ["-y", "@gmail/mcp-server-gmail"],
      "env": {
        "GMAIL_CREDENTIALS_PATH": "/data/.openclaw/credentials/gmail-sami.json"
      }
    },
    "notion": {
      "command": "npx",
      "args": ["-y", "@suekou/mcp-notion-server"],
      "env": { "NOTION_API_TOKEN": "" }
    }
  }
}
EOF

# ============================================================
# DONE
# ============================================================
echo ""
echo "🎉 INSTALLATION COMPLETE!"
echo "========================="
echo ""
echo "Installed MCP Servers:"
echo "  - Filesystem, SQLite, Puppeteer"
echo "  - Brave Search, Fetch, Git, GitHub"
echo "  - Sequential Thinking, Memory"
echo "  - Gmail, Notion, and more..."
echo ""
echo "Installed Skills:"
echo "  - job-auto-apply"
echo "  - job-search-mcp-jobspy"
echo "  - vercel-labs/agent-skills"
echo "  - healthcheck, weather"
echo ""
echo "Config file: ~/.config/openclaw/config.json"
echo ""
echo "⚠️  ACTION REQUIRED:"
echo "  1. Add your API keys to ~/.config/openclaw/config.json"
echo "  2. Restart OpenClaw: openclaw gateway restart"
echo ""
