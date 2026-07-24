"""
MVP чат-бот для сайта строительного/малярного магазина «Владимиров и партнер».
Работает на стандартной библиотеке Python (без pip install) + Gemini API.

Запуск:
    python server.py
Потом открыть в браузере:
    http://localhost:8080
"""

import json
import mimetypes
import re
import ssl
import sys
import time
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# На Windows консоль по умолчанию может быть не в UTF-8, из-за чего print()
# с кириллицей иногда роняет скрипт с UnicodeEncodeError. Подстраховываемся.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_original_print = print

def safe_print(*args, **kwargs):
    new_args = []
    for arg in args:
        if isinstance(arg, str):
            encoding = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
            try:
                arg.encode(encoding)
                new_args.append(arg)
            except UnicodeEncodeError:
                new_args.append(arg.encode(encoding, errors="replace").decode(encoding))
        else:
            new_args.append(arg)
    try:
        _original_print(*new_args, **kwargs)
    except Exception:
        try:
            _original_print(*(repr(a) for a in args), **kwargs)
        except Exception:
            pass

print = safe_print

import settings

# Настраиваем SSL-контекст, чтобы избежать ошибок SSL: UNEXPECTED_EOF_WHILE_READING
# на некоторых Python/OpenSSL версиях при работе с API.
ssl_context = ssl.create_default_context()
if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
    ssl_context.options |= ssl.OP_IGNORE_UNEXPECTED_EOF

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
INDEX_PATH = WEB_DIR / "simple.html"
SITE_DIR = WEB_DIR / "site"
SITE_INDEX_PATH = SITE_DIR / "index.html"

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{settings.MODEL_NAME}:generateContent"
)
GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{settings.MODEL_NAME}:streamGenerateContent?alt=sse"
)


CATALOG_JSON_PATH = DATA_DIR / "catalog.json"

