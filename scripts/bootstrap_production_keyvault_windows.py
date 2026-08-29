"""Windows-safe launcher for bootstrap_production_keyvault.py.

Azure CLI installed by the Windows MSI is commonly exposed through az.cmd.
Calling that batch wrapper through cmd.exe makes quoting fragile, especially when
secret values contain shell metacharacters. This launcher bypasses az.cmd and
invokes Azure CLI with the Python runtime bundled in the Azure CLI installation.

Usage:
    python scripts/bootstrap_production_keyvault_windows.py --env-file .env
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import bootstrap_production_keyvault as bootstrap_module


def resolve_windows_azure_cli_python() -> Path:
    az_cmd = shutil.which("az.cmd")
    if not az_cmd:
        raise SystemExit(
            "Azure CLI az.cmd was not found. Verify `where az` and `az version` first."
        )

    cli_root = Path(az_cmd).resolve().parent.parent
    candidates = (
        cli_root / "python.exe",
        cli_root / "python3.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise SystemExit(
        "Azure CLI bundled Python was not found next to az.cmd. "
        f"Expected it under: {cli_root}"
    )


AZURE_CLI_PYTHON = resolve_windows_azure_cli_python()


def windows_az(*args: str, capture: bool = False, check: bool = True) -> str:
    command = [str(AZURE_CLI_PYTHON), "-IBm", "azure.cli", *args]
    completed = subprocess.run(
        command,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=None,
    )
    return completed.stdout.strip() if capture and completed.stdout else ""


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit(
            "This launcher is only for Windows. Use bootstrap_production_keyvault.py elsewhere."
        )

    # Patch the module-level Azure CLI runner before bootstrap_module.main() calls
    # account/resource/container/key-vault commands. No shell is involved.
    bootstrap_module.az = windows_az
    bootstrap_module.AZURE_CLI = f"{AZURE_CLI_PYTHON} -IBm azure.cli"
    bootstrap_module.main()


if __name__ == "__main__":
    main()
