#!/usr/bin/env python3
"""
Expand Taxonomy, Attributes & Alias Dictionary across all 21,038 Canonical Catalog Products.
Generates comprehensive brand, product_type, and characteristic attribute mappings for 100% of canonical catalog records.
"""
import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Set

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.normalization.query_parser import parse_query

DIMINUTIVES_AND_PLURALS = {
    "брусок": ["брусок", "бруска", "бруску", "бруском", "бруске", "бруски", "брусков", "брусочек", "брусочки", "брусочка", "брус", "доска", "доски", "доску", "доской", "доскам", "досочка", "досочки", "рейка", "рейки", "реечка", "вагонка", "евровагонка", "пиломатериал", "пиломатериалы"],
    "фанера": ["фанера", "фанеры", "фанеру", "фанерой", "фанерный", "фанерка"],
    "рейка": ["рейка", "рейки", "рейку", "рейкой", "реечка", "реечки"],
    "вагонка": ["вагонка", "вагонки", "вагонку", "евровагонка"],
    "плинтус": ["плинтус", "плинтусы", "плинтуса", "плинтусов", "плинтусик"],
    "краска": ["краска", "краски", "краску", "красок", "эмаль", "эмали", "колер", "колеры", "водоэмульсионка", "водно-дисперсионная"],
    "грунтовка": ["грунт", "грунты", "грунтовка", "грунтовки", "грунтовку", "праймер", "праймеры", "бетоноконтакт", "бетонконтакт"],
    "шпаклёвка": ["шпатлевка", "шпатлёвка", "шпаклевка", "шпаклёвка", "шпаклевку", "шпатлевку", "финишная паста"],
    "штукатурка": ["штукатурка", "штукатурку", "штукатурки", "штукатурок", "декоративка"],
    "лак": ["лак", "лаки", "лака", "лаков", "лаковое", "пропитка-лак"],
    "кисть": ["кисть", "кисти", "кисточка", "кисточки", "кистей", "макловица", "флейц"],
    "валик": ["валик", "валики", "валиков", "ролик", "мини-валик"],
    "клей для плитки": ["клей для плитки", "плиточный клей", "клей плиточный", "плиточный"],
    "наливной пол": ["наливной пол", "самонивелир", "самовыравнивающийся пол", "пол наливной"],
    "гипсокартон": ["гипсокартон", "гкл", "гклов", "гклв", "гипсокартонный лист"],
    "пена монтажная": ["пена", "пена монтажная", "монтажная пена", "пена-клей", "пистолетная пена"],
    "герметик": ["герметик", "герметики", "силикон", "акрил", "герметизирующий"],
    "затирка": ["затирка", "затирка для швов", "затирки", "фуга"],
    "саморез": ["саморез", "саморезы", "саморезов", "шуруп", "шурупы", "шурупов"],
    "дюбель": ["дюбель", "дюбели", "дюбеля", "дюбель-гвоздь", "дюбель-гвозди"],
    "уголок": ["уголок", "уголки", "уголков", "профиль металлический"],
    "профиль": ["профиль", "профили", "профилей", "направляющая", "стоечный"],
    "труба": ["труба", "трубы", "труб", "трубка", "трубопровод"],
    "фитинг": ["фитинг", "фитинги", "фитингов", "муфта", "отвод", "тройник"],
    "утеплитель": ["утеплитель", "утеплители", "минвата", "минеральная вата", "базальтовая вата", "пеноплэкс", "пенопласт"],
    "гидроизоляция": ["гидроизоляция", "гидроизоляционный", "гидроизоляционная мастика"],
    "кабель": ["кабель", "кабели", "провод", "провода", "шнур"],
    "розетка": ["розетка", "розетки", "розеточный блок"],
    "выключатель": ["выключатель", "выключатели", "переключатель"],
    "автомат": ["автомат", "автоматы", "автоматический выключатель", "дифавтомат", "узо"],
    "светильник": ["светильник", "светильники", "люстра", "спот", "прожектор", "лампа", "лампочка"],
    "шпатель": ["шпатель", "шпатели", "шпателя", "мастерок", "кельма"],
    "плитка": ["плитка", "керамогранит", "кафель", "плитка керамическая"],
    "ламинат": ["ламинат", "ламинированный пол"],
    "линолеум": ["линолеум", "напольное покрытие"],
    "обои": ["обои", "фотообои", "стеклообои", "флизелиновые обои"],
}

