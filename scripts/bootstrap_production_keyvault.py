"""Bootstrap FE!N production secrets from a local .env into Azure Key Vault.

This script intentionally never prints secret values. It is a one-time operator tool:

    python scripts/bootstrap_production_keyvault.py --env-file .env

Requirements:
- Azure CLI installed and authenticated (`az login`)
- permission to update the Backend Container App and Key Vault
- permission to grant the Backend managed identity Key Vault access when needed

The .env file stays local and is never uploaded by this script.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Iterable


DEFAULT_RESOURCE_GROUP = "project-3rd-team-1"
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


def az(*args: str, capture: bool = False, check: bool = True) -> str:
    completed = subprocess.run(
        ["az", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=None,
    )
    return completed.stdout.strip() if capture and completed.stdout else ""


def require_values(env: dict[str, str], names: Iterable[str]) -> None:
    missing = [name for name in names if not env.get(name, "").strip()]
    if missing:
        raise SystemExit(
            "Missing required values in local .env: " + ", ".join(missing)
        )


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
        "--resource-group",
        resource_group,
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
        "--resource-group",
        resource_group,
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
            "--resource-group",
            resource_group,
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
    resource_group: str,
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
    az("account", "show", "--output", "none")
    if subscription:
        az("account", "set", "--subscription", subscription)

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
            # All current mappings are expected for the production flow, but keep
            # this guard so future optional entries can be added safely.
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
    parser.add_argument("--resource-group", default=DEFAULT_RESOURCE_GROUP)
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
