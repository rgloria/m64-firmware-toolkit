@echo off
REM Flash a raw slot-A .bin to 0x08000000 and leave DFU (reboot).
REM Usage: flash.bat <raw-mcu.bin>
REM This WRITES flash. Confirm with the owner first. Run backup.bat before this.
REM Pass a raw 778,128-byte slot-A image, NOT the 7.7 MB M64.BIN container.

setlocal EnableExtensions
cd /d "%~dp0.."

if "%~1"=="" (
    echo usage: flash.bat ^<raw-mcu.bin^>
    echo Example: flash.bat firmware\mcu_mod.bin
    exit /b 1
)
if not exist "%~1" (
    echo ERROR: file not found: %~1
    exit /b 1
)

set "DFU=dfu\dfu-util.exe"
if not exist "%DFU%" set "DFU=dfu\dfu-util-static.exe"
if not exist "%DFU%" (
    echo ERROR: dfu-util not found under dfu\
    exit /b 1
)

echo.
echo About to WRITE %~1 to 0x08000000 (:leave will reboot the MCU).
echo An "Invalid DFU suffix" warning is harmless.
echo.
"%DFU%" -a 0 -s 0x08000000:leave -D "%~1"
if errorlevel 1 (
    echo ERROR: flash failed.
    exit /b 1
)

echo.
echo Flash command finished. Power-cycle if needed and verify the change on the device.
echo To roll back: scripts\recover.bat
endlocal
