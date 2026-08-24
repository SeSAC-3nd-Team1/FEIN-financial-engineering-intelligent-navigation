@echo off
setlocal

set MODE=%~1
if "%MODE%"=="" set MODE=check

if /I "%MODE%"=="check" goto run
if /I "%MODE%"=="profile" goto run
if /I "%MODE%"=="processed" goto run
if /I "%MODE%"=="features" goto run
if /I "%MODE%"=="audit" goto run
if /I "%MODE%"=="all" goto run

echo Usage: run-financial-pipeline.cmd [check^|profile^|processed^|features^|audit^|all]
exit /b 2

:run
echo [financial-pipeline] stage=%MODE%
docker compose --profile data run --rm --no-deps data python -m scripts.run_financial_pipeline --stage %MODE% --schema-version 1 --feature-version 1
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
  echo [financial-pipeline] FAILED stage=%MODE% exit=%EXIT_CODE%
  echo Check data\reports\pipeline-runs\latest.md
  exit /b %EXIT_CODE%
)

echo [financial-pipeline] SUCCESS stage=%MODE%
echo Report: data\reports\pipeline-runs\latest.md
exit /b 0
