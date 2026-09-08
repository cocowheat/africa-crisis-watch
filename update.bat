@echo off
setlocal
REM ============================================================
REM  Africa Crisis Watch - collect data and publish in one click
REM
REM  1. runs the collector (rewrites data\news.js)
REM  2. commits and pushes to git, which makes GitHub Pages /
REM     Gitee Pages rebuild the public site automatically
REM
REM  If no git remote is configured yet, step 2 is skipped and
REM  only the local copy is refreshed.
REM ============================================================
cd /d "%~dp0"

set "PY=C:\Users\sykwh\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo ============================================================
echo  Africa Crisis Watch - update and publish
echo ============================================================
echo.

echo [1/3] Collecting from public feeds, 1-3 minutes...
echo.
"%PY%" scraper\scrape.py
if errorlevel 1 (
  echo.
  echo FAILED during collection. Read the messages above.
  echo The previous dataset is untouched, nothing was published.
  goto end
)
echo.
echo Collection finished.
echo.

echo [2/3] Publishing...
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo   No git repository here - local refresh only.
  goto done
)
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo   No git remote configured - local refresh only.
  echo   Run setup-publish.bat once to wire up GitHub Pages.
  goto done
)

git add -A
git commit -m "data refresh %date% %time%" >nul 2>&1
if errorlevel 1 (
  echo   Everything already up to date, nothing new to commit.
) else (
  echo   Committed the new data.
)

git push
if errorlevel 1 (
  echo   First attempt did not go through, retrying in 5 seconds...
  timeout /t 5 >nul
  git pull --rebase >nul 2>&1
  if errorlevel 1 git rebase --abort >nul 2>&1
  git push
)
if errorlevel 1 (
  echo.
  echo   PUSH FAILED. The local data is fine, but the public site
  echo   was not updated. Check your network or git credentials.
  goto end
)
echo   Pushed. The public site rebuilds within about a minute.

:done
echo.
echo [3/3] Done.
echo.
echo  Local:   http://127.0.0.1:8765/index.html
set "PUB="
if exist PUBLIC_URL.txt (
  for /f "usebackq eol=# delims=" %%u in ("PUBLIC_URL.txt") do set "PUB=%%u"
)
if defined PUB (
  echo  Public:  %PUB%
) else (
  echo  Public:  not configured yet - run setup-publish.bat once
)
echo.
echo  Tip: press Ctrl+F5 in the browser to bypass the cache.

:end
echo.
timeout /t 20 >nul