def load_catalog_database():
    try:
        with open(CATALOG_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки catalog.json: {e}")
        return []

CATALOG_DATABASE = load_catalog_database()
CATALOG_BY_ID = {str(product.get("id")): product for product in CATALOG_DATABASE}
PRODUCT_MARKER_PATTERN = re.compile(r"\[id\s*:\s*(\d+)\]", re.IGNORECASE)
RESPONSE_MARKER_PATTERN = re.compile(
    r"\[id\s*:\s*(?P<product_id>\d+)\]"
    r"|\[compare\s*:\s*(?P<compare_id>\d+)\s*\|\s*"
    r"(?P<compare_summary>[^\]\r\n]{1,240})\]"
    r"|\[compare_result\s*:\s*"
    r"(?P<comparison_analysis>[^\]\r\n]{1,500})\]",
    re.IGNORECASE,
)
COMPARISON_REQUEST_PATTERN = re.compile(
    r"\b(?:сравн\w*|сопостав\w*|отлич(?:а|и|е)\w*|разниц\w*|"
    r"что\s+лучше|како[йюаяе]\s+(?:из\s+них\s+)?лучше|"
    r"како[йюаяе]\s+(?:из\s+них\s+)?выбрать|выбрать\s+между|"
    r"плюсы\s+и\s+минусы)\b",
    re.IGNORECASE,
)

def retrieve_relevant_products(query, top_k=25):
    if not query:
        return []
    query_clean = query.lower()
    keywords = re.findall(r'[a-zA-Zа-яА-Я0-9]+', query_clean)
    stop_words = {
        "и", "в", "во", "на", "под", "за", "с", "со", "из", "от", "до", "для",
        "без", "о", "об", "обо", "при", "по", "у", "к", "ко", "а", "но", "да",
        "или", "бы", "ли", "же", "что", "как", "где", "когда", "кто", "это",
        "был", "была", "были", "не", "нет", "the", "a", "an", "and", "or", "to", "for"
    }
    keywords = [kw for kw in keywords if kw not in stop_words and len(kw) > 1]
    if not keywords:
        return []
    scored_products = []
    for p in CATALOG_DATABASE:
        score = 0
        name_lower = str(p.get("name") or "").lower()
        brand_lower = str(p.get("brand") or "").lower()
        sub_lower = str(p.get("subcategory") or "").lower()
        cat_lower = str(p.get("category") or "").lower()
        for kw in keywords:
            if kw in name_lower:
                score += 10
                if f" {kw}" in name_lower or name_lower.startswith(kw):
                    score += 5
            if kw in brand_lower:
                score += 8
                if brand_lower == kw:
                    score += 4
            if kw in sub_lower:
                score += 4
            if kw in cat_lower:
                score += 2
        if score > 0:
            scored_products.append((score, p))
    scored_products.sort(key=lambda x: x[0], reverse=True)
    if not scored_products:
        return []
    return [p for score, p in scored_products[:top_k]]

def wants_product_comparison(query):
    return isinstance(query, str) and bool(COMPARISON_REQUEST_PATTERN.search(query))


def build_system_prompt(retrieved_items, allow_comparison=False):
    lines_list = []
    for p in retrieved_items:
        price_val = int(p["price"]) if isinstance(p["price"], float) and p["price"].is_integer() else p["price"]
        lines_list.append(f"{p['id']}|{p['category']}|{p['subcategory']}|{p['brand']}|{p['name']}|{price_val}")
    catalog_text = "\n".join(lines_list)
    if retrieved_items:
        search_result = (
            f"Найдено {len(retrieved_items)} наиболее подходящих позиций. "
            "Используй только их."
        )
    else:
        search_result = (
            "По текущему запросу в каталоге ничего не найдено. Прямо скажи "
            "покупателю об этом и не предлагай случайные товары."
        )
    if allow_comparison:
        comparison_rules = """10. Пользователь ЯВНО запросил сравнение. Сначала создай таблицу для 2–3 товаров: поставь подряд служебные маркеры [compare:ID|Короткое практическое отличие], по одному на товар. Используй тот же ID, что и у товара. После | напиши не больше 140 символов; не используй внутри символы | и ].
11. Сразу ПОСЛЕ маркеров compare поставь один служебный маркер [compare_result:Короткий вывод по сравнению]. Внутри дай 1–2 коротких предложения: главное различие, кому какой товар подходит лучше и, если возможно, практическую рекомендацию. Не используй внутри символ ]. Затем поставь подряд соответствующие маркеры карточек [id:ID] в том же порядке. Интерфейс покажет таблицу, блок «Короткий вывод», затем карточки товаров."""
    else:
        comparison_rules = """10. Пользователь НЕ просил сравнивать товары. Не используй маркеры [compare:...], не создавай сравнительную таблицу и не оформляй ответ как сравнение. Показывай только обычный текст и карточки [id:ID].
11. Сравнительную таблицу можно создавать только в ответ на явную просьбу пользователя сравнить товары, найти отличия или выбрать лучший из нескольких вариантов."""
    return f"""Ты — ИИ-консультант интернет-магазина строительных материалов «Владимиров и партнер».
Отвечаешь покупателям в чате на сайте магазина. В твоей базе данных содержится {len(CATALOG_DATABASE)} товаров.

РЕЗУЛЬТАТ ПОИСКА: {search_result}
Тебе доступен локальный фрагмент каталога ниже:
Для каждого товара указаны: id, категория, подкатегория, бренд, точное название (часто с весом/объёмом) и розничная цена в рублях.

ПРАВИЛА:
1. Используй ТОЛЬКО товары и цены из каталога ниже. Никогда не придумывай товары, бренды, артикулы или цены, которых нет в списке.
2. Если нужного товара или категории в каталоге нет — прямо скажи об этом и предложи уточнить у менеджера магазина. Не придумывай замену как будто она есть в наличии.
3. Если спрашивают про материалы «для строительства дома», «для ремонта» или похожую широкую задачу — составь список актуальных для задачи позиций именно из разделов ниже (например: гидроизоляция фундамента, кладочная смесь для стен, штукатурка, шпаклёвка под покраску, стяжка пола, клей для плитки в санузлах, утепление фасада, грунтовка и краска для стен/фасада) с конкретными товарами и ценами, и честно уточни, что это только часть общего ассортимента магазина — кирпич, лес, металл, кровля, инструмент и т.п. в эту выгрузку каталога не входят.
4. Если просят сравнить два товара — найди оба в каталоге (по названию, поиск может быть неточным) и выведи сравнение: бренд, название, цена, подкатегория, назначение, и краткий вывод, что дешевле или для какой задачи каждый подходит лучше. Если под описание подходит несколько товаров — уточни у пользователя, какой именно он имеет в виду, перечислив варианты.
5. Отвечай на русском языке, дружелюбно и по-деловому, без лишней воды. Цены указывай в рублях со знаком ₽. Будь максимально лаконичен: избегай длинных вступлений, приветствий и рассуждений.
6. Если вопрос не про товары магазина — отвечай коротко и по-человечески, не притворяйся, что не понимаешь вопрос.
7. Форматируй обычный текст БЕЗ markdown-разметки (без **, #, |, таблиц). Используй переносы строк и тире для списков. Единственное исключение для символа | — служебные маркеры сравнения из правила 10.
8. В том месте ответа, где должен появиться рекомендуемый или сравниваемый товар, поставь отдельной строкой только его идентификатор в формате [id:123]. Не пиши рядом название, цену или артикул — интерфейс сам покажет их внутри карточки. Используй только id из каталога ниже.
9. Если предлагаешь два или больше товаров одной категории, поставь все маркеры их карточек подряд, без текста между ними: интерфейс покажет товары в одной горизонтальной строке. Не смешивай в этой строке товары разных категорий.
{comparison_rules}
12. При переходе к другой категории, задаче, этапу работ или подкатегории сначала напиши отдельный текст для нового раздела, затем относящиеся к нему служебные маркеры. Не переноси маркеры разных разделов в один общий блок.
13. Пиши кратко и по делу. Ограничивай рекомендации максимум 3 наиболее релевантными товарами на категорию/задачу. Описания товаров должны быть предельно сжатыми — не более 1-2 предложений на товар.

КАТАЛОГ (id|категория|подкатегория|бренд|название|цена_руб):
{catalog_text}
"""

def scrub(text):
    """Никогда не отдаём API-ключ наружу, даже в текстах ошибок."""
    res = text
    gemini_key = getattr(settings, "GEMINI_API_KEY", "")
    if gemini_key and len(gemini_key) > 5:
        res = res.replace(gemini_key, "***")
    yandex_key = getattr(settings, "YANDEX_API_KEY", "")
    if yandex_key and len(yandex_key) > 5:
        res = res.replace(yandex_key, "***")
    return res



def safe_product_url(value):
    if not isinstance(value, str):
        return ""
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return ""
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or hostname not in ("remplanika.ru", "www.remplanika.ru"):
        return ""
    return value


def category_url_from_product_url(value):
    product_url = safe_product_url(value)
    if not product_url:
        return ""
    parsed = urllib.parse.urlparse(product_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2 or path_parts[0] != "catalog":
        return ""
    category_slug = path_parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", category_slug):
        return ""
    return urllib.parse.urlunparse(
        ("https", "remplanika.ru", f"/catalog/{category_slug}/", "", "", "")
    )


def safe_product_image(value):
    if not isinstance(value, str):
        return ""
    if not re.fullmatch(r"/site/catalog-images/[a-zA-Z0-9_.-]+", value):
        return ""
    return value


def serialize_product(product):
    price = product.get("price")
    if isinstance(price, float) and price.is_integer():
        price = int(price)
    product_url = safe_product_url(product.get("url", ""))
    return {
        "id": product.get("id"),
        "name": product.get("name", ""),
        "brand": product.get("brand", ""),
        "sku": product.get("sku", ""),
        "price": price,
        "category": product.get("category", ""),
        "subcategory": product.get("subcategory", ""),
        "url": product_url,
        "category_url": category_url_from_product_url(product_url),
        "image": safe_product_image(product.get("image", "")),
    }


def _normalize_reply_text(value):
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r" {2,}", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _remove_repeated_product_name(value, product):
    """Убирает название перед маркером, если модель всё же его продублировала."""
    name = str(product.get("name") or "").strip()
    if not name:
        return value
    position = value.casefold().rfind(name.casefold())
    if position < 0:
        return value
    suffix = value[position + len(name):]
    if suffix.strip(" \t:;,.—–-()"):
        return value
    return value[:position].rstrip()


def _inject_fallback_markers(text, retrieved_items, limit):
    """Вставляет маркеры после названий или артикулов, если модель забыла формат."""
    existing_ids = set(PRODUCT_MARKER_PATTERN.findall(text))
    insertions = []
    text_lower = text.casefold()
    seen_ids = set()
    for product in retrieved_items:
        product_id = str(product.get("id"))
        if product_id in existing_ids or product_id in seen_ids:
            continue
        name = str(product.get("name") or "").strip()
        sku = str(product.get("sku") or "").strip()
        
        # Сначала ищем по полному названию
        if name:
            position = text_lower.find(name.casefold())
            if position >= 0:
                insertions.append((position + len(name), product_id))
                seen_ids.add(product_id)
                if len(insertions) >= limit:
                    break
                continue
                
        # Если название не найдено, ищем по артикулу (если он длиннее 2 символов)
        if sku and len(sku) > 2:
            position = text_lower.find(sku.casefold())
            if position >= 0:
                insertions.append((position + len(sku), product_id))
                seen_ids.add(product_id)
                if len(insertions) >= limit:
                    break
                continue

    for position, product_id in sorted(insertions, key=lambda x: x[0], reverse=True):
        text = f"{text[:position]} [id:{product_id}]{text[position:]}"
    return text


def _group_product_content(content):
    grouped_content = []
    for block in content:
        if block["type"] == "comparison_item":
            item = block["item"]
            category = item["product"].get("category") or "Другие товары"
            previous = grouped_content[-1] if grouped_content else None
            if (
                previous
                and previous["type"] == "comparison"
                and previous["category"] == category
            ):
                if len(previous["items"]) < 3:
                    previous["items"].append(item)
                continue
            grouped_content.append({
                "type": "comparison",
                "category": category,
                "items": [item],
            })
            continue
        if block["type"] != "product":
            grouped_content.append(block)
            continue
        product = block["product"]
        category = product.get("category") or "Другие товары"
        previous = grouped_content[-1] if grouped_content else None
        if (
            previous
            and previous["type"] == "product_group"
            and previous["category"] == category
        ):
            previous["products"].append(product)
            continue
        grouped_content.append({
            "type": "product_group",
            "category": category,
            "products": [product],
            "category_url": product.get("category_url", ""),
        })
    return [
        block
        for block in grouped_content
        if block["type"] != "comparison" or len(block["items"]) >= 2
    ]


def _strip_trailing_header(text):
    """Удаляет заголовок в конце текста, если соответствующий маркер карточки был пропущен."""
    lines = text.split("\n")
    modified = False
    while lines:
        last_line = lines[-1].strip()
        if not last_line:
            lines.pop()
            modified = True
            continue
        # Если строка заканчивается на двоеточие — это заголовок категории/секции
        if last_line.endswith(":") or last_line.endswith("："):
            lines.pop()
            modified = True
            continue
        break
    return "\n".join(lines) if modified else text


def build_response_content(text, retrieved_items, limit=10):
    """Строит последовательность текст → карточка → текст в исходных местах маркеров."""
    text = _inject_fallback_markers(text, retrieved_items, limit)
    content = []
    products = []
    seen = set()
    compared = set()
    cursor = 0

    for match in RESPONSE_MARKER_PATTERN.finditer(text):
        prefix = text[cursor:match.start()]
        product_id = match.group("product_id")
        compare_id = match.group("compare_id")
        comparison_analysis = match.group("comparison_analysis")
        product = CATALOG_BY_ID.get(product_id or compare_id)
        if product_id and product and product_id not in seen and len(products) < limit:
            prefix = _remove_repeated_product_name(prefix, product)
            prefix = _normalize_reply_text(prefix)
            if prefix:
                content.append({"type": "text", "text": prefix})
            serialized = serialize_product(product)
            products.append(serialized)
            content.append({"type": "product", "product": serialized})
            seen.add(product_id)
        elif compare_id and product and compare_id not in compared:
            prefix = _normalize_reply_text(prefix)
            if prefix:
                content.append({"type": "text", "text": prefix})
            summary = _normalize_reply_text(match.group("compare_summary"))[:240]
            if summary:
                content.append({
                    "type": "comparison_item",
                    "item": {
                        "product": serialize_product(product),
                        "summary": summary,
                    },
                })
                compared.add(compare_id)
        elif comparison_analysis and len(compared) >= 2:
            prefix = _normalize_reply_text(prefix)
            if prefix:
                content.append({"type": "text", "text": prefix})
            analysis_text = _normalize_reply_text(comparison_analysis)[:500]
            if analysis_text:
                content.append({
                    "type": "comparison_analysis",
                    "text": analysis_text,
                })
        else:
            prefix = _strip_trailing_header(prefix)
            prefix = _normalize_reply_text(prefix)
            if prefix:
                content.append({"type": "text", "text": prefix})
        cursor = match.end()

    tail = _normalize_reply_text(text[cursor:])
    if tail:
        content.append({"type": "text", "text": tail})

    history_parts = []
    for block in content:
        if block["type"] == "text":
            history_parts.append(block["text"])
        elif block["type"] == "product":
            history_parts.append(block["product"].get("name", ""))
        elif block["type"] == "comparison_item":
            product_name = block["item"]["product"].get("name", "")
            history_parts.append(f"{product_name}: {block['item']['summary']}")
        elif block["type"] == "comparison_analysis":
            history_parts.append(block["text"])
    history_text = _normalize_reply_text("\n".join(history_parts))
    if not content and history_text:
        content.append({"type": "text", "text": history_text})
    return history_text, _group_product_content(content), products


def prepare_gemini_request(messages):
    """Готовит единый payload для обычного и потокового запросов Gemini."""
    contents = []
    user_queries = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        text = (m.get("text") or "").strip()
        if not text:
            continue
        contents.append({"role": role, "parts": [{"text": text}]})
        if role == "user":
            user_queries.append(text)

    latest_user_query = user_queries[-1] if user_queries else ""
    allow_comparison = wants_product_comparison(latest_user_query)
    user_query = "\n".join(user_queries[-3:])
    retrieved_items = retrieve_relevant_products(user_query, top_k=25)
    system_prompt = build_system_prompt(retrieved_items, allow_comparison)

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1024,
        },
    }
    return json.dumps(payload).encode("utf-8"), retrieved_items


