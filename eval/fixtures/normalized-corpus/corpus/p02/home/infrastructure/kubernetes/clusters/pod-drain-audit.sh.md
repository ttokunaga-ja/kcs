```sh
#!/usr/bin/env bash
#
# Records the checkout pods affected by the node maintenance window. The output
# is intended for the incident channel and can be attached to a change record.

set -euo pipefail

cluster_name="${1:-atlas-prod-eks}"
namespace="${2:-checkout}"
audit_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

kubectl config use-context "${cluster_name}" >/dev/null

printf 'pod-drain audit at %s\n' "${audit_time}"
printf 'cluster=%s namespace=%s\n' "${cluster_name}" "${namespace}"
printf '%-46s %-18s %-16s %s\n' "POD" "NODE" "READY" "PDB"

while IFS=$'\t' read -r pod node ready; do
  pdb="$(kubectl -n "${namespace}" get pod "${pod}" \
    -o jsonpath='{range .metadata.ownerReferences[*]}{.kind}:{.name}{end}' 2>/dev/null || true)"
  printf '%-46s %-18s %-16s %s\n' "${pod}" "${node}" "${ready}" "${pdb:-unmanaged}"
done < <(
  kubectl -n "${namespace}" get pods \
    -l app.kubernetes.io/part-of=atlas-checkout \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\t"}{range .status.conditions[?(@.type=="Ready")]}{.status}{end}{"\n"}{end}'
)

echo
echo "Verify that every listed replica has a ready peer before approving a drain."
```
