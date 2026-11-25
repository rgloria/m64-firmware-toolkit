@echo off
REM Read RDP (option bytes) then take a full-chip DFU backup.
REM Run from the toolkit root, or this script will cd there itself.
REM Does NOT write firmware. Always inspect the RDP result before flashing.

setlocal EnableExtensions
cd /d "%~dp0.."

set "DFU=dfu\dfu-util.exe"
if not exist "%DFU%" set "DFU=dfu\dfu-util-static.exe"
if not exist "%DFU%" (
    echo ERROR: dfu-util not found under dfu\
    exit /b 1
)

if not exist firmware mkdir firmware

echo.
echo === 1/2  Reading option bytes (RDP) to firmware\optbytes_read.bin ===
"%DFU%" -a 1 -s 0x5200201C -U firmware\optbytes_read.bin
if errorlevel 1 (
    echo ERROR: option-bytes read failed. Is the M64 in DFU mode? Is WinUSB installed via Zadig?
    exit /b 1
)

REM Decode FLASH_OPTSR_CUR at offset +4; RDP is bits [15:8].
python -c "d=open(r'firmware\optbytes_read.bin','rb').read(); v=int.from_bytes(d[4:8],'little'); r=(v>>8)&0xFF; print('FLASH_OPTSR_CUR=0x%%08X  RDP=0x%%02X'%%(v,r)); print('Level 0 SAFE' if r==0xAA else ('Level 2 NEVER FLASH' if r==0xCC else 'Level 1 - a write mass-erases; stop'))"
if errorlevel 1 (
    echo (Python not available to decode RDP. Open firmware\optbytes_read.bin and check the word at offset +4; RDP bits [15:8] must be 0xAA before any flash.)
)

echo.
echo === 2/2  Full-chip backup (2 MB) ===
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set DAY=%%i
set "BAK=firmware\chip_backup_%DAY%.bin"
echo Writing %BAK%
"%DFU%" -a 0 -s 0x08000000 -U "%BAK%"
if errorlevel 1 (
    echo ERROR: chip backup failed.
    exit /b 1
)

echo.
echo Backup complete: %BAK%
echo Next: confirm RDP is 0xAA, then (only after the owner agrees) scripts\flash.bat ^<image.bin^>
endlocal
