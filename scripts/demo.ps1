# Bat toan bo he thong demo tren Windows bang mot lenh (chay tu thu muc goc repo, trong PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
# Mo 2 cua so: backend (uvicorn, cong 8000) va frontend (Vite, cong 5173), roi mo trinh duyet.
# Lan dau can: pip install -e ".[api]" (trong .venv) va: cd frontend; npm install
# Luu y: file nay chi dung chu khong dau vi Windows PowerShell 5.1 doc sai tieng Viet co dau.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

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

Write-Host "4/5 Mo backend va frontend..." -ForegroundColor Cyan
$venv = Join-Path $root ".venv\Scripts\Activate.ps1"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; . '$venv'; uvicorn backend.app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

Write-Host "5/5 Cho backend khoi dong..." -ForegroundColor Cyan
for ($i = 0; $i -lt 40; $i++) {
  try { Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 2 }
}
Start-Process "http://localhost:5173"
Write-Host "Xong. Tat: dong 2 cua so PowerShell, roi chay: docker compose -f db/docker-compose.yml down" -ForegroundColor Green
