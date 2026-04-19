#!/usr/bin/env python3
"""
Populate the memberUid custom attribute on lldap groups.

lldap stores group members as full DNs (uniqueMember), but Synology DSM 6.x
needs memberUid containing plain uid strings. This script reads all groups
via GraphQL and sets memberUid = [uid, uid, ...] on each group.

Prerequisites:
    pip install requests
    kubectl port-forward -n lldap svc/lldap 17170:17170

    In lldap web UI, create the following custom attribute (Group Attributes):
      - memberUid  (Text, IS a list)

Usage:
    python3 set-member-uid.py \
        --lldap-url http://localhost:17170 \
        --admin-password <lldap_admin_password>
"""
import argparse
import requests


def login(url: str, password: str) -> str:
    resp = requests.post(
        f"{url}/auth/simple/login",
        json={"username": "admin", "password": password},
    )
    resp.raise_for_status()
    return resp.json()["token"]


def graphql(url: str, token: str, query: str, variables: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{url}/api/graphql",
        headers=headers,
        json={"query": query, "variables": variables or {}},
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def get_groups(url: str, token: str) -> list[dict]:
    data = graphql(url, token, """
        query {
            groups {
                id
                displayName
                users {
                    id
                }
            }
        }
    """)
    return data["groups"]


def set_member_uid(url: str, token: str, group: dict) -> None:
    uids = [u["id"] for u in group["users"]]
    if not uids:
        print(f"  [skip] {group['displayName']}: no members")
        return

    try:
        graphql(url, token, """
            mutation UpdateGroup($group: UpdateGroupInput!) {
                updateGroup(group: $group) { ok }
            }
        """, {"group": {"id": group["id"], "insertAttributes": [{"name": "memberuid", "value": uids}]}})
        print(f"  [ok]   {group['displayName']}: {', '.join(uids)}")
    except RuntimeError as e:
        print(f"  [fail] {group['displayName']}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set memberUid on lldap groups for Synology DSM compatibility")
    parser.add_argument("--lldap-url", default="http://localhost:17170")
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    print("→ Authenticating to lldap...")
    token = login(args.lldap_url, args.admin_password)

    print("→ Fetching groups...")
    groups = get_groups(args.lldap_url, token)
    print(f"  Found {len(groups)} groups\n")

    print("→ Setting memberUid...")
    for group in groups:
        set_member_uid(args.lldap_url, token, group)

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
