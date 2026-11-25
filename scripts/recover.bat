@echo off
REM Re-enter DFU first, then run this to reflash stock slot A (firmware\mcu_stock.bin).
REM This WRITES flash. Confirm with the owner first.

setlocal EnableExtensions
cd /d "%~dp0.."

set "IMG=firmware\mcu_stock.bin"
if not exist "%IMG%" (
    echo ERROR: %IMG% is missing.
    exit /b 1
)

set "DFU=dfu\dfu-util.exe"
if not exist "%DFU%" set "DFU=dfu\dfu-util-static.exe"
if not exist "%DFU%" (
    echo ERROR: dfu-util not found under dfu\
    exit /b 1
)

echo.
echo About to WRITE stock %IMG% to 0x08000000 (:leave will reboot the MCU).
echo.
"%DFU%" -a 0 -s 0x08000000:leave -D "%IMG%"
if errorlevel 1 (
    echo ERROR: recover flash failed.
    exit /b 1
)

echo.
echo Recover command finished. The unit should boot stock slot-A firmware.
endlocal
