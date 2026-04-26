#!/usr/bin/env node
// LENA — Claude Code SessionStart hook
//
// Runs once per session when the LENA plugin is enabled:
//   1. Injects SKILL.md body as hidden context so orchestration rules are primed.
//   2. Injects agent pool (scanned from disk, mtime-cached, 14-day ceiling).
//   3. Injects agent pool (scanned from disk, mtime-cached, 14-day ceiling).
//   4. Injects lightweight repo context (git stats, no MCP cost).
//
// Plugin: __dirname = <plugin_root>/hooks/, SKILL at ../skills/lena/SKILL.md

const fs   = require('fs');
const path = require('path');
const os   = require('os');
const { execSync } = require('child_process');

const pluginRoot   = process.env.CLAUDE_PLUGIN_ROOT || path.join(__dirname, '..');
const configDir    = process.env.CLAUDE_CONFIG_DIR  || path.join(os.homedir(), '.claude');
const skillPath    = path.join(pluginRoot, 'skills', 'lena', 'SKILL.md');
const settingsPath = path.join(configDir, 'settings.json');
const hooksDir     = path.join(configDir, 'hooks');
const statuslineSrc  = path.join(pluginRoot, 'hooks', 'lena-statusline.sh');
const statuslineDest = path.join(hooksDir, 'lena-statusline.sh');
const agentPoolCache = path.join(configDir, '.lena-agent-pool.json');
const projectDir     = process.env.CLAUDE_PROJECT_DIR || process.cwd();

// Agent directories to scan (global + workspace)
const AGENT_DIRS = [
  path.join(os.homedir(), '.claude', 'agents'),
  path.join(os.homedir(), '.cursor', 'agents'),
  path.join(projectDir, '.claude', 'agents'),
  path.join(projectDir, '.cursor', 'agents'),
].filter(d => { try { return fs.statSync(d).isDirectory(); } catch (_) { return false; } });

// Known built-in agents from SKILL.md — used to flag new/custom agents
const BUILTIN_AGENTS = new Set([
  'architect-reviewer','backend-developer','frontend-developer','fullstack-developer',
  'refactoring-specialist','debugger','error-detective','code-reviewer','dx-optimizer',
  'test-automator','database-administrator','database-optimizer','postgres-pro',
  'cloud-architect','kubernetes-specialist','documentation-engineer','technical-writer',
  'llm-architect','weave-planner',
]);

// Name-first category map — canonical for all known agents.
// Keyword fallback handles new agents installed in the future.
const NAME_CAT = {
  'architect-reviewer':      'Architecture',
  'microservices-architect': 'Architecture',
  'api-designer':            'Architecture',
  'backend-developer':       'Implementation',
  'frontend-developer':      'Implementation',
  'fullstack-developer':     'Implementation',
  'python-pro':              'Implementation',
  'golang-pro':              'Implementation',
  'javascript-pro':          'Implementation',
  'typescript-pro':          'Implementation',
  'fastapi-developer':       'Implementation',
  'django-developer':        'Implementation',
  'laravel-specialist':      'Implementation',
  'symfony-specialist':      'Implementation',
  'php-pro':                 'Implementation',
  'react-specialist':        'Implementation',
  'mcp-developer':           'Implementation',
  'ui-designer':             'Implementation',
  'debugger':                'Debugging',
  'error-detective':         'Debugging',
  'code-reviewer':           'Code Review',
  'refactoring-specialist':  'Code Review',
  'legacy-modernizer':       'Code Review',
  'dx-optimizer':            'Performance',
  'test-automator':          'Testing',
  'database-administrator':  'Database',
  'database-optimizer':      'Database',
  'postgres-pro':            'Database',
  'data-engineer':           'Database',
  'cloud-architect':         'DevOps',
  'kubernetes-specialist':   'DevOps',
  'git-workflow-manager':    'DevOps',
  'documentation-engineer':  'Documentation',
  'readme-generator':        'Documentation',
  'technical-writer':        'Documentation',
  'llm-architect':           'ML/AI',
  'machine-learning-engineer':'ML/AI',
  'ml-engineer':             'ML/AI',
  'data-scientist':          'ML/AI',
  'data-analyst':            'ML/AI',
  'expo-react-native-expert':'Mobile',
  'mobile-app-developer':    'Mobile',
  'mobile-developer':        'Mobile',
  'swift-expert':            'Mobile',
  'ai-writing-auditor':      'Content/Writing',
  'content-marketer':        'Content/Writing',
  'human-lyrics-writer':     'Content/Writing',
  'suno-prompt-engineer':    'Content/Writing',
  'competitive-analyst':     'Research/Analysis',
  'research-analyst':        'Research/Analysis',
  'trend-analyst':           'Research/Analysis',
  'project-idea-validator':  'Research/Analysis',
  'fintech-engineer':        'Enterprise/Domain',
  'm365-admin':              'Enterprise/Domain',
  'iot-engineer':            'Enterprise/Domain',
  'agent-organizer':         'Orchestration',
  'context-manager':         'Orchestration',
  'weave-planner':           'Orchestration',
  'workflow-orchestrator':   'Orchestration',
};

