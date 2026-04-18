# Shipping LENA as a Standalone GitHub Project

Complete guide to publishing LENA so others can install via `npx lena-ai` or `claude plugin add`.

---

## Project Structure

```
lena/
├── README.md
├── CLAUDE.md                 # maintainer / repo context for Claude in this project
├── SHIPPING.md
├── LICENSE
├── package.json              # npm package — enables npx install
├── install.js                # install script run by npx
├── hooks/
│   ├── lena-activate.js      # SessionStart: injects SKILL.md into each session
│   ├── README.md
│   └── package.json          # CommonJS marker for node
├── skills/
│   └── lena/
│       └── SKILL.md          # the actual skill loaded by Claude Code
└── .claude-plugin/
    └── plugin.json           # skills + SessionStart hooks
```

---

## Step 1: Create the GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Name: `lena`
3. Visibility: Public
4. Initialize with no README (you already have one)

```bash
cd ~/lena
git init
git add .
git commit -m "feat: initial release of LENA AI orchestrator"
git branch -M main
git remote add origin https://github.com/justjammin/lena.git
git push -u origin main
```

---

## Step 2: Publish to npm (enables npx)

### First time setup

```bash
# Create npm account at npmjs.com if you don't have one
npm login
```

### Make install.js executable

```bash
chmod +x install.js
```

### Publish

```bash
cd ~/lena
npm publish
```

> Package name `lena-ai` must be available on npm. Check at `npmjs.com/package/lena-ai`.
> If taken, update `"name"` in `package.json` to something like `@justjammin/lena` (scoped package).

### Scoped package (if name is taken)

```bash
# In package.json, change:
# "name": "lena-ai"  →  "name": "@justjammin/lena"

npm publish --access public
```

Users then install with:
```bash
npx @justjammin/lena
```

---

## Step 3: Verify npx Install Works

```bash
# Test locally before publishing
node install.js

# Test via npx after publishing
npx lena-ai
# or
npx @justjammin/lena
```

Expected output:
```
LENA installed.

  Skill: ~/.claude/skills/lena/SKILL.md
  Invoke: /lena in Claude Code
```

---

## Step 4: Claude Code Plugin Marketplace

The `.claude-plugin/plugin.json` file registers LENA with Claude Code's plugin system.

Once your GitHub repo is public, users can install with:

```bash
claude plugin add justjammin/lena
```

### What plugin.json does

Claude Code reads `.claude-plugin/plugin.json` to discover skills, hooks, and metadata. The `"skills": "./skills/"` field tells Claude Code where to find skill files. The `"hooks"."SessionStart"` entry runs `hooks/lena-activate.js` so each new session injects `skills/lena/SKILL.md` (see `hooks/README.md`).

### Submitting to the marketplace

Claude Code's plugin marketplace is managed by Anthropic. To get listed:

1. Ensure your repo is public with a complete README
2. Submit at: [github.com/anthropics/claude-code](https://github.com/anthropics/claude-code) — open an issue or PR following their plugin submission process
3. Until listed, users can still install directly: `claude plugin add justjammin/lena`

---

## Step 5: Publishing Updates

```bash
# Bump version
npm version patch   # 1.0.0 → 1.0.1
npm version minor   # 1.0.0 → 1.1.0
npm version major   # 1.0.0 → 2.0.0

# Publish update
npm publish

# Push tag to GitHub
git push --follow-tags
```

---

## Step 6: Add a GitHub Release

```bash
gh release create v1.0.0 \
  --title "LENA v1.0.0" \
  --notes "Initial release. AI orchestrator for Claude Code."
```

---

## Install Methods Summary

After publishing, users have three options:

```bash
# Option 1: Claude Code native (recommended)
claude plugin add justjammin/lena

# Option 2: npx
npx lena-ai

# Option 3: Manual
mkdir -p ~/.claude/skills/lena
curl -o ~/.claude/skills/lena/SKILL.md \
  https://raw.githubusercontent.com/justjammin/lena/main/skills/lena/SKILL.md
```

---

## Checklist Before Shipping

- [ ] `SKILL.md` tested locally — `/lena` works in Claude Code
- [ ] `install.js` runs without errors: `node install.js`
- [ ] `package.json` has correct name, version, author, repository URL
- [ ] GitHub repo is public
- [ ] README clearly explains what LENA does and how to install
- [ ] LICENSE file present
- [ ] npm package published and `npx lena-ai` works end-to-end
- [ ] GitHub release created with version tag

---

## Troubleshooting

**`npx lena-ai` doesn't find the package**
→ Wait 1–2 minutes after `npm publish` for propagation. Run `npm view lena-ai` to verify.

**`claude plugin add` fails**
→ Ensure repo is public. Check `.claude-plugin/plugin.json` is valid JSON. Try `claude plugin add github.com/justjammin/lena`.

**Skill doesn't appear after install**
→ Restart Claude Code. Skills are loaded at session start.

**npm name taken**
→ Use scoped: `"name": "@justjammin/lena"` in package.json. Publish with `npm publish --access public`.
