#!/usr/bin/env python3
"""
Add POSIX attributes (uidNumber, gidNumber, homeDirectory, gecos) to lldap users
from a Synology LDIF export.

Prerequisites:
    pip install requests
    kubectl port-forward -n lldap svc/lldap 17170:17170

    In lldap web UI, create the following custom attributes (User Attributes section):
      - uidNumber  (Integer, not a list)
      - gidNumber  (Integer, not a list)
      - homeDirectory (String, not a list)
      - gecos      (String, not a list)

Usage:
    python3 set-posix-attributes.py \\
        --ldif synology-export.ldif \\
        --lldap-url http://localhost:17170 \\
        --admin-password <lldap_admin_password>
"""
import argparse
import base64
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


def parse_ldif(path: str) -> list[dict]:
    with open(path) as f:
        raw = f.read()

    raw = raw.replace("\n ", "")
    users = []

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
        obj_classes = [oc.lower() for oc in entry.get("objectclass", [])]
        if "person" in obj_classes and entry.get("uid"):
            users.append(entry)

    return users


def update_user_posix(url: str, token: str, entry: dict) -> None:
    uid = entry.get("uid", [""])[0]
    if not uid:
        return

    attrs = []
    for field in ("uidnumber", "gidnumber", "homedirectory", "gecos"):
        value = entry.get(field, [""])[0]
        if value:
            # lldap attribute names are camelCase
            name_map = {
                "uidnumber": "uidNumber",
                "gidnumber": "gidNumber",
                "homedirectory": "homeDirectory",
                "gecos": "gecos",
            }
            attrs.append({"name": name_map[field], "value": [value]})

    if not attrs:
        print(f"  [skip] {uid}: no POSIX attributes found in LDIF")
        return

    try:
        graphql(url, token, """
            mutation UpdateUser($user: UpdateUserInput!) {
                updateUser(user: $user) { ok }
            }
        """, {"user": {"id": uid, "insertAttributes": attrs}})
        attr_summary = ", ".join(f"{a['name']}={a['value'][0]}" for a in attrs)
        print(f"  [ok]   {uid}: {attr_summary}")
    except RuntimeError as e:
        print(f"  [fail] {uid}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set POSIX attributes on lldap users")
    parser.add_argument("--ldif", required=True)
    parser.add_argument("--lldap-url", default="http://localhost:17170")
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    print("→ Authenticating to lldap...")
    token = login(args.lldap_url, args.admin_password)

    print("→ Parsing LDIF...")
    users = parse_ldif(args.ldif)
    print(f"  Found {len(users)} users\n")

    print("→ Setting POSIX attributes...")
    for user in users:
        update_user_posix(args.lldap_url, token, user)

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