function categorizeByKeyword(name, desc) {
  const d = desc.toLowerCase();
  if (d.includes('llm') || d.includes('rag') || d.includes('machine learning')) return 'ML/AI';
  if (d.includes('database') || d.includes('postgres') || d.includes('sql') || d.includes('etl')) return 'Database';
  if (d.includes('mobile') || d.includes('ios') || d.includes('android') || d.includes('react native')) return 'Mobile';
  if (d.includes('kubernetes') || d.includes('cloud') && d.includes('infra')) return 'DevOps';
  if (d.includes('debug') || d.includes('diagnose') || d.includes('root cause')) return 'Debugging';
  if (d.includes('test framework') || d.includes('test script') || d.includes('ci/cd')) return 'Testing';
  if (d.includes('documentation') || d.includes('readme')) return 'Documentation';
  if (d.includes('competitor') || d.includes('trend') || d.includes('research')) return 'Research/Analysis';
  if (d.includes('content') || d.includes('lyrics') || d.includes('writing')) return 'Content/Writing';
  if (d.includes('payment') || d.includes('iot') || d.includes('microsoft 365')) return 'Enterprise/Domain';
  if (d.includes('system design') || name.includes('architect')) return 'Architecture';
  if (d.includes('code review') || d.includes('refactor') || d.includes('moderniz')) return 'Code Review';
  return 'Implementation';
}

