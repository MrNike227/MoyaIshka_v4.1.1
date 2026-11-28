@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
echo Building ISH 4.3.1 onedir Windows application...

if defined MOYA_BUILD_PYTHON (
  set "PY=%MOYA_BUILD_PYTHON%"
  goto have_python
)
where python >nul 2>nul
if not errorlevel 1 (
  set "PY=python"
  goto have_python
)
where py >nul 2>nul
if not errorlevel 1 goto use_py
goto no_python

:use_py
set "PY=py -3.11"

:have_python
%PY% --version
if errorlevel 1 goto failed
%PY% -c "import struct; assert struct.calcsize('P') * 8 == 64, '64-bit Python is required'"
if errorlevel 1 goto failed
%PY% -m pip install --upgrade pip
if errorlevel 1 goto failed
%PY% -m pip install --upgrade -r requirements.txt piper-tts==1.8.0
if errorlevel 1 goto failed
%PY% -c "import sys, cryptography, cffi, _cffi_backend; from cryptography.hazmat.primitives.ciphers.aead import AESGCM; from cryptography.hazmat.primitives.kdf.scrypt import Scrypt; print('Build Python:', sys.executable); print('cryptography:', cryptography.__version__, cryptography.__file__); print('cffi:', cffi.__version__, cffi.__file__); print('_cffi_backend:', _cffi_backend.__file__)"
if errorlevel 1 goto failed
%PY% -c "import cryptography, cffi, _cffi_backend; from cryptography.exceptions import InvalidTag; from cryptography.hazmat.primitives.ciphers.aead import AESGCM; from cryptography.hazmat.primitives.kdf.scrypt import Scrypt; print('cryptography preflight OK:', cryptography.__version__)"
if errorlevel 1 goto crypto_failed
%PY% prepare_python_runtime.py
if errorlevel 1 goto runtime_failed

if exist "dist\ISH" rmdir /s /q "dist\ISH"
if exist "build\ISH" rmdir /s /q "build\ISH"
if exist "dist\ISH.zip" del /q "dist\ISH.zip"
if exist "dist\ISH.zip.sha256" del /q "dist\ISH.zip.sha256"

%PY% -m PyInstaller --noconfirm --clean --onedir --contents-directory _internal --windowed --noupx --name "ISH" --icon app_icon.ico --version-file version_info.txt --additional-hooks-dir hooks ^
  --add-data "app_icon.ico;." ^
  --add-data "version_info.txt;source_project" ^
  --add-data "app_icon_256.png;." ^
  --add-data "app_icon_128.png;." ^
  --add-data "app_icon_64.png;." ^
  --add-data "app_icon_32.png;." ^
  --add-data "app_icon_16.png;." ^
  --add-data "main.py;source_project" ^
  --add-data "conversation_store.py;source_project" ^
  --add-data "secure_storage.py;source_project" ^
  --add-data "app_runtime.py;source_project" ^
  --add-data "backup_interface.py;source_project" ^
  --add-data "chat_interface.py;source_project" ^
  --add-data "cloud_interface.py;source_project" ^
  --add-data "memory_interface.py;source_project" ^
  --add-data "plugin_interface.py;source_project" ^
  --add-data "research_interface.py;source_project" ^
  --add-data "self_improvement_interface.py;source_project" ^
  --add-data "settings_interface.py;source_project" ^
  --add-data "ui_components.py;source_project" ^
  --add-data "update_interface.py;source_project" ^
  --add-data "voice_interface.py;source_project" ^
  --add-data "app_configuration.py;source_project" ^
  --add-data "app_helpers.py;source_project" ^
  --add-data "app_startup.py;source_project" ^
  --add-data "app_initialization_interface.py;source_project" ^
  --add-data "app_lifecycle_interface.py;source_project" ^
  --add-data "model_settings_interface.py;source_project" ^
  --add-data "ui_pages_interface.py;source_project" ^
  --add-data "ui_theme_interface.py;source_project" ^
  --add-data "context_engine.py;source_project" ^
  --add-data "package_onedir.py;source_project" ^
  --add-data "TEST_WINDOWS10.ps1;source_project" ^
  --add-data "windows_control.py;source_project" ^
  --add-data "voice_assistant.py;source_project" ^
  --add-data "voice_manager.py;source_project" ^
  --add-data "auto_memory.py;source_project" ^
  --add-data "intelligent_memory.py;source_project" ^
  --add-data "backup_manager.py;source_project" ^
  --add-data "backup_cloud.py;source_project" ^
  --add-data "supabase_backup.py;source_project" ^
  --add-data "avatar_widget.py;source_project" ^
  --add-data "plugin_manager.py;source_project" ^
  --add-data "self_improvement.py;source_project" ^
  --add-data "improvement_delivery.py;source_project" ^
  --add-data "improvement_testing.py;source_project" ^
  --add-data "windows_sandbox.py;source_project" ^
  --add-data "background_developer.py;source_project" ^
  --add-data "module_dependency_analyzer.py;source_project" ^
  --add-data "architecture_knowledge.py;source_project" ^
  --add-data "github_pr.py;source_project" ^
  --add-data "updater.py;source_project" ^
  --add-data "updater_helper.py;source_project" ^
  --add-data "temporary_storage.py;source_project" ^
  --add-data "web_research.py;source_project" ^
  --add-data "cloud_sync.py;source_project" ^
  --add-data "google_drive_sync.py;source_project" ^
  --add-data "resource_governor.py;source_project" ^
  --add-data "sql;source_project/sql" ^
  --add-data "requirements.txt;source_project" ^
  --add-data "requirements_voice.txt;source_project" ^
  --add-data "prepare_python_runtime.py;source_project" ^
  --add-data "verify_pe_dependencies.py;source_project" ^
  --add-binary "build_runtime\python_runtime;." ^
  --add-data "START.bat;source_project" ^
  --add-data "BUILD_EXE.bat;source_project" ^
  --add-data "INSTALL_OPTIONAL_DOCS.bat;source_project" ^
  --add-data "INSTALL_VOICE.bat;source_project" ^
  --add-data "INSTALLER.iss;source_project" ^
  --add-data "README_RU.md;source_project" ^
  --add-data "SUPABASE_SETUP_RU.md;source_project" ^
  --add-data "GOOGLE_DRIVE_SETUP_RU.md;source_project" ^
  --add-data "CHANGELOG_RU.md;source_project" ^
  --add-data "PLAN_4.2.6_RU.md;source_project" ^
  --add-data "PLAN_4.2.7_RU.md;source_project" ^
  --add-data "PLAN_4.2.8_RU.md;source_project" ^
  --add-data "PLAN_4.2.9_RU.md;source_project" ^
  --add-data "PLAN_4.3.1_RU.md;source_project" ^
  --add-data "LICENSE.txt;source_project" ^
  --add-data "THIRD_PARTY_NOTICES.md;source_project" ^
  --add-data "licenses/GPL-3.0.txt;source_project/licenses" ^
  --add-data "app_icon.ico;source_project" ^
  --add-data "tests;source_project/tests" ^
  --add-data "hooks;source_project/hooks" ^
  --add-data ".github;source_project/.github" ^
  --add-data "skills;source_project/skills" ^
  --collect-all pypdf --collect-all docx --collect-all speech_recognition ^
  --collect-all piper --collect-all onnxruntime ^
  --collect-all pyaudio --collect-all pyttsx3 --collect-all comtypes ^
  --collect-all cryptography --collect-submodules cryptography --collect-binaries cryptography --collect-data cryptography ^
  --collect-all cffi --hidden-import=cffi --hidden-import=_cffi_backend --collect-all psutil ^
  --hidden-import=context_engine ^
  --hidden-import=cryptography --hidden-import=cryptography.exceptions ^
  --hidden-import=cryptography.hazmat.primitives.ciphers.aead ^
  --hidden-import=cryptography.hazmat.primitives.kdf.scrypt ^
  --hidden-import=cryptography.hazmat.bindings._rust ^
  --copy-metadata cryptography ^
  --hidden-import=pyaudio --hidden-import=pythoncom --hidden-import=pywintypes ^
  --hidden-import=win32com.client --hidden-import=pyttsx3.drivers.sapi5 ^
  --hidden-import=piper --hidden-import=onnxruntime.capi.onnxruntime_pybind11_state main.py
