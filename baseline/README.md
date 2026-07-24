# Legacy baseline

Это компактная неизменяемая копия текущего Paints Chat, используемая как источник существующего retrieval, API и UI-контракта.

Состав:

- `server.py` — текущий backend и `retrieve_relevant_products()`;
- `settings.py` — текущая конфигурация;
- `simple.html` — самодостаточный UI карточек и `product_group`;
- `run.bat` и `.env.example` — справочные файлы запуска.

Не копировались `.env`, Cloudflare scripts, тяжёлая статическая реконструкция сайта, wiki, caches и runtime artifacts.

Важно: baseline server перенаправляет `/` на отсутствующую в этом компактном пакете `/site/`. До самостоятельного запуска Backend Agent должен либо переключить default route на `simple.html`, либо использовать `/simple`. Не редактируйте baseline: копируйте нужную логику в новую runtime-зону.
