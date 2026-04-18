#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const SKILL_SRC = path.join(__dirname, 'skills', 'lena', 'SKILL.md');
const CLAUDE_SKILLS_DIR = path.join(os.homedir(), '.claude', 'skills', 'lena');
const SKILL_DEST = path.join(CLAUDE_SKILLS_DIR, 'SKILL.md');

function install() {
  if (!fs.existsSync(path.join(os.homedir(), '.claude'))) {
    console.error('Error: Claude Code not found. Install from https://claude.ai/code first.');
    process.exit(1);
  }

  if (!fs.existsSync(CLAUDE_SKILLS_DIR)) {
    fs.mkdirSync(CLAUDE_SKILLS_DIR, { recursive: true });
  }

  fs.copyFileSync(SKILL_SRC, SKILL_DEST);

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
