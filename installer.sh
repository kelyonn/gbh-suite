#!/bin/bash
# GBH v2 Installer — one-shot setup
# Usage: bash installer.sh

set -e
GBH_DIR="$(cd "$(dirname "$0")" && pwd)"

# Always install into a project-local venv, creating it if it doesn't exist.
#
# This used to prefer an existing venv but silently fall back to the system
# Python (with --user installs) if one wasn't there. That fallback is exactly
# how a venv going missing turns into a full outage: every LaunchAgent plist
# is baked with an absolute interpreter path at install time, so if the venv
# it pointed to later disappears (as happened — deleted by something during
# an unclean shutdown), the daemons don't fall back to anything; they just
# fail with EX_CONFIG, silently, forever, because ProgramArguments[0] no
# longer exists. Always creating the venv here means re-running this script
# is a real fix for that state, not just a reconfirmation of a Python that
# hasn't existed in days.
if [ ! -f "$GBH_DIR/venv/bin/python3" ]; then
    echo "🐍 No venv found — creating one..."
    if ! command -v python3 &>/dev/null; then
        echo "❌ python3 not found on PATH. Install Python 3.11+ and re-run this script." >&2
        exit 1
    fi
    python3 -m venv "$GBH_DIR/venv"
fi
PYTHON="$GBH_DIR/venv/bin/python3"

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "🏨 Grand Budapest Hotel v2 — Installer"
echo "   Project: $GBH_DIR"
echo "   Python:  $($PYTHON --version)"
echo ""

# 1. Install dependencies
echo "📦 Installing dependencies..."
$PYTHON -m pip install --quiet --upgrade pip
$PYTHON -m pip install --quiet watchdog psutil fastapi uvicorn jinja2 websockets
brew install terminal-notifier --quiet 2>/dev/null || true

# Verify the interpreter every plist is about to be pointed at can actually
# import what the server and staff modules need. This is the check that
# would have caught this session's outage in ten seconds instead of days:
# don't declare success and wire up nine LaunchAgents around a Python that
# can't run the code. Deliberately no `|| true` here — a broken environment
# must stop the install, not get reported as done.
if ! $PYTHON -c "import watchdog, psutil, fastapi, uvicorn, jinja2, websockets" 2>/dev/null; then
    echo "❌ Dependency verification failed — $PYTHON cannot import required packages." >&2
    echo "   Try removing venv/ and re-running this script." >&2
    exit 1
fi
echo "   ✅ Dependencies installed and verified"

# 2. Create runtime data dir
mkdir -p "$HOME/.gbh"
echo "   ✅ ~/.gbh created"

# Install the notification stack properly (this is what silently broke for months).
#
# Rules:
#   1. NEVER attribute notifications to com.gbh.concierge via -sender unless
#      Concierge.app has a real executable AND Notification Centre permission.
#   2. Copy terminal-notifier.app into ~/Applications and register it so macOS
#      actually grants/keeps notification permission for the helper.
#   3. Run an end-to-end probe; refuse to declare success if delivery fails.
mkdir -p "$HOME/Applications"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

# Ensure Concierge.app has a real (no-op) executable so it is a valid bundle.
APP_BUNDLE="GBH Concierge.app"
if [ -d "$GBH_DIR/$APP_BUNDLE" ]; then
    mkdir -p "$GBH_DIR/$APP_BUNDLE/Contents/MacOS"
    cat > "$GBH_DIR/$APP_BUNDLE/Contents/MacOS/GBHConcierge" <<'STUB'