def extract_candidate_text(body):
    candidates = body.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts)


def _gemini_request(url, data):
    return urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.GEMINI_API_KEY,
        },
        method="POST",
    )


def _open_gemini_response(url, data):
    """Открывает ответ Gemini, повторяя только безопасные ошибки 429/503."""
    for attempt in range(settings.GEMINI_MAX_RETRIES + 1):
        try:
            return urllib.request.urlopen(
                _gemini_request(url, data),
                timeout=settings.GEMINI_TIMEOUT_SECONDS,
                context=ssl_context,
            )
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            can_retry = (
                e.code in (429, 503) and attempt < settings.GEMINI_MAX_RETRIES
            )
            if can_retry:
                delay = settings.GEMINI_RETRY_BASE_SECONDS * (2 ** attempt)
                print(
                    f"Gemini вернул {e.code}; повтор через {delay:g} сек. "
                    f"({attempt + 1}/{settings.GEMINI_MAX_RETRIES})"
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f"Gemini API error {e.code}: {scrub(err_body)}")
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Не удалось подключиться к Gemini API: {scrub(str(e.reason))}"
            )


def call_gemini(messages):
    """Возвращает готовый ответ одним JSON-объектом (совместимый маршрут)."""
    data, retrieved_items = prepare_gemini_request(messages)

    with _open_gemini_response(GEMINI_URL, data) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    candidates = body.get("candidates") or []
    if not candidates:
        feedback = body.get("promptFeedback", {})
        raise RuntimeError(f"Пустой ответ от модели. promptFeedback={feedback}")

    text_out = extract_candidate_text(body).strip()
    if not text_out:
        raise RuntimeError("Модель вернула пустой текст ответа.")
    reply, content, products = build_response_content(text_out, retrieved_items)
    return {"reply": reply, "content": content, "products": products}


