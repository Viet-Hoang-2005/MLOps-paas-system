param (
    [string]$TargetImage = "",
    [string]$Severity = "CRITICAL,HIGH",
    [switch]$AllSeverities
)

$severityFlag = if ($AllSeverities) { "" } else { "--severity $Severity" }
$cachePath = "${HOME}/.cache/trivy"

if ($TargetImage) {
    $images = @($TargetImage)
} else {
    $images = docker images --format "{{.Repository}}:{{.Tag}}" | Select-String "mlops-paas" | ForEach-Object { $_.Line }
}

if (-not $images -or $images.Count -eq 0) {
    Write-Host "No image found matching 'mlops-paas''." -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($images.Count) image(s) to scan for security vulnerabilities using Trivy:`n" -ForegroundColor Cyan
$images | ForEach-Object { Write-Host " - $_" -ForegroundColor Gray }
Write-Host ""

foreach ($img in $images) {
    Write-Host " [TRIVY SCAN] Image: $img" -ForegroundColor Green

    $cmd = "docker run --rm -v //var/run/docker.sock:/var/run/docker.sock -v ${cachePath}:/root/.cache/ aquasec/trivy:latest image $severityFlag --ignore-unfixed $img"
    Invoke-Expression $cmd
}

