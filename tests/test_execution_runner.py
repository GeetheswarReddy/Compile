from backend.contracts import Provenance, Question, TestCase, Topic
from backend.execution_runner import run_submission, verify_question


def _question(*tests: TestCase) -> Question:
    return Question(
        question_id="arrays-1",
        topic=Topic.ARRAYS,
        difficulty=3,
        prompt="Return the first item.",
        starter_code="",
        hidden_tests=tuple(tests),
        reference_solution="def solve(items):\n    return items[0]\n",
        provenance=Provenance.SEEDED,
    )


def test_passing_submission_and_reference_verification() -> None:
    question = _question(TestCase([1], 1), TestCase([2], 2))

    assert run_submission(question, "def solve(items):\n    return items[0]\n").passed
    assert verify_question(question)


def test_failing_verdict_is_redacted_and_bounded_to_two_cases() -> None:
    question = _question(TestCase([1], 1), TestCase([2], 2), TestCase([3], 3))

    verdict = run_submission(question, "def solve(items):\n    return 0\n")

    assert not verdict.passed
    assert len(verdict.failed_cases) == 2
    assert [case.input_data for case in verdict.failed_cases] == [[1], [2]]
    assert all(case.actual_output == 0 for case in verdict.failed_cases)
    assert "reference_solution" not in repr(verdict)


def test_infinite_loop_is_stopped_by_wall_clock_timeout() -> None:
    question = _question(TestCase([1], 1), TestCase([2], 2))

    verdict = run_submission(question, "def solve(items):\n    while True:\n        pass\n")

    assert not verdict.passed


def test_memory_heavy_submission_is_stopped_by_address_space_cap() -> None:
    question = _question(TestCase([1], 1), TestCase([2], 2))

    verdict = run_submission(question, "def solve(items):\n    return [0] * (200 * 1024 * 1024)\n")

    assert not verdict.passed


def test_network_import_is_blocked() -> None:
    question = _question(TestCase([1], 1), TestCase([2], 2))

    verdict = run_submission(question, "def solve(items):\n    import socket\n    return 1\n")

    assert not verdict.passed


def test_function_scaffold_selects_entry_point_before_helper():
    from dataclasses import replace
    question = replace(_question(TestCase([1], 1), TestCase([2], 2)), starter_code='def solve(items): pass')
    code = 'def solve(items):\n    return items[0]\ndef helper():\n    return 999'
    assert run_submission(question, code).passed


def test_linux_kernel_restrictions_block_raw_socket_and_process_creation():
    import sys
    import pytest
    if sys.platform != 'linux':
        pytest.skip('Kernel sandbox is enforced on the deployed Linux runtime')
    question = _question(TestCase([1], 1), TestCase([2], 2))
    # _socket bypasses the friendly import blacklist; the kernel must deny it.
    assert not run_submission(question, 'def solve(items):\n    import _socket\n    _socket.socket()\n    return items[0]').passed
    assert not run_submission(question, 'def solve(items):\n    import os\n    os.fork()\n    return items[0]').passed
    assert not run_submission(question, 'def solve(items):\n    open("/proc/self/environ").read()\n    return items[0]').passed
