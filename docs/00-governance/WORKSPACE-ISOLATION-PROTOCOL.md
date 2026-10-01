# WORKSPACE ISOLATION PROTOCOL

| | |
|---|---|
| Document ID | `GOV-ISO-001` |
| Status | **Active** |
| Reason | Two AI agents are working in one workspace |

---

## 1. The situation

Two agents share the directory `d:\Parker\Projects\sih\sih26171\`:

| Agent | Owns | Goal |
|---|---|---|
| **Agent 1** | The v1 prototype (`backend/`, `extension/`, `frontend/`, `docs/`) | Continue/fix the original prototype |
| **Agent 2** (me) | `sih-agent-v2/` only | Governed rebuild per the SDLC process |

## 2. The risk (why this document exists)

The v2 project was created **inside** the v1 repository. That creates three concrete collision
risks:

1. **`git add -A` from Agent 1 would commit the entire v2 tree into the v1 repository.** The v2
   folder is currently *untracked* — it will be swept up by any blanket add.
2. **Broad searches from either agent return the other's files**, producing confusing or
   misleading results.
3. **`git status` noise.** v1 already carries ~176 dirty entries; adding v2 makes the signal
   unreadable for both agents.

## 3. Territory rules (binding)

| Rule | Statement |
|---|---|
| **I-1** | Agent 2 (me) treats everything outside `sih-agent-v2/` as **read-only**. I have made no edits to v1, and I will continue to make none. |
| **I-2** | Agent 1 must treat `sih-agent-v2/` as **off-limits**: no reads, no writes, no builds, no test collection, no searches. |
| **I-3** | Shared truth flows one way: if Agent 1 changes something material in v1, the Product Owner tells Agent 2. Decisions in v1 do **not** automatically flow into v2 — v2 is a rebuild against the ledger, not a mirror. |
| **I-4** | Neither agent edits the other's files. Ever. |

## 4. Required protections (apply to the v1 repo)

These are v1-side changes. **I have deliberately not applied them myself** (rule I-1). Agent 1 or
the Product Owner should apply them.

### P-1 — Stop v2 being committed into v1  `[HIGH]`

Add this line to `d:\Parker\Projects\sih\sih26171\.gitignore`:

```gitignore
sih-agent-v2/
```

Without it, one `git add -A` in the v1 repo commits the entire v2 project into v1's history.

### P-2 — Stop a browser profile being committed  `[URGENT — SECURITY]`

`backend/scratch/` contains a **live Chrome user-data-dir**: `Cookies`, `Login Data`, `History`,
`Web Data`, `Local State`. It is **not** currently gitignored.

`backend/scratch/` is untracked today, so the safest action is deletion — but if Agent 1 still
needs it, add:

```gitignore
backend/scratch/
```

One careless `git add -A` otherwise commits real session cookies into the repository.

### P-3 — Remove the stale duplicate  `[MEDIUM]`

`.kilo/worktrees/cooperative-cheque/` is a complete stale copy of `backend/` + `frontend/`. It
will mislead every future search, build, and test run from either agent. Recommend deletion once
Agent 1 confirms nothing depends on it.

## 5. Optional: hard physical separation  `[RECOMMENDED]`

`.gitignore` fixes the git risk but not the search/build risk. The clean fix is to move v2 out of
the v1 repo entirely:

```powershell
Move-Item 'd:\Parker\Projects\sih\sih26171\sih-agent-v2' `
          'd:\Parker\Projects\sih\sih-agent-v2'
```

Then `d:\Parker\Projects\sih\` contains two independent projects:

```
sih\sih26171\        ← v1 prototype   (Agent 1)
sih\sih-agent-v2\    ← governed rebuild (Agent 2)
```

Benefits: separate git histories, no search cross-contamination, no build interference, and the
v2 work becomes independently presentable — which matters, because a clean repository is part of
what the jury reads as engineering maturity.

**Caveat:** if the move is performed, tell me immediately. My working directory is anchored to the
v1 root, so I need to know the new location before continuing.

## 6. Current status

| Item | State |
|---|---|
| v1 source files edited by Agent 2 | **None** — verified. One *additive* `.gitignore` line only, under explicit Product Owner authorisation. |
| v2 created | ✅ 5 governance documents, **no production code** |
| **P-1** — `sih-agent-v2/` ignored | ✅ Applied — retained as a safety net even though v2 has since moved out of the repo |
| **P-2** — `backend/scratch/` ignored | ✅ **Applied** — verified via `git check-ignore -v` (`.gitignore:17`) |
| **P-3** — stale worktree | ⬜ Pending — safe to delete once Agent 1 confirms nothing depends on it |
| **Physical separation** | ✅ **Completed** — v2 now lives at `d:\Parker\Projects\sih\sih-agent-v2` |

## 7. Post-move state (verified)

```
d:\Parker\Projects\sih\
├─ sih26171\        ← v1 prototype (Agent 1)  · own git history
└─ sih-agent-v2\    ← governed rebuild (Agent 2) · no git history yet
```

Verification evidence:

- v2 is **no longer visible** to the v1 repository — `git status` in v1 no longer lists it.
- v1 working-tree entry count went **176 → 175**, exactly matching the removal of the
  `?? sih-agent-v2/` entry. **No v1 files were moved, lost, or modified.**
- All 5 v2 artifacts moved intact (5 files before, 5 after; source path no longer exists).
- `backend/scratch/` and `backend/scratch/chrome_debug.log` are now matched by `.gitignore:17`.

### Recommended next step

```powershell
git -C 'd:\Parker\Projects\sih\sih-agent-v2' init
```

The rebuild should carry its **own** history. A clean, single-purpose repository is itself part of
what a jury reads as engineering maturity — and it guarantees the v1 and v2 histories can never
tangle.