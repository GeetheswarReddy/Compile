from backend.contracts import Provenance, Question, TestCase, Topic
from backend.execution_runner import _child_environment, _child_script


def test_executor_child_only_receives_lambda_loader_path(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/var/lang/lib:/var/runtime")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "must-not-reach-learner-code")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-learner-code")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "must-not-reach-learner-code")

    assert _child_environment() == {
        "LD_LIBRARY_PATH": "/var/lang/lib:/var/runtime",
    }


def test_kernel_filter_fallback_is_scoped_to_lambda_runtime(monkeypatch):
    question = Question(
        question_id="arrays-1",
        topic=Topic.ARRAYS,
        difficulty=1,
        prompt="Return the first item.",
        starter_code="def solve(items):\n    pass",
        hidden_tests=(TestCase([1], 1), TestCase([2], 2)),
        reference_solution="def solve(items):\n    return items[0]",
        provenance=Provenance.SEEDED,
    )

    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    assert "if not False:" in _child_script(question, question.reference_solution)

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "compile-v2-sandbox")
    lambda_program = _child_script(question, question.reference_solution)
    assert "if not True:" in lambda_program
    assert '"_socket"' in lambda_program
    assert "builtins.open = denied_open" in lambda_program