def stream_gemini(messages):
    """Передаёт сырые текстовые фрагменты, затем готовый богатый ответ."""
    data, retrieved_items = prepare_gemini_request(messages)
    text_parts = []

    with _open_gemini_response(GEMINI_STREAM_URL, data) as resp:
        event_data = []
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if line.startswith("data:"):
                event_data.append(line[5:].lstrip())
                continue
            if line or not event_data:
                continue

            payload_text = "\n".join(event_data)
            event_data = []
            if payload_text == "[DONE]":
                continue
            try:
                body = json.loads(payload_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Gemini вернул повреждённый поток данных.") from exc
            delta = extract_candidate_text(body)
            if delta:
                text_parts.append(delta)
                yield "delta", {"text": delta}

        if event_data:
            payload_text = "\n".join(event_data)
            if payload_text and payload_text != "[DONE]":
                try:
                    body = json.loads(payload_text)
                except json.JSONDecodeError as exc:
                    raise RuntimeError("Gemini вернул повреждённый поток данных.") from exc
                delta = extract_candidate_text(body)
                if delta:
                    text_parts.append(delta)
                    yield "delta", {"text": delta}

    text_out = "".join(text_parts).strip()
    if not text_out:
        raise RuntimeError("Модель вернула пустой текст ответа.")
    reply, content, products = build_response_content(text_out, retrieved_items)
    yield "final", {"reply": reply, "content": content, "products": products}


YANDEX_URL = "https://llm.api.cloud.yandex.net/v1/chat/completions"


def prepare_yandexgpt_request(messages):
    """Готовит единый payload и заголовки для запросов к YandexGPT (OpenAI-совместимый эндпоинт)."""
    contents = []
    user_queries = []
    for m in messages:
        role = "assistant" if m.get("role") == "assistant" else "user"
        text = (m.get("text") or "").strip()
        if not text:
            continue
        contents.append({"role": role, "content": text})
        if role == "user":
            user_queries.append(text)

    latest_user_query = user_queries[-1] if user_queries else ""
    allow_comparison = wants_product_comparison(latest_user_query)
    user_query = "\n".join(user_queries[-3:])
    retrieved_items = retrieve_relevant_products(user_query, top_k=25)
    system_prompt = build_system_prompt(retrieved_items, allow_comparison)

    contents.insert(0, {"role": "system", "content": system_prompt})

    # Напоминание правил форматирования в конце последнего сообщения пользователя для усиления внимания модели
    if contents and contents[-1]["role"] == "user":
        reminder = (
            "\n\n[Важное системное требование по форматированию: Отвечай строго БЕЗ markdown-разметки (без **, #, |, таблиц). "
            "Вместо упоминания названий товаров в тексте, обязательно ставь их идентификаторы [id:ID] на отдельной строке. "
        )
        if allow_comparison:
            reminder += (
                "Так как запрошено сравнение, сначала выведи служебные маркеры сравнения подряд: "
                "[compare:ID|Короткое практическое отличие] по одному на каждый товар. "
                "Затем сразу ПОСЛЕ них выведи один маркер [compare_result:Короткий вывод по сравнению]. "
                "И только после этого выведи карточки [id:ID] сравниваемых товаров подряд на отдельной строке.]"
            )
        else:
            reminder += "Для рекомендации товаров используй только маркеры [id:ID] на отдельной строке.]"
        
        contents[-1]["content"] += reminder

    model_uri = settings.YANDEX_MODEL
    if not model_uri.startswith("gpt://"):
        model_uri = f"gpt://{settings.YANDEX_FOLDER_ID}/{settings.YANDEX_MODEL}"

    payload = {
        "model": model_uri,
        "messages": contents,
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {settings.YANDEX_API_KEY}",
        "x-folder-id": settings.YANDEX_FOLDER_ID,
    }

    return json.dumps(payload).encode("utf-8"), headers, retrieved_items


def _yandex_request(url, data, headers):
    return urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )


