"""app/flags/service.py: evaluation, fallbacks when flagd can't answer, and the provider's lifecycle.

flagd itself is the external boundary. These run the real flagd provider:
in FILE mode against flags files (as the whole suite does), and in its
in-process mode against an address where nothing listens, which is what
the app sees while flagd is down.
"""

import logging
import socket
import threading
import time
from collections.abc import Iterator

import pytest
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.contrib.provider.flagd.config import ResolverType
from prometheus_client import REGISTRY

from app.auth.models import User
from app.flags import service
from app.flags.constants import ADMIN_ATTRIBUTE, FLAGD_DEFAULT_SYNC_PORT, Flag
from tests.helpers import FLAGS_FILE, serve_flags_file

STARTUP_BUDGET_SECONDS = 1.0  # configure() must not wait for flagd

# Shutting down a provider that never connected races its background
# threads: grpcio's connectivity poller ("Cannot monitor channel state") or
# the provider's sync loop ("Cannot invoke RPC") can touch the channel after
# it closed, and the thread dies with "Channel closed!". Harmless to the app
# (it happens only at shutdown); recheck when upgrading
# openfeature-provider-flagd past 0.5.2. The filter matches only that message.
pytestmark = pytest.mark.filterwarnings(
    "ignore:(?s).*Channel closed!:pytest.PytestUnhandledThreadExceptionWarning"
)
THREAD_EXIT_SECONDS = (
    5  # the provider gives up connecting after FLAGD_DEADLINE_MS; grpc winds down within ~3 s
)


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _evaluations(flag: Flag, variant: str, reason: str) -> float:
    labels = {"flag": flag.value, "variant": variant, "reason": reason}
    return REGISTRY.get_sample_value("flag_evaluations_total", labels) or 0.0


@pytest.fixture()
def restore_repo_flags() -> Iterator[None]:
    """For tests that replace or remove the suite's provider."""
    yield
    service.shutdown()
    serve_flags_file(FLAGS_FILE)


@pytest.fixture()
def flagd_down(monkeypatch, restore_repo_flags) -> Iterator[None]:
    """configure() pointed at a flagd that isn't there.

    Afterwards, waits for the provider's threads to exit, so nothing they do
    at shutdown lands in another module's test.
    """
    monkeypatch.setenv("FLAGD_HOST", "127.0.0.1")
    monkeypatch.setenv("FLAGD_PORT", str(_closed_port()))
    before = set(threading.enumerate())
    yield
    service.shutdown()
    for thread in set(threading.enumerate()) - before:
        if thread.is_alive():  # grpc can list a thread object it hasn't started yet
            thread.join(THREAD_EXIT_SECONDS)


class TestIsEnabled:
    def test_follows_the_flags_file(self, set_flags):
        set_flags({Flag.CHRONICLE_LLM_NARRATION: True})
        assert service.is_enabled(Flag.CHRONICLE_LLM_NARRATION, User(id=7, is_admin=False))
        set_flags({Flag.CHRONICLE_LLM_NARRATION: False})
        assert not service.is_enabled(Flag.CHRONICLE_LLM_NARRATION, User(id=7, is_admin=False))

    def test_targets_on_the_users_admin_attribute(self):
        assert service.is_enabled(Flag.CHRONICLE_LLM_NARRATION, User(id=1, is_admin=True))

    def test_counts_each_evaluation_by_variant_and_reason(self):
        before = _evaluations(Flag.CHRONICLE_LLM_NARRATION, "on", "TARGETING_MATCH")
        service.is_enabled(Flag.CHRONICLE_LLM_NARRATION, User(id=1, is_admin=True))
        assert _evaluations(Flag.CHRONICLE_LLM_NARRATION, "on", "TARGETING_MATCH") == before + 1