#!/bin/bash
# Minimal executable so Launch Services treats this as a real app bundle.
exit 0
STUB
    chmod +x "$GBH_DIR/$APP_BUNDLE/Contents/MacOS/GBHConcierge"
    # Ensure Info.plist declares the executable (idempotent-ish via rewrite).
    cat > "$GBH_DIR/$APP_BUNDLE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>GBHConcierge</string>
    <key>CFBundleIdentifier</key>
    <string>com.gbh.concierge</string>
    <key>CFBundleName</key>
    <string>GBH Concierge</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST
    rm -rf "$HOME/Applications/$APP_BUNDLE"
    cp -R "$GBH_DIR/$APP_BUNDLE" "$HOME/Applications/$APP_BUNDLE"
    [ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$HOME/Applications/$APP_BUNDLE" 2>/dev/null || true
    echo "   ✅ $APP_BUNDLE installed with real executable stub"
fi

# Copy terminal-notifier into ~/Applications (cellar path alone is flaky on modern macOS)
TN_SRC=""
for candidate in \
    "/opt/homebrew/Cellar/terminal-notifier/"*"/terminal-notifier.app" \
    "/usr/local/Cellar/terminal-notifier/"*"/terminal-notifier.app"
do
    if [ -d "$candidate" ]; then
        TN_SRC="$candidate"
        break
    fi
done
if [ -n "$TN_SRC" ]; then
    rm -rf "$HOME/Applications/terminal-notifier.app"
    cp -R "$TN_SRC" "$HOME/Applications/terminal-notifier.app"
    [ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$HOME/Applications/terminal-notifier.app" 2>/dev/null || true
    # Opening once forces Notification Centre to register the app / show the
    # permission prompt if needed. Harmless if already allowed.
    open "$HOME/Applications/terminal-notifier.app" 2>/dev/null || true
    echo "   ✅ terminal-notifier.app installed in ~/Applications"
else
    echo "   ⚠️  terminal-notifier.app not found in Homebrew Cellar" >&2
fi

echo ""
echo "🔔 Probing notification delivery…"
if $PYTHON -c "from staff.notify import probe; import sys; r=probe(); print(r); sys.exit(0 if r.get('ok') else 1)"; then
    echo "   ✅ Notify probe passed"
else
    echo "   ❌ Notify probe FAILED" >&2
    echo "      System Settings → Notifications → enable Banners for:" >&2
    echo "        • Script Editor (osascript)" >&2
    echo "        • terminal-notifier" >&2
    echo "      Then re-run: bash installer.sh" >&2
    echo "      Or test with: $PYTHON $GBH_DIR/main.py notify-test" >&2
    # Don't abort the whole install — agents still matter — but surface loudly.
    NOTIFY_PROBE_FAILED=1
fi

# 3. Install LaunchAgents
echo ""
echo "🔧 Installing LaunchAgents..."
FAILED_AGENTS=()
for plist in "$GBH_DIR/launchagents/"*.plist; do
    name=$(basename "$plist")
    label="${name%.plist}"
    dest="$LAUNCH_AGENTS/$name"

    # Bootout if already loaded (safe to ignore if not loaded — that's the
    # expected case on a first install, so this one's || true is correct).
    launchctl bootout "gui/$UID/$label" 2>/dev/null || true

    # Copy plist file and substitute placeholders dynamically
    sed -e "s|/Users/kalyan/Documents/projects/gbh|$GBH_DIR|g" \
        -e "s|/opt/homebrew/bin/python3.11|$PYTHON|g" \
        "$plist" > "$dest"

    # Bootstrap into the gui domain — persists across reboots. Unlike the
    # steps above, a failure here is real and must be reported as one: the
    # old `|| true` printed "✅ $name" even when bootstrap failed, which is
    # exactly the kind of silent lie that let a dead daemon look installed.
    #
    # bootstrap can race the bootout just above it — observed firsthand on
    # the server agent, whose bootstrap failed immediately after bootout
    # (port 2525 not yet released) and then succeeded on the very next
    # attempt. Retry briefly before treating it as a genuine failure.
    ok=false
    for attempt in 1 2 3; do
        if launchctl bootstrap "gui/$UID" "$dest" 2>/dev/null; then
            ok=true
            break
        fi
        sleep 0.5
    done
    if $ok; then
        launchctl enable "gui/$UID/$label" 2>/dev/null || true
        echo "   ✅ $name"
    else
        echo "   ❌ $name — bootstrap failed" >&2
        FAILED_AGENTS+=("$label")
    fi
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
if [ ${#FAILED_AGENTS[@]} -eq 0 ] && [ "${NOTIFY_PROBE_FAILED:-0}" != "1" ]; then
    echo "✅ Installation complete!"
    echo ""
    echo "   Run 'source ~/.zshrc' then try: gbh"
    echo "   Dashboard: http://127.0.0.1:2525"
    echo "   Notify test: gbh notify-test"
elif [ ${#FAILED_AGENTS[@]} -eq 0 ]; then
    echo "⚠️  Agents installed, but notifications are NOT delivering." >&2
    echo "   Fix System Settings → Notifications (Banners), then:" >&2
    echo "   $PYTHON $GBH_DIR/main.py notify-test" >&2
    exit 1
else
    echo "⚠️  Installation finished with ${#FAILED_AGENTS[@]} failed agent(s): ${FAILED_AGENTS[*]}" >&2
    echo "   Everything else installed. Investigate with:" >&2
    echo "   launchctl bootstrap gui/\$UID ~/Library/LaunchAgents/<label>.plist" >&2
    exit 1
fi
