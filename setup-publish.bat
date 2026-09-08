@echo off
setlocal
REM ============================================================
REM  One-time setup: turn this folder into a git repository that
REM  pushes to GitHub Pages, so update.bat can publish by itself.
REM
REM  Before running this:
REM    1. Create an empty repository on github.com (public).
REM    2. Copy its HTTPS URL, something like:
REM         https://github.com/yourname/africa-crisis-watch.git
REM    3. Run this file and paste the URL when asked.
REM
REM  After it finishes, enable Pages:
REM    repo -> Settings -> Pages -> Build and deployment
REM    Source: Deploy from a branch
REM    Branch: main, folder: / (root) -> Save
REM ============================================================
cd /d "%~dp0"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo Initialising a local repository...
  git init -b main
) else (
  echo A git repository already exists here.
)

git remote get-url origin >nul 2>&1
if not errorlevel 1 (
  echo.
  echo A remote named origin is already configured:
  git remote get-url origin
  echo Delete it with:  git remote remove origin
  echo.
)

set /p REPO=Paste the GitHub repository URL (or press Enter to skip): 
if "%REPO%"=="" (
  echo Skipped. You can add it later with:
  echo   git remote add origin https://github.com/yourname/africa-crisis-watch.git
  goto finish
)

git remote remove origin >nul 2>&1
git remote add origin "%REPO%"
echo Remote set to:
git remote get-url origin

git add -A
git commit -m "initial commit: Africa Crisis Watch" >nul 2>&1
echo.
echo Pushing. If GitHub asks you to sign in, use your browser window.
git push -u origin main
if errorlevel 1 (
  echo.
  echo Push failed. Common causes:
  echo   - not signed in to GitHub on this machine
  echo   - the repository is not empty (create it without a README)
  echo Fix it, then run:  git push -u origin main
) else (
  echo.
  echo SUCCESS. Now enable Pages:
  echo   repo Settings - Pages - Build and deployment
  echo   Source: Deploy from a branch - Branch: main - / (root) - Save
  echo.
  echo Your site will appear at:
  echo   https://yourname.github.io/africa-crisis-watch/
  echo Put that address into PUBLIC_URL.txt so update.bat prints it.
)

:finish
echo.
timeout /t 20 >nul