def _open_yandex_response(url, data, headers):
    """Открывает ответ YandexGPT, повторяя только безопасные ошибки 429/503."""
    for attempt in range(settings.GEMINI_MAX_RETRIES + 1):
        try:
            return urllib.request.urlopen(
                _yandex_request(url, data, headers),
                timeout=settings.GEMINI_TIMEOUT_SECONDS,
                context=ssl_context,
            )
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            can_retry = (
                e.code in (429, 503) and attempt < settings.GEMINI_MAX_RETRIES
            )
            if can_retry:
                delay = settings.GEMINI_RETRY_BASE_SECONDS * (2 ** attempt)
                print(
                    f"YandexGPT вернул {e.code}; повтор через {delay:g} сек. "
                    f"({attempt + 1}/{settings.GEMINI_MAX_RETRIES})"
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f"YandexGPT API error {e.code}: {scrub(err_body)}")
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Не удалось подключиться к YandexGPT API: {scrub(str(e.reason))}"
            )


def call_yandexgpt(messages):
    """Возвращает готовый ответ одним JSON-объектом."""
    for attempt in range(3):
        data, headers, retrieved_items = prepare_yandexgpt_request(messages)
        try:
            with _open_yandex_response(YANDEX_URL, data, headers) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < 2:
                print(f"Ошибка вызова YandexGPT ({e}). Повтор {attempt + 1}/3...")
                time.sleep(0.5)
                continue
            raise

        choices = body.get("choices") or []
        if not choices:
            if attempt < 2:
                print(f"Пустой choices от YandexGPT. Попытка {attempt + 1}/3...")
                time.sleep(0.5)
                continue
            raise RuntimeError(f"Пустой ответ от модели. Response={body}")

        content_text = choices[0].get("message", {}).get("content") or ""
        text_out = content_text.strip()
        if not text_out:
            if attempt < 2:
                print(f"Модель вернула пустой текст. Попытка {attempt + 1}/3...")
                time.sleep(0.5)
                continue
            raise RuntimeError("Модель вернула пустой текст ответа.")
        
        reply, content, products = build_response_content(text_out, retrieved_items)
        return {"reply": reply, "content": content, "products": products}


