# Module 19 — Git version control and responsible AI use

> **Exam objectives:** Linux+ 4.4 (given a scenario, use Git to manage
> versions) and 4.5 (summarize best practices for AI use).
> **Study time:** about 100 minutes, including the mission.
> **Mission:** `build_repo.sh` — a reviewable Git workflow: ignore rules,
> branch, merge, annotated tag, and a human-review record for AI-assisted code.

## What the exam expects

### Git (4.4)

- repositories: `git init`, `git clone`,
- the three trees: working directory, index (staging), repository,
- the commit cycle: `status`, `add`, `commit`,
- history: `log`, `show`, `diff`, `blame`,
- branches: `branch`, `checkout`/`switch`, `merge`, `rebase`,
- remotes: `remote`, `fetch`, `pull`, `push`,
- tags: lightweight and annotated,
- undoing: `restore`, `reset`, `revert`, `stash`,
- config: `user.name`, `user.email`, aliases, `.gitignore`,
- hooks and protected branches (concepts).

### AI best practices (4.5)

- human review of generated code and configuration,
- verification with tests and linters,
- no secrets or personal data in prompts,
- license and provenance awareness,
- documentation of AI assistance,
- prompt discipline: context, constraints, acceptance criteria,
- privacy, bias, and accuracy limits,
- never let an agent run destructive commands unreviewed.

## The Git model

Git stores **snapshots**, not diffs. Each commit points to a tree and a parent,
and is identified by a SHA-1/SHA-256 hash.

```
working directory  --git add-->  index (staging)  --git commit-->  repository
      ^                                                                  |
      +---------------------------- git checkout / restore --------------+
```

Three states of a file:

- **untracked** — never added,
- **modified** — changed since the last commit,
- **staged** — the change is in the index and will go into the next commit.

```bash
git status
git status -sb
git diff              # working tree vs index
git diff --staged     # index vs HEAD
git diff HEAD         # working tree vs last commit
```

## Configuration

```bash
git config --global user.name "Alice Example"
git config --global user.email "alice@example.com"
git config --global init.defaultBranch main
git config --global core.editor vim
git config --list --show-origin
```

Set `user.name`/`user.email` per repository when a shared machine needs
different identities. The email is recorded permanently in every commit.

## The daily cycle

```bash
git init -b main
git add app.py
git commit -m "Add application entry point"
git add -A
git commit -m "Add tests"
git log --oneline --graph --decorate
git show HEAD
git blame app.py
```

A good commit:

- contains one logical change,
- has a message that explains **why**, not just what,
- includes tests when behaviour changes,
- does not include secrets, build artifacts, or unrelated formatting.

Conventional prefixes (`feat:`, `fix:`, `docs:`, `chore:`) help automation
generate changelogs.

## `.gitignore`

```gitignore
*.env
*.tmp
__pycache__/
*.pyc
.venv/
node_modules/
dist/
*.log
```

`.gitignore` affects **untracked** files. If a secret is already tracked,
adding it to `.gitignore` does not remove it from history:

```bash
git rm --cached secrets.env
git commit -m "Stop tracking secrets.env"
# history rewrite (destructive, coordinate with the team):
git filter-repo --path secrets.env --invert-paths
```

Treat any committed secret as compromised: rotate it, then clean history.

## Branches

```bash
git branch
git branch feature/greeting
git switch feature/greeting
git switch -c feature/greeting    # create and switch
git switch main
git branch -d feature/greeting    # delete merged branch
git branch -D feature/greeting    # delete unmerged (careful)
```

A branch is a movable pointer to a commit. Creating one is cheap, which is why
short-lived feature branches are the norm.

### Merge versus rebase

```bash
git switch main
git merge --no-ff feature/greeting
git rebase main                   # replay feature commits on top of main
```

- **Merge** preserves history and creates a merge commit with `--no-ff`. It is
  the safe choice for shared branches.
- **Rebase** rewrites commits onto a new base for a linear history. Never
  rebase commits that others have already pulled.

Merge conflicts show as `<<<<<<<`, `=======`, `>>>>>>>` markers. Edit the file,
then `git add` and continue (`git merge --continue` or `git rebase
--continue`). `git merge --abort` returns to the previous state.

## Remotes

```bash
git remote add origin git@example.com:team/app.git
git remote -v
git fetch origin
git pull --ff-only origin main
git push -u origin main
git push origin feature/greeting
```

`fetch` downloads without changing your branch; `pull` is fetch plus merge (or
rebase). `--ff-only` refuses to create a surprise merge commit. Protected
branches on the server reject direct pushes and require review plus passing CI.

## Tags

```bash
git tag v1.0.0                                  # lightweight
git tag -a v1.0.0 -m "Release 1.0.0"            # annotated
git tag
git show v1.0.0
git push origin v1.0.0
git push --tags
```

Annotated tags store a message, tagger, and date — use them for releases.
Lightweight tags are just pointers for local bookkeeping.

