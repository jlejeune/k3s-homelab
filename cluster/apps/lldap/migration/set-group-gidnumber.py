#!/usr/bin/env python3
"""
Set gidNumber on lldap groups from a Synology LDIF export.

Prerequisites:
    pip install requests
    kubectl port-forward -n lldap svc/lldap 17170:17170

    In lldap web UI, create the following custom attribute (Group Attributes):
      - gidnumber  (Integer, not a list)

Usage:
    python3 set-group-gidnumber.py \
        --ldif synology-export.ldif \
        --lldap-url http://localhost:17170 \
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


def parse_group_gidnumbers(path: str) -> dict[str, str]:
    with open(path) as f:
        raw = f.read()

    raw = raw.replace("\n ", "")
    result = {}

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
        if "posixgroup" in obj_classes and entry.get("cn") and entry.get("gidnumber"):
            cn = entry["cn"][0]
            gid = entry["gidnumber"][0]
            result[cn] = gid

    return result


def get_groups(url: str, token: str) -> list[dict]:
    data = graphql(url, token, """
        query {
            groups {
                id
                displayName
            }
        }
    """)
    return data["groups"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Set gidNumber on lldap groups")
    parser.add_argument("--ldif", required=True)
    parser.add_argument("--lldap-url", default="http://localhost:17170")
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    print("→ Authenticating to lldap...")
    token = login(args.lldap_url, args.admin_password)

    print("→ Parsing LDIF for group gidNumbers...")
    gid_map = parse_group_gidnumbers(args.ldif)
    print(f"  Found {len(gid_map)} groups in LDIF\n")

    print("→ Fetching groups from lldap...")
    groups = get_groups(args.lldap_url, token)

    print("→ Setting gidNumber...")
    for group in groups:
        name = group["displayName"]
        if name not in gid_map:
            print(f"  [skip] {name}: not in LDIF")
            continue
        gid = gid_map[name]
        try:
            graphql(args.lldap_url, token, """
                mutation UpdateGroup($group: UpdateGroupInput!) {
                    updateGroup(group: $group) { ok }
                }
            """, {"group": {"id": group["id"], "insertAttributes": [{"name": "gidnumber", "value": [gid]}]}})
            print(f"  [ok]   {name}: gidNumber={gid}")
        except RuntimeError as e:
            print(f"  [fail] {name}: {e}")

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
