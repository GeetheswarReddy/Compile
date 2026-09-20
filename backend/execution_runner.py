"""The isolated executor for untrusted Python submissions.

This module deliberately keeps execution here: callers receive only the public
``SubmissionVerdict`` contract and never the question's reference solution.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import pickle
import signal
import subprocess
import sys
import textwrap
from typing import Any

from backend.contracts import FailedCase, Question, SubmissionVerdict


EXECUTION_TIMEOUT_SECONDS = 5.0
ADDRESS_SPACE_BYTES = 128 * 1024 * 1024
_RESULT_FD = 198
logger = logging.getLogger(__name__)


_CHILD_PROGRAM = r'''
import ast
import builtins
import base64
import contextlib
import io
import json
import os
import pickle
import resource
import sys

tests = pickle.loads(base64.b64decode(__TESTS__))
submission = pickle.loads(base64.b64decode(__CODE__))
starter = pickle.loads(base64.b64decode(__STARTER__))

# Keep ordinary submissions from reaching network clients.  The subprocess is
# also started without inherited environment variables or descriptors.
blocked = {
    "_socket", "asyncio", "ctypes", "ftplib", "http", "http.client",
    "httpx", "importlib", "multiprocessing", "os", "pathlib", "requests",
    "socket", "ssl", "subprocess", "sys", "telnetlib", "urllib",
    "urllib.request",
}
real_import = builtins.__import__
def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".", 1)[0] in blocked:
        raise ImportError("network access is disabled")
    return real_import(name, globals, locals, fromlist, level)

def safe_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [safe_value(item) for item in value[:1000]]
    if isinstance(value, dict):
        return {str(key): safe_value(item) for key, item in list(value.items())[:1000]}
    try:
        rendered = repr(value)
    except BaseException:
        rendered = "<unavailable>"
    return rendered[:4000]

def emit(payload):
    data = json.dumps(payload, separators=(",", ":")).encode()
    os.write(198, data if len(data) < 4000 else b'{"passed":false,"failed":[]}')

# Load the standard exercise libraries before closing filesystem access.
# Imports of these modules still work from sys.modules after the filter.
import bisect, collections, functools, heapq, itertools, math, operator
import random, re, statistics, string, typing
__SANDBOX__
kernel_filter_enforced = True
try:
    # Start the Lambda-provided interpreter before applying RLIMIT_AS. The
    # runtime's dynamic loader and standard-library imports need more virtual
    # address space than learner code is allowed to allocate afterwards.
    restrict_child()
except RuntimeError:
    # Lambda's own sandbox can reject installing a second seccomp filter. The
    # private executor still has no service permissions, credentials, network
    # route, DNS, inherited descriptors or process environment. Tighten the
    # Python boundary as defense in depth and retain the resource limits.
    if not __ALLOW_KERNEL_FILTER_FALLBACK__:
        emit({"infrastructureError": "sandbox initialization failed", "errorType": "RuntimeError"})
        sys.exit(0)
    kernel_filter_enforced = False
    def denied_open(*args, **kwargs):
        raise PermissionError("filesystem access is disabled")
    builtins.open = denied_open
except BaseException as error:
    emit({"infrastructureError": "sandbox initialization failed", "errorType": type(error).__name__})
    sys.exit(0)

try:
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (__ADDRESS_SPACE_BYTES__, __ADDRESS_SPACE_BYTES__))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
except BaseException as error:
    emit({"infrastructureError": "sandbox initialization failed", "errorType": type(error).__name__})
    sys.exit(0)

builtins.__import__ = safe_import
namespace = {"__name__": "__submission__"}
try:
    # starter_code supplies the exercise's normal function scaffold.  Running
    # the submitted source afterwards also supports complete submissions.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        exec(starter, namespace, namespace)
        exec(submission, namespace, namespace)

    candidates = [
        value for name, value in namespace.items()
        if not name.startswith("_") and callable(value)
    ]
    if not candidates:
        raise RuntimeError("submission did not define a callable")
    definitions = [node.name for node in ast.parse(starter or submission).body if isinstance(node, ast.FunctionDef)]
    function = namespace[definitions[0]] if definitions else candidates[-1]
    failures = []
    for input_data, expected, positional in tests:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                actual = function(*input_data) if positional or isinstance(input_data, tuple) else function(input_data)
            if actual != expected:
                failures.append({
                    "input": safe_value(input_data),
                    "expected": safe_value(expected),
                    "actual": safe_value(actual),
                })
                if len(failures) == 2:
                    break
        except BaseException:
            failures.append({
                "input": safe_value(input_data),
                "expected": safe_value(expected),
                "actual": "<execution error>",
            })
            if len(failures) == 2:
                break
    emit({"passed": not failures, "failed": failures, "kernelFilter": kernel_filter_enforced})
except BaseException:
    emit({"passed": False, "failed": []})
'''


def _child_script(question: Question, code: str) -> str:
    from pathlib import Path
    replacements = {
        "__SANDBOX__": Path(__file__).with_name("sandbox_limits.py").read_text(),
        "__TESTS__": repr(base64.b64encode(pickle.dumps(
            [(test.input_data, test.expected_output, test.positional) for test in question.hidden_tests]
        )).decode()),
        "__CODE__": repr(base64.b64encode(pickle.dumps(code)).decode()),
        "__STARTER__": repr(base64.b64encode(pickle.dumps(question.starter_code)).decode()),
        "__ADDRESS_SPACE_BYTES__": str(ADDRESS_SPACE_BYTES),
        "__ALLOW_KERNEL_FILTER_FALLBACK__": repr(bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))),
    }
    # The child decodes the trusted, parent-created values before execution.
    program = _CHILD_PROGRAM
    for token, value in replacements.items():
        program = program.replace(token, value)
    return textwrap.dedent(program)


def _kill_process(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        process.kill()


def _local_preexec_limits() -> None:
    """Apply the address cap before exec on platforms that reject lowering it later."""

    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES))
    except (ImportError, OSError, ValueError):
        pass


def _child_environment() -> dict[str, str]:
    """Pass only the Lambda runtime's dynamic-loader path to the child.

    The AWS Python executable needs ``LD_LIBRARY_PATH`` after ``execve``.
    Forwarding the complete Lambda environment would also expose temporary AWS
    credentials to learner code, so every other variable remains absent.
    """

    loader_path = os.environ.get("LD_LIBRARY_PATH")
    return {"LD_LIBRARY_PATH": loader_path} if loader_path else {}


def run_submission(question: Question, code: str) -> SubmissionVerdict:
    """Run ``code`` against all hidden tests and return a redacted verdict."""

    if not isinstance(question, Question):
        raise TypeError("question must be a Question")
    if not isinstance(code, str):
        raise TypeError("code must be a string")
    if len(code.encode()) > 65536:
        raise ValueError("code must be at most 64 KiB")

    read_fd, write_fd = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    try:
        os.dup2(write_fd, _RESULT_FD)
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _child_script(question, code)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=(_RESULT_FD,),
            close_fds=True,
            start_new_session=True,
            preexec_fn=_local_preexec_limits if os.name != "nt" and sys.platform != "linux" else None,
            env=_child_environment(),
        )
        # The parent must not retain a writer, otherwise the reader below can
        # wait forever for EOF after the child exits.
        if _RESULT_FD != write_fd:
            os.close(_RESULT_FD)
        os.close(write_fd)
        write_fd = -1
        try:
            process.wait(timeout=EXECUTION_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            _kill_process(process)
            process.wait()
            return SubmissionVerdict(False)
        with os.fdopen(read_fd, "rb") as result_pipe:
            payload = json.loads(result_pipe.read(1_000_000).decode("utf-8"))
        if payload.get("infrastructureError"):
            logger.error(
                "execution sandbox initialization failed (error=%s)",
                payload.get("errorType", "unknown"),
            )
            raise RuntimeError("execution sandbox unavailable")
        if payload.get("kernelFilter") is False:
            logger.warning("Lambda rejected the additional child kernel filter; using the isolated executor boundary")
        if payload.get("passed") is True:
            return SubmissionVerdict(True)
        failures = tuple(
            FailedCase(item.get("input"), item.get("expected"), item.get("actual"))
            for item in payload.get("failed", [])[:2]
        )
        return SubmissionVerdict(False, failures)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning(
            "sandbox child failed before returning a verdict (returncode=%s, error=%s)",
            process.returncode if process is not None else None,
            type(exc).__name__,
        )
        raise RuntimeError("execution sandbox unavailable") from exc
    finally:
        if write_fd != -1:
            os.close(write_fd)
        if process is not None and process.poll() is None:
            _kill_process(process)
            process.wait()
        if read_fd != -1:
            try:
                os.close(read_fd)
            except OSError:
                pass


def verify_question(question: Question) -> bool:
    """Return whether the private reference solution passes every hidden test."""

    if not isinstance(question, Question):
        raise TypeError("question must be a Question")
    return run_submission(question, question.reference_solution).passed


def handler(event, context):
    """Private Lambda boundary. This function has no database or S3 permissions."""
    from .repositories import _question_from_item
    from .contracts import serialize_verdict
    return serialize_verdict(run_submission(_question_from_item(event["question"]), event["code"]))
