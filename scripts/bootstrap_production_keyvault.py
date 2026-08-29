"""Bootstrap FE!N production secrets from a local .env into Azure Key Vault.

The script never prints secret values. It is intended as a one-time operator tool:

    python scripts/bootstrap_production_keyvault.py --env-file .env

Requirements:
- Azure CLI installed and authenticated (`az login`)
- permission to update the Backend Container App and Key Vault
- permission to grant the Backend managed identity Key Vault access when needed

The local .env file is read only by this process and is never uploaded.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


DEFAULT_BACKEND_APP = "ca-backend-fein-vnet"
DEFAULT_KEY_VAULT = "kv-fein"

# env name -> (Key Vault secret name, Container App secret name)
SECRET_MAPPINGS: dict[str, tuple[str, str]] = {
    "ACS_EMAIL_CONNECTION_STRING": ("email-service-key", "acs-email"),
    "KIS_APP_KEY": ("kis-app-key", "kis-key"),
    "KIS_APP_SECRET": ("kis-app-secret", "kis-secret"),
    "NAVER_API_HUB_CLIENT_ID": ("naver-api-hub-client-id", "naver-id"),
    "NAVER_API_HUB_CLIENT_SECRET": ("naver-api-hub-client-secret", "naver-secret"),
    "AZURE_OPENAI_API_KEY": ("openai-api-key", "aoai-key"),
    "AZURE_OPENAI_CHATBOT_API_KEY": ("openai-chatbot-api-key", "aoai-chat-key"),
}

# Non-secret production settings that are safe to copy from local .env.
PLAIN_ENV_NAMES = (
    "ACS_EMAIL_SENDER_ADDRESS",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_RECOMMENDATION_DEPLOYMENT",
    "AZURE_OPENAI_REBALANCING_DEPLOYMENT",
    "AZURE_OPENAI_COMPARISON_DEPLOYMENT",
    "AZURE_OPENAI_CHATBOT_ENDPOINT",
    "AZURE_OPENAI_CHATBOT_DEPLOYMENT",
)


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_azure_cli() -> str:
    """Resolve Azure CLI in a cross-platform way.

    On Windows the Microsoft installer commonly exposes Azure CLI as az.cmd.
    Passing the extension-less name `az` directly to CreateProcess can fail even
    when CMD resolves it successfully via PATHEXT.
    """
    candidates = ("az.cmd", "az.exe", "az") if os.name == "nt" else ("az",)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SystemExit(
        "Azure CLI executable was not found. Confirm `where az`/`az version` works "
        "and reopen the terminal after installing Azure CLI."
    )


AZURE_CLI = resolve_azure_cli()


def az(*args: str, capture: bool = False, check: bool = True) -> str:
    if os.name == "nt" and AZURE_CLI.lower().endswith((".cmd", ".bat")):
        comspec = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        cli_command = subprocess.list2cmdline([AZURE_CLI, *args])
        command = [comspec, "/d", "/s", "/c", cli_command]
    else:
        command = [AZURE_CLI, *args]

    try:
        completed = subprocess.run(
            command,
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=None,
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Azure CLI could not be executed from Python: {AZURE_CLI}. "
            "Close and reopen the terminal, then verify `az version`."
        ) from exc
    return completed.stdout.strip() if capture and completed.stdout else ""


def require_values(env: dict[str, str], names: Iterable[str]) -> None:
    missing = [name for name in names if not env.get(name, "").strip()]
    if missing:
        raise SystemExit(
            "Missing required values in local .env: " + ", ".join(missing)
        )


def resolve_resource_group(backend_app: str, requested: str | None) -> str:
    if requested:
        return requested
    resource_group = az(
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
    return resource_group


def ensure_backend_keyvault_access(
    *, resource_group: str, backend_app: str, vault_name: str
) -> None:
    az(
        "containerapp",
        "identity",
        "assign",
        "--name",
        backend_app,
        "--resource-group",
        resource_group,
        "--system-assigned",
        "--output",
        "none",
    )

    principal_id = az(
        "containerapp",
        "show",
        "--name",
        backend_app,
        "--resource-group",
        resource_group,
        "--query",
        "identity.principalId",
        "--output",
        "tsv",
        capture=True,
    )
    if not principal_id:
        raise SystemExit("Backend managed identity principalId could not be resolved.")

    vault_id = az(
        "keyvault",
        "show",
        "--name",
        vault_name,
        "--query",
        "id",
        "--output",
        "tsv",
        capture=True,
    )
    if not vault_id:
        raise SystemExit(f"Key Vault {vault_name} could not be resolved.")

    rbac_enabled = az(
        "keyvault",
        "show",
        "--name",
        vault_name,
        "--query",
        "properties.enableRbacAuthorization",
        "--output",
        "tsv",
        capture=True,
    ).lower()

    if rbac_enabled == "true":
        role_count = az(
            "role",
            "assignment",
            "list",
            "--assignee-object-id",
            principal_id,
            "--scope",
            vault_id,
            "--role",
            "Key Vault Secrets User",
            "--query",
            "length(@)",
            "--output",
            "tsv",
            capture=True,
        )
        if role_count == "0":
            az(
                "role",
                "assignment",
                "create",
                "--assignee-object-id",
                principal_id,
                "--assignee-principal-type",
                "ServicePrincipal",
                "--role",
                "Key Vault Secrets User",
                "--scope",
                vault_id,
                "--output",
                "none",
            )
    else:
        az(
            "keyvault",
            "set-policy",
            "--name",
            vault_name,
            "--object-id",
            principal_id,
            "--secret-permissions",
            "get",
            "list",
            "--output",
            "none",
        )


def bootstrap(
    *,
    env_file: Path,
    resource_group: str | None,
    backend_app: str,
    vault_name: str,
    subscription: str | None,
) -> None:
    if not env_file.is_file():
        raise SystemExit(f".env file not found: {env_file}")

    env = parse_dotenv(env_file)
    require_values(
        env,
        (
            "ACS_EMAIL_CONNECTION_STRING",
            "ACS_EMAIL_SENDER_ADDRESS",
            "KIS_APP_KEY",
            "KIS_APP_SECRET",
            "NAVER_API_HUB_CLIENT_ID",
            "NAVER_API_HUB_CLIENT_SECRET",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_CHATBOT_ENDPOINT",
            "AZURE_OPENAI_CHATBOT_API_KEY",
            "AZURE_OPENAI_CHATBOT_DEPLOYMENT",
        ),
    )

    # Fail before touching resources if Azure CLI authentication is unavailable.
    try:
        az("account", "show", "--output", "none")
    except subprocess.CalledProcessError as exc:
        raise SystemExit("Azure CLI is not authenticated. Run `az login` first.") from exc

    if subscription:
        az("account", "set", "--subscription", subscription)

    resource_group = resolve_resource_group(backend_app, resource_group)

    print(f"Using Azure CLI: {AZURE_CLI}")
    print(f"Using Resource Group: {resource_group}")
    print(f"Using Key Vault: {vault_name}")
    print(f"Using Backend Container App: {backend_app}")
    print("Secret values will not be printed.")

    ensure_backend_keyvault_access(
        resource_group=resource_group,
        backend_app=backend_app,
        vault_name=vault_name,
    )

    configured_secret_refs: list[str] = []
    for env_name, (kv_secret_name, app_secret_name) in SECRET_MAPPINGS.items():
        value = env.get(env_name, "").strip()
        if not value:
            print(f"Skipping unset optional secret: {env_name}")
            continue

        az(
            "keyvault",
            "secret",
            "set",
            "--vault-name",
            vault_name,
            "--name",
            kv_secret_name,
            "--value",
            value,
            "--output",
            "none",
        )
        print(f"Stored Key Vault secret: {kv_secret_name}")

        keyvault_ref = (
            f"{app_secret_name}=keyvaultref:https://{vault_name}.vault.azure.net/"
            f"secrets/{kv_secret_name},identityref:system"
        )
        az(
            "containerapp",
            "secret",
            "set",
            "--name",
            backend_app,
            "--resource-group",
            resource_group,
            "--secrets",
            keyvault_ref,
            "--output",
            "none",
        )
        configured_secret_refs.append(f"{env_name}=secretref:{app_secret_name}")

    plain_env_args = [
        f"{name}={env[name].strip()}"
        for name in PLAIN_ENV_NAMES
        if env.get(name, "").strip()
    ]
    env_args = [*configured_secret_refs, *plain_env_args]

    if env_args:
        az(
            "containerapp",
            "update",
            "--name",
            backend_app,
            "--resource-group",
            resource_group,
            "--set-env-vars",
            *env_args,
            "--output",
            "none",
        )

    print("Production Key Vault/bootstrap configuration completed.")
    print(
        "Note: recommendation/rebalancing/comparison deployment variables are only "
        "set when they are non-empty in the local .env."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--resource-group",
        default=None,
        help="Azure resource group. Omit to auto-resolve from the Backend Container App.",
    )
    parser.add_argument("--backend-app", default=DEFAULT_BACKEND_APP)
    parser.add_argument("--key-vault", default=DEFAULT_KEY_VAULT)
    parser.add_argument("--subscription", default=None)
    args = parser.parse_args()

    bootstrap(
        env_file=args.env_file,
        resource_group=args.resource_group,
        backend_app=args.backend_app,
        vault_name=args.key_vault,
        subscription=args.subscription,
    )


if __name__ == "__main__":
    main()
