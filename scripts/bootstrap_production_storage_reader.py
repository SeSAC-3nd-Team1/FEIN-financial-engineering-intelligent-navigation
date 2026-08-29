#!/usr/bin/env python3
"""Grant the production GitHub Actions OIDC principal read-only access to the feature Blob container.

This is a one-time operator bootstrap. It never reads or prints Blob contents or secret values.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

DEFAULT_RESOURCE_GROUP = "project-3rd-team-1"
DEFAULT_STORAGE_ACCOUNT = "stfeindata"
DEFAULT_CONTAINER = "features"
# Production GitHub Actions OIDC service principal object id observed in Deploy production Run #99.
DEFAULT_PRINCIPAL_OBJECT_ID = "b886bd9e-d37f-42bb-aac2-e9d6308d6fa7"
ROLE_NAME = "Storage Blob Data Reader"


def az(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("az")
    if not executable:
        raise SystemExit("Azure CLI was not found. Install Azure CLI and ensure `az` is on PATH.")
    return subprocess.run(
        [executable, *args],
        check=check,
        text=True,
        capture_output=True,
    )


def output(*args: str) -> str:
    return az(*args).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-group", default=DEFAULT_RESOURCE_GROUP)
    parser.add_argument("--storage-account", default=DEFAULT_STORAGE_ACCOUNT)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--principal-object-id", default=DEFAULT_PRINCIPAL_OBJECT_ID)
    args = parser.parse_args()

    try:
        subscription_id = output("account", "show", "--query", "id", "-o", "tsv")
    except subprocess.CalledProcessError:
        raise SystemExit("Azure CLI is not authenticated. Run `az login` first.") from None

    if not subscription_id:
        raise SystemExit("Azure subscription could not be resolved from the current Azure CLI session.")

    # Confirm that the target storage account exists in the current subscription/RG.
    try:
        account_id = output(
            "storage",
            "account",
            "show",
            "--name",
            args.storage_account,
            "--resource-group",
            args.resource_group,
            "--query",
            "id",
            "-o",
            "tsv",
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise SystemExit(
            f"Storage account {args.storage_account} could not be resolved in resource group "
            f"{args.resource_group}. Check the selected Azure subscription.\n{detail}"
        ) from None

    if not account_id:
        raise SystemExit(f"Storage account {args.storage_account} could not be resolved.")

    container_scope = (
        f"{account_id}/blobServices/default/containers/{args.container}"
    )

    # Validate the container exists without reading data. ARM resource lookup only.
    container_lookup = az(
        "storage",
        "container-rm",
        "show",
        "--storage-account",
        args.storage_account,
        "--name",
        args.container,
        "--resource-group",
        args.resource_group,
        "--output",
        "none",
        check=False,
    )
    if container_lookup.returncode != 0:
        detail = (container_lookup.stderr or "").strip()
        raise SystemExit(
            f"Blob container {args.container} could not be resolved in {args.storage_account}.\n{detail}"
        )

    existing = output(
        "role",
        "assignment",
        "list",
        "--assignee-object-id",
        args.principal_object_id,
        "--scope",
        container_scope,
        "--role",
        ROLE_NAME,
        "--query",
        "length(@)",
        "-o",
        "tsv",
    )

    print(f"Subscription: {subscription_id}")
    print(f"Storage account: {args.storage_account}")
    print(f"Blob container: {args.container}")
    print(f"Role: {ROLE_NAME}")
    print(f"Principal object id: {args.principal_object_id}")

    if existing and existing != "0":
        print("Role assignment already exists. No change required.")
        return 0

    result = az(
        "role",
        "assignment",
        "create",
        "--assignee-object-id",
        args.principal_object_id,
        "--assignee-principal-type",
        "ServicePrincipal",
        "--role",
        ROLE_NAME,
        "--scope",
        container_scope,
        "--output",
        "json",
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise SystemExit(
            "Failed to assign Storage Blob Data Reader. The current Azure user needs "
            "Microsoft.Authorization/roleAssignments/write at this container scope or above.\n"
            f"{detail}"
        )

    payload = json.loads(result.stdout or "{}")
    if payload.get("roleDefinitionName") not in {None, ROLE_NAME}:
        raise SystemExit("Unexpected role assignment result returned by Azure CLI.")

    print("Storage Blob Data Reader assigned successfully at the features container scope.")
    print("Azure RBAC propagation can take several minutes before GitHub Actions can read Blob data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
