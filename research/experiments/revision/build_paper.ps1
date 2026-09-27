param([string]$OutputDirectory = (Join-Path $PSScriptRoot 'build'))
$ErrorActionPreference = 'Stop'
$paperDirectory = Split-Path $PSScriptRoot -Parent
$repositoryRoot = Split-Path (Split-Path $paperDirectory -Parent) -Parent
$templateDirectory = Join-Path $repositoryRoot 'paper/LaTeX2e Proceedings Template'
$savedTexInputs = $env:TEXINPUTS
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$resolvedOutput = (Resolve-Path -LiteralPath $OutputDirectory).Path
try {
    $env:TEXINPUTS = $paperDirectory + ';' + $templateDirectory + ';' + $savedTexInputs
    Push-Location $paperDirectory
    for ($pass = 1; $pass -le 2; $pass++) {
        & pdflatex -interaction=nonstopmode -halt-on-error "-output-directory=$resolvedOutput" A_Drift-Aware_MLOps_Framework_for_Multi-Model_Serving_CSONET.tex
        if ($LASTEXITCODE -ne 0) { throw "LaTeX pass $pass failed." }
    }
} finally {
    Pop-Location
    $env:TEXINPUTS = $savedTexInputs
}
Write-Output "Review the PDF and log in $resolvedOutput before replacing the manuscript PDF."
