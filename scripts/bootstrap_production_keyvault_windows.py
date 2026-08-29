"""Windows-safe launcher for bootstrap_production_keyvault.py.

Azure CLI installed by the Windows MSI is commonly exposed through az.cmd.
Calling that batch wrapper through cmd.exe makes quoting fragile, especially when
secret values contain shell metacharacters. This launcher bypasses az.cmd and
invokes Azure CLI with the Python runtime bundled in the Azure CLI installation.

It also sanitizes Azure CLI failures so secret values passed through --value are
never echoed by Python exception tracebacks.

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


def _safe_cli_error(stderr: str, returncode: int) -> SystemExit:
    message = (stderr or "").strip()

    if "ForbiddenByConnection" in message or "not an approved private link" in message:
        return SystemExit(
            "Key Vault network access is blocked. kv-fein allows private-endpoint "
            "traffic only. Connect this PC to the FE!N Azure VNet through the P2S "
            "VPN (or run the bootstrap from a workload inside that VNet), verify "
            "kv-fein.vault.azure.net resolves to a private IP, then run the script again."
        )

    if "az login" in message.lower() or "please run 'az login'" in message.lower():
        return SystemExit("Azure CLI is not authenticated. Run `az login` first.")

    if message:
        return SystemExit(
            f"Azure CLI command failed with exit code {returncode}.\n{message}"
        )
    return SystemExit(f"Azure CLI command failed with exit code {returncode}.")


def windows_az(*args: str, capture: bool = False, check: bool = True) -> str:
    # Pass every argument directly to the bundled Python runtime. No cmd.exe or
    # shell is involved, so secret values are not interpreted as shell syntax.
    command = [str(AZURE_CLI_PYTHON), "-IBm", "azure.cli", *args]
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    if completed.returncode != 0 and check:
        # Never raise CalledProcessError here: its repr includes the full argv and
        # would expose values supplied to `az keyvault secret set --value`.
        raise _safe_cli_error(completed.stderr, completed.returncode)

    if completed.stderr and completed.returncode == 0:
        # Azure CLI sometimes writes non-sensitive warnings to stderr on success.
        print(completed.stderr.strip(), file=sys.stderr)

    return completed.stdout.strip() if capture and completed.stdout else ""


def get_option(name: str, default: str) -> str:
    try:
        index = sys.argv.index(name)
    except ValueError:
        return default
    if index + 1 >= len(sys.argv):
        raise SystemExit(f"Missing value after {name}")
    return sys.argv[index + 1]


def ensure_resource_group_argument() -> None:
    if "--resource-group" in sys.argv:
        return

    backend_app = get_option("--backend-app", bootstrap_module.DEFAULT_BACKEND_APP)
    resource_group = windows_az(
        "containerapp",
        "list",
        "--query",
        f"[?name=='{backend_app}'].resourceGroup | [0]",
        "--output",
        "tsv",
        capture=True,
    )
    if not resource_group:
        raise SystemExit(
            f"Resource group for Backend Container App {backend_app} could not be resolved. "
            "Pass it explicitly with --resource-group."
        )
    sys.argv.extend(["--resource-group", resource_group])
    print(f"Resolved Resource Group: {resource_group}")


def preflight_keyvault_network() -> None:
    """Fail before any secret value is passed if the Key Vault data plane is unreachable."""
    vault_name = get_option("--key-vault", bootstrap_module.DEFAULT_KEY_VAULT)
    windows_az(
        "keyvault",
        "secret",
        "list",
        "--vault-name",
        vault_name,
        "--maxresults",
        "1",
        "--query",
        "length(@)",
        "--output",
        "tsv",
        capture=True,
    )


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit(
            "This launcher is only for Windows. Use bootstrap_production_keyvault.py elsewhere."
        )

    windows_az("account", "show", "--output", "none")
    ensure_resource_group_argument()

    # Test Key Vault network/data-plane access before passing any secret value to
    # Azure CLI. This prevents a network failure from occurring on --value calls.
    preflight_keyvault_network()

    # Patch the module-level Azure CLI runner before bootstrap_module.main() calls
    # account/resource/container/key-vault commands. No shell is involved.
    bootstrap_module.az = windows_az
    bootstrap_module.main()


if __name__ == "__main__":
    main()
