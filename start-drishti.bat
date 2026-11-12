@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [Drishti] Local Python environment not found.
  echo Create it once with:
  echo   py -3.11 -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r server\requirements.txt
  echo.
  pause
  exit /b 1
)

echo [Drishti] Starting the local server on http://127.0.0.1:8787 ...
start "Drishti server" cmd /k ".venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8787"

echo [Drishti] Waiting for the health endpoint ...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 40;$i++){ try { $r=Invoke-WebRequest 'http://127.0.0.1:8787/health' -UseBasicParsing -TimeoutSec 1; if($r.StatusCode -eq 200){$ok=$true;break} } catch {} ; Start-Sleep -Milliseconds 500 }; if(-not $ok){exit 1}"

if errorlevel 1 (
  echo [Drishti] Server did not become healthy. Check the server window for the error.
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8787/cockpit"
echo [Drishti] Cockpit opened. If Chrome has not loaded the extension yet:
echo   1. Open chrome://extensions
echo   2. Enable Developer mode
echo   3. Load unpacked -^> select this project's dist folder
echo.
echo Keep the server window open while you use Drishti.
pause
