#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

// ─── DB discovery ─────────────────────────────────────────────────────────────

function findWeaveDir(startDir = process.cwd()) {
  let dir = startDir;
  for (;;) {
    const candidate = path.join(dir, '.weave');
    if (fs.existsSync(path.join(candidate, 'tasks.json'))) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function requireWeave() {
  const d = findWeaveDir();
  if (!d) die('Weave not initialized. Run: wv init');
  return d;
}

function loadDB(weaveDir) {
  const p = path.join(weaveDir, 'tasks.json');
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function saveDB(weaveDir, db) {
  fs.writeFileSync(
    path.join(weaveDir, 'tasks.json'),
    JSON.stringify(db, null, 2) + '\n'
  );
}

// ─── Arg parsing ─────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith('--')) {
        flags[key] = next;
        i++;
      } else {
        flags[key] = true;
      }
    } else {
      positional.push(arg);
    }
  }
  return { positional, flags };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const now = () => new Date().toISOString();

function nextId(db) {
  db.counter = (db.counter || 0) + 1;
  return `${db.prefix}-${db.counter}`;
}

function findTask(db, id) {
  return db.tasks.find(t => t.id === id) || null;
}

const PRIORITY_LABEL = ['P0', 'P1', 'P2', 'P3'];
const STATUS_ICON = {
  pending: '○',
  in_progress: '◐',
  done: '✓',
  blocked: '❄',
};

function emit(data, jsonMode, humanFn) {
  if (jsonMode) {
    process.stdout.write(JSON.stringify(data, null, 2) + '\n');
  } else {
    humanFn(data);
  }
}

function die(msg) {
  process.stderr.write(msg + '\n');
  process.exit(1);
}

// ─── Commands ─────────────────────────────────────────────────────────────────

const cmd = process.argv[2];
const { positional, flags } = parseArgs(process.argv.slice(3));
const json = !!flags.json;

