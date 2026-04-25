#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const SKILL_SRC        = path.join(__dirname, 'skills', 'lena', 'SKILL.md');
const WEAVE_SKILL_SRC  = path.join(__dirname, 'skills', 'weave', 'SKILL.md');
const CLAUDE_DIR       = path.join(os.homedir(), '.claude');
const CLAUDE_SKILLS_DIR       = path.join(CLAUDE_DIR, 'skills', 'lena');
const WEAVE_CLAUDE_SKILLS_DIR = path.join(CLAUDE_DIR, 'skills', 'weave');
const SKILL_DEST       = path.join(CLAUDE_SKILLS_DIR, 'SKILL.md');
const WEAVE_SKILL_DEST = path.join(WEAVE_CLAUDE_SKILLS_DIR, 'SKILL.md');
const SETTINGS_PATH    = path.join(CLAUDE_DIR, 'settings.json');
const HOOK_COMMAND     = `node "${path.join(__dirname, 'hooks', 'lena-activate.js')}"`;
const HOOKS_DIR        = path.join(CLAUDE_DIR, 'hooks');
const STATUSLINE_SRC   = path.join(__dirname, 'hooks', 'lena-statusline.sh');
const STATUSLINE_DEST  = path.join(HOOKS_DIR, 'lena-statusline.sh');
const WV_SRC           = path.join(__dirname, 'bin', 'wv');
const LOCAL_BIN        = path.join(os.homedir(), '.local', 'bin');
const WV_DEST          = path.join(LOCAL_BIN, 'wv');
const AGENTS_SRC_DIR   = path.join(__dirname, 'agents');
const AGENTS_DEST_DIR  = path.join(CLAUDE_DIR, 'agents');

function install() {
  if (!fs.existsSync(CLAUDE_DIR)) {
    console.error('Error: Claude Code not found. Install from https://claude.ai/code first.');
    process.exit(1);
  }

  // Copy LENA skill
  if (!fs.existsSync(CLAUDE_SKILLS_DIR)) {
    fs.mkdirSync(CLAUDE_SKILLS_DIR, { recursive: true });
  }
  fs.copyFileSync(SKILL_SRC, SKILL_DEST);

  // Copy Weave skill
  if (!fs.existsSync(WEAVE_CLAUDE_SKILLS_DIR)) {
    fs.mkdirSync(WEAVE_CLAUDE_SKILLS_DIR, { recursive: true });
  }
  fs.copyFileSync(WEAVE_SKILL_SRC, WEAVE_SKILL_DEST);

  // Install wv CLI to ~/.local/bin
  if (!fs.existsSync(LOCAL_BIN)) {
    fs.mkdirSync(LOCAL_BIN, { recursive: true });
  }
  fs.copyFileSync(WV_SRC, WV_DEST);
  try { fs.chmodSync(WV_DEST, 0o755); } catch (_) {}

  // Copy harness-native agents to ~/.claude/agents/
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
  console.log('LENA + Weave installed.');
  console.log('');
  console.log('  Skill:  ~/.claude/skills/lena/SKILL.md');
  console.log('  Skill:  ~/.claude/skills/weave/SKILL.md');
  console.log('  CLI:    ~/.local/bin/wv');
  for (const file of agentFiles) {
    console.log(`  Agent:  ~/.claude/agents/${file}`);
  }
  console.log('');

  // PATH warning if ~/.local/bin not on PATH
  const pathDirs = (process.env.PATH || '').split(':');
  if (!pathDirs.includes(LOCAL_BIN)) {
    console.log('  Note: add ~/.local/bin to your PATH to use wv:');
    console.log('    echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.zshrc');
    console.log('');
  }

  console.log('Usage:');
  console.log('  /lena                    Activate LENA orchestrator');
  console.log('  /lena build auth system  Immediate orchestrated task');
  console.log('  wv init                  Init Weave in a project');
  console.log('  wv help                  Weave CLI reference');
  console.log('');
}

install();
