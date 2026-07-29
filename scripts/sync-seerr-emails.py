#!/usr/bin/env python3
"""
Sync user emails from OpenLDAP into Seerr, matched by Jellyfin username.

Usage:
    export SEERR_API_KEY="..."          # from Seerr config Settings.json
    kubectl port-forward -n media-automation svc/seerr 5055:5055 &
    kubectl port-forward -n openldap svc/openldap 3890:389 &
    python3 sync-seerr-emails.py [--dry-run]

Requires: python3-ldap3, requests  (pip install ldap3 requests)
"""
import os
import sys
import requests
from ldap3 import Server, Connection, ALL

SEERR_URL = "http://localhost:5055"
LDAP_URL = "ldap://localhost:3890"
LDAP_BIND_DN = "cn=admin,dc=jlejeune,dc=home"
LDAP_BASE_DN = "ou=people,dc=jlejeune,dc=home"

DRY_RUN = "--dry-run" in sys.argv


def get_ldap_password():
    pw = os.environ.get("LDAP_BIND_PASSWORD")
    if not pw:
        sys.exit("Set LDAP_BIND_PASSWORD env var (bind password for cn=admin)")
    return pw


def get_ldap_mail_map():
    server = Server(LDAP_URL, get_info=ALL)
    conn = Connection(server, LDAP_BIND_DN, get_ldap_password(), auto_bind=True)
    conn.search(
        LDAP_BASE_DN,
        "(objectClass=inetOrgPerson)",
        attributes=["uid", "mail"],
    )
    mapping = {}
    for entry in conn.entries:
        uid = str(entry.uid)
        mail = str(entry.mail) if "mail" in entry else None
        if mail:
            mapping[uid.lower()] = mail
    conn.unbind()
    return mapping


def get_seerr_headers():
    api_key = os.environ.get("SEERR_API_KEY")
    if not api_key:
        sys.exit("Set SEERR_API_KEY env var (from Seerr config settings.json -> main.apiKey)")
    return {"X-Api-Key": api_key, "Content-Type": "application/json"}


def get_seerr_users(headers):
    users = []
    take, skip = 100, 0
    while True:
        resp = requests.get(
            f"{SEERR_URL}/api/v1/user",
            headers=headers,
            params={"take": take, "skip": skip},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        users.extend(results)
        if len(results) < take:
            break
        skip += take
    return users


def main():
    mail_map = get_ldap_mail_map()
    headers = get_seerr_headers()
    users = get_seerr_users(headers)

    updated, skipped = 0, 0
    for user in users:
        user_id = user["id"]
        username = (user.get("jellyfinUsername") or user.get("username") or "").lower()
        current_email = user.get("email")

        mail = mail_map.get(username)
        if not mail:
            print(f"[skip] {username or user_id}: no LDAP mail match")
            skipped += 1
            continue

        if current_email == mail:
            print(f"[ok]   {username}: already {mail}")
            skipped += 1
            continue

        print(f"[sync] {username}: {current_email!r} -> {mail}")
        if not DRY_RUN:
            resp = requests.post(
                f"{SEERR_URL}/api/v1/user/{user_id}/settings/main",
                headers=headers,
                json={"email": mail},
            )
            if resp.status_code >= 300:
                print(f"       ERROR {resp.status_code}: {resp.text}")
                continue
        updated += 1

    print(f"\nDone. Updated: {updated}, skipped: {skipped}{' (dry-run)' if DRY_RUN else ''}")


if __name__ == "__main__":
    main()
