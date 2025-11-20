# PowerShell script to check if electrs is using the persisted database
# Run this on Windows: .\check_electrs_db_usage.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "electrs Database Usage Checker" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$dbPath = "C:\BitcoinCore\electrs-data\bitcoin"

# Check if directory exists
if (Test-Path $dbPath) {
    Write-Host "✓ Database directory exists: $dbPath" -ForegroundColor Green
    
    # Get total size
    $files = Get-ChildItem $dbPath -Recurse -File -ErrorAction SilentlyContinue
    $totalSize = ($files | Measure-Object -Property Length -Sum).Sum
    $totalSizeGB = [math]::Round($totalSize / 1GB, 2)
    
    Write-Host "  Total database size: $totalSizeGB GB" -ForegroundColor Yellow
    Write-Host "  Number of files: $($files.Count)" -ForegroundColor Yellow
    
    # Check for nested bitcoin directory
    $nestedPath = Join-Path $dbPath "bitcoin"
    if (Test-Path $nestedPath) {
        Write-Host ""
        Write-Host "⚠️  WARNING: Nested bitcoin directory found!" -ForegroundColor Red
        Write-Host "   Path: $nestedPath" -ForegroundColor Yellow
        Write-Host "   This suggests a path configuration issue" -ForegroundColor Yellow
        
        $nestedFiles = Get-ChildItem $nestedPath -Recurse -File -ErrorAction SilentlyContinue
        $nestedSize = ($nestedFiles | Measure-Object -Property Length -Sum).Sum
        $nestedSizeGB = [math]::Round($nestedSize / 1GB, 2)
        Write-Host "   Nested directory size: $nestedSizeGB GB" -ForegroundColor Yellow
    }
    
    # Check most recent file modification
    $recentFile = $files | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($recentFile) {
        Write-Host ""
        Write-Host "Most recently modified file:" -ForegroundColor Cyan
        Write-Host "  Name: $($recentFile.Name)" -ForegroundColor White
        Write-Host "  Modified: $($recentFile.LastWriteTime)" -ForegroundColor White
        Write-Host "  Size: $([math]::Round($recentFile.Length / 1MB, 2)) MB" -ForegroundColor White
    }
} else {
    Write-Host "✗ Database directory not found: $dbPath" -ForegroundColor Red
    Write-Host "  Database is not being persisted!" -ForegroundColor Red
}

Write-Host ""
Write-Host "Checking electrs logs for database usage..." -ForegroundColor Cyan
Write-Host ""

# Check electrs logs
$logs = docker logs electrs 2>&1 | Select-Object -Last 50

$resumeFound = $false
$startFound = $false

foreach ($line in $logs) {
    if ($line -match "resuming|continuing|found.*database") {
        Write-Host "  ✓ $line" -ForegroundColor Green
        $resumeFound = $true
    }
    if ($line -match "starting.*index|initializing.*index|creating.*database") {
        Write-Host "  ⚠️  $line" -ForegroundColor Yellow
        $startFound = $true
    }
}

if (-not $resumeFound -and -not $startFound) {
    Write-Host "  (No clear database status messages found)" -ForegroundColor Gray
    Write-Host "  Recent log entries:" -ForegroundColor Gray
    $logs | Select-Object -Last 5 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if ($totalSizeGB -gt 1) {
    Write-Host "✓ Database exists and is substantial ($totalSizeGB GB)" -ForegroundColor Green
    Write-Host "  This suggests indexing has progressed significantly" -ForegroundColor Green
} else {
    Write-Host "⚠️  Database is small ($totalSizeGB GB)" -ForegroundColor Yellow
    Write-Host "  Indexing may not have progressed far" -ForegroundColor Yellow
}

if ($resumeFound) {
    Write-Host "✓ electrs is resuming from existing database" -ForegroundColor Green
} elseif ($startFound) {
    Write-Host "⚠️  electrs appears to be starting fresh" -ForegroundColor Yellow
    Write-Host "  This could indicate:" -ForegroundColor Yellow
    Write-Host "    - Database path mismatch" -ForegroundColor Yellow
    Write-Host "    - Database corruption" -ForegroundColor Yellow
    Write-Host "    - Version incompatibility" -ForegroundColor Yellow
} else {
    Write-Host "? Could not determine database usage from logs" -ForegroundColor Gray
}

if (Test-Path $nestedPath) {
    Write-Host ""
    Write-Host "⚠️  RECOMMENDATION: Fix nested directory issue" -ForegroundColor Red
    Write-Host "  Change ELECTRS_DB_DIR from /data/bitcoin to /data" -ForegroundColor Yellow
    Write-Host "  Or move files from bitcoin\bitcoin to bitcoin\" -ForegroundColor Yellow
}

Write-Host ""

