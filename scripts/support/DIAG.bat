@echo off
cd /d "%~dp0\..\.."
set "LOG=%CD%\diag_log.txt"
echo SanWich diagnostic > "%LOG%"
echo Time: %date% %time% >> "%LOG%"
echo Folder: %cd% >> "%LOG%"
echo. >> "%LOG%"
echo --- files in this folder --- >> "%LOG%"
dir /b >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo --- app folder --- >> "%LOG%"
if exist "app" ( dir /b "app" >> "%LOG%" 2>&1 ) else ( echo NO app folder here ^(did you extract the zip?^) >> "%LOG%" )
echo. >> "%LOG%"
echo --- venv python --- >> "%LOG%"
if exist "app\.venv\Scripts\python.exe" (
  echo FOUND app\.venv\Scripts\python.exe >> "%LOG%"
  "app\.venv\Scripts\python.exe" -c "import sys;print(sys.version)" >> "%LOG%" 2>&1
) else (
  echo NOT found app\.venv  -- run 01_setup.bat first >> "%LOG%"
)
echo. >> "%LOG%"
echo --- system python --- >> "%LOG%"
where python >> "%LOG%" 2>&1
py -3 --version >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo --- try launch app, capture errors --- >> "%LOG%"
if exist "app\.venv\Scripts\python.exe" (
  if exist "app\SanWich.py" (
    set "SANWICH_MAIN_RELAUNCHED=1"
    "app\.venv\Scripts\python.exe" "app\SanWich.py" >> "%LOG%" 2>&1
  ) else (
    echo skipped ^(no SanWich.py^) >> "%LOG%"
  )
) else (
  echo skipped ^(no venv^) >> "%LOG%"
)
echo. >> "%LOG%"
echo ============================================================
echo Diagnostic done. A file "diag_log.txt" was created next to this BAT.
echo Please send me that diag_log.txt
echo ============================================================
pause
