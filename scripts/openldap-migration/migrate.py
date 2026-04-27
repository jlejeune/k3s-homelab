#!/usr/bin/env python3
"""
Migrate users and groups from lldap to OpenLDAP, enriched with Synology LDIF.

Users are created with posix attributes (uidNumber, gidNumber, givenName, sn)
sourced from the Synology LDIF. Groups are created as posixGroup with gidNumber
and memberUid from the Synology LDIF. Passwords are taken from the lldap SQLite DB.

Prerequisites:
    pip install requests ldap3
    kubectl port-forward -n lldap svc/lldap 17170:17170
    kubectl port-forward -n openldap svc/openldap 3389:389
    kubectl cp lldap/<pod-name>:/data/users.db /tmp/lldap-users.db

Usage:
    python3 migrate.py \
        --ldif /backup/synology-export.ldif \
        --lldap-password <lldap_admin_password> \
        --sqlite-db /tmp/lldap-users.db \
        --ldap-password <openldap_admin_password>
"""
import argparse
import base64
import sqlite3

import requests
from ldap3 import ALL, Connection, Server


USERS_QUERY = """
query {
  users {
    id
    email
    displayName
  }
}
"""

GROUPS_QUERY = """
query {
  groups {
    displayName
    users { id }
  }
}
"""

# Synology internal groups irrelevant for homelab
SKIP_GROUPS = {"Directory Operators", "Directory Clients", "Directory Consumers"}

# lldap internal groups — skip from migration
LLDAP_GROUPS = {"lldap_admin", "lldap_password_manager", "lldap_strict_readonly"}


def parse_ldif(path: str) -> list[dict]:
    with open(path) as f:
        lines = f.readlines()

    joined = []
    for line in lines:
        if line.startswith(" ") and joined:
            joined[-1] = joined[-1].rstrip("\n") + line[1:]
        else:
            joined.append(line)

    entries = []
    current: dict = {}
    for line in joined:
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            if current:
                entries.append(current)
                current = {}
            continue
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        if raw.startswith(": "):
            val = base64.b64decode(raw[2:].strip()).decode("utf-8", errors="replace")
        else:
            val = raw.lstrip(" ").strip()
        current.setdefault(key, []).append(val)

    if current:
        entries.append(current)

    return entries


def split_gecos(gecos: str) -> tuple[str, str]:
    """Split 'Firstname REST OF NAME' → (givenName, sn)."""
    parts = gecos.strip().split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], parts[0]


def load_synology_users(entries: list[dict]) -> dict[str, dict]:
    """Extract posixAccount entries from Synology LDIF."""
    users = {}
    for entry in entries:
        if "posixAccount" not in entry.get("objectClass", []):
            continue
        uid = (entry.get("uid") or [None])[0]
        if not uid or uid == "admin":
            continue
        gecos = (entry.get("gecos") or [uid])[0]
        given_name, sn = split_gecos(gecos)
        users[uid] = {
            "uidNumber": (entry.get("uidNumber") or ["10000"])[0],
            "gidNumber": (entry.get("gidNumber") or ["10000"])[0],
            "givenName": given_name,
            "sn": sn,
            "displayName": gecos,
            "homeDirectory": (entry.get("homeDirectory") or [f"/home/{uid}"])[0],
        }
    return users


def load_synology_groups(entries: list[dict]) -> dict[str, dict]:
    """Extract posixGroup entries from Synology LDIF."""
    groups = {}
    for entry in entries:
        if "posixGroup" not in entry.get("objectClass", []):
            continue
        cn = (entry.get("cn") or [None])[0]
        if not cn or cn in SKIP_GROUPS:
            continue
        groups[cn] = {
            "gidNumber": (entry.get("gidNumber") or ["20000"])[0],
            "memberUid": entry.get("memberUid", []),
        }
    return groups


def load_passwords(sqlite_db: str) -> dict[str, str]:
    conn = sqlite3.connect(sqlite_db)
    rows = conn.execute("SELECT user_id, password_hash FROM users").fetchall()
    conn.close()
    # lldap stores bcrypt as "$2b$..." — OpenLDAP accepts it with {CRYPT} prefix
    return {uid: f"{{CRYPT}}{pw}" for uid, pw in rows if pw}


def lldap_login(url: str, password: str) -> str:
    resp = requests.post(
        f"{url}/auth/simple/login",
        json={"username": "admin", "password": password},
    )
    resp.raise_for_status()
    return resp.json()["token"]


