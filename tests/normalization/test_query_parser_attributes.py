#!/usr/bin/env python3
"""
Unit tests for attribute & characteristic extraction in query_parser.
"""
from src.normalization.query_parser import parse_query

def test_surface_attribute_extraction():
    parsed = parse_query("строганный брус")
    assert parsed["product_type_id"] == "type:brusok"
    assert parsed["attributes"].get("surface") == "строганый"
    assert "строганный" not in parsed["unparsed_tokens"]

def test_surface_variant_extraction():
    parsed = parse_query("доска строганая")
    assert parsed["product_type_id"] == "type:brusok"
    assert parsed["attributes"].get("surface") == "строганый"
    assert "строганая" not in parsed["unparsed_tokens"]

def test_moisture_attribute_extraction():
    parsed = parse_query("сухой брусок 50х50")
    assert parsed["product_type_id"] == "type:brusok"
    assert parsed["attributes"].get("moisture") == "сухой"
    assert "сухой" not in parsed["unparsed_tokens"]

def test_finish_and_color_extraction():
    parsed = parse_query("матовая краска белая 10л")
    assert parsed["product_type_id"] == "type:paint"
    assert parsed["attributes"].get("finish") == "матовый"
    assert parsed["attributes"].get("color") == "белый"
    assert parsed["attributes"].get("volume_l") == 10
    assert "матовая" not in parsed["unparsed_tokens"]
    assert "белая" not in parsed["unparsed_tokens"]

def test_property_attribute_extraction():
    parsed = parse_query("влагостойкий гипсокартон")
    assert parsed["product_type_id"] == "type:gypsum_board"
    assert parsed["attributes"].get("properties") == "влагостойкий"
    assert "влагостойкий" not in parsed["unparsed_tokens"]
