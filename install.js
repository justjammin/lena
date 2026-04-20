#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const SKILL_SRC = path.join(__dirname, 'skills', 'lena', 'SKILL.md');
const CLAUDE_DIR = path.join(os.homedir(), '.claude');
const CLAUDE_SKILLS_DIR = path.join(CLAUDE_DIR, 'skills', 'lena');
const SKILL_DEST = path.join(CLAUDE_SKILLS_DIR, 'SKILL.md');
const SETTINGS_PATH = path.join(CLAUDE_DIR, 'settings.json');
const HOOK_COMMAND = `node "${path.join(__dirname, 'hooks', 'lena-activate.js')}"`;
const HOOKS_DIR = path.join(CLAUDE_DIR, 'hooks');
const STATUSLINE_SRC = path.join(__dirname, 'hooks', 'lena-statusline.sh');
const STATUSLINE_DEST = path.join(HOOKS_DIR, 'lena-statusline.sh');

function install() {
  if (!fs.existsSync(CLAUDE_DIR)) {
    console.error('Error: Claude Code not found. Install from https://claude.ai/code first.');
    process.exit(1);
  }

  // Copy skill
  if (!fs.existsSync(CLAUDE_SKILLS_DIR)) {
    fs.mkdirSync(CLAUDE_SKILLS_DIR, { recursive: true });
  }
  fs.copyFileSync(SKILL_SRC, SKILL_DEST);

  // Copy statusline script
  if (!fs.existsSync(HOOKS_DIR)) {
    fs.mkdirSync(HOOKS_DIR, { recursive: true });
  }
  fs.copyFileSync(STATUSLINE_SRC, STATUSLINE_DEST);
  try { fs.chmodSync(STATUSLINE_DEST, 0o755); } catch (_) {}

  // Register SessionStart hook
  let settings = {};
  if (fs.existsSync(SETTINGS_PATH)) {
    try { settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8')); } catch (_) {}
  }

  if (!settings.hooks) settings.hooks = {};
  if (!settings.hooks.SessionStart) settings.hooks.SessionStart = [];

  const alreadyRegistered = settings.hooks.SessionStart.some(
    entry => entry.hooks && entry.hooks.some(h => h.command && h.command.includes('lena-activate.js'))
  );

  if (!alreadyRegistered) {
    settings.hooks.SessionStart.push({
      hooks: [{
        type: 'command',
        command: HOOK_COMMAND,
        timeout: 5,
        statusMessage: 'Loading LENA...'
      }]
    });
    console.log('  Hook:  SessionStart → hooks/lena-activate.js');
  } else {
    console.log('  Hook:  already registered (skipped)');
  }

  // Register statusLine — set if empty, chain if already configured
  const statusLineCmd = `bash "${STATUSLINE_DEST}"`;
  if (!settings.statusLine) {
    settings.statusLine = { type: 'command', command: statusLineCmd };
    console.log('  Status: statusLine → hooks/lena-statusline.sh');
  } else if (settings.statusLine.command && !settings.statusLine.command.includes('lena-statusline')) {
    const existing = settings.statusLine.command;
    settings.statusLine = {
      type: 'command',
      command: `(${existing}) 2>/dev/null; printf ' '; ${statusLineCmd}`
    };
    console.log('  Status: [LENA] badge chained to existing statusLine');
  } else {
    console.log('  Status: [LENA] badge already in statusLine (skipped)');
  }

  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2) + '\n');

  console.log('');
  console.log('LENA installed.');
  console.log('');
  console.log('  Skill: ~/.claude/skills/lena/SKILL.md');
  console.log('  Invoke: /lena in Claude Code');
  console.log('');
  console.log('Usage:');
  console.log('  /lena                    Activate LENA orchestrator');
  console.log('  /lena build auth system  Immediate orchestrated task');
  console.log('');
}

install();
