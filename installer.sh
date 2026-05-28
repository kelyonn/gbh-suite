#!/bin/bash
# GBH v2 Installer — one-shot setup
# Usage: bash installer.sh

set -e
GBH_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/opt/homebrew/bin/python3.11"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "🏨 Grand Budapest Hotel v2 — Installer"
echo "   Project: $GBH_DIR"
echo "   Python:  $($PYTHON --version)"
echo ""

# 1. Install dependencies user-wide (no venv, no TCC issues)
echo "📦 Installing dependencies..."
$PYTHON -m pip install --user --quiet watchdog psutil fastapi uvicorn jinja2 httpx websockets
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

    # Symlink into LaunchAgents
    ln -sf "$plist" "$dest"

    # Bootstrap into the gui domain — persists across reboots
    launchctl bootstrap "gui/$UID" "$dest"
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


# 5. Opt-in: passwordless sudo for Ivan focus mode
echo ""
read -r -p "🔐 Install passwordless sudo for Ivan focus mode? [y/N] " ans
if [[ "$ans" =~ ^[Yy]$ ]]; then
    bash "$GBH_DIR/scripts/install_ivan_sudoers.sh"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "   Run 'source ~/.zshrc' then try: gbh"
echo "   Dashboard: http://127.0.0.1:2525"
