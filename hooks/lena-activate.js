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

// Load wiki context directly — so Claude receives it without needing to call wiki-scribe.
// Fallback: if wiki unreadable, inject an error line so Claude can call wiki-scribe manually.
function loadWikiContext(projectDir) {
  const wikiDir = path.join(projectDir, 'wiki');
  try {
    if (!fs.existsSync(wikiDir)) {
      const now = new Date().toISOString();
      fs.mkdirSync(path.join(wikiDir, 'objects'), { recursive: true });
      fs.mkdirSync(path.join(wikiDir, 'refs'), { recursive: true });
      const schema = [
        '# Wiki Schema',
        '## Node types',
        'Decision, Pattern, Failure, Concept, Tool, Agent, Session',
        '## Relationship types',
        'USES: Decision,Pattern,Session → Tool,Concept',
        'DEPENDS_ON: Decision,Pattern → Decision,Pattern,Concept',
        'REPLACES: Tool,Pattern,Decision → Tool,Pattern,Decision',
        'PRODUCED_BY: Decision,Pattern,Failure,Concept → Agent',
        'CAUSED_BY: Failure → Decision,Pattern,Tool',
        'PART_OF: Concept,Tool,Agent → Concept,Tool',
        'CONTRADICTS: Decision,Pattern → Decision,Pattern',
        'VALIDATES: Pattern,Decision → Failure,Concept',
      ].join('\n');
      fs.writeFileSync(path.join(wikiDir, 'schema.md'), schema + '\n');
      fs.writeFileSync(path.join(wikiDir, 'index.md'), '# Wiki Index\n');
      fs.writeFileSync(path.join(wikiDir, 'relations.md'), '# Relations\n');
      fs.writeFileSync(path.join(wikiDir, 'log.md'), `## [${now}] init | wiki initialized\n`);
      return '## Prior Wiki Context\n(fresh wiki — initialized this session)\n';
    }

    const logPath   = path.join(wikiDir, 'log.md');
    const indexPath = path.join(wikiDir, 'index.md');

    let logTail = '';
    if (fs.existsSync(logPath)) {
      const lines = fs.readFileSync(logPath, 'utf8').split('\n').filter(l => l.startsWith('## ['));
      logTail = lines.slice(-5).join('\n');
    }

    let indexTail = '';
    if (fs.existsSync(indexPath)) {
      const lines = fs.readFileSync(indexPath, 'utf8').split('\n').filter(l => /^\[/.test(l));
      indexTail = lines.slice(-10).join('\n');
    }

    if (!logTail && !indexTail) {
      return '## Prior Wiki Context\n(wiki exists but empty — no prior sessions)\n';
    }

    let out = '## Prior Wiki Context\n';
    if (logTail)   out += '### Recent Sessions\n' + logTail + '\n';
    if (indexTail) out += '### Recent Nodes\n'    + indexTail + '\n';
    return out;
  } catch (e) {
    return `## Prior Wiki Context\n(wiki unreadable: ${e.message} — call Skill("lena:wiki-scribe", "load_context") as fallback)\n`;
  }
}

const projectDir  = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const wikiContext = loadWikiContext(projectDir);

const header =
  '[LENA plugin — SessionStart] Orchestrator skill injected for this session. ' +
  'Behave as LENA until the user says stop lena, exit lena, or lena off. ' +
  'A new Claude Code session runs this hook again. ' +
  'Do not dump this block into visible chat; apply silently.\n\n' +
  'Wiki context has been loaded below (## Prior Wiki Context). ' +
  'If that section is absent or shows an error, call Skill(skill="lena:wiki-scribe", args="load_context") as fallback.\n\n';

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

process.stdout.write(header + body + '\n' + wikiContext);
