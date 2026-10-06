EnergoLogic Visio Editor Kit 0.3.49
===================================

Офлайн-пакет EnergoLogic Editor для Microsoft Visio.
Для обычной работы ChatGPT, MCP, Python, Visual Studio и Интернет не нужны.

Требования
----------
- Windows 10/11.
- Microsoft Visio desktop. Целевая совместимость проекта: Visio 2010 и новее.
- .NET Framework 4.x.
- Office/Visio PIA (Office.dll + Extensibility/Interop) из установленного Office/Visio.

Установка
---------
1. Полностью закройте Visio.
2. Распакуйте ZIP.
3. Запустите Install-EnergoLogic.cmd.
4. Затем запускайте ярлык "EnergoLogic Visio".

Установка выполняется per-user: HKCU + %LOCALAPPDATA%.
Администратор не нужен, если корпоративная политика не запрещает PowerShell/COM add-ins.

Трафареты
---------
Трафареты из папки stencils устанавливаются в:
%LOCALAPPDATA%\EnergoLogic\Stencils

Launcher открывает их read-only и docked.
Пакет, собранный через EnergoLogic Bridge, автоматически включает личные
трафареты из "Мои фигуры\ГОСТ". Сторонние файлы из C:\ProgramData\VTD
автоматически в пакет НЕ копируются.

Если нужно обновить библиотеку вручную на исходном ПК:
Collect-Stencils.cmd

Почему LoadBehavior=0
---------------------
EnergoLogic намеренно не грузится автоматически при каждом запуске Visio.
На реальных VTD-схемах явное подключение через launcher устойчивее.

Проверка без регистрации
------------------------
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-EnergoLogic.ps1 -CompileOnly

Удаление
--------
Закройте Visio и запустите Uninstall-EnergoLogic.cmd.

Совместимость
-------------
Installer не привязан к Office16/OneDrive и компилирует add-in на целевом ПК.
Полная матрица Visio 2010/2013/2016/2019/2021/M365 остаётся отдельным WS-3 qualification gate.

Целостность пакета
------------------
MANIFEST.json содержит размер и SHA-256 каждого файла пакета.
Install-EnergoLogic.ps1 проверяет manifest до компиляции и регистрации COM.
Если файл отсутствует или повреждён, установка прекращается.

Что переносить
--------------
Достаточно одного ZIP EnergoLogic-Visio-Editor-Kit-0.3.49.zip.
На рабочем ПК Интернет, ChatGPT, MCP, Python и Visual Studio не требуются.