if errorlevel 1 goto failed
if not exist "dist\ISH\ISH.exe" goto failed
%PY% -c "from pathlib import Path; root=Path('dist/ISH/_internal'); removed=[p for p in root.rglob('*.dll') if p.name.casefold() == 'ucrtbase.dll' or p.name.casefold().startswith('api-ms-win-crt-')]; [p.unlink() for p in removed]; print('Removed build-host UCRT/API-set DLLs:', len(removed))"
if errorlevel 1 goto failed

%PY% verify_pe_dependencies.py "dist\ISH"
if errorlevel 1 goto dependency_failed
"dist\ISH\ISH.exe" --self-test-imports
if errorlevel 1 goto crypto_bundle_failed
%PY% -c "import shutil; shutil.copy2('TEST_WINDOWS10.ps1', 'dist/ISH/TEST_WINDOWS10.ps1')"
if errorlevel 1 goto failed
%PY% package_onedir.py --dist-dir "dist\ISH" --output "dist\ISH.zip" --version 4.3.1
if errorlevel 1 goto failed
%PY% -c "from updater_helper import validate_app_directory; validate_app_directory('dist/ISH', '4.3.1')"
if errorlevel 1 goto failed

echo.
echo BUILD COMPLETE: dist\ISH\ISH.exe + dist\ISH.zip
echo Python 3.11, VC runtime and application dependencies are bundled in _internal.
echo Run TEST_WINDOWS10.ps1 on Windows 10 Pro 22H2 to validate the target PC.
if not defined GITHUB_ACTIONS pause
endlocal & exit /b 0

:failed
echo.
echo BUILD FAILED. Check the first error above. Use 64-bit Python 3.11 on the build PC.
if not defined GITHUB_ACTIONS pause
endlocal & exit /b 1

:crypto_failed
echo.
echo CRYPTOGRAPHY PREFLIGHT FAILED. Verify cryptography, cffi and _cffi_backend in build Python.
if not defined GITHUB_ACTIONS pause
endlocal & exit /b 1

:crypto_bundle_failed
echo.
echo CRYPTOGRAPHY BUNDLE SMOKE TEST FAILED. Package must not be published.
if not defined GITHUB_ACTIONS pause
endlocal & exit /b 1

:dependency_failed
echo.
echo Python DLL dependency audit failed. Package must not be published.
if not defined GITHUB_ACTIONS pause
endlocal & exit /b 1

:runtime_failed
echo.
echo Python DLL runtime preparation failed. Check Microsoft Visual C++ runtime DLLs.
if not defined GITHUB_ACTIONS pause
endlocal & exit /b 1

:no_python
echo.
echo Python 3.11 x64 was not found. Install it on the build computer only.
if not defined GITHUB_ACTIONS pause
endlocal & exit /b 1
