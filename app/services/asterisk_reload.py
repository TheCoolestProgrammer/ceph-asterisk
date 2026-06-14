import subprocess
from dataclasses import dataclass


@dataclass
class ReloadResult:
    stdout: str
    stderr: str
    returncode: int


class AsteriskReloadError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        self.message = message
        self.stderr = stderr
        super().__init__(message)


def container_name_for_instance(instance_name: str) -> str:
    return f"asterisk-{instance_name}"


def _output_indicates_success(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}".lower()
    if not combined.strip():
        return True
    success_markers = (
        "reloaded",
        "reload",
        "reloading",
        "already loaded",
        "module loaded",
    )
    return any(marker in combined for marker in success_markers)


def run_asterisk_cli(
    instance_name: str,
    command: str,
    *,
    timeout: int = 30,
    strict: bool = True,
) -> ReloadResult:
    """Выполняет `asterisk -rx "<command>"` (команда — один аргумент после -rx)."""
    container = container_name_for_instance(instance_name)
    try:
        result = subprocess.run(
            ["docker", "exec", container, "asterisk", "-rx", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise AsteriskReloadError(
            f"Timeout while running '{command}' in {container}",
        ) from e
    except Exception as e:
        raise AsteriskReloadError(
            f"Error running '{command}' in {container}: {e}",
        ) from e

    reload_result = ReloadResult(
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        returncode=result.returncode,
    )

    if result.returncode != 0:
        if not strict or _output_indicates_success(
            reload_result.stdout, reload_result.stderr
        ):
            return reload_result
        raise AsteriskReloadError(
            f"Command '{command}' failed in {container}",
            stderr=reload_result.stderr.strip(),
        )

    return reload_result


def reload_asterisk_config(
    instance_name: str,
    *,
    timeout: int = 30,
) -> list[ReloadResult]:
    """
    Перезагружает конфигурацию после изменений в ast_config.
    manager reload — AMI/manager.conf; http reload — http.conf; core reload — остальное.
    """
    commands = (
        "module reload res_config_odbc.so",
        "manager reload",
        "http reload",
        "module reload res_rtp_asterisk.so",
        "module reload res_musiconhold.so",
        "module reload res_pjsip.so",
        "pjsip set logger on",
        "pjsip reload",
        "dialplan reload",
        "core reload",
    )
    results: list[ReloadResult] = []
    for command in commands:
        results.append(
            run_asterisk_cli(
                instance_name, command, timeout=timeout, strict=False
            )
        )
    return results