def stream_yandexgpt(messages):
    """Передаёт сырые текстовые фрагменты, затем готовый богатый ответ."""
    for attempt in range(3):
        data, headers, retrieved_items = prepare_yandexgpt_request(messages)
        payload = json.loads(data.decode("utf-8"))
        payload["stream"] = True
        data = json.dumps(payload).encode("utf-8")

        text_parts = []
        try:
            with _open_yandex_response(YANDEX_URL, data, headers) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        payload_text = line[5:].strip()
                        if payload_text == "[DONE]":
                            continue
                        try:
                            body = json.loads(payload_text)
                            choices = body.get("choices") or []
                            if choices:
                                delta = choices[0].get("delta", {}).get("content", "")
                                if delta:
                                    text_parts.append(delta)
                                    yield "delta", {"text": delta}
                        except json.JSONDecodeError:
                            continue

            text_out = "".join(text_parts).strip()
            if text_out:
                reply, content, products = build_response_content(text_out, retrieved_items)
                yield "final", {"reply": reply, "content": content, "products": products}
                return
        except Exception as e:
            if attempt < 2:
                print(f"Ошибка в стриме YandexGPT ({e}). Повтор {attempt + 1}/3...")
                time.sleep(0.5)
                continue
            raise

        if attempt < 2:
            print(f"Стрим вернул пустой текст. Повтор {attempt + 1}/3...")
            time.sleep(0.5)
            continue
        raise RuntimeError("Модель вернула пустой текст ответа.")


