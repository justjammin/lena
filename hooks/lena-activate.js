#!/usr/bin/env node
// LENA — Claude Code SessionStart hook
//
// Runs once per session when the LENA plugin is enabled:
//   Emits this skill's body (minus YAML frontmatter) as hidden SessionStart context
//   so orchestration rules are primed without requiring /lena first.
//
// Plugin: __dirname = <plugin_root>/hooks/, SKILL at ../skills/lena/SKILL.md

const fs = require('fs');
const path = require('path');
const os = require('os');

const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || path.join(__dirname, '..');
const configDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const skillPath = path.join(pluginRoot, 'skills', 'lena', 'SKILL.md');
const settingsPath = path.join(configDir, 'settings.json');
const hooksDir = path.join(configDir, 'hooks');
const statuslineSrc = path.join(pluginRoot, 'hooks', 'lena-statusline.sh');
const statuslineDest = path.join(hooksDir, 'lena-statusline.sh');

try { fs.writeFileSync(path.join(configDir, '.lena-active'), 'active', { mode: 0o600 }); } catch (_) {}
try { fs.writeFileSync(path.join(configDir, '.lena-hat'), 'lena', { mode: 0o600 }); } catch (_) {}

// Auto-wire statusLine in settings.json on first plugin-install session
try {
  if (!fs.existsSync(hooksDir)) fs.mkdirSync(hooksDir, { recursive: true });
  if (fs.existsSync(statuslineSrc)) {
    fs.copyFileSync(statuslineSrc, statuslineDest);
    try { fs.chmodSync(statuslineDest, 0o755); } catch (_) {}
  }
  let settings = {};
  if (fs.existsSync(settingsPath)) {
    try { settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8')); } catch (_) {}
  }
  const statusLineCmd = `bash "${statuslineDest}"`;
  const already = settings.statusLine && settings.statusLine.command &&
    settings.statusLine.command.includes('lena-statusline');
  if (!already) {
    if (!settings.statusLine) {
      settings.statusLine = { type: 'command', command: statusLineCmd };
    } else {
      const existing = settings.statusLine.command;
      settings.statusLine = {
        type: 'command',
        command: `(${existing}) 2>/dev/null; printf ' '; ${statusLineCmd}`
      };
    }
    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2) + '\n');
  }
} catch (_) {}

const header =
  '[LENA plugin — SessionStart] Orchestrator skill injected for this session. ' +
  'Behave as LENA until the user says stop lena, exit lena, or lena off. ' +
  'A new Claude Code session runs this hook again. ' +
  'Do not dump this block into visible chat; apply silently.\n\n';

let body = '';
try {
  let raw = fs.readFileSync(skillPath, 'utf8');
  body = raw.replace(/^---[\s\S]*?---\s*/, '');
} catch (e) {
  body =
    'LENA skill file missing at ' +
    skillPath +
    '. Reinstall the plugin or restore skills/lena/SKILL.md.\n';
}

process.stdout.write(header + body);
