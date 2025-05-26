@echo off
echo ==========================================
echo  Push automatico a GitHub
echo ==========================================

:: Colores para la consola
color 0A

:: Obtener fecha y hora actual para el mensaje del commit
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "fecha=%dt:~6,2%/%dt:~4,2%/%dt:~0,4% %dt:~8,2%:%dt:~10,2%"

echo.
echo [1/3] Agregando todos los archivos modificados...
git add .

echo.
echo [2/3] Creando commit con fecha: %fecha%
git commit -m "Actualizacion automatica - %fecha%"

echo.
echo [3/3] Subiendo cambios a GitHub...
git push origin main

echo.
echo ==========================================
echo  Push completado exitosamente!
echo ==========================================
echo.

timeout /t 3 