function parseDescription(content) {
  // Quoted single-line: description: "text" or description: text
  let m = content.match(/^description:\s*["'](.+?)["']\s*$/m);
  if (m) return m[1].trim();
  // Unquoted single-line
  m = content.match(/^description:\s*([^>\n].+?)\s*$/m);
  if (m) return m[1].trim();
  // Block scalar (> or |): grab lines until next non-indented key
  m = content.match(/^description:\s*[>|]\s*\n((?:[ \t]+.+\n?)+)/m);
  if (m) return m[1].replace(/\n\s+/g, ' ').trim();
  return '';
}

// --- Agent Pool ----------------------------------------------------------

function newestMtime(dirs) {
  let newest = 0;
  for (const dir of dirs) {
    try {
      for (const f of fs.readdirSync(dir)) {
        if (!f.endsWith('.md')) continue;
        const mt = fs.statSync(path.join(dir, f)).mtimeMs;
        if (mt > newest) newest = mt;
      }
    } catch (_) {}
  }
  return newest;
}

function needsAgentPoolRefresh() {
  if (!fs.existsSync(agentPoolCache)) return true;
  try {
    const cacheMtime = fs.statSync(agentPoolCache).mtimeMs;
    if (Date.now() - cacheMtime > 14 * 24 * 60 * 60 * 1000) return true; // 14-day ceiling
    const agentMtime = newestMtime(AGENT_DIRS);
    return agentMtime > cacheMtime;
  } catch (_) { return true; }
}

function buildAgentPool() {
  const pool = {};   // category → [{name, src, isNew}]
  const seen = new Set();

  for (const dir of AGENT_DIRS) {
    let files;
    try { files = fs.readdirSync(dir).filter(f => f.endsWith('.md')); }
    catch (_) { continue; }

    for (const f of files) {
      const name = f.replace('.md', '');
      if (seen.has(name)) continue;   // deduplicate global/workspace overlap
      seen.add(name);

      let desc = '';
      try {
        const content = fs.readFileSync(path.join(dir, f), 'utf8');
        desc = parseDescription(content);
      } catch (_) {}

      const cat = NAME_CAT[name] || categorizeByKeyword(name, desc);
      if (!pool[cat]) pool[cat] = [];
      pool[cat].push({ name, src: path.basename(dir), isNew: !BUILTIN_AGENTS.has(name) });
    }
  }

  return { updated: new Date().toISOString(), dirs: AGENT_DIRS, pool };
}

function loadAgentPool() {
  let data;
  if (needsAgentPoolRefresh()) {
    data = buildAgentPool();
    try { fs.writeFileSync(agentPoolCache, JSON.stringify(data, null, 2) + '\n'); } catch (_) {}
  } else {
    try { data = JSON.parse(fs.readFileSync(agentPoolCache, 'utf8')); }
    catch (_) { data = buildAgentPool(); }
  }

  const { updated, pool } = data;
  const total = Object.values(pool).flat().length;
  const date  = (updated || '').slice(0, 10);

  const lines = [
    `## Available Agents (${total} agents · refreshed ${date})`,
    'Use these subagent_type values when dispatching. New/custom agents marked with *.',
  ];

  for (const [cat, agents] of Object.entries(pool).sort()) {
    const names = agents.map(a => a.isNew ? a.name + '*' : a.name).join(', ');
    lines.push(`${cat}: ${names}`);
  }

  const newAgents = Object.values(pool).flat().filter(a => a.isNew);
  if (newAgents.length) {
    lines.push(`\nNew/custom agents (*): ${newAgents.map(a => a.name).join(', ')}`);
    lines.push('Route these when description matches — treat like built-in agents.');
  }

  return lines.join('\n') + '\n';
}

// --- Repo Context --------------------------------------------------------
// Lightweight git-based analysis: zero MCP calls, ~5ms, always fresh.
// For deep structural analysis, LENA runs ctx_architecture + ctx_graph once
// and stores result in ctx_knowledge keyed by HEAD — zero cost after first session.

function loadRepoContext() {
  const lines = ['## Repo Context'];
  try {
    const run = (cmd) => execSync(cmd, { cwd: projectDir, timeout: 3000, stdio: ['ignore','pipe','ignore'] })
      .toString().trim();

    // Git basics
    try {
      const log = run('git log --oneline -3 2>/dev/null');
      if (log) lines.push('Recent commits:\n' + log.split('\n').map(l => '  ' + l).join('\n'));
    } catch (_) {}

    try {
      const stat = run('git diff --stat HEAD 2>/dev/null | tail -1');
      if (stat) lines.push('Working tree: ' + stat);
    } catch (_) {}

    try {
      const branch = run('git rev-parse --abbrev-ref HEAD 2>/dev/null');
      const head   = run('git rev-parse --short HEAD 2>/dev/null');
      if (branch) lines.push(`Branch: ${branch} @ ${head}`);
    } catch (_) {}

    // Hint: LENA will check ctx_knowledge for repo:overview keyed to HEAD in Step 0
  } catch (_) {
    lines.push('(git unavailable — no repo context)');
  }

  return lines.join('\n') + '\n';
}

// --- Main ----------------------------------------------------------------

try { fs.writeFileSync(path.join(configDir, '.lena-active'), 'active', { mode: 0o600 }); } catch (_) {}
try { fs.writeFileSync(path.join(configDir, '.lena-hat'), 'lena',   { mode: 0o600 }); } catch (_) {}

// Auto-wire statusLine in settings.json on first install
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
      settings.statusLine = {
        type: 'command',
        command: `(${settings.statusLine.command}) 2>/dev/null; printf ' '; ${statusLineCmd}`,
      };
    }
    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2) + '\n');
  }
} catch (_) {}

// Build SKILL body (strip YAML frontmatter)
let body = '';
try {
  body = fs.readFileSync(skillPath, 'utf8').replace(/^---[\s\S]*?---\s*/, '');
} catch (e) {
  body = `LENA skill file missing at ${skillPath}. Reinstall or restore skills/lena/SKILL.md.\n`;
}

const header =
  '[LENA plugin — SessionStart] Orchestrator skill injected for this session. ' +
  'Behave as LENA until the user says stop lena, exit lena, or lena off. ' +
  'A new Claude Code session runs this hook again. ' +
  'Do not dump this block into visible chat; apply silently.\n\n' +
  'Agent pool and repo context loaded below. ' +
  'Run ctx_session(load) + ctx_knowledge(wakeup) in Step 0 to restore prior session state.\n\n';

const agentPool   = loadAgentPool();
const repoContext = loadRepoContext();

process.stdout.write(header + body + '\n' + agentPool + '\n' + repoContext);
