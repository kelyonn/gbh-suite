#!/bin/bash
# GBH v2 Installer — one-shot setup
# Usage: bash installer.sh

set -e
GBH_DIR="$(cd "$(dirname "$0")" && pwd)"

# Detect Python interpreter (prefer project venv if it exists)
if [ -f "$GBH_DIR/venv/bin/python3" ]; then
    PYTHON="$GBH_DIR/venv/bin/python3"
elif [ -f "$GBH_DIR/venv/bin/python" ]; then
    PYTHON="$GBH_DIR/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="$(command -v python3)"
else
    PYTHON="/usr/bin/python3"
fi

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "🏨 Grand Budapest Hotel v2 — Installer"
echo "   Project: $GBH_DIR"
echo "   Python:  $($PYTHON --version)"
echo ""

# 1. Install dependencies
echo "📦 Installing dependencies..."
if [[ "$PYTHON" == *"/venv/"* ]]; then
    $PYTHON -m pip install --quiet watchdog psutil fastapi uvicorn jinja2 httpx websockets
else
    $PYTHON -m pip install --user --quiet watchdog psutil fastapi uvicorn jinja2 httpx websockets
fi
brew install terminal-notifier --quiet 2>/dev/null || true
echo "   ✅ Dependencies installed"

# 2. Create runtime data dir
mkdir -p "$HOME/.gbh"
echo "   ✅ ~/.gbh created"

# 3. Install LaunchAgents
echo ""
echo "🔧 Installing LaunchAgents..."
for plist in "$GBH_DIR/launchagents/"*.plist; do
    name=$(basename "$plist")
    label="${name%.plist}"
    dest="$LAUNCH_AGENTS/$name"

    # Bootout if already loaded (safe to ignore if not loaded)
    launchctl bootout "gui/$UID/$label" 2>/dev/null || true

    # Copy plist file and substitute placeholders dynamically
    sed -e "s|/Users/kalyan/Documents/projects/gbh|$GBH_DIR|g" \
        -e "s|/opt/homebrew/bin/python3.11|$PYTHON|g" \
        "$plist" > "$dest"

    # Bootstrap into the gui domain — persists across reboots
    launchctl bootstrap "gui/$UID" "$dest" 2>/dev/null || true
    launchctl enable "gui/$UID/$label" 2>/dev/null || true
    echo "   ✅ $name"
done

# 4. Add gbh alias to .zshrc if not present
if ! grep -q "alias gbh=" "$HOME/.zshrc" 2>/dev/null; then
    echo "" >> "$HOME/.zshrc"
    echo "# GBH Suite" >> "$HOME/.zshrc"
    echo "alias gbh=\"$PYTHON $GBH_DIR/main.py\"" >> "$HOME/.zshrc"
    echo "   ✅ Added 'gbh' alias to ~/.zshrc"
else
    echo "   ℹ️  gbh alias already in ~/.zshrc"
fi


echo ""
echo "✅ Installation complete!"
echo ""
echo "   Run 'source ~/.zshrc' then try: gbh"
echo "   Dashboard: http://127.0.0.1:2525"
