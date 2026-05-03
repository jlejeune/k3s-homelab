#!/usr/bin/env bash
set -euo pipefail

LDAP_HOST="${LDAP_HOST:-192.168.1.210}"
LDAP_BIND_DN="${LDAP_BIND_DN:-cn=admin,dc=jlejeune,dc=home}"
LDAP_BASE_DN="ou=people,dc=jlejeune,dc=home"
VALID_ROLES=(internal external admin)

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Manage LDAP user roles (ou attribute).

Valid roles: internal, external, admin

Commands:
  add <uid> <role>       Add a role to a user
  remove <uid> <role>    Remove a role from a user
  list <uid>             List roles of a user
  list-by-role <role>    List all users with a given role

Environment variables:
  LDAP_HOST       LDAP server (default: 192.168.1.210)
  LDAP_BIND_DN    Bind DN (default: cn=admin,dc=jlejeune,dc=home)
  LDAP_PASSWORD   Admin password (auto-read from SOPS if not set)

Examples:
  $(basename "$0") add alice internal
  $(basename "$0") add alice admin
  $(basename "$0") remove alice external
  $(basename "$0") list alice
  $(basename "$0") list-by-role internal
EOF
}

get_password() {
  if [[ -n "${LDAP_PASSWORD:-}" ]]; then
    echo "$LDAP_PASSWORD"
    return
  fi
  local secrets="$REPO_ROOT/cluster/config/cluster-secrets.sops.yaml"
  if ! command -v sops &>/dev/null; then
    echo "Error: LDAP_PASSWORD not set and sops not found" >&2
    exit 1
  fi
  sops -d "$secrets" | grep 'SECRET_LDAP_ADMIN_QUERY_PASSWORD' | awk '{print $2}'
}

validate_role() {
  local role="$1"
  for r in "${VALID_ROLES[@]}"; do
    [[ "$r" == "$role" ]] && return 0
  done
  echo "Error: invalid role '$role'. Valid roles: ${VALID_ROLES[*]}" >&2
  exit 1
}

cmd_add() {
  local uid="$1" role="$2"
  validate_role "$role"
  local password
  password="$(get_password)"
  ldapmodify -x -H "ldap://$LDAP_HOST" -D "$LDAP_BIND_DN" -w "$password" <<EOF
dn: uid=$uid,$LDAP_BASE_DN
changetype: modify
add: ou
ou: $role
EOF
  echo "Added role '$role' to user '$uid'."
}

cmd_remove() {
  local uid="$1" role="$2"
  validate_role "$role"
  local password
  password="$(get_password)"
  ldapmodify -x -H "ldap://$LDAP_HOST" -D "$LDAP_BIND_DN" -w "$password" <<EOF
dn: uid=$uid,$LDAP_BASE_DN
changetype: modify
delete: ou
ou: $role
EOF
  echo "Removed role '$role' from user '$uid'."
}

cmd_list() {
  local uid="$1"
  local password
  password="$(get_password)"
  local result
  result=$(ldapsearch -x -H "ldap://$LDAP_HOST" -D "$LDAP_BIND_DN" -w "$password" \
    -b "$LDAP_BASE_DN" "(uid=$uid)" ou 2>/dev/null | grep "^ou:" | awk '{print $2}')
  if [[ -z "$result" ]]; then
    echo "User '$uid' has no roles."
  else
    echo "Roles for '$uid': $result"
  fi
}

cmd_list_by_role() {
  local role="$1"
  validate_role "$role"
  local password
  password="$(get_password)"
  ldapsearch -x -H "ldap://$LDAP_HOST" -D "$LDAP_BIND_DN" -w "$password" \
    -b "$LDAP_BASE_DN" "(ou=$role)" uid 2>/dev/null \
    | grep "^uid:" | awk '{print $2}' | sort
}

[[ $# -lt 1 ]] && { usage; exit 1; }

case "$1" in
  add)
    [[ $# -ne 3 ]] && { usage; exit 1; }
    cmd_add "$2" "$3"
    ;;
  remove)
    [[ $# -ne 3 ]] && { usage; exit 1; }
    cmd_remove "$2" "$3"
    ;;
  list)
    [[ $# -ne 2 ]] && { usage; exit 1; }
    cmd_list "$2"
    ;;
  list-by-role)
    [[ $# -ne 2 ]] && { usage; exit 1; }
    cmd_list_by_role "$2"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Error: unknown command '$1'" >&2
    usage
    exit 1
    ;;
esac
