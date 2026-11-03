# Bat toan bo he thong demo tren Windows bang mot lenh (chay tu thu muc goc repo, trong PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1          # che do DEMO: giao dien ban build, khong tu tai lai trang
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Dev     # che do PHAT TRIEN: sua code thi trang tu cap nhat
# Phan nao dang chay roi (cong 8000, 5173) thi bo qua, khong mo them cua so hay tab trinh duyet moi.
# Lan dau can: pip install -e ".[api]" (trong .venv) va: cd frontend; npm install
# Luu y: file nay chi dung chu khong dau vi Windows PowerShell 5.1 doc sai tieng Viet co dau.
param([switch]$Dev)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Test-Port($port) {
  try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $port); $c.Close(); return $true } catch { return $false }
}

Write-Host "1/5 Kiem tra Docker Desktop..." -ForegroundColor Cyan
docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Docker chua chay. Mo Docker Desktop, cho bieu tuong bao 'Engine running' roi chay lai lenh nay." -ForegroundColor Red
  exit 1
}

Write-Host "2/5 Bat PostgreSQL + Neo4j..." -ForegroundColor Cyan
docker compose -f db/docker-compose.yml --env-file .env up -d
if ($LASTEXITCODE -ne 0) { Write-Host "docker compose loi, xem thong bao o tren." -ForegroundColor Red; exit 1 }

Write-Host "3/5 Cho Neo4j san sang (toi da 60 giay)..." -ForegroundColor Cyan
for ($i = 0; $i -lt 30; $i++) {
  try { Invoke-WebRequest -Uri "http://localhost:7474" -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 2 }
}

Write-Host "4/5 Backend va giao dien..." -ForegroundColor Cyan
$venv = Join-Path $root ".venv\Scripts\Activate.ps1"
if (Test-Port 8000) {
  Write-Host "  Backend da chay o cong 8000, bo qua. (Muon nap code moi: dong cua so uvicorn roi chay lai lenh nay.)"
} else {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; . '$venv'; uvicorn backend.app.main:app --port 8000"
}
$openBrowser = $false
if (Test-Port 5173) {
  Write-Host "  Giao dien da chay o cong 5173, bo qua. Dung lai tab trinh duyet dang mo."
} else {
  if ($Dev) {
    $cmd = "Set-Location '$root\frontend'; npm run dev"
  } else {
    $cmd = "Set-Location '$root\frontend'; npm run build; npm run preview -- --port 5173 --strictPort"
  }
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
  $openBrowser = $true
}

Write-Host "5/5 Cho backend va giao dien khoi dong..." -ForegroundColor Cyan
for ($i = 0; $i -lt 60; $i++) {
  if ((Test-Port 8000) -and (Test-Port 5173)) { break }
  Start-Sleep -Seconds 2
}
if ($openBrowser) { Start-Process "http://localhost:5173" }
Write-Host "Xong. Tat: dong cac cua so PowerShell vua mo, roi chay: docker compose -f db/docker-compose.yml down" -ForegroundColor Green
