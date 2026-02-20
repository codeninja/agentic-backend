"""Tests for shared UI utilities."""

from __future__ import annotations

from ninja_ui.shared.assets import FIELD_TYPE_INPUT_MAP, snake_case


class TestSnakeCase:
    """Tests for snake_case conversion."""

    def test_pascal_case(self):
        assert snake_case("CustomerOrder") == "customer_order"

    def test_single_word(self):
        assert snake_case("Order") == "order"

    def test_already_lower(self):
        assert snake_case("order") == "order"

    def test_acronym(self):
        assert snake_case("HTMLParser") == "h_t_m_l_parser"

    def test_empty(self):
        assert snake_case("") == ""


class TestFieldTypeInputMap:
    """Tests for FIELD_TYPE_INPUT_MAP."""

    def test_string_maps_to_text(self):
        assert FIELD_TYPE_INPUT_MAP["string"] == "text"

    def test_text_maps_to_textarea(self):
        assert FIELD_TYPE_INPUT_MAP["text"] == "textarea"

    def test_integer_maps_to_number(self):
        assert FIELD_TYPE_INPUT_MAP["integer"] == "number"

    def test_boolean_maps_to_checkbox(self):
        assert FIELD_TYPE_INPUT_MAP["boolean"] == "checkbox"

    def test_datetime_maps_to_datetime_local(self):
        assert FIELD_TYPE_INPUT_MAP["datetime"] == "datetime-local"

    def test_date_maps_to_date(self):
        assert FIELD_TYPE_INPUT_MAP["date"] == "date"

    def test_enum_maps_to_select(self):
        assert FIELD_TYPE_INPUT_MAP["enum"] == "select"

    def test_all_field_types_covered(self):
        expected = {
            "string",
            "text",
            "integer",
            "float",
            "boolean",
            "datetime",
            "date",
            "uuid",
            "json",
            "array",
            "binary",
            "enum",
        }
        assert set(FIELD_TYPE_INPUT_MAP.keys()) == expected
