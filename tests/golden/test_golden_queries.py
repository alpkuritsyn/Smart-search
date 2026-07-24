import sys
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.normalization.query_parser import parse_query

def test_paint_tikkurila_query():
    parsed = parse_query("краска тикурила")
    assert parsed["brand_id"] == "brand:tikkurila"
    assert parsed["product_type_id"] == "type:paint"

def test_paint_tikkurila_latin_query():
    parsed = parse_query("краска tikkurila")
    assert parsed["brand_id"] == "brand:tikkurila"
    assert parsed["product_type_id"] == "type:paint"

def test_word_order_independence():
    parsed = parse_query("тикурила краска")
    assert parsed["brand_id"] == "brand:tikkurila"
    assert parsed["product_type_id"] == "type:paint"

def test_primer_dulux_query():
    parsed = parse_query("грунтовка dulux")
    assert parsed["brand_id"] == "brand:dulux"
    assert parsed["product_type_id"] == "type:primer"

def test_wood_varnish_query():
    parsed = parse_query("лак для дерева")
    assert parsed["brand_id"] is None
    assert parsed["product_type_id"] == "type:varnish"
    assert "дерева" in parsed["unparsed_tokens"]

def test_putty_20kg_query():
    parsed = parse_query("шпаклевка 20 кг")
    assert parsed["brand_id"] is None
    assert parsed["product_type_id"] == "type:putty"
    assert parsed["attributes"].get("weight_kg") == 20

def test_unknown_brand():
    parsed = parse_query("краска неизвестныйбренд")
    assert parsed["brand_id"] is None
    assert parsed["product_type_id"] == "type:paint"
    assert "неизвестныйбренд" in parsed["unparsed_tokens"]


def test_alias_is_not_matched_inside_another_word():
    parsed = parse_query("латексная краска")
    assert parsed["brand_id"] is None
    assert parsed["product_type_id"] == "type:paint"
