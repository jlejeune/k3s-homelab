#!/usr/bin/env bash
# Set a temporary password for all lldap users (except admin) via ldappasswd.
#
# Prerequisites:
#   kubectl port-forward -n lldap svc/lldap 3890:3890
#
# Usage:
#   ./set-passwords.sh \
#     --admin-password <lldap_admin_password> \
#     --temp-password  <temp_password_for_all_users> \
#     [--ldap-url      ldap://localhost:3890]
#     [--base-dn       dc=jlejeune,dc=home]

set -euo pipefail

LDAP_URL="ldap://localhost:3890"
BASE_DN="dc=jlejeune,dc=home"
ADMIN_DN="uid=admin,ou=people,dc=jlejeune,dc=home"
ADMIN_PASSWORD=""
TEMP_PASSWORD=""

usage() {
  grep '^#' "$0" | sed 's/^# \?//'
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --admin-password) ADMIN_PASSWORD="$2"; shift 2 ;;
    --temp-password)  TEMP_PASSWORD="$2";  shift 2 ;;
    --ldap-url)       LDAP_URL="$2";       shift 2 ;;
    --base-dn)        BASE_DN="$2";        shift 2 ;;
    *) usage ;;
  esac
done

[[ -z "$ADMIN_PASSWORD" || -z "$TEMP_PASSWORD" ]] && usage

echo "→ Listing users from lldap..."
USERS=$(ldapsearch -x -H "$LDAP_URL" \
  -D "$ADMIN_DN" -w "$ADMIN_PASSWORD" \
  -b "ou=people,$BASE_DN" \
  "(objectClass=inetOrgPerson)" uid \
  2>/dev/null | grep "^uid:" | awk '{print $2}')

if [[ -z "$USERS" ]]; then
  echo "  No users found. Is port-forward running?"
  exit 1
fi

echo ""
echo "→ Setting temporary password for all users (except admin)..."
while IFS= read -r uid; do
  if [[ "$uid" == "admin" ]]; then
    echo "  [skip] admin"
    continue
  fi
  ldappasswd -x -H "$LDAP_URL" \
    -D "$ADMIN_DN" -w "$ADMIN_PASSWORD" \
    -s "$TEMP_PASSWORD" \
    "uid=${uid},ou=people,${BASE_DN}" 2>&1 && echo "  [ok]  $uid" || echo "  [fail] $uid"
done <<< "$USERS"

echo ""
echo "✓ Done. All users can now log in with the temporary password."
echo "  Remind them to change it after Phase 2 is deployed."
