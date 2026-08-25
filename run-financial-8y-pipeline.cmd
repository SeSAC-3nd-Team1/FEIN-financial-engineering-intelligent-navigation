@echo off
setlocal

echo [financial-8y] baseline=2018-01-01
echo [financial-8y] applying database migrations...
docker compose --profile migration run --rm --no-deps db-init
if errorlevel 1 goto failed

echo [financial-8y] checking Azure CLI login...
docker compose --profile data run --rm --no-deps data sh -lc "az account show >/dev/null 2>&1 || az login --use-device-code"
if errorlevel 1 goto failed

echo [financial-8y] collecting and preparing KRX + ECOS + OpenDART...
docker compose --profile data run --rm --no-deps data python -m scripts.run_financial_8y_pipeline
if errorlevel 1 goto failed

echo [financial-8y] SUCCESS
echo Report: data\reports\pipeline-runs\financial-8y-latest.md
exit /b 0

:failed
set EXIT_CODE=%ERRORLEVEL%
echo [financial-8y] FAILED exit=%EXIT_CODE%
echo Check the terminal error and data\reports\pipeline-runs\financial-8y-latest.md if it exists.
exit /b %EXIT_CODE%
