#!/usr/bin/env bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                                                           ║"
echo "║   🎩 Smithers Installer                                   ║"
echo "║   Your loyal PR automation assistant                      ║"
echo "║                                                           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check for required commands
check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 found"
        return 0
    else
        echo -e "${RED}✗${NC} $1 not found"
        return 1
    fi
}

install_uv() {
    echo -e "${YELLOW}Installing uv...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Source the env to get uv in path
    source "$HOME/.local/bin/env" 2>/dev/null || true
    export PATH="$HOME/.local/bin:$PATH"
}

echo -e "\n${BLUE}Checking prerequisites...${NC}\n"

# Check for uv
if ! check_command uv; then
    echo -e "\n${YELLOW}uv is required but not installed.${NC}"
    read -p "Install uv now? [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        install_uv
        check_command uv || { echo -e "${RED}Failed to install uv${NC}"; exit 1; }
    else
        echo -e "${RED}uv is required. Please install it: https://docs.astral.sh/uv/${NC}"
        exit 1
    fi
fi

# Check optional dependencies
echo ""
MISSING_OPTIONAL=()

check_command tmux || MISSING_OPTIONAL+=("tmux")
check_command gh || MISSING_OPTIONAL+=("gh (GitHub CLI)")
check_command claude || MISSING_OPTIONAL+=("claude (Claude Code CLI)")
check_command git || { echo -e "${RED}git is required${NC}"; exit 1; }

if [ ${#MISSING_OPTIONAL[@]} -gt 0 ]; then
    echo -e "\n${YELLOW}Optional dependencies not found:${NC}"
    for dep in "${MISSING_OPTIONAL[@]}"; do
        echo "  - $dep"
    done
    echo -e "\nSmithers will still install, but some features may not work."
    echo "Install them with:"
    echo "  brew install tmux gh"
    echo "  npm install -g @anthropic-ai/claude-code"
fi

# Install smithers
echo -e "\n${BLUE}Installing smithers...${NC}\n"

REPO_URL="git+https://github.com/Metaview/smithers.git"

if uv tool install "$REPO_URL" --force; then
    echo -e "\n${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                           ║${NC}"
    echo -e "${GREEN}║   ✓ Smithers installed successfully!                      ║${NC}"
    echo -e "${GREEN}║                                                           ║${NC}"
    echo -e "${GREEN}║   Run 'smithers --help' to get started                    ║${NC}"
    echo -e "${GREEN}║                                                           ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Try: ${BLUE}smithers quote${NC}"
else
    echo -e "\n${RED}Installation failed.${NC}"
    exit 1
fi