def validate_messages(messages):
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages пуст или имеет неверный формат")

    normalized = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("каждое сообщение должно быть объектом")
        role = message.get("role")
        if role not in ("user", "assistant"):
            raise ValueError("неверная роль сообщения")
        text = message.get("text")
        if not isinstance(text, str):
            raise ValueError("текст сообщения должен быть строкой")
        text = text.strip()
        if not text:
            continue
        if role == "user" and len(text) > settings.MAX_USER_MESSAGE_CHARS:
            raise ValueError(
                "сообщение пользователя длиннее "
                f"{settings.MAX_USER_MESSAGE_CHARS} символов"
            )
        normalized.append({"role": role, "text": text})

    if not normalized or not any(m["role"] == "user" for m in normalized):
        raise ValueError("нет пользовательского сообщения")
    return normalized


def resolve_public_path(root, relative_path):
    """Возвращает путь только внутри разрешённого каталога."""
    try:
        root = root.resolve()
        candidate = (root / urllib.parse.unquote(relative_path)).resolve()
        candidate.relative_to(root)
        return candidate
    except (OSError, RuntimeError, ValueError):
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} - {fmt % args}")

    def _send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _start_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _send_sse(self, event, data):
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        body = f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _serve_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if content_type.startswith("text/html"):
                self.send_header("Cache-Control", "no-store, max-age=0")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            self._send_json(404, {"error": "not found"})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        parsed_path = parsed.path

        if parsed_path in ("/", "/index.html", "/site"):
            self.send_response(302)
            self.send_header("Location", "/site/")
            self.end_headers()
            return

        if parsed_path in ("/site/", "/site/index.html"):
            self._serve_file(SITE_INDEX_PATH, "text/html; charset=utf-8")
            return

        if parsed_path in ("/simple", "/simple.html"):
            self._serve_file(INDEX_PATH, "text/html; charset=utf-8")
            return

        if parsed_path.startswith("/site/"):
            rel = parsed_path[len("/site/"):]
            full = resolve_public_path(SITE_DIR, rel)
            if full is None:
                self._send_json(403, {"error": "forbidden"})
                return
            ctype = mimetypes.guess_type(full)[0]
            if not ctype and ".js." in full.name:
                ctype = "application/javascript"
            ctype = ctype or "application/octet-stream"
            self._serve_file(full, ctype)
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path).path
        if parsed_path not in ("/api/chat", "/api/chat/stream"):
            self._send_json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8"))
            messages = validate_messages(data.get("messages", []))

            if parsed_path == "/api/chat/stream":
                self._start_sse()
                try:
                    if settings.LLM_PROVIDER == "yandexgpt":
                        for event, payload in stream_yandexgpt(messages):
                            self._send_sse(event, payload)
                    else:
                        for event, payload in stream_gemini(messages):
                            self._send_sse(event, payload)
                except RuntimeError as e:
                    print("LLM streaming error:", e)
                    try:
                        self._send_sse("error", {"error": str(e)})
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                except (BrokenPipeError, ConnectionResetError):
                    print("Клиент закрыл поток до завершения ответа.")
                return

            if settings.LLM_PROVIDER == "yandexgpt":
                result = call_yandexgpt(messages)
            else:
                result = call_gemini(messages)
            self._send_json(200, result)
        except (ValueError, json.JSONDecodeError) as e:
            self._send_json(400, {"error": str(e)})
        except RuntimeError as e:
            print("LLM error:", e)
            self._send_json(502, {"error": str(e)})
        except Exception as e:
            import traceback
            print("Server error:")
            traceback.print_exc()
            self._send_json(500, {"error": f"Внутренняя ошибка сервера: {e}"})


