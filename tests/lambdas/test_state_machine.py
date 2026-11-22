"""Tests for infra/media-pipeline/state_machine.asl.json, the item 29 workflow:
it must fit the Lambda it calls and the API that reads its results, and no
path may lose a failing image. (AWS's validator also passed it:
aws stepfunctions validate-state-machine-definition.)"""

import json
import re
from pathlib import Path

import pytest

from app.media.constants import RESULT_VARIANTS as API_RESULT_VARIANTS
from lambdas.image_variants.constants import RESULT_VARIANTS

ASL = Path(__file__).resolve().parents[2] / "infra" / "media-pipeline" / "state_machine.asl.json"
STEP_FUNCTIONS_TF = ASL.with_name("step_functions.tf")
PLACEHOLDERS = {
    "function_arn": "arn:aws:lambda:us-east-2:123456789012:function:f",
    "results_queue_url": "https://sqs.us-east-2.amazonaws.com/123456789012/results",
    "dead_letter_queue_url": "https://sqs.us-east-2.amazonaws.com/123456789012/dlq",
    "task_timeout_seconds": "70",
    "max_attempts": "2",
}


def _rendered() -> dict:
    text = ASL.read_text()
    for name, value in PLACEHOLDERS.items():
        text = text.replace("${" + name + "}", value)
    assert "${" not in text, "a placeholder templatefile() doesn't fill"
    return json.loads(text)


def _scopes(machine: dict) -> list[dict]:
    """Every States block: the top level and each Map's item processor."""
    found = [machine["States"]]
    for state in machine["States"].values():
        if "ItemProcessor" in state:
            found += _scopes(state["ItemProcessor"])
    return found


def _states() -> dict[str, dict]:
    return {name: state for scope in _scopes(_rendered()) for name, state in scope.items()}


def test_terraform_fills_every_placeholder():
    used = set(re.findall(r"\$\{(\w+)\}", ASL.read_text()))
    passed = set(
        re.findall(
            r"^\s*(\w+)\s*=",
            STEP_FUNCTIONS_TF.read_text().split("templatefile")[1].split("})")[0],
            re.M,
        )
    )
    assert used == set(PLACEHOLDERS) == passed


def test_every_transition_lands_on_a_state_in_its_scope():
    for scope in _scopes(_rendered()):
        targets = (
            {s.get("Next") for s in scope.values()}
            | {c["Next"] for s in scope.values() for c in s.get("Choices", []) + s.get("Catch", [])}
            | {s.get("Default") for s in scope.values()}
        )
        assert targets - {None} <= set(scope)


def test_the_lambda_gets_the_keys_its_handler_reads():
    payload = _states()["MakeVariants"]["Parameters"]["Payload"]
    assert set(payload) == {"bucket.$", "key.$"}


def test_only_a_result_with_variants_is_reported():
    choice = _states()["AnyVariants"]["Choices"][0]
    assert choice["Variable"] == f"$.made.result.{RESULT_VARIANTS}"
    assert RESULT_VARIANTS == API_RESULT_VARIANTS  # what app/media/ validates


def test_the_api_gets_the_lambdas_result_unchanged():
    report = _states()["ReportResult"]["Parameters"]
    assert report["MessageBody.$"] == "$.made.result"
    assert report["QueueUrl"] == PLACEHOLDERS["results_queue_url"]


@pytest.mark.parametrize("task", ["MakeVariants", "ReportResult"])
def test_every_task_retries_then_parks_its_failures(task):
    state = _states()[task]
    assert state["Retry"]
    (catch,) = state["Catch"]
    assert catch["ErrorEquals"] == ["States.ALL"]
    assert catch["Next"] == "ParkInDeadLetterQueue"


def test_parking_keeps_the_original_notification_for_a_redrive():
    park = _states()["ParkInDeadLetterQueue"]
    assert park["Parameters"]["QueueUrl"] == PLACEHOLDERS["dead_letter_queue_url"]
    assert park["Parameters"]["MessageBody.$"] == "$.raw"
    assert set(park["Parameters"]["MessageAttributes"]) == {"error", "key", "execution"}
    assert park["Next"] == "Failed" and _states()["Failed"]["Type"] == "Fail"


def test_transient_lambda_errors_back_off_with_jitter():
    lambda_retry = _states()["MakeVariants"]["Retry"][0]
    assert "Lambda.TooManyRequestsException" in lambda_retry["ErrorEquals"]
    assert lambda_retry["BackoffRate"] > 1 and lambda_retry["JitterStrategy"] == "FULL"


def test_the_task_times_out_before_running_up_a_bill():
    assert _states()["MakeVariants"]["TimeoutSeconds"] == int(PLACEHOLDERS["task_timeout_seconds"])


def test_s3s_test_event_ends_quietly():
    choice = _states()["IsTestEvent"]["Choices"][0]
    assert choice == {
        "Variable": "$.notification.Records",
        "IsPresent": False,
        "Next": "TestEventDone",
    }
