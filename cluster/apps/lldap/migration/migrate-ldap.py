#!/usr/bin/env python3
"""
Migrate users and groups from Synology LDAP (LDIF export) to lldap REST API.

Prerequisites:
    pip install requests
    kubectl port-forward -n lldap svc/lldap 17170:17170

Usage:
    python3 migrate-ldap.py \\
        --ldif synology-export.ldif \\
        --lldap-url http://localhost:17170 \\
        --admin-password <lldap_admin_password> \\
        --temp-password <temp_password_for_all_migrated_users>
"""
import argparse
import base64
import sys
import requests


def login(url: str, password: str) -> str:
    resp = requests.post(
        f"{url}/auth/simple/login",
        json={"username": "admin", "password": password},
    )
    resp.raise_for_status()
    return resp.json()["token"]


def parse_ldif(path: str) -> tuple[list[dict], list[dict]]:
    """Parse a multi-entry LDIF file into user and group dicts."""
    users: list[dict] = []
    groups: list[dict] = []
    entries: list[dict] = []

    with open(path) as f:
        raw = f.read()

    # Fold continuation lines (RFC 2849: line starting with a space)
    raw = raw.replace("\n ", "")

    for block in raw.strip().split("\n\n"):
        entry: dict[str, list[str]] = {}
        for line in block.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            if ":: " in line:
                key, _, value = line.partition(":: ")
                decoded = base64.b64decode(value).decode("utf-8", errors="replace")
                entry.setdefault(key.lower(), []).append(decoded)
            elif ": " in line:
                key, _, value = line.partition(": ")
                entry.setdefault(key.lower(), []).append(value)
        if entry:
            entries.append(entry)

    for entry in entries:
        obj_classes = [oc.lower() for oc in entry.get("objectclass", [])]
        if "person" in obj_classes:
            users.append(entry)
        elif "posixgroup" in obj_classes:
            groups.append(entry)

    return users, groups


def create_user(url: str, token: str, entry: dict, temp_password: str) -> None:
    uid = entry.get("uid", [""])[0]
    if not uid:
        print(f"  Skipping entry with no uid: {entry.get('dn', ['?'])[0]}")
        return

    mail = entry.get("mail", [f"{uid}@jlejeune.home"])[0]
    display_name = entry.get("gecos", entry.get("cn", [uid]))[0]
    first_name = entry.get("givenname", [""])[0]
    last_name = entry.get("sn", [""])[0]

    try:
        graphql(url, token, """
            mutation CreateUser($user: CreateUserInput!) {
                createUser(user: $user) { id }
            }
        """, {"user": {
            "id": uid,
            "email": mail,
            "displayName": display_name,
            "firstName": first_name,
            "lastName": last_name,
        }})
    except RuntimeError as e:
        if "already exists" in str(e).lower() or "unique" in str(e).lower():
            print(f"  [skip] User already exists: {uid}")
            return
        raise

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.put(
        f"{url}/api/user/{uid}/reset_password",
        headers=headers,
        json={"userId": uid, "password": temp_password},
    )
    if not resp.ok:
        print(f"  [ok]   Created user: {uid} <{mail}> (password NOT set — reset manually)")
    else:
        print(f"  [ok]   Created user: {uid} <{mail}>")


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


def get_or_create_group(url: str, token: str, name: str) -> int:
    # Check if group already exists
    result = graphql(url, token, """
        query { groups { id displayName } }
    """)
    for g in result["groups"]:
        if g["displayName"] == name:
            print(f"  [skip] Group already exists: {name} (id={g['id']})")
            return g["id"]

    result = graphql(url, token, """
        mutation CreateGroup($name: String!) {
            createGroup(name: $name) { id displayName }
        }
    """, {"name": name})
    group_id = result["createGroup"]["id"]
    print(f"  [ok]   Created group: {name} (id={group_id})")
    return group_id


def add_user_to_group(url: str, token: str, group_id: int, user_id: str) -> None:
    try:
        graphql(url, token, """
            mutation AddUserToGroup($userId: String!, $groupId: Int!) {
                addUserToGroup(userId: $userId, groupId: $groupId) { ok }
            }
        """, {"userId": user_id, "groupId": group_id})
        print(f"    [ok] Added {user_id} → group {group_id}")
    except RuntimeError as e:
        err = str(e)
        if "FOREIGN KEY" in err:
            print(f"    [warn] Skipped {user_id} → group {group_id}: user not found in lldap")
        elif "UNIQUE constraint" in err:
            print(f"    [skip] {user_id} already in group {group_id}")
        else:
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Synology LDAP to lldap")
    parser.add_argument("--ldif", required=True, help="Path to LDIF export file")
    parser.add_argument("--lldap-url", default="http://localhost:17170")
    parser.add_argument("--admin-password", required=True, help="lldap admin password")
    parser.add_argument("--temp-password", required=True,
                        help="Temporary password assigned to all migrated users")
    args = parser.parse_args()

    print("→ Authenticating to lldap...")
    token = login(args.lldap_url, args.admin_password)

    print("→ Parsing LDIF...")
    users, groups = parse_ldif(args.ldif)
    print(f"  Found {len(users)} users and {len(groups)} groups\n")

    print("→ Creating users...")
    for user in users:
        create_user(args.lldap_url, token, user, args.temp_password)

    print("\n→ Creating groups and memberships...")
    for group in groups:
        name = group.get("cn", [""])[0]
        if not name:
            continue
        members = group.get("memberuid", [])
        group_id = get_or_create_group(args.lldap_url, token, name)
        for member_uid in members:
            add_user_to_group(args.lldap_url, token, group_id, member_uid)

    print("\n✓ Migration complete.")
    print(f"  All users have temporary password. Remind them to reset via Authelia after Phase 2.")


if __name__ == "__main__":
    main()
