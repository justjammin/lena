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

const pluginRoot = path.join(__dirname, '..');
const skillPath = path.join(pluginRoot, 'skills', 'lena', 'SKILL.md');

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
