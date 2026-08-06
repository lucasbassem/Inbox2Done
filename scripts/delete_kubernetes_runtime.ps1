param([string]$Namespace = "inbox2done")
$ErrorActionPreference = "Stop"
kubectl delete namespace $Namespace --ignore-not-found
if ($LASTEXITCODE -ne 0) { throw "Failed to delete namespace '$Namespace'." }
Write-Host "Deleted the Inbox2Done namespace. The kind cluster still exists."
Write-Host "Delete the cluster with: kind delete cluster --name inbox2done"