def main():
    try:
        server = ThreadingHTTPServer((settings.HOST, settings.PORT), Handler)
    except OSError as e:
        print(f"НЕ УДАЛОСЬ ЗАПУСТИТЬ СЕРВЕР на порту {settings.PORT}: {e}")
        print("Скорее всего порт уже занят другим процессом (например, вы уже")
        print("запускали run.bat раньше и окно осталось открытым). Закройте")
        print("старое окно/процесс python и запустите run.bat ещё раз, либо")
        print("поменяйте PORT в .env на другой, например 8080.")
        return

    url = f"http://localhost:{settings.PORT}/site/"
    print(f"Каталог: {len(CATALOG_DATABASE)} позиций загружено.")
    if settings.LLM_PROVIDER == "yandexgpt":
        print(f"Провайдер LLM: YandexGPT (Модель: {settings.YANDEX_MODEL})")
    else:
        print(f"Провайдер LLM: Gemini (Модель: {settings.MODEL_NAME})")
    print(f"Сервер запущен: http://localhost:{settings.PORT}")
    print(f"Демо-сайт (реконструкция remplanika.ru + чат): {url}")
    print(f"Простой макет (запасной вариант): http://localhost:{settings.PORT}/simple")
    print("Открываю демо-сайт в браузере автоматически...")
    print("Если браузер не открылся сам — откройте эту ссылку вручную:", url)
    print("НЕ открывайте index.html двойным кликом напрямую — работать будет")
    print("только через ссылку localhost, иначе чат не сможет достучаться")
    print("до сервера.")
    print("Остановить сервер — Ctrl+C")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановка сервера...")
        server.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n=== СЕРВЕР УПАЛ С ОШИБКОЙ ===")
        traceback.print_exc()
        print("=============================")
        print("Скопируйте текст ошибки выше и пришлите его для диагностики.")
    input("\nНажмите Enter, чтобы закрыть это окно...")
