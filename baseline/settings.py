"""Настройки приложения из переменных окружения и локального файла .env."""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path):
    """Минимальный загрузчик .env, чтобы сохранить запуск без pip install."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name:
            os.environ[name] = value


def _get_int(name, default, minimum=0):
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} должен быть целым числом") from exc
    if value < minimum:
        raise RuntimeError(f"{name} должен быть не меньше {minimum}")
    return value


def _get_float(name, default, minimum=0.0):
    raw_value = os.environ.get(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} должен быть числом") from exc
    if value < minimum:
        raise RuntimeError(f"{name} должен быть не меньше {minimum}")
    return value


_load_dotenv(BASE_DIR / ".env")

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()

YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "").strip()
YANDEX_FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID", "").strip()
YANDEX_MODEL = os.environ.get("YANDEX_MODEL", "deepseek-v4-flash").strip()

if LLM_PROVIDER == "gemini":
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Не задан GEMINI_API_KEY. Скопируйте .env.example в .env и добавьте ключ."
        )
elif LLM_PROVIDER == "yandexgpt":
    if not YANDEX_API_KEY:
        raise RuntimeError(
            "Не задан YANDEX_API_KEY. Скопируйте .env.example в .env и добавьте ключ."
        )
    if not YANDEX_FOLDER_ID:
        raise RuntimeError(
            "Не задан YANDEX_FOLDER_ID. Скопируйте .env.example в .env и добавьте каталог (folder ID)."
        )
else:
    raise RuntimeError(
        f"Неизвестный LLM_PROVIDER: {LLM_PROVIDER}. Допустимые значения: gemini, yandexgpt."
    )

HOST = os.environ.get("HOST", "127.0.0.1").strip()
PORT = _get_int("PORT", 8000, minimum=1)
MAX_USER_MESSAGE_CHARS = _get_int("MAX_USER_MESSAGE_CHARS", 400, minimum=1)
GEMINI_MAX_RETRIES = _get_int("GEMINI_MAX_RETRIES", 2, minimum=0)
GEMINI_RETRY_BASE_SECONDS = _get_float(
    "GEMINI_RETRY_BASE_SECONDS", 1, minimum=0
)
GEMINI_TIMEOUT_SECONDS = _get_float("GEMINI_TIMEOUT_SECONDS", 60, minimum=1)

