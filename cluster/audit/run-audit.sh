#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="${SCRIPT_DIR}/reports/$(date +%Y-%m-%d)"
mkdir -p "${REPORT_DIR}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
section() { echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${GREEN}  $*${NC}"; echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }

# ─── Pre-flight checks ────────────────────────────────────────────────────────
check_deps() {
  for cmd in kubectl; do
    command -v "$cmd" &>/dev/null || { error "Missing command: $cmd"; exit 1; }
  done
}

# ─── 1. kube-bench (control plane) ───────────────────────────────────────────
run_kube_bench_master() {
  section "kube-bench — Control Plane (theoden)"

  kubectl delete job kube-bench-master --ignore-not-found=true -n default
  kubectl apply -f "${SCRIPT_DIR}/kube-bench-master.yaml"
  info "Job started, waiting for completion..."

  if kubectl wait --for=condition=complete job/kube-bench-master -n default --timeout=120s 2>/dev/null; then
    kubectl logs job/kube-bench-master -n default | tee "${REPORT_DIR}/kube-bench-master.txt"
    info "Report saved: ${REPORT_DIR}/kube-bench-master.txt"
  else
    error "Job kube-bench-master failed or timed out"
    kubectl logs job/kube-bench-master -n default || true
  fi

  kubectl delete job kube-bench-master -n default --ignore-not-found=true
}

# ─── 2. kube-bench (single worker node) ──────────────────────────────────────
run_kube_bench_single_node() {
  local node="$1"

  if ! kubectl get node "${node}" &>/dev/null; then
    error "Unknown node: ${node}"
    error "Available nodes: $(kubectl get nodes -o jsonpath='{.items[*].metadata.name}')"
    exit 1
  fi

  info "Scanning node: ${node}"
  local arch
  arch=$(kubectl get node "${node}" -o jsonpath='{.status.nodeInfo.architecture}')
  info "Architecture: ${arch}"

  kubectl delete job kube-bench-node --ignore-not-found=true -n default

  python3 -c "
import sys, yaml
with open('${SCRIPT_DIR}/kube-bench-node.yaml') as f:
    doc = yaml.safe_load(f)
doc['spec']['template']['spec']['nodeName'] = '${node}'
doc['spec']['template']['spec'].pop('affinity', None)
print(yaml.dump(doc))
" | kubectl apply -f -

  if kubectl wait --for=condition=complete job/kube-bench-node -n default --timeout=120s 2>/dev/null; then
    kubectl logs job/kube-bench-node -n default | tee "${REPORT_DIR}/kube-bench-node-${node}.txt"
    info "Report saved: ${REPORT_DIR}/kube-bench-node-${node}.txt"
  else
    error "Job kube-bench-node failed on ${node}"
    kubectl logs job/kube-bench-node -n default || true
  fi

  kubectl delete job kube-bench-node -n default --ignore-not-found=true
}

# ─── 2. kube-bench (all worker nodes) ────────────────────────────────────────
run_kube_bench_nodes() {
  section "kube-bench — Workers"
  local nodes
  nodes=$(kubectl get nodes -l node-role.kubernetes.io/worker=true -o jsonpath='{.items[*].metadata.name}')

  for node in $nodes; do
    run_kube_bench_single_node "${node}"
  done
}

# ─── 3. kube-score (live manifests from cluster) ─────────────────────────────
run_kube_score() {
  section "kube-score — Manifest analysis"

  if ! command -v kube-score &>/dev/null; then
    warning "kube-score not found, installing..."
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
    VERSION=$(curl -sL "https://api.github.com/repos/zegl/kube-score/releases/latest" | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'].lstrip('v'))")
    curl -sSL "https://github.com/zegl/kube-score/releases/download/v${VERSION}/kube-score_${VERSION}_${OS}_${ARCH}.tar.gz" | tar xz -C /tmp
    mkdir -p ~/.local/bin && mv /tmp/kube-score ~/.local/bin/kube-score
    info "kube-score installed (v${VERSION})"
  fi

  info "Fetching resources from cluster..."
  kubectl get \
    deployments,statefulsets,daemonsets,replicasets,jobs,cronjobs,pods,\
services,ingresses,networkpolicies,poddisruptionbudgets,\
horizontalpodautoscalers \
    --all-namespaces -o yaml 2>/dev/null \
  > /tmp/kube-score-input.yaml

  info "Running kube-score analysis..."
  if ! kube-score score /tmp/kube-score-input.yaml \
    --output-format ci \
    | tee "${REPORT_DIR}/kube-score.txt"; then
    warning "kube-score exited with non-zero (expected when issues are found)"
  fi

  info "Summary of CRITICAL and WARNING issues:"
  grep -E "(CRITICAL|WARNING)" "${REPORT_DIR}/kube-score.txt" | sort | uniq -c | sort -rn | head -30 || true
  info "Full report: ${REPORT_DIR}/kube-score.txt"
  rm -f /tmp/kube-score-input.yaml
}

# ─── 4. Popeye ───────────────────────────────────────────────────────────────
run_popeye() {
  section "Popeye — Live cluster scan"

  if ! command -v popeye &>/dev/null; then
    warning "popeye not found, installing..."
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
    curl -sSL "https://github.com/derailed/popeye/releases/latest/download/popeye_${OS}_${ARCH}.tar.gz" | tar xz -C /tmp
    mkdir -p ~/.local/bin && mv /tmp/popeye ~/.local/bin/popeye
    info "popeye installed"
  fi

  # HTML report
  popeye \
    --save \
    --out html \
    --output-file "${REPORT_DIR}/popeye-report.html" \
    2>/dev/null || true

  # Text summary
  popeye \
    --out standard \
    2>/dev/null \
    | tee "${REPORT_DIR}/popeye.txt" || true

  info "HTML report: ${REPORT_DIR}/popeye-report.html"
  info "Text report: ${REPORT_DIR}/popeye.txt"
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  check_deps

  local target="${1:-all}"
  local extra="${2:-}"

  case "$target" in
    master)       run_kube_bench_master ;;
    nodes)        run_kube_bench_nodes ;;
    node)
      [[ -z "$extra" ]] && { error "Usage: $0 node <node-name>"; exit 1; }
      section "kube-bench — Node ${extra}"
      run_kube_bench_single_node "${extra}"
      ;;
    kube-bench)   run_kube_bench_master; run_kube_bench_nodes ;;
    kube-score)   run_kube_score ;;
    popeye)       run_popeye ;;
    all)
      run_kube_bench_master
      run_kube_bench_nodes
      run_kube_score
      run_popeye
      ;;
    *)
      echo "Usage: $0 [all|master|nodes|node <name>|kube-bench|kube-score|popeye]"
      exit 1
      ;;
  esac

  section "Audit complete"
  info "Reports available in: ${REPORT_DIR}/"
  ls -lh "${REPORT_DIR}/"
}

main "$@"
