"""Safe launcher for production Key Vault bootstrap.

This wrapper protects secret values from process argv / traceback exposure by
converting `az keyvault secret set --value ...` calls into temporary-file based
`--file` calls. It also performs a Key Vault data-plane preflight before any
secret is staged.

Usage:
    python scripts/bootstrap_production_keyvault_safe.py --env-file .env
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import bootstrap_production_keyvault as bootstrap_module


AZURE_CLI = shutil.which("az")
if not AZURE_CLI:
    raise SystemExit("Azure CLI was not found. Verify `az version` first.")


def _get_option(name: str, default: str) -> str:
    try:
        index = sys.argv.index(name)
    except ValueError:
        return default
    if index + 1 >= len(sys.argv):
        raise SystemExit(f"Missing value after {name}")
    return sys.argv[index + 1]


def safe_az(*args: str, capture: bool = False, check: bool = True) -> str:
    command_args = list(args)
    secret_file: Path | None = None

    # Never place a raw Key Vault secret value in process argv.
    if command_args[:3] == ["keyvault", "secret", "set"] and "--value" in command_args:
        value_index = command_args.index("--value")
        if value_index + 1 >= len(command_args):
            raise SystemExit("Malformed Key Vault secret set command.")
        secret_value = command_args[value_index + 1]

        fd, temp_name = tempfile.mkstemp(prefix="fein-kv-", suffix=".txt")
        secret_file = Path(temp_name)
        try:
            if os.name != "nt":
                os.chmod(secret_file, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(secret_value)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            secret_file.unlink(missing_ok=True)
            raise

        command_args[value_index : value_index + 2] = [
            "--file",
            str(secret_file),
            "--encoding",
            "utf-8",
        ]

    try:
        completed = subprocess.run(
            [AZURE_CLI, *command_args],
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=None,
        )
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Azure CLI command failed. Review the Azure CLI error above. "
            "Command arguments are intentionally omitted to protect Secret values."
        ) from None
    finally:
        if secret_file is not None:
            secret_file.unlink(missing_ok=True)

    return completed.stdout.strip() if capture and completed.stdout else ""


def preflight_keyvault(vault_name: str) -> None:
    try:
        safe_az(
            "keyvault",
            "secret",
            "list",
            "--vault-name",
            vault_name,
            "--maxresults",
            "1",
            "--output",
            "none",
        )
    except SystemExit:
        raise SystemExit(
            f"Key Vault data-plane preflight failed for {vault_name}. "
            "Confirm the FE!N VPN/private network is connected and that your Azure identity has Secret list access."
        ) from None
    print(f"Key Vault data-plane preflight passed: {vault_name}")


def main() -> None:
    try:
        safe_az("account", "show", "--output", "none")
    except SystemExit:
        raise SystemExit("Azure CLI is not authenticated. Run `az login` first.") from None

    vault_name = _get_option("--key-vault", bootstrap_module.DEFAULT_KEY_VAULT)
    preflight_keyvault(vault_name)

    bootstrap_module.az = safe_az
    bootstrap_module.main()


if __name__ == "__main__":
    main()