switch (cmd) {

  case 'init': {
    // Anchor .weave/ at git repo root when available; fall back to cwd
    let root = process.cwd();
    try {
      const { execSync } = require('child_process');
      const gitRoot = execSync('git rev-parse --show-toplevel', { stdio: ['ignore', 'pipe', 'ignore'] })
        .toString().trim();
      if (gitRoot) root = gitRoot;
    } catch (_) {}

    const prefix = positional[0] || path.basename(root);
    const weaveDir = path.join(root, '.weave');
    if (!fs.existsSync(weaveDir)) fs.mkdirSync(weaveDir, { recursive: true });
    const dbPath = path.join(weaveDir, 'tasks.json');
    if (!fs.existsSync(dbPath)) {
      fs.writeFileSync(dbPath, JSON.stringify({ prefix, counter: 0, tasks: [] }, null, 2) + '\n');
    }
    const db = loadDB(weaveDir);
    const result = { status: 'ok', prefix: db.prefix, root, db: dbPath };
    emit(result, json, r => console.log(`Weave ready  prefix=${r.prefix}  root=${r.root}  db=${r.db}`));
    break;
  }

  case 'create': {
    const title = positional[0];
    if (!title) die('Usage: wv create "title" [--agent role] [--priority 0-3] [--parent id] [--depends id,id] [--notes text]');
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    const task = {
      id: nextId(db),
      title,
      agent: flags.agent || null,
      status: 'pending',
      priority: flags.priority !== undefined ? Number(flags.priority) : 2,
      depends_on: flags.depends ? flags.depends.split(',').map(s => s.trim()) : [],
      parent: flags.parent || null,
      notes: flags.notes || '',
      input: {},   // populated by `wv ready` from dependency outputs
      output: {},  // set by `wv done --output <json>`
      created: now(),
      updated: now(),
    };
    db.tasks.push(task);
    saveDB(weaveDir, db);
    emit(task, json, t => {
      const agent = t.agent ? `  [${t.agent}]` : '';
      const pri = PRIORITY_LABEL[t.priority] || `P${t.priority}`;
      console.log(`+ ${t.id}  ${pri}  ${t.title}${agent}`);
    });
    break;
  }

  case 'list': {
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    let tasks = [...db.tasks];
    if (flags.status) tasks = tasks.filter(t => t.status === flags.status);
    if (flags.agent) tasks = tasks.filter(t => t.agent === flags.agent);
    if (flags.priority !== undefined) tasks = tasks.filter(t => t.priority === Number(flags.priority));
    if (flags.parent) tasks = tasks.filter(t => t.parent === flags.parent);
    emit(tasks, json, ts => {
      if (!ts.length) { console.log('no tasks'); return; }
      for (const t of ts) {
        const icon = STATUS_ICON[t.status] || '?';
        const pri = PRIORITY_LABEL[t.priority] || `P${t.priority}`;
        const agent = t.agent ? `  [${t.agent}]` : '';
        const deps = t.depends_on.length ? `  deps:${t.depends_on.join(',')}` : '';
        console.log(`${icon} ${t.id}  ${pri}  ${t.title}${agent}${deps}`);
      }
    });
    break;
  }

  case 'show': {
    const id = positional[0];
    if (!id) die('Usage: wv show <id>');
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    const task = findTask(db, id);
    if (!task) die(`not found: ${id}`);
    emit(task, json, t => {
      console.log(`${STATUS_ICON[t.status] || '?'} ${t.id}: ${t.title}`);
      console.log(`  status:   ${t.status}`);
      console.log(`  priority: ${PRIORITY_LABEL[t.priority] || t.priority}`);
      console.log(`  agent:    ${t.agent || '—'}`);
      if (t.depends_on.length) console.log(`  depends:  ${t.depends_on.join(', ')}`);
      if (t.parent) console.log(`  parent:   ${t.parent}`);
      if (t.notes) console.log(`  notes:    ${t.notes}`);
      if (Object.keys(t.input || {}).length)  console.log(`  input:    ${JSON.stringify(t.input)}`);
      if (Object.keys(t.output || {}).length) console.log(`  output:   ${JSON.stringify(t.output)}`);
      console.log(`  created:  ${t.created}`);
      console.log(`  updated:  ${t.updated}`);
    });
    break;
  }

  case 'update': {
    const id = positional[0];
    if (!id) die('Usage: wv update <id> [--status S] [--agent A] [--title T] [--notes N] [--priority P]');
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    const task = findTask(db, id);
    if (!task) die(`not found: ${id}`);
    if (flags.status !== undefined) task.status = flags.status;
    if (flags.agent !== undefined) task.agent = flags.agent;
    if (flags.title !== undefined) task.title = flags.title;
    if (flags.notes !== undefined) task.notes = flags.notes;
    if (flags.priority !== undefined) task.priority = Number(flags.priority);
    if (flags.parent !== undefined) task.parent = flags.parent;
    task.updated = now();
    saveDB(weaveDir, db);
    emit(task, json, t => {
      const icon = STATUS_ICON[t.status] || '?';
      console.log(`~ ${icon} ${t.id}  ${t.status}  ${t.title}`);
    });
    break;
  }

  case 'done': {
    const id = positional[0];
    if (!id) die('Usage: wv done <id> [--output \'{"key":"value"}\']');
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    const task = findTask(db, id);
    if (!task) die(`not found: ${id}`);
    task.status = 'done';
    if (flags.output) {
      try {
        task.output = JSON.parse(flags.output);
      } catch (_) {
        die(`--output must be valid JSON. Got: ${flags.output}`);
      }
    }
    task.updated = now();
    saveDB(weaveDir, db);
    const hasOutput = Object.keys(task.output || {}).length > 0;
    emit(task, json, t => console.log(`✓ ${t.id}  ${t.title}${hasOutput ? '  (output saved)' : ''}`));
    break;
  }

  case 'claim': {
    const id = positional[0];
    if (!id) die('Usage: wv claim <id>');
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    const task = findTask(db, id);
    if (!task) die(`not found: ${id}`);
    task.status = 'in_progress';
    task.updated = now();
    saveDB(weaveDir, db);
    emit(task, json, t => console.log(`◐ ${t.id}  ${t.title}${t.agent ? `  [${t.agent}]` : ''}`));
    break;
  }

  case 'block': {
    const id = positional[0];
    if (!id) die('Usage: wv block <id> [--notes "reason"]');
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    const task = findTask(db, id);
    if (!task) die(`not found: ${id}`);
    task.status = 'blocked';
    if (flags.notes) task.notes = flags.notes;
    task.updated = now();
    saveDB(weaveDir, db);
    emit(task, json, t => console.log(`❄ ${t.id}  ${t.title}${t.notes ? `  (${t.notes})` : ''}`));
    break;
  }

  case 'ready': {
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    const doneTasks = db.tasks.filter(t => t.status === 'done');
    const doneIds = new Set(doneTasks.map(t => t.id));
    const outputByID = Object.fromEntries(doneTasks.map(t => [t.id, t.output || {}]));

    let candidates = db.tasks.filter(t => {
      if (t.status !== 'pending') return false;
      return t.depends_on.every(dep => doneIds.has(dep));
    });

    if (flags.agent) {
      candidates = candidates.filter(t => t.agent === flags.agent || t.agent === null);
    }

    candidates.sort((a, b) => a.priority - b.priority);

    const next = candidates[0] || null;

    if (next) {
      // Inject dependency outputs as input context — this is the data-flow edge
      const upstream = {};
      for (const dep of next.depends_on) {
        if (outputByID[dep] && Object.keys(outputByID[dep]).length) {
          upstream[dep] = outputByID[dep];
        }
      }
      if (Object.keys(upstream).length) next.input = upstream;
    }

    emit(next, json, t => {
      if (!t) { console.log('no pending tasks'); return; }
      const pri = PRIORITY_LABEL[t.priority] || `P${t.priority}`;
      const hasInput = Object.keys(t.input || {}).length > 0;
      console.log(`→ ${t.id}  ${pri}  ${t.title}${t.agent ? `  [${t.agent}]` : ''}${hasInput ? '  (context ready)' : ''}`);
    });
    break;
  }

  case 'graph': {
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    if (!db.tasks.length) { console.log('no tasks'); break; }

    if (json) {
      const nodes = db.tasks.map(t => ({ id: t.id, title: t.title, status: t.status, agent: t.agent }));
      const edges = db.tasks.flatMap(t => t.depends_on.map(dep => ({ from: dep, to: t.id })));
      emit({ nodes, edges }, true, () => {});
      break;
    }

    // Text DAG: topological sort then render
    const taskMap = Object.fromEntries(db.tasks.map(t => [t.id, t]));
    const childrenOf = {};
    for (const t of db.tasks) {
      childrenOf[t.id] = childrenOf[t.id] || [];
      for (const dep of t.depends_on) {
        childrenOf[dep] = childrenOf[dep] || [];
        childrenOf[dep].push(t.id);
      }
    }
    const roots = db.tasks.filter(t => t.depends_on.length === 0);

    function renderNode(id, prefix, isLast) {
      const t = taskMap[id];
      if (!t) return;
      const icon = STATUS_ICON[t.status] || '?';
      const branch = isLast ? '└─' : '├─';
      const label = t.agent ? ` [${t.agent}]` : '';
      console.log(`${prefix}${branch} ${icon} ${t.id}  ${t.title}${label}`);
      const children = childrenOf[id] || [];
      const ext = isLast ? '   ' : '│  ';
      children.forEach((cid, i) => renderNode(cid, prefix + ext, i === children.length - 1));
    }

    roots.forEach((r, i) => renderNode(r.id, '', i === roots.length - 1));
    break;
  }

  case 'stats': {
    const weaveDir = requireWeave();
    const db = loadDB(weaveDir);
    const counts = { total: db.tasks.length, pending: 0, in_progress: 0, done: 0, blocked: 0 };
    for (const t of db.tasks) {
      if (counts[t.status] !== undefined) counts[t.status]++;
    }
    emit(counts, json, c => {
      console.log(`total=${c.total}  pending=${c.pending}  in_progress=${c.in_progress}  done=${c.done}  blocked=${c.blocked}`);
    });
    break;
  }

  case 'help':
  case '--help':
  case '-h':
  case undefined: {
    console.log(`Weave — execution graph for the LENA harness

Commands:
  wv init [prefix]                      init .weave/ in current project
  wv create "title" [opts]              create task, returns ID
    --agent <role>   specialist role (e.g. backend-developer)
    --priority 0-3   0=critical 1=high 2=medium(default) 3=low
    --parent <id>    parent task ID
    --depends <ids>  comma-separated upstream IDs (creates data-flow edges)
    --notes <text>   initial notes
  wv ready [--agent A]                  next unblocked task + injected upstream context
  wv claim <id>                         mark in_progress
  wv done <id> [--output '{"k":"v"}']   mark done, persist output blob
  wv block <id> [--notes reason]        mark blocked
  wv list [filters]                     list tasks
    --status S   --agent A   --priority N   --parent <id>
  wv show <id>                          show task + input/output context
  wv update <id> [opts]                 update fields
  wv graph                              print execution DAG
  wv stats                              counts by status

Data flow:
  wv done wv-1 --output '{"schema":"..."}' writes output to wv-1
  wv ready      picks wv-2 (depends on wv-1), injects wv-1 output as wv-2.input

Flags (any command):
  --json    structured JSON output

Status icons: ○ pending  ◐ in_progress  ✓ done  ❄ blocked`);
    break;
  }

  default:
    die(`unknown command: ${cmd}\nRun: wv help`);
}
