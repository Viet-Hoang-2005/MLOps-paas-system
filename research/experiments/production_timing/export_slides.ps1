param([string]$OutputStem = 'CSONET_2026_Presentation_Production_Benchmark')
$ErrorActionPreference = 'Stop'
$deckPath = Join-Path $PSScriptRoot "output/$OutputStem.pptx"
$pdfPath = Join-Path $PSScriptRoot "output/$OutputStem.pdf"
$renderPath = Join-Path $PSScriptRoot ".build/$OutputStem-renders"
New-Item -ItemType Directory -Path $renderPath -Force | Out-Null
$application = New-Object -ComObject PowerPoint.Application
try {
    $deck = $application.Presentations.Open($deckPath, -1, 0, 0)
    if ($deck.Slides.Count -ne 23) { throw 'Unexpected slide count' }
    $deck.Export($renderPath, 'PNG', 1280, 720)
    foreach ($slide in $deck.Slides) { $slide.SlideShowTransition.Hidden = 0 }
    $deck.SaveAs($pdfPath, 32)
    $deck.Saved = -1
    $deck.Close()
} finally {
    if ($application.Presentations.Count -eq 0) { $application.Quit() }
}
