## Agent skills

### Issue tracker

Issues and specs live in this repo’s GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: root `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.

<!-- BEGIN USER AUTO-COMMIT POLICY -->
## Automatic Commit Policy

User preference: `AI_AUTO_COMMIT=meaningful`.

After completing authorized work, automatically commit meaningful, coherent
changes that improve code, configuration, tests or documentation. Run relevant
checks and review the diff first. If nothing worthwhile changed, do not create
an empty commit or manufacture edits just to commit.

Stage only the agent's task changes; preserve unrelated edits. Never include
secrets, local credentials, runtime data or generated build artifacts. Use a
focused Conventional Commit message and report the commit and verification.
If relevant checks fail, fix them before committing, or report the blocker.

This is standing authorization for local commits, not for new product scope,
deployment, publishing releases, destructive Git operations or remote pushes.
Push only when the user requests it or an existing task explicitly authorizes
it. Never force-push as a routine completion step. Specific later user
instructions override this default. Follow this policy even if the environment
variable is unavailable; environment variables alone do not govern agents.
<!-- END USER AUTO-COMMIT POLICY -->
