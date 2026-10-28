@echo off
cd /d "%~dp0.."
python "%~dp0ejecutar_integracion.py" --quick --suite --output results\integracion_nueva
if errorlevel 1 echo Revise el mensaje anterior y los requisitos de README.md.
pause