## Undoing

| Goal | Command |
|---|---|
| discard unstaged changes to a file | `git restore file` |
| unstage a file | `git restore --staged file` |
| amend the last commit message | `git commit --amend` |
| undo a commit with a new commit | `git revert HEAD` |
| move the branch back, keep changes | `git reset --soft HEAD~1` |
| move the branch back, discard changes | `git reset --hard HEAD~1` |
| save work temporarily | `git stash` / `git stash pop` |
| recover a lost commit | `git reflog` + `git reset --hard <hash>` |

`reset --hard` destroys uncommitted work. `revert` is the safe public undo
because it does not rewrite history.

## Hooks

Hooks are scripts in `.git/hooks/` that run at points in the workflow:

- `pre-commit` — lint, format, secret scan,
- `commit-msg` — enforce a message format,
- `pre-push` — run tests,
- `post-receive` — deploy (server side).

Hooks are local and can be bypassed with `--no-verify`; server-side checks are
the real gate.

## AI-assisted work: the rules

AI tools write plausible code. Plausible is not correct. The exam objective is
about **discipline**, not tool names.

### Before you prompt

- State the goal, constraints, environment, and acceptance criteria.
- Provide only the context needed; never paste secrets, customer data, or
  proprietary code you are not allowed to share.
- Ask for a small, testable change rather than a rewrite.

### After you generate

1. **Read every line.** If you cannot explain it, do not ship it.
2. **Run the tests** and add tests for new behaviour.
3. **Lint and type-check** (`ruff`, `shellcheck`, `mypy`).
4. **Check dependencies and licences** — generated code may import a package
   with an incompatible licence.
5. **Scan for secrets** and for prompt-injected instructions in fetched content.
6. **Review security-sensitive code by hand** — auth, crypto, permissions,
   shell execution, deserialization.
7. **Document the assistance** in the commit or a review note.

### What never to do

- paste credentials, keys, or customer data into a prompt,
- let an agent run `rm -rf`, `dd`, `git push --force`, or cloud commands
  without review,
- trust generated facts, version numbers, or API signatures without checking,
- accept code you cannot maintain,
- use AI output as the only test of correctness,
- ignore licence and attribution requirements.

### A review checklist to commit

```markdown
# AI assistance review

- [ ] Human reviewed every changed line
- [ ] Local tests pass
- [ ] No secrets, tokens, or personal data
- [ ] License and source of any generated code verified
- [ ] Documentation updated
- [ ] Security-sensitive paths reviewed manually
```

Recording the checklist in the repository turns “we reviewed it” into evidence.

## Mission 19 — what you build

The folder is a small application with `app.py`, `README.md`, a test,
`secrets.env`, and `notes.tmp`.

Create an executable `build_repo.sh` that:

1. runs `git init -b main` and sets local `user.name` and `user.email`,
2. writes `.gitignore` covering `*.env`, `*.tmp`, `__pycache__/`, `*.pyc`, and
   `.venv/`,
3. commits the app, README, tests, `.gitignore`, and `build_repo.sh` so the tree
   ends clean,
4. creates `feature/greeting`, adds a `farewell()` function, and commits it,
5. checks out main and merges the branch with `--no-ff`,
6. creates annotated tag `v1.0.0`,
7. adds `docs/ai-review.md` with a human-review checklist covering human
   review, local tests, no secrets, license/source, and documentation, then
   commits it.

The final working tree must be clean, `secrets.env` and `notes.tmp` must never
be tracked, and no `API_KEY` may appear in tracked history. Run
`python3 main.py verify 19`.

## Exam traps

- `.gitignore` does not untrack a file that is already committed.
- `git pull` can create a merge commit you did not intend; prefer
  `--ff-only` or `--rebase`.
- Rebasing a shared branch breaks everyone else's history.
- `reset --hard` discards work irreversibly (except via reflog, briefly).
- A tag is not pushed by a normal `git push`.
- `merge --no-ff` preserves the branch topology; a fast-forward hides it.
- Committing `.env` files is the most common secret leak.
- Committed secrets remain in history until rewritten and rotated.
- AI output needs tests, review, and licence checks like any other code.

## Check yourself

1. What are the three trees in Git?
2. What is the difference between `git diff` and `git diff --staged`?
3. When would you use `rebase` instead of `merge`, and when must you not?
4. How do you stop tracking a file without deleting it?
5. What does `git revert` do that `git reset` does not?
6. Which command creates a release tag with a message?
7. Why is `.gitignore` not a secret-protection mechanism?
8. Which five checks belong in an AI-assisted change review?

## Going deeper

- Deliberately commit a fake secret, then remove it with `git filter-repo` and
  verify with `git log -S`.
- Practise a merge conflict and resolve it both with merge and with rebase.
- Add a `pre-commit` hook that runs `ruff` and a secret scanner.
- Write a short AI-use policy for a team and map each rule to a Git control.
