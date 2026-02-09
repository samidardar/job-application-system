# 🤖 OpenClaw MCP Servers & Skills - Complete Resource List

> Comprehensive AI agent capabilities for OpenClaw

---

## 🚀 Quick Start

**Install everything:**
```bash
chmod +x /data/.openclaw/install-all-mcp.sh
/data/.openclaw/install-all-mcp.sh
```

**Copy config to OpenClaw:**
```bash
cp /data/.openclaw/openclaw-mcp-config.json ~/.config/openclaw/config.json
```

---

## 📦 MCP Servers (Model Context Protocol)

### Official Servers (by Anthropic)

| Server | Install | Description |
|--------|---------|-------------|
| **Filesystem** | `npx -y @modelcontextprotocol/server-filesystem /path` | Read/write files |
| **SQLite** | `npx -y @modelcontextprotocol/server-sqlite /path/to.db` | Database queries |
| **PostgreSQL** | `npx -y @modelcontextprotocol/server-postgres <url>` | Postgres access |
| **Puppeteer** | `npx -y @modelcontextprotocol/server-puppeteer` | Web scraping |
| **Brave Search** | `npx -y @modelcontextprotocol/server-brave-search` | Web search |
| **Fetch** | `npx -y @modelcontextprotocol/server-fetch` | HTTP requests |
| **Git** | `npx -y @modelcontextprotocol/server-git /path` | Git operations |
| **GitHub** | `npx -y @modelcontextprotocol/server-github` | GitHub API |
| **Sequential Thinking** | `npx -y @modelcontextprotocol/server-sequential-thinking` | Complex reasoning |
| **Memory** | `npx -y @modelcontextprotocol/server-memory` | Persistent memory |
| **Google Drive** | `npx -y @modelcontextprotocol/server-gdrive` | GDrive files |
| **Slack** | `npx -y @modelcontextprotocol/server-slack` | Slack messaging |

### Community Servers

| Server | Install | Description |
|--------|---------|-------------|
| **Gmail** | `npx -y @gmail/mcp-server-gmail` | Email management |
| **Notion** | `npx -y @suekou/mcp-notion-server` | Notion pages |
| **YouTube** | `npx -y @mcp-servers/youtube-transcript` | Video transcripts |
| **Discord** | `npx -y @modelcontextprotocol/server-discord` | Discord bot |
| **Weather** | `npx -y @modelcontextprotocol/server-weather` | Weather data |
| **Stripe** | `npx -y @stripe/mcp-server-stripe` | Payments |
| **Twilio** | `npx -y @twilio-labs/mcp-server-twilio` | SMS/Voice |
| **AWS** | `npx -y @awslabs/mcp-server-aws` | AWS services |
| **Docker** | `npx -y @modelcontextprotocol/server-docker` | Containers |
| **Kubernetes** | `npx -y @modelcontextprotocol/server-kubernetes` | K8s clusters |
| **Browserbase** | `npx -y @browserbase/mcp-server-browserbase` | Browser automation |

---

## 🎯 Skills.sh / OpenClaw Skills

### Install Skills

```bash
# From skills.sh / npx
npx skills add <owner>/<repo> -y

# From ClawHub
clawhub install <skill-name>

# List installed
npx skills list
clawhub list

# Search for skills
clawhub search <query>
npx skills find
```

### Recommended Skills

| Skill | Command | Description |
|-------|---------|-------------|
| Vercel React | `npx skills add vercel-labs/agent-skills -y` | React best practices |
| Job Auto-Apply | `clawhub install job-auto-apply` | Automated applications |
| Job Search | `clawhub install job-search-mcp-jobspy` | Multi-platform search |
| Health Check | `clawhub install healthcheck` | System monitoring |
| Weather | `clawhub install weather` | Weather forecasts |

---

## 🔧 Essential Resources

### Skills Directories
- **skills.sh** - https://skills.sh (Official)
- **clawhub.com** - https://clawhub.com
- **GitHub Skills Topic** - https://github.com/topics/ai-agent-skills

### MCP Resources
- **MCP Spec** - https://modelcontextprotocol.io
- **MCP Servers** - https://github.com/modelcontextprotocol/servers
- **Awesome MCP** - https://github.com/punkpeye/awesome-mcp-servers

### Agent Frameworks
- **OpenClaw** - https://openclaw.ai
- **Claude Code** - https://docs.anthropic.com/en/docs/agents-and-tools/claude-code
- **Vercel AI SDK** - https://sdk.vercel.ai
- **LangChain** - https://langchain.com

---

## 🔌 Configuration

### OpenClaw Config Location
```
~/.config/openclaw/config.json
```

### Example Server Config
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"
      }
    }
  }
}
```

---

## 📚 By Category

### 💼 Job Search & Career
- `clawhub install job-auto-apply`
- `clawhub install job-search-mcp-jobspy`
- `npx -y @modelcontextprotocol/server-puppeteer` (scraping)

### 💻 Development
- `npx skills add vercel-labs/agent-skills`
- `npx -y @modelcontextprotocol/server-github`
- `npx -y @modelcontextprotocol/server-git`

### 📊 Data Science
- `npx -y @modelcontextprotocol/server-sqlite`
- `npx -y @modelcontextprotocol/server-postgres`
- `npx -y @modelcontextprotocol/server-fetch`

### 🔍 Research
- `npx -y @modelcontextprotocol/server-brave-search`
- `npx -y @modelcontextprotocol/server-puppeteer`
- `npx -y @mcp-servers/youtube-transcript`

### 💬 Communication
- `npx -y @modelcontextprotocol/server-slack`
- `npx -y @gmail/mcp-server-gmail`
- `npx -y @modelcontextprotocol/server-discord`

### ☁️ Cloud & Infrastructure
- `npx -y @awslabs/mcp-server-aws`
- `npx -y @modelcontextprotocol/server-docker`
- `npx -y @modelcontextprotocol/server-kubernetes`

### 💰 Business
- `npx -y @stripe/mcp-server-stripe`
- `npx -y @twilio-labs/mcp-server-twilio`
- `npx -y @modelcontextprotocol/server-gdrive`

---

## ⚡ Quick Commands

```bash
# Install single MCP server
npx -y @modelcontextprotocol/server-<name>

# Install skill
npx skills add <owner>/<repo> -y

# List all installed
npx skills list
clawhub list

# Update all skills
npx skills update
clawhub update

# Search skills
clawhub search "job"
npx skills find "react"
```

---

## 🔐 API Keys Setup

Add to `~/.config/openclaw/config.json`:

```json
{
  "apiKeys": {
    "brave": "YOUR_BRAVE_API_KEY",
    "github": "ghp_YOUR_TOKEN",
    "openai": "sk-...",
    "google": "...",
    "stripe": "sk_..."
  }
}
```

---

## 🆘 Troubleshooting

```bash
# Check if MCP server is running
curl http://localhost:PORT/health

# Restart OpenClaw
openclaw gateway restart

# Update MCP servers
npm update -g @modelcontextprotocol/server-<name>
```

---

**Total: 20+ MCP Servers | 6+ Skills Installed | 100+ Available**

Last updated: 2026-02-10