def lldap_graphql(url: str, token: str, query: str) -> dict:
    resp = requests.post(
        f"{url}/api/graphql",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": query},
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def migrate_users(
    conn: Connection,
    lldap_users: list[dict],
    synology_users: dict[str, dict],
    passwords: dict[str, str],
    base_dn: str,
) -> None:
    people_dn = f"ou=people,{base_dn}"
    ok = fail = 0
    for u in lldap_users:
        uid = u["id"]
        if uid == "admin":
            print(f"  [skip] {uid}: lldap internal admin")
            continue
        dn = f"uid={uid},{people_dn}"
        syn = synology_users.get(uid, {})
        display_name = syn.get("displayName") or u.get("displayName") or uid
        attrs = {
            "objectClass": ["inetOrgPerson", "posixAccount"],
            "uid": uid,
            "cn": display_name,
            "sn": syn.get("sn") or u.get("lastName") or uid,
            "givenName": syn.get("givenName") or u.get("firstName") or uid,
            "displayName": display_name,
            "mail": u.get("email") or f"{uid}@jlejeune.home",
            "uidNumber": syn.get("uidNumber") or "10000",
            "gidNumber": syn.get("gidNumber") or "10000",
            "homeDirectory": syn.get("homeDirectory") or f"/home/{uid}",
            "loginShell": "/bin/sh",
        }
        pw = passwords.get(uid)
        if pw:
            attrs["userPassword"] = pw
        if conn.add(dn, attributes=attrs):
            print(f"  [ok]   {uid} (uid={attrs['uidNumber']}, gid={attrs['gidNumber']})")
            ok += 1
        else:
            print(f"  [fail] {uid}: {conn.result['description']}")
            fail += 1
    print(f"  → {ok} created, {fail} failed")


def migrate_groups(
    conn: Connection,
    synology_groups: dict[str, dict],
    lldap_groups: list[dict],
    base_dn: str,
) -> None:
    groups_dn = f"ou=groups,{base_dn}"
    # Build set of group names coming from lldap (excluding internal ones) for reference
    lldap_names = {g["displayName"] for g in lldap_groups if g["displayName"] not in LLDAP_GROUPS}
    ok = fail = 0
    for cn, g in synology_groups.items():
        if cn not in lldap_names:
            print(f"  [skip] {cn}: not in lldap, skipping")
            continue
        dn = f"cn={cn},{groups_dn}"
        attrs: dict = {
            "objectClass": ["top", "posixGroup"],
            "cn": cn,
            "gidNumber": g["gidNumber"],
        }
        if g["memberUid"]:
            attrs["memberUid"] = g["memberUid"]
        if conn.add(dn, attributes=attrs):
            print(f"  [ok]   {cn} (gid={g['gidNumber']}, {len(g['memberUid'])} members)")
            ok += 1
        else:
            print(f"  [fail] {cn}: {conn.result['description']}")
            fail += 1
    print(f"  → {ok} created, {fail} failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate lldap → OpenLDAP using Synology LDIF")
    parser.add_argument("--ldif", required=True, help="Path to synology-export.ldif")
    parser.add_argument("--lldap-url", default="http://localhost:17170")
    parser.add_argument("--lldap-password", required=True)
    parser.add_argument("--sqlite-db", required=True, help="Path to lldap users.db SQLite file")
    parser.add_argument("--ldap-url", default="ldap://localhost:3389")
    parser.add_argument("--ldap-bind-dn", default="cn=admin,dc=jlejeune,dc=home")
    parser.add_argument("--ldap-password", required=True)
    parser.add_argument("--base-dn", default="dc=jlejeune,dc=home")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("→ Parsing Synology LDIF...")
    entries = parse_ldif(args.ldif)
    synology_users = load_synology_users(entries)
    synology_groups = load_synology_groups(entries)
    print(f"  {len(synology_users)} users, {len(synology_groups)} groups in LDIF")

    print("→ Loading password hashes from SQLite...")
    passwords = load_passwords(args.sqlite_db)
    print(f"  {len(passwords)} password hashes")

    print("→ Authenticating to lldap...")
    token = lldap_login(args.lldap_url, args.lldap_password)

    print("→ Fetching users from lldap...")
    lldap_users = lldap_graphql(args.lldap_url, token, USERS_QUERY)["users"]
    print(f"  {len(lldap_users)} users")

    print("→ Fetching groups from lldap...")
    lldap_groups = lldap_graphql(args.lldap_url, token, GROUPS_QUERY)["groups"]
    print(f"  {len(lldap_groups)} groups")

    if args.dry_run:
        print("\n[dry-run] Users to create:")
        for u in lldap_users:
            uid = u["id"]
            if uid == "admin":
                continue
            syn = synology_users.get(uid, {})
            print(
                f"  {uid}: uid={syn.get('uidNumber', '10000')} gid={syn.get('gidNumber', '10000')}"
                f"  givenName={syn.get('givenName', uid)!r}  sn={syn.get('sn', uid)!r}"
            )
        print("\n[dry-run] Groups to create (posixGroup):")
        lldap_names = {g["displayName"] for g in lldap_groups if g["displayName"] not in LLDAP_GROUPS}
        for cn, g in synology_groups.items():
            if cn in lldap_names:
                print(f"  {cn}: gid={g['gidNumber']}, members={g['memberUid']}")
        print("\n[dry-run] No changes applied.")
        return

    print("→ Connecting to OpenLDAP...")
    server = Server(args.ldap_url, get_info=ALL)
    conn = Connection(server, user=args.ldap_bind_dn, password=args.ldap_password, auto_bind=True)

    print("→ Migrating users...")
    migrate_users(conn, lldap_users, synology_users, passwords, args.base_dn)

    print("→ Migrating groups (posixGroup)...")
    migrate_groups(conn, synology_groups, lldap_groups, args.base_dn)

    conn.unbind()
    print("\n✓ Migration complete.")
    print("  Verify passwords work — if {CRYPT} bcrypt hashes fail, users can reset via Authelia.")


if __name__ == "__main__":
    main()
