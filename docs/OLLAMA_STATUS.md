# Ollama / Graphify status

Дата проверки: 2026-07-21.

## Результат

- `http://localhost:11434/api/tags` отвечает: PASS.
- Точный model tag `gemma4:e2b` установлен: PASS.
- Размер модели по Ollama API: 7 162 405 898 bytes.
- Прямая JSON-генерация `/api/chat` с `think=false`: PASS, около 12,8 секунды.
- Graphify 0.8.40 native backend `ollama`: PASS после установки недостающего Python-пакета `openai` в изолированное окружение Graphify.
- End-to-end smoke: 2 markdown documents → 3 nodes, 4 edges; 768 input / 1 013 output tokens; estimated cost $0.0000.
- `graphify query "paint primer brush"`: PASS, найдены Paint, Primer и Brush.

## Обнаруженные особенности

- Ollama CLI не найден в текущем `PATH`, но локальный HTTP API работает. Обновлённый runner не требует CLI.
- При слишком маленьком `num_predict` модель может потратить лимит на reasoning и вернуть пустой content с `done_reason=length`. Preflight runner использует `think=false` и 512 output tokens.
- Graphify сам использует большой output limit; фактический end-to-end extraction с `gemma4:e2b` прошёл.
- Для локальной модели оставлена последовательная обработка: `--max-concurrency 1 --max-workers 1`.

## Команда проекта

```powershell
powershell -ExecutionPolicy Bypass -File tools/run_graphify_ollama.ps1 -CorpusPath . -Model "gemma4:e2b"
```

Тег нельзя заменять молча. Если модель отсутствует или API не отвечает, workflow фиксирует блокер и не переходит к публикации графа.
