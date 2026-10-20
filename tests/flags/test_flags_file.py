"""flags/flags.flagd.json, the flags flagd serves: its contract with the code and its rollouts.

Evaluated by the same flagd provider the app uses (FILE mode, set up for the
whole suite in conftest), so these check what flagd would answer.
"""

import json

import pytest
from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import Reason

from app.flags.constants import ADMIN_ATTRIBUTE, Flag
from tests.helpers import FLAGS_FILE

ROLLOUT_SAMPLE = 10_000
CHRONICLE_ROLLOUT_SHARE = 0.10
ROLLOUT_TOLERANCE = 0.01  # 10,000 hashed ids land within a point of the target


def _document() -> dict:
    return json.loads(FLAGS_FILE.read_text())


def _value(flag: Flag, context: EvaluationContext) -> bool:
    return api.get_client().get_boolean_value(flag.value, False, context)


def _user(user_id: int, *, admin: bool = False) -> EvaluationContext:
    return EvaluationContext(targeting_key=str(user_id), attributes={ADMIN_ATTRIBUTE: admin})


class TestContractWithTheCode:
    def test_every_flag_the_code_uses_is_defined(self):
        assert {f.value for f in Flag} <= set(_document()["flags"])

    def test_no_flag_outlives_its_code(self):
        """A flag nothing reads is dead configuration: delete it with the code that used it."""
        assert set(_document()["flags"]) <= {f.value for f in Flag}

    @pytest.mark.parametrize("flag", list(Flag), ids=[f.value for f in Flag])
    def test_boolean_variants_on_and_off(self, flag):
        entry = _document()["flags"][flag.value]
        assert entry["variants"] == {"on": True, "off": False}
        assert entry["state"] == "ENABLED"

    @pytest.mark.parametrize("flag", list(Flag), ids=[f.value for f in Flag])
    def test_evaluates_without_error(self, flag):
        details = api.get_client().get_boolean_details(flag.value, False, _user(1))
        assert details.error_code is None
        assert details.reason != Reason.ERROR


class TestWidgetKillSwitch:
    def test_on_by_default_so_the_env_var_decides(self):
        assert _value(Flag.WIDGET_SERVER_EXECUTION, _user(1))
        assert _value(Flag.WIDGET_SERVER_EXECUTION, EvaluationContext())


class TestChronicleRollout:
    def test_admins_always_get_llm_narration(self):
        assert all(_value(Flag.CHRONICLE_LLM_NARRATION, _user(i, admin=True)) for i in range(100))

    def test_anonymous_visitors_never_do(self):
        details = api.get_client().get_boolean_details(
            Flag.CHRONICLE_LLM_NARRATION.value,
            True,
            EvaluationContext(attributes={ADMIN_ATTRIBUTE: False}),
        )
        assert details.value is False
        assert details.error_code is None

    def test_reaches_ten_percent_of_signed_in_users(self):
        on = sum(_value(Flag.CHRONICLE_LLM_NARRATION, _user(i)) for i in range(ROLLOUT_SAMPLE))
        assert abs(on / ROLLOUT_SAMPLE - CHRONICLE_ROLLOUT_SHARE) < ROLLOUT_TOLERANCE

    def test_each_user_stays_in_or_out(self):
        """The bucket is a hash of the user id, not a coin flip per request."""
        first = [_value(Flag.CHRONICLE_LLM_NARRATION, _user(i)) for i in range(500)]
        again = [_value(Flag.CHRONICLE_LLM_NARRATION, _user(i)) for i in range(500)]
        assert first == again
