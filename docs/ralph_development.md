# Ralph Development Guide

## Overview

Ralph is an autonomous AI development agent built on Claude Code. 
It runs locally on developer machines to assist with coding tasks through iterative development loops.

**Think of Ralph as**: An AI pair programmer that works autonomously on defined tasks while you monitor progress.

---

## Developer Onboarding

### Installation Checklist

- [ ] **Install Prerequisites**
  ```bash
  # macOS
  brew install node jq git coreutils tmux
  
  # Ubuntu/Debian
  sudo apt-get install nodejs npm jq git coreutils tmux
  ```

- [ ] **Install Claude Code CLI**
  ```bash
  npm install -g @anthropic-ai/claude-code
  ```

- [ ] **Get Anthropic API Key**
  - Configure Claude CLI: `claude init`

- [ ] **Install Ralph**
  ```bash
  git clone https://github.com/frankbria/ralph-claude-code.git
  cd ralph-claude-code
  ./install.sh
  ```
  
  This installs to `~/.local/bin/` (ensure it's in your PATH):
  ```bash
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  source ~/.bashrc
  ```

- [ ] **Verify Installation**
  ```bash
  ralph --help
  ralph-setup --help
  ```

- [ ] **Set Up Pre-Commit Hooks** (see Security section below)
  - Install gitleaks `brew install gitleaks`
  - Create a `.git/hooks/pre-commit` file that runs `gitleaks`

---

## Ralph File Structure

When you enable Ralph in a project, it creates a `.ralph/` directory:

```
your-project/
├── .ralph/                      # Ralph's workspace (DO NOT manually edit most files)
│   ├── PROMPT.md               # ✏️ YOU EDIT: High-level project goals and principles
│   ├── fix_plan.md             # ✏️ YOU EDIT: Task list Ralph executes
│   ├── AGENT.md                # 🤖 AUTO: Build/test commands (Ralph maintains)
│   ├── specs/                  # ✏️ YOU ADD: Detailed requirements (optional)
│   │   ├── api.md              #   - API specifications
│   │   ├── database.md         #   - Schema details
│   │   └── stdlib/             #   - Reusable patterns/conventions
│   ├── logs/                   # 🤖 AUTO: Execution logs (gitignored)
│   ├── .call_count             # 🤖 AUTO: API usage tracking
│   ├── .circuit_breaker_state  # 🤖 AUTO: Safety mechanism state
│   └── .claude_session_id      # 🤖 AUTO: Session continuity
├── .ralphrc                    # ⚙️ CONFIG: Project settings (use team defaults)
├── .gitignore                  # ✏️ YOU EDIT: Add Ralph-specific ignores
└── src/                        # Your application code
```

### Key Files Explained

| File | Purpose | You Should... |
|------|---------|---------------|
| **PROMPT.md** | High-level goals, tech stack, principles | Review and customize for your project |
| **fix_plan.md** | Prioritized TODO list with checkboxes | Add tasks, Ralph checks them off |
| **specs/** | Detailed requirements (API contracts, schemas, etc.) | Add files when PROMPT.md isn't detailed enough |
| **AGENT.md** | Build/run/test commands | Let Ralph maintain this (auto-updated) |
| **logs/** | Execution history | Review after Ralph runs, never commit |

### File Hierarchy

```
PROMPT.md (what are we building?)
    ↓
specs/ (detailed requirements)
    ↓
fix_plan.md (specific tasks to execute)
    ↓
AGENT.md (how to build/test)
```

---

## Getting Started with Ralph

### 1. Enable Ralph in Your Project

```bash
cd your-project/
ralph-enable
```

This wizard will:
- Detect your project type (Node.js, Python, etc.)
- Create `.ralph/` directory structure
- Generate initial `PROMPT.md` and `fix_plan.md`
- Set up `.ralphrc` with safe defaults

### 2. Configure Your Project

**Edit `.ralph/PROMPT.md`** - Define what Ralph should build:
```markdown
# Ralph Development Instructions

## Context
You are building a REST API for inventory management.

## Technology Stack
- Python 3.11+ with FastAPI
- PostgreSQL with SQLAlchemy
- pytest for testing

## Key Principles
- Write tests for all endpoints
- Follow REST conventions
- Use async/await throughout
```

**Edit `.ralph/fix_plan.md`** - Add specific tasks:
```markdown
## High Priority
- [ ] Set up FastAPI application structure
- [ ] Create database models for Product and Category
- [ ] Implement GET /products endpoint with pagination

## Medium Priority
- [ ] Add authentication with JWT
- [ ] Write integration tests
```

### 3. Run Ralph

```bash
cd your-project/
git checkout -b feature/your-task  # Always use a branch
ralph --monitor  # Starts with tmux monitoring dashboard
```

**Ralph will**:
- Read `PROMPT.md` and `fix_plan.md`
- Execute the highest priority uncompleted task
- Modify code, run tests, update documentation
- Check off completed tasks
- Loop until done or you stop it

**Stop Ralph**: Press `Ctrl+C` in the Ralph terminal

---

## Using Ralph Safely

Ralph is a powerful AI coding assistant. Follow these guidelines:

### Before You Start

- [ ] **Use a feature branch** - Never run Ralph on `main` or `develop`
- [ ] **Set safe limits** - Use team `.ralphrc` (max 50 API calls, 20min timeout)
- [ ] **Check your environment** - No production credentials in `.env`
- [ ] **Review the task list** - Understand what's in `.ralph/fix_plan.md`

### After Ralph Completes

- [ ] **Review all changes**: `git diff` - don't blindly trust AI output
- [ ] **Check for secrets**: Logs are auto-scanned by pre-commit hook
- [ ] **Test locally**: Ensure all tests pass
- [ ] **Normal PR process**: Ralph code needs same review as human code

### Code Review Checklist

Add to your PR description when using Ralph:

```markdown
## Ralph was used for this PR
- [ ] I've reviewed every file Ralph modified
- [ ] No credentials in code or logs
- [ ] Tests pass locally
- [ ] Ralph's changes align with the original task
- [ ] No unexpected file modifications (checked `git diff --stat`)
- [ ] `.ralph/logs/` not committed
```

## Security

### Security Model

Ralph operates with the **same permissions as you**, like any IDE or developer tool:
- Runs locally on your machine
- Uses your git credentials
- Subject to branch protection rules
- All code reviewed and tested before merging

### Threat Model

Since Ralph:
1. Runs **locally** (not in CI/CD)
2. Works on **feature branches** (protected by branch rules)
3. Produces code that's **reviewed** (like any developer)

The main risks are:
- **Accidental secret commits** (API keys in code/logs)
- **Runaway API costs** (Claude API is metered)
- **Data sent to Anthropic** (code leaves your machine)

### Mitigations in Place

| Risk | Mitigation |
|------|------------|
| **Secret leakage** | Pre-commit hooks scan all files with gitleaks |
| **Log commits** | `.ralph/logs/` in `.gitignore`, enforced by hook |
| **Runaway costs** | API call limits (50/hour), timeouts (20min) |
| **Code quality** | Same PR review process as human developers |
| **Data exposure** | Personal API keys (not shared), documented in onboarding |
| **Unauthorized changes** | Branch protection, required reviews |

### Security Checklist

When setting up a repo for Ralph:

- [ ] `.gitignore` includes Ralph runtime files
- [ ] Pre-commit hooks installed (gitleaks)
- [ ] Team `.ralphrc` with safe defaults committed
- [ ] Developers use personal Anthropic API keys
- [ ] PR template includes Ralph-specific checklist

---

## Setting Up Pre-Commit Secret Scanning

We use [gitleaks](https://github.com/gitleaks/gitleaks) to prevent secrets from being committed.

### 1. Install gitleaks

```bash
# macOS
brew install gitleaks

# Linux
# Download from https://github.com/gitleaks/gitleaks/releases
wget https://github.com/gitleaks/gitleaks/releases/download/v8.18.2/gitleaks_8.18.2_linux_x64.tar.gz
tar -xzf gitleaks_8.18.2_linux_x64.tar.gz
sudo mv gitleaks /usr/local/bin/
```

### 2. Add `.git/hooks/pre-commit` file

```bash
touch .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### 3. Run gitleaks as a pre-commit hook
Add this line to your pre-commit file:
```
git diff | gitleaks -v stdin
git diff --staged | gitleaks -v stdin
```

## Ignore ralph runtime files in `.gitignore`

Ensure that these Ralph-specific entries are git-ignored.

```gitignore
# Ralph runtime files - never commit
.ralph/logs/
.ralph/.call_count
.ralph/.last_reset
.ralph/.exit_signals
.ralph/.circuit_breaker_state
.ralph/.circuit_breaker_history
.ralph/.claude_session_id
.ralph/.response_analysis
.ralph/status.json
.ralph/live.log
```

### Manual Scan (Optional)

Scan entire repo history for leaked secrets:

```bash
gitleaks git .
```

---

## Best Practices

### DO

- Use Ralph for well-defined, isolated tasks
- Review all Ralph-generated code carefully
- Run tests after Ralph completes
- Keep `PROMPT.md` and `fix_plan.md` updated
- Use `ralph --monitor` for visibility
- Stop Ralph if it's stuck (circuit breaker will auto-halt)

### DON'T

- Run Ralph on `main` or production branches
- Commit `.ralph/logs/` directory
- Let Ralph run unattended overnight
- Skip code review because "AI wrote it"
- Store production credentials in `.env` while using Ralph

## Getting Help

- **Ralph Documentation**: https://github.com/frankbria/ralph-claude-code
