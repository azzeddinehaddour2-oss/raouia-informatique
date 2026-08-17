# ============================================================
# photos_audit_cycle.ps1
# Un cycle du pilote automatique de recherche de photos produit.
# Invoque Claude Code en mode non-interactif avec les regles strictes
# de photos_audit_prompt.md, sur un lot borne de references (voir le
# prompt). Le garde-fou scripts/verify_product_images.py est une etape
# obligatoire executee PAR Claude a la fin de son propre cycle - ce
# script PowerShell ne fait qu'orchestrer et journaliser.
# Planifie via la tache Windows RAOUIA_Boutique_PhotosAudit (toutes les 4h).
# ============================================================

$ErrorActionPreference = "Stop"
$repo = "C:\Users\Administrateur.RAOUIAINFO\Documents\raouia-informatique"
$log = Join-Path $repo "scripts\photos_audit_cycle.log"
$promptFile = Join-Path $repo "scripts\photos_audit_prompt.md"

Set-Location $repo

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$ts] $msg" | Out-File -FilePath $log -Append -Encoding utf8
}

Write-Log "=== Debut cycle photos_audit ==="

try {
    $prompt = Get-Content -Raw -Encoding utf8 $promptFile
    $output = $prompt | & claude -p --permission-mode acceptEdits 2>&1
    $exitCode = $LASTEXITCODE
    $output | Out-File -FilePath $log -Append -Encoding utf8
    Write-Log "Claude Code termine avec code retour $exitCode"
}
catch {
    Write-Log "ERREUR : $($_.Exception.Message)"
    exit 1
}

Write-Log "=== Fin cycle photos_audit ==="
exit 0
