"""Tests for CRUD viewer generation."""

from __future__ import annotations

from ninja_ui.crud.generator import CrudGenerator, _build_field_meta, _find_relationships


class TestBuildFieldMeta:
    """Tests for field metadata preprocessing."""

    def test_basic_fields(self, customer_entity):
        meta = _build_field_meta(customer_entity)
        assert len(meta) == 4
        assert meta[0]["name"] == "id"
        assert meta[0]["primary_key"] is True
        assert meta[0]["input_type"] == "text"

    def test_field_type_mapping(self, customer_entity):
        meta = _build_field_meta(customer_entity)
        name_field = next(f for f in meta if f["name"] == "name")
        assert name_field["input_type"] == "text"
        active_field = next(f for f in meta if f["name"] == "active")
        assert active_field["input_type"] == "checkbox"

    def test_constraints_extracted(self, customer_entity):
        meta = _build_field_meta(customer_entity)
        name_field = next(f for f in meta if f["name"] == "name")
        assert name_field["constraints"]["minlength"] == 1
        assert name_field["constraints"]["maxlength"] == 100

    def test_numeric_constraints(self, order_entity):
        meta = _build_field_meta(order_entity)
        total_field = next(f for f in meta if f["name"] == "total")
        assert total_field["constraints"]["min"] == 0
        assert total_field["input_type"] == "number"

    def test_nullable_field(self, customer_entity):
        meta = _build_field_meta(customer_entity)
        active_field = next(f for f in meta if f["name"] == "active")
        assert active_field["nullable"] is True

    def test_embedding_field(self, product_entity):
        meta = _build_field_meta(product_entity)
        desc_field = next(f for f in meta if f["name"] == "description")
        assert desc_field["input_type"] == "textarea"
        assert desc_field["field_type"] == "text"


class TestFindRelationships:
    """Tests for relationship discovery."""

    def test_outgoing_relationship(self, customer_entity, sample_asd):
        rels = _find_relationships(customer_entity, sample_asd)
        assert len(rels) == 1
        assert rels[0]["target_entity"] == "Order"
        assert rels[0]["direction"] == "outgoing"

    def test_incoming_relationship(self, order_entity, sample_asd):
        rels = _find_relationships(order_entity, sample_asd)
        assert len(rels) == 1
        assert rels[0]["target_entity"] == "Customer"
        assert rels[0]["direction"] == "incoming"

    def test_no_relationships(self, product_entity, sample_asd):
        rels = _find_relationships(product_entity, sample_asd)
        assert len(rels) == 0

    def test_relationship_slug(self, customer_entity, sample_asd):
        rels = _find_relationships(customer_entity, sample_asd)
        assert rels[0]["target_slug"] == "order"


class TestCrudGenerator:
    """Tests for CRUD page generation."""

    def test_generate_entity_page(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        assert path.exists()
        assert path.name == "customer.html"
        content = path.read_text()
        assert "Customer" in content
        assert "data-table" in content

    def test_entity_page_has_fields(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "name" in content
        assert "email" in content

    def test_entity_page_inline_editing(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "inline-edit" in content
        assert "toggleEdit" in content

    def test_entity_page_validation(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "minlength" in content
        assert "maxlength" in content

    def test_entity_page_relationships(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "order.html" in content
        assert "customer_orders" in content

    def test_entity_page_semantic_search(self, sample_asd, product_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(product_entity, tmp_path)
        content = path.read_text()
        assert "semantic-search" in content
        assert "search_${ENTITY}" in content

    def test_entity_page_no_semantic_search_without_embedding(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "semantic-search" not in content

    def test_entity_page_pagination(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "pagination" in content
        assert "prevPage" in content
        assert "nextPage" in content

    def test_entity_page_sorting(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "sort-header" in content

    def test_entity_page_filtering(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "filter-input" in content

    def test_generate_index(self, sample_asd, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_index(tmp_path)
        assert path.exists()
        assert path.name == "index.html"
        content = path.read_text()
        assert "test-shop" in content
        assert "Customer" in content
        assert "Order" in content
        assert "Product" in content

    def test_index_links_to_entity_pages(self, sample_asd, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_index(tmp_path)
        content = path.read_text()
        assert "customer.html" in content
        assert "order.html" in content
        assert "product.html" in content

    def test_index_shows_storage_engine(self, sample_asd, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_index(tmp_path)
        content = path.read_text()
        assert "sql" in content.lower()
        assert "vector" in content.lower()

    def test_generate_all(self, sample_asd, tmp_path):
        gen = CrudGenerator(sample_asd)
        paths = gen.generate(tmp_path)
        # index + 3 entity pages
        assert len(paths) == 4
        assert all(p.exists() for p in paths)
        assert (tmp_path / "crud" / "index.html").exists()
        assert (tmp_path / "crud" / "customer.html").exists()
        assert (tmp_path / "crud" / "order.html").exists()
        assert (tmp_path / "crud" / "product.html").exists()

    def test_entity_page_has_create_form(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "create-form" in content
        assert "createRecord" in content

    def test_entity_page_has_delete(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "deleteRecord" in content

    def test_entity_page_gql_integration(self, sample_asd, customer_entity, tmp_path):
        gen = CrudGenerator(sample_asd)
        path = gen.generate_entity_page(customer_entity, tmp_path)
        content = path.read_text()
        assert "GQL_ENDPOINT" in content
        assert "gqlQuery" in content
        assert 'ENTITY = "customer"' in content
