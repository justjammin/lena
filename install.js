#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const LENA_SKILL_SRC_DIR     = path.join(__dirname, 'skills', 'lena');
const CLAUDE_DIR             = path.join(os.homedir(), '.claude');
const LENA_SKILL_DEST_DIR    = path.join(CLAUDE_DIR, 'skills', 'lena');
const SETTINGS_PATH          = path.join(CLAUDE_DIR, 'settings.json');
const HOOKS_DIR              = path.join(CLAUDE_DIR, 'hooks');
const ACTIVATE_SRC           = path.join(__dirname, 'hooks', 'lena-activate.js');
const ACTIVATE_DEST          = path.join(HOOKS_DIR, 'lena-activate.js');
const HOOK_COMMAND           = `node "${ACTIVATE_DEST}"`;
const STATUSLINE_SRC         = path.join(__dirname, 'hooks', 'lena-statusline.sh');
const STATUSLINE_DEST        = path.join(HOOKS_DIR, 'lena-statusline.sh');
const AGENTS_SRC_DIR         = path.join(__dirname, 'agents');
const AGENTS_DEST_DIR        = path.join(CLAUDE_DIR, 'agents');

function copyDirRecursive(src, dest) {
  if (!fs.existsSync(dest)) {
    fs.mkdirSync(dest, { recursive: true });
  }
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath  = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDirRecursive(srcPath, destPath);
    } else if (!entry.name.endsWith('.original.md')) {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function install() {
  if (!fs.existsSync(CLAUDE_DIR)) {
    console.error('Error: Claude Code not found. Install from https://claude.ai/code first.');
    process.exit(1);
  }

  // Copy LENA skill (entire directory — includes reference/ subdirectory)
  copyDirRecursive(LENA_SKILL_SRC_DIR, LENA_SKILL_DEST_DIR);

  // Copy harness-native agents to ~/.claude/agents/ (skip if no agents/ dir)
  if (fs.existsSync(AGENTS_SRC_DIR)) {
    if (!fs.existsSync(AGENTS_DEST_DIR)) {
      fs.mkdirSync(AGENTS_DEST_DIR, { recursive: true });
    }
    const agentFiles = fs.readdirSync(AGENTS_SRC_DIR).filter(f => f.endsWith('.md'));
    for (const file of agentFiles) {
      fs.copyFileSync(
        path.join(AGENTS_SRC_DIR, file),
        path.join(AGENTS_DEST_DIR, file)
      );
    }
  }

  // Copy hook scripts to ~/.claude/hooks/
  if (!fs.existsSync(HOOKS_DIR)) {
    fs.mkdirSync(HOOKS_DIR, { recursive: true });
  }
  fs.copyFileSync(ACTIVATE_SRC, ACTIVATE_DEST);
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
    console.log('  Hook:  SessionStart already registered (skipped)');
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
  console.log('  Skill:  ~/.claude/skills/lena/ (SKILL.md + reference/)');
  console.log('');

  console.log('Usage:');
  console.log('  /lena                    Activate LENA orchestrator');
  console.log('  /lena build auth system  Immediate orchestrated task');
  console.log('  bd init                  Init Beads in a project');
  console.log('  bd prime                 Full Beads workflow reference');
  console.log('');
}

install();
