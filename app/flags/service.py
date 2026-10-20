"""Feature flags through OpenFeature, served by flagd (item 17b).

    if is_enabled(Flag.CHRONICLE_LLM_NARRATION, user): ...

Code talks only to the OpenFeature API, so the flag backend is a provider
choice: flagd now; Unleash, Flagsmith or LaunchDarkly later by swapping the
provider in configure(), with no change at any call site.

The provider runs in-process: it syncs the flag rules from flagd's sync
service and evaluates them here, so a check costs no network round trip,
and if flagd goes away the last rules it sent stay in force. Without
FLAGD_HOST (tests that don't configure one, and ECS until go-live) no
provider is set and every flag returns its fallback from constants.py.

The evaluation context carries the user's id (the key percentage rollouts
hash on, so a user stays in or out consistently) and whether they are an
admin. Never email or other personal data: targeting doesn't need it.
"""

import logging
import os

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.contrib.provider.flagd.config import ResolverType
from openfeature.evaluation_context import EvaluationContext
from openfeature.provider import FeatureProvider
from prometheus_client import REGISTRY, CollectorRegistry, Counter

from app.auth.models import User
from app.flags.constants import (
    ADMIN_ATTRIBUTE,
    FALLBACKS,
    FLAGD_DEADLINE_MS,
    FLAGD_DEFAULT_SYNC_PORT,
    FLAGD_HOST_ENV_VAR,
    FLAGD_PORT_ENV_VAR,
    Flag,
)

logger = logging.getLogger(__name__)

NO_VARIANT = "<none>"  # the variant label when a fallback was served


class FlagMetrics:
    """flag_evaluations_total{flag, variant, reason}: who got what, and why.

    Bounded labels (flag keys and variants come from code and the flags
    file, reasons from the OpenFeature spec), so a rollout can be watched on
    the dashboard: the share of "on", and any ERROR reasons.
    """

    def __init__(self, registry: CollectorRegistry) -> None:
        self._evaluations = Counter(
            "flag_evaluations",
            "Feature flag evaluations, by flag, variant served and reason.",
            ["flag", "variant", "reason"],
            registry=registry,
        )

    def observe(self, flag: Flag, variant: str | None, reason: str) -> None:
        self._evaluations.labels(
            flag=flag.value, variant=variant or NO_VARIANT, reason=reason
        ).inc()


FLAG_METRICS = FlagMetrics(REGISTRY)
# Flags whose last evaluation failed: logged once when the error starts and
# once when it clears, not on every request while flagd is down.
_failing: set[Flag] = set()
# The provider configure() installed, so shutdown() stops only what it started.
_installed: list[FeatureProvider] = []


def flagd_provider() -> FeatureProvider | None:
    """The provider for the configured flagd, or None when none is configured."""
    host = os.getenv(FLAGD_HOST_ENV_VAR)
    if not host:
        return None
    port = int(os.getenv(FLAGD_PORT_ENV_VAR, str(FLAGD_DEFAULT_SYNC_PORT)))
    return FlagdProvider(
        resolver_type=ResolverType.IN_PROCESS, host=host, port=port, deadline_ms=FLAGD_DEADLINE_MS
    )


def configure(provider: FeatureProvider | None = None) -> None:
    """Install the flag provider at startup. Never blocks on flagd."""
    provider = provider or flagd_provider()
    if provider is None:
        logger.info("%s is not set: every feature flag uses its fallback", FLAGD_HOST_ENV_VAR)
        return
    api.set_provider(provider)
    _installed.append(provider)
    logger.info("Feature flags from %s", provider.get_metadata().name)


def shutdown() -> None:
    """Stop the provider configure() installed (its sync stream and threads)."""
    if _installed:
        api.shutdown()
        _installed.clear()
    _failing.clear()


def context_for(user: User | None) -> EvaluationContext:
    """Anonymous visitors get no targeting key, so no percentage rollout reaches them."""
    if user is None:
        return EvaluationContext(attributes={ADMIN_ATTRIBUTE: False})
    return EvaluationContext(
        targeting_key=str(user.id), attributes={ADMIN_ATTRIBUTE: bool(user.is_admin)}
    )


def is_enabled(flag: Flag, user: User | None = None) -> bool:
    """The flag's value for this user, or its fallback if flagd can't say."""
    details = api.get_client().get_boolean_details(flag.value, FALLBACKS[flag], context_for(user))
    FLAG_METRICS.observe(flag, details.variant, str(details.reason))
    if details.error_code is not None:
        if flag not in _failing:
            _failing.add(flag)
            logger.warning(
                "Flag %s failed (%s); serving its fallback, %s",
                flag,
                details.error_code,
                details.value,
            )
    elif flag in _failing:
        _failing.discard(flag)
        logger.info("Flag %s is evaluating again", flag)
    return details.value
