"""Feature flag keys, their safe fallbacks, and how to reach flagd (item 17b).

The flags themselves (variants, targeting, rollout percentages) live in
flags/flags.flagd.json, which flagd serves and hot-reloads. This module is
the code's side of the contract: which flags exist and what each one means
when flagd can't answer.
"""

from enum import StrEnum


class Flag(StrEnum):
    # Runtime kill switch for server-side widget execution. Sits under the
    # WIDGET_SERVER_EXECUTION_ENABLED deploy-time ceiling: the flag can turn
    # execution off without a redeploy, never on where the env var says no.
    WIDGET_SERVER_EXECUTION = "widget-server-execution"
    # Chronicle narration by the LLM (Claude spend) instead of the rule-based
    # fallback; rolled out per user.
    CHRONICLE_LLM_NARRATION = "chronicle-llm-narration"


# What each flag evaluates to when flagd is unreachable, not configured, or
# the flag is missing: the safe side. Off for both: no code execution, no spend.
FALLBACKS: dict[Flag, bool] = {
    Flag.WIDGET_SERVER_EXECUTION: False,
    Flag.CHRONICLE_LLM_NARRATION: False,
}

FLAGD_HOST_ENV_VAR = "FLAGD_HOST"  # unset: no flagd; every flag uses its fallback
FLAGD_PORT_ENV_VAR = "FLAGD_PORT"
FLAGD_DEFAULT_SYNC_PORT = 8015  # flagd's flag sync service (in-process evaluation)
# How long the provider waits for flagd before reporting not-ready. The app
# never blocks on it: evaluations return fallbacks until it connects.
FLAGD_DEADLINE_MS = 2000

# Evaluation context attributes; targeting rules in flags.flagd.json use these.
ADMIN_ATTRIBUTE = "is_admin"
