# Development Bridge Browser Binder

Небольшое WebExtension для одноразовой привязки логического route Development Bridge к текущему чату ChatGPT через OOB Browser Binder API.

## Установка для разработки

Firefox: `about:debugging` → This Firefox → Load Temporary Add-on → выбрать `manifest.json`.
Chromium: Extensions → Developer mode → Load unpacked → выбрать каталог `browser-extension/bridge-binder/`.

## Настройка

Откройте Options расширения и укажите полный route-control URL вашего Bridge (например, URL развертывания, заканчивающийся на `/mcp/x/route-control`) и отдельный Browser Binder token. Значения сохраняются только в `storage.local`. При сохранении расширение запрашивает доступ только к origin указанного Bridge.

## Использование

Сначала подготовьте pending bind через канонический ingress. Затем откройте нужный конкретный чат на `https://chatgpt.com`, откройте popup расширения, выберите логический route и нажмите **«Привязать эту вкладку»**. Привязка никогда не запускается автоматически. Если pending route один, он выбирается автоматически; при нескольких route выбор обязателен.

URL активной вкладки передаётся напрямую из расширения в Browser Binder API только после явного клика владельца. Popup не отображает и не журналирует физический идентификатор чата. Секрет Binder не является credential для обычных Bridge/MCP операций.