class TestContext:
    def test_a_user_is_keyed_by_id_with_their_admin_flag(self):
        context = service.context_for(User(id=42, is_admin=True, email="someone@example.com"))
        assert context.targeting_key == "42"
        assert context.attributes == {ADMIN_ATTRIBUTE: True}, "nothing personal, such as email"

    def test_anonymous_has_no_targeting_key(self):
        context = service.context_for(None)
        assert context.targeting_key is None
        assert context.attributes == {ADMIN_ATTRIBUTE: False}


class TestWhenFlagdCannotAnswer:
    def test_no_flagd_configured_means_fallbacks(self, monkeypatch, restore_repo_flags, caplog):
        monkeypatch.delenv("FLAGD_HOST", raising=False)
        api.clear_providers()
        with caplog.at_level(logging.INFO, logger="app.flags.service"):
            service.configure()
        assert "FLAGD_HOST is not set" in caplog.text
        assert not service.is_enabled(Flag.WIDGET_SERVER_EXECUTION, User(id=1, is_admin=True))

    def test_startup_does_not_wait_for_flagd(self, flagd_down):
        started = time.monotonic()
        service.configure()
        assert time.monotonic() - started < STARTUP_BUDGET_SECONDS

    def test_flagd_down_serves_fallbacks_and_logs_once(self, flagd_down, caplog):
        service.configure()
        with caplog.at_level(logging.WARNING, logger="app.flags.service"):
            results = [service.is_enabled(Flag.WIDGET_SERVER_EXECUTION) for _ in range(5)]
        assert results == [False] * 5, "the kill switch's safe side"
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        # Before the deadline the provider says it isn't ready; after it, its
        # flag store is simply empty. Either way: the fallback, logged once.
        assert any(
            code in warnings[0].getMessage() for code in ("PROVIDER_NOT_READY", "FLAG_NOT_FOUND")
        )

    def test_logs_when_the_flag_evaluates_again(self, flagd_down, caplog):
        service.configure()
        service.is_enabled(Flag.WIDGET_SERVER_EXECUTION)
        serve_flags_file(FLAGS_FILE)  # flagd is back
        with caplog.at_level(logging.INFO, logger="app.flags.service"):
            assert service.is_enabled(Flag.WIDGET_SERVER_EXECUTION)
        assert "is evaluating again" in caplog.text

    def test_counts_fallbacks_as_errors(self, flagd_down):
        service.configure()
        before = _evaluations(Flag.CHRONICLE_LLM_NARRATION, service.NO_VARIANT, "ERROR")
        service.is_enabled(Flag.CHRONICLE_LLM_NARRATION)
        assert _evaluations(Flag.CHRONICLE_LLM_NARRATION, service.NO_VARIANT, "ERROR") == before + 1


class TestProvider:
    def test_none_without_a_host(self, monkeypatch):
        monkeypatch.delenv("FLAGD_HOST", raising=False)
        assert service.flagd_provider() is None

    def test_in_process_against_the_sync_port_by_default(self, monkeypatch):
        monkeypatch.setenv("FLAGD_HOST", "flagd")
        monkeypatch.delenv("FLAGD_PORT", raising=False)
        provider = service.flagd_provider()
        assert isinstance(provider, FlagdProvider)
        assert (provider.config.resolver, provider.config.host, provider.config.port) == (
            ResolverType.IN_PROCESS,
            "flagd",
            FLAGD_DEFAULT_SYNC_PORT,
        )

    def test_shutdown_leaves_a_provider_it_did_not_install(self):
        """The app's shutdown hook must not tear down someone else's provider (the suite's)."""
        service.shutdown()
        assert service.is_enabled(Flag.WIDGET_SERVER_EXECUTION)

    def test_shutdown_stops_the_provider_it_installed(self, restore_repo_flags, tmp_path):
        flags = tmp_path / "flags.flagd.json"
        flags.write_text(FLAGS_FILE.read_text())
        service.configure(
            FlagdProvider(resolver_type=ResolverType.FILE, offline_flag_source_path=str(flags))
        )
        service.shutdown()
        assert not service.is_enabled(Flag.WIDGET_SERVER_EXECUTION), "no provider left: fallback"