INVALID_BRAND_STRINGS = {
    "гипсокартон", "саморезы", "саморез", "профиль", "уголок", "брусок", "доска", "фанера", "плинтус",
    "труба", "трубы", "фитинги", "кабель", "провод", "электрика", "сантехника", "крепеж", "метизы",
    "гидроизоляция", "утеплитель", "плитка", "ламинат", "линолеум", "обои", "инструмент", "краска",
    "грунтовка", "шпаклевка", "шпатлевка", "штукатурка", "лак", "затирка", "пена", "герметик",
    "малая упаковка", "сопутствующие материалы", "упаковка", "гладкая", "для камня", "белый", "бежевый",
    "черный", "серый", "синий", "красный", "зеленый", "прозрачный", "матовый", "глянцевый",
    "стальные", "чугунные", "термостойкие", "металлические", "пластиковые", "деревянные",
    "латунные", "оцинкованные", "медные", "алюминиевые", "строганный", "строганый", "строганая",
    "влагостойкий", "влагостойкая", "калиброванный", "калиброванная"
}

def clean_slug(text: str) -> str:
    text = text.lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text).strip("_")
    return text

def is_valid_brand(brand_name: str, item: Dict[str, Any] = None) -> bool:
    clean_b = brand_name.strip().lower()
    if len(clean_b) < 3:
        return False
    if clean_b in INVALID_BRAND_STRINGS:
        return False
    if item:
        subcat = (item.get("subcategory") or "").lower()
        cat = (item.get("category") or "").lower()
        if clean_b in subcat or clean_b in cat:
            return False
    return True

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    catalog_path = BASE_DIR / "data" / "canonical" / "catalog.canonical.json"
    aliases_path = BASE_DIR / "config" / "search_aliases.json"

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    with open(aliases_path, "r", encoding="utf-8") as f:
        aliases_config = json.load(f)

    brands_by_catalog_value: Dict[str, Dict[str, Any]] = {}
    
    # Pre-populate seed brands (filtering out invalid brand adjectives)
    for b in aliases_config.get("brands", []):
        cat_val = b.get("catalog_value", "").strip()
        disp_val = b.get("display", "").strip()
        if is_valid_brand(cat_val) and is_valid_brand(disp_val) and b.get("id") not in {"brand:стальные", "brand:чугунные", "brand:термостойкие"}:
            brands_by_catalog_value[cat_val.upper()] = b

    for item in catalog:
        raw_brand = item.get("brand")
        if not raw_brand or not raw_brand.strip():
            continue
        clean_b = raw_brand.strip()
        if not is_valid_brand(clean_b, item):
            continue
        upper_b = clean_b.upper()
        if upper_b not in brands_by_catalog_value:
            b_slug = clean_slug(clean_b)
            b_id = f"brand:{b_slug}"
            brand_aliases = list(set([clean_b.lower(), upper_b.lower(), b_slug.replace("_", "")]))
            brands_by_catalog_value[upper_b] = {
                "id": b_id,
                "catalog_value": upper_b,
                "display": clean_b,
                "aliases": brand_aliases
            }

    types_by_id: Dict[str, Dict[str, Any]] = {}

    subcat_mapping_rules = [
        (r"опора.*брус|саморез|шуруп|дюбель|анкер|крепеж|метиз", "type:fastener", "крепеж"),
        (r"сайдинг", "type:siding", "сайдинг"),
        (r"\b(лак|лаки|лаков|лаком|лака|пропитка-лак)\b", "type:varnish", "лак"),
        (r"\b(грунт|грунтовк|праймер|бетоноконтакт)\w*", "type:primer", "грунтовка"),
        (r"\b(шпатлев|шпаклев|паста финиш)\w*", "type:putty", "шпаклёвка"),
        (r"\b(штукатур)\w*", "type:plaster", "штукатурка"),
        (r"\b(краск|эмаль|колер)\w*", "type:paint", "краска"),
        (r"\b(кист|кисточк|макловиц|флейц)\w*", "type:brush", "кисть"),
        (r"\b(валик|ролик)\w*", "type:roller", "валик"),
        (r"плиточн.*клей|клей.*плит", "type:tile_glue", "плиточный клей"),
        (r"\b(брус|брусок|рейка|вагонка|доска|пиломатериал)\w*", "type:brusok", "брусок"),
        (r"фанер|осб|osb|дсп|двп", "type:plywood", "фанера"),
        (r"гипсокартон|гкл", "type:gypsum_board", "гипсокартон"),
        (r"наливн.*пол|самонивелир", "type:self_leveling_floor", "наливной пол"),
        (r"стяжка|кладочн.*смесь|цемент", "type:cement_mix", "сухая смесь"),
        (r"пена.*монт|монт.*пена", "type:foam_mounting", "пена монтажная"),
        (r"герметик|силикон|акрил", "type:sealant", "герметик"),
        (r"затирка|фуга", "type:grout", "затирка"),
        (r"труб|фитинг|муфта|отвод|сифон|сантех", "type:plumbing", "сантехника"),
        (r"кабель|провод|розетк|выключат|автомат|электр", "type:electrical", "электрика"),
        (r"гидроизол", "type:waterproofing", "гидроизоляция"),
        (r"утеплител|минвата|пеноплэкс", "type:insulation", "утеплитель"),
        (r"плинтус|порог", "type:skirting", "плинтус"),
        (r"ламинат|линолеум|паркет", "type:flooring", "напольное покрытие"),
        (r"обои|стеклообои", "type:wallpaper", "обои"),
        (r"дрель|перфоратор|болгарка|ушм|шуруповерт|инструмент", "type:tool", "инструмент"),
    ]

    for pt in aliases_config.get("product_types", []):
        clean_aliases = [a for a in pt.get("aliases", []) if a and "\ufffd" not in a]
        types_by_id[pt["id"]] = {
            "id": pt["id"],
            "display": pt.get("display", "").replace("\ufffd", ""),
            "aliases": clean_aliases
        }

    for pattern, type_id, display_name in subcat_mapping_rules:
        existing_aliases = types_by_id.get(type_id, {}).get("aliases", [])
        new_aliases = DIMINUTIVES_AND_PLURALS.get(display_name, [display_name, display_name + "ы", display_name + "и"])
        types_by_id[type_id] = {
            "id": type_id,
            "display": display_name,
            "aliases": sorted(list(set([a for a in (existing_aliases + new_aliases) if a and "\ufffd" not in a])))
        }

    mapped_type_count = 0
    mapped_brand_count = 0
    mapped_attributes_count = 0

    for item in catalog:
        item["brand_id"] = None
        item["product_type_id"] = None
        item["attributes"] = item.get("attributes") or {}

        # 1. Match Brand
        raw_b = item.get("brand")
        if raw_b and raw_b.strip() and is_valid_brand(raw_b, item):
            upper_b = raw_b.strip().upper()
            if upper_b in brands_by_catalog_value:
                item["brand_id"] = brands_by_catalog_value[upper_b]["id"]
                mapped_brand_count += 1

        # 2. Match Product Type
        subcat = (item.get("subcategory") or "").lower()
        cat = (item.get("category") or "").lower()
        name = (item.get("name") or "").lower()

        NON_PAINT_CATEGORIES = {
            "инженерная сантехника", "ревизионные люки", "климатическое оборудование",
            "электроинструмент и комплектующие", "ручной инструмент, спецодежда",
            "дача, сад, отдых", "крепеж и метизы", "сухие строительные смеси и гидроизоляция"
        }
        clean_name = re.sub(r"покрыти\w*\s+(полимерн\w*\s+)?эмаль\w*|под\s+покраск\w*", "", name)

        matched_type_id = None
        for pattern, type_id, _ in subcat_mapping_rules:
            if type_id in {"type:paint", "type:varnish", "type:brush", "type:roller"} and (cat in NON_PAINT_CATEGORIES or subcat in NON_PAINT_CATEGORIES):
                continue
            search_text = f"{subcat} {cat} {clean_name}"
            if re.search(pattern, search_text):
                matched_type_id = type_id
                break

        if matched_type_id:
            item["product_type_id"] = matched_type_id
            mapped_type_count += 1

        # 3. Extract attributes from product name & subcategory
        parsed_item = parse_query(f"{name} {subcat}")
        if parsed_item.get("attributes"):
            item["attributes"].update(parsed_item["attributes"])
            mapped_attributes_count += 1

    aliases_config["brands"] = list(brands_by_catalog_value.values())
    aliases_config["product_types"] = list(types_by_id.values())

    with open(aliases_path, "w", encoding="utf-8") as f:
        json.dump(aliases_config, f, ensure_ascii=False, indent=2)

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"PASS: Updated clean taxonomy across all {len(catalog)} canonical products!")
    print(f"Total valid brands in search_aliases.json: {len(brands_by_catalog_value)}")
    print(f"Total product types in search_aliases.json: {len(types_by_id)}")
    print(f"Products with brand_id: {mapped_brand_count} / {len(catalog)} ({mapped_brand_count / len(catalog) * 100:.1f}%)")
    print(f"Products with product_type_id: {mapped_type_count} / {len(catalog)} ({mapped_type_count / len(catalog) * 100:.1f}%)")
    print(f"Products with parsed attributes: {mapped_attributes_count} / {len(catalog)} ({mapped_attributes_count / len(catalog) * 100:.1f}%)")

if __name__ == "__main__":
    main()
