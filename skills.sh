#!/bin/bash
# Skills installation script for OpenClaw
# Usage: chmod +x skills.sh && ./skills.sh

echo "Installing OpenClaw skills..."

# Job search and application skills
clawhub install job-auto-apply
clawhub install job-search-mcp-jobspy

# Add more skills here as needed
# clawhub install <skill-name>

echo "Skills installed successfully!"
echo ""
echo "Installed skills:"
clawhub list
