"""Run generated analysis in a disposable local Docker container."""
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from typing import BinaryIO
from uuid import uuid4

IMAGE = "lsn-analysis:1"
TIMEOUT_SECONDS = 30
MAX_OUTPUT = 4 * 1024 * 1024
_slots = BoundedSemaphore(2)


class SandboxError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _run_container(directory: Path) -> dict:
    name = f"lsn-analysis-{uuid4().hex}"
    create = [
        "docker", "create", "--rm", "--pull=never", "--name", name,
        "--network=none", "--read-only", "--user=65534:65534",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--cpus=1", "--memory=512m", "--memory-swap=512m", "--pids-limit=64",
        "--ulimit", "nofile=128:128", "--log-driver=none",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
        "--mount", f"type=bind,source={directory},target=/input,readonly",
        IMAGE,
    ]
    try:
        subprocess.run(create, check=True, capture_output=True, timeout=15)
        # Read at most MAX_OUTPUT + 1 bytes even if code writes directly to stdout.
        with subprocess.Popen(
            ["docker", "start", "--attach", name], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ) as proc, ThreadPoolExecutor(max_workers=1) as reader:
            future = reader.submit(proc.stdout.read, MAX_OUTPUT + 1)
            try:
                data = future.result(timeout=TIMEOUT_SECONDS)
                if len(data) > MAX_OUTPUT:
                    raise SandboxError(422, "Analysis output exceeded 4 MiB")
                if proc.wait(timeout=5):
                    raise SandboxError(422, "Analysis worker stopped before returning a result")
            finally:
                if proc.poll() is None:
                    proc.kill()
    except (TimeoutError, subprocess.TimeoutExpired) as exc:
        raise SandboxError(504, "Analysis sandbox timed out") from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SandboxError(503, f"Analysis sandbox unavailable. Check Docker and image {IMAGE}.") from exc
    finally:
        if shutil.which("docker"):
            try:
                cleanup = subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
                stderr = cleanup.stderr.lower()
                if cleanup.returncode and b"no such container" not in stderr and b"already in progress" not in stderr:
                    raise SandboxError(503, "Docker could not confirm sandbox cleanup")
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SandboxError(503, "Docker could not confirm sandbox cleanup") from exc

    try:
        answer = json.loads(data)
        if not isinstance(answer, dict):
            raise ValueError
        if "error" in answer:
            raise SandboxError(422, str(answer["error"])[:600])
        if answer.get("result_type") not in ("table", "series", "scalar") or "result" not in answer:
            raise ValueError
        json.dumps(answer, allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, RecursionError) as exc:
        raise SandboxError(422, "Analysis returned an invalid result") from exc
    return {key: answer[key] for key in ("result_type", "result", "plot_png_base64") if key in answer}


def execute(stream: BinaryIO, ext: str, sheet: str | None, code: str) -> dict:
    if not _slots.acquire(blocking=False):
        raise SandboxError(503, "Analysis sandbox is busy")
    try:
        with TemporaryDirectory(prefix="analysis-") as temp:
            directory = Path(temp) / "input"
            directory.mkdir()
            # The unprivileged container user needs read access on Linux hosts.
            directory.chmod(0o755)
            stream.seek(0)
            with (directory / "data").open("wb") as dest:
                shutil.copyfileobj(stream, dest)
            job = {"code": code, "ext": ext, "sheet": sheet}
            (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
            for path in directory.iterdir():
                path.chmod(0o644)
            return _run_container(directory)
    finally:
        _slots.release()
