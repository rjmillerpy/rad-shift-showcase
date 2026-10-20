# Feature flags (roadmap item 17b)

`flags.flagd.json` is the single source of the app's feature flags. flagd
(in `compose.yaml`) serves it, and the API evaluates flags in-process with
the OpenFeature SDK (`app/flags/`). Saving this file changes behaviour
within about a second: no restart, no redeploy.

Deploying code and releasing a feature become separate steps: code ships
dark behind a flag, then the flag opens it to you, to a percentage of users,
to everyone, and closes it again instantly if something goes wrong.

| Flag | What it controls | Now | If flagd can't answer |
|---|---|---|---|
| `widget-server-execution` | Runtime kill switch for server-side widget execution. Under the `WIDGET_SERVER_EXECUTION_ENABLED` env var: it can switch execution off, never on where the env var says no | on (the env var decides) | off |
| `chronicle-llm-narration` | Claude narrates Chronicle instead of the rule-based fallback (this is the Anthropic spend) | admins, plus 10% of signed-in users; never anonymous visitors | off |

## Changing a flag

Edit the file, open a pull request, merge: flags are reviewed and versioned
like code. On the CD-deployed stack the Deploy job's checkout brings the new
file and flagd reloads it.

**Kill switch (incident):** set the flag's `defaultVariant` to `"off"` and
delete its `targeting`, in the file flagd is actually reading: in your
checkout for a stack you started yourself, or in the runner's checkout
(`~/actions-runner/rad-shift/_work/rad-shift/rad-shift/flags/`) for the
CD-deployed one. Then make the same change in git, or the next deploy puts
the old file back.

**Rolling out:** raise the `fractional` split (`["on", 10], ["off", 90]` →
`50/50` → `100/0`), then make `"on"` the `defaultVariant` and drop the
targeting. Bucketing hashes the flag key with the user id, so a user keeps
their answer as the percentage grows, and different flags pick different
users.

**Watching a rollout:** `flag_evaluations_total{flag, variant, reason}` on
the API's `/metrics` (Prometheus and Grafana from item 15) shows the share
of each variant and any `ERROR` reasons, next to the error-rate panels.

## Rules

- **Every flag has a safe fallback in code** (`app/flags/constants.py`):
  what happens when flagd is down, not configured (tests, ECS until go-live)
  or the flag is missing. Both are off: no code execution, no spend.
- **No flag outlives its code.** `tests/flags/test_flags_file.py` fails on a
  flag the code doesn't read, and on a flag the code reads that this file
  lacks. When a rollout reaches 100%, delete the flag and the `if`.
- **Targeting uses the user id and `is_admin`, nothing personal.** Anonymous
  visitors have no id, so percentage rollouts never reach them.
- **Never mount this file on its own** into a container: editors save by
  renaming a new file over the old one, and a single-file bind mount keeps
  the old one. Mount the directory (as `compose.yaml` does).

## At go-live

flagd runs next to the backend on ECS and syncs this file from S3 or an
HTTPS URL instead of a local path (flagd supports both), so a merged flag
change goes live without redeploying the app. The code doesn't change: the
OpenFeature API hides the backend. Moving to LaunchDarkly, Unleash or
Flagsmith later is a provider swap in `app/flags/service.py`'s
`configure()`, nothing at the call sites.
