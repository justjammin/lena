#!/usr/bin/env node

const fs   = require('fs');
const path = require('path');
const os   = require('os');

const CLAUDE_DIR      = path.join(os.homedir(), '.claude');
const SKILL_DEST_DIR  = path.join(CLAUDE_DIR, 'skills', 'lena');
const HOOKS_DIR       = path.join(CLAUDE_DIR, 'hooks');
const ACTIVATE_DEST   = path.join(HOOKS_DIR, 'lena-activate.js');
const STATUSLINE_DEST = path.join(HOOKS_DIR, 'lena-statusline.sh');
const SETTINGS_PATH   = path.join(CLAUDE_DIR, 'settings.json');

function rmrf(p) {
  if (!fs.existsSync(p)) return false;
  fs.rmSync(p, { recursive: true, force: true });
  return true;
}

function removeSkill() {
  const removed = rmrf(SKILL_DEST_DIR);
  console.log(removed
    ? `  Skill:   removed ${SKILL_DEST_DIR}`
    : '  Skill:   not found (skipped)');
}

function removeHooks() {
  const a = rmrf(ACTIVATE_DEST);
  const s = rmrf(STATUSLINE_DEST);
  console.log(a ? `  Hook:    removed lena-activate.js` : '  Hook:    lena-activate.js not found (skipped)');
  console.log(s ? `  Status:  removed lena-statusline.sh` : '  Status:  lena-statusline.sh not found (skipped)');
}

function cleanSettings() {
  if (!fs.existsSync(SETTINGS_PATH)) {
    console.log('  Settings: not found (skipped)');
    return;
  }

  let settings = {};
  try {
    settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));
  } catch (_) {
    console.log('  Settings: could not parse — skipping');
    return;
  }

  let changed = false;

  // Remove SessionStart hook entry
  if (settings.hooks && Array.isArray(settings.hooks.SessionStart)) {
    const before = settings.hooks.SessionStart.length;
    settings.hooks.SessionStart = settings.hooks.SessionStart.filter(entry =>
      !(entry.hooks && entry.hooks.some(h => h.command && h.command.includes('lena-activate.js')))
    );
    if (settings.hooks.SessionStart.length < before) {
      changed = true;
      console.log('  Settings: SessionStart hook removed');
    }
    if (settings.hooks.SessionStart.length === 0) {
      delete settings.hooks.SessionStart;
    }
    if (Object.keys(settings.hooks).length === 0) {
      delete settings.hooks;
    }
  }

  // Clean statusLine
  if (settings.statusLine && settings.statusLine.command) {
    const cmd = settings.statusLine.command;
    if (cmd.includes('lena-statusline')) {
      // Chained form: "(original) 2>/dev/null; printf ' '; bash "...lena-statusline.sh""
      // Try to recover the original command from the chain pattern
      const chainMatch = cmd.match(/^\((.+)\) 2>\/dev\/null; printf ' '; bash ".*lena-statusline\.sh"$/);
      if (chainMatch) {
        settings.statusLine = { type: 'command', command: chainMatch[1] };
        console.log(`  Settings: statusLine restored to previous command`);
      } else {
        delete settings.statusLine;
        console.log('  Settings: statusLine removed');
      }
      changed = true;
    }
  }

  if (changed) {
    fs.writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2) + '\n');
  } else {
    console.log('  Settings: no LENA entries found (skipped)');
  }
}

function uninstall() {
  console.log('Uninstalling LENA...');
  console.log('');

  removeSkill();
  removeHooks();
  cleanSettings();

  console.log('');
  console.log('LENA removed. Restart Claude Code to apply.');
}

uninstall();