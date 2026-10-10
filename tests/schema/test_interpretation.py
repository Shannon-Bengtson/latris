"""Round-trip and validation tests for the interpretation schema."""

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.ids import new_id
from latris.schema.interpretation import (
    INTERPRET_SECTION_IDS,
    InterpretationStore,
    InterpretSection,
    InterpretTextVersion,
)


def _make_section(section_type="structural_summary", model_type="cld"):
    return InterpretSection(
        id=new_id("interpret-section"),
        section_type=section_type,
        model_type=model_type,
        claims=["Claim A", "Claim B"],
        claims_at_generation=[],
        prose="",
        generation_state="claims_only",
    )


class TestInterpretSectionIds:
    def test_nine_section_types(self):
        assert len(INTERPRET_SECTION_IDS) == 10

    def test_known_types(self):
        assert "structural_summary" in INTERPRET_SECTION_IDS
        assert "answer_to_question" in INTERPRET_SECTION_IDS
        assert "open_questions" in INTERPRET_SECTION_IDS


class TestInterpretSection:
    def test_create_section(self):
        section = _make_section()
        assert section.section_type == "structural_summary"
        assert section.model_type == "cld"
        assert section.claims == ["Claim A", "Claim B"]
        assert section.generation_state == "claims_only"

    def test_id_prefix(self):
        section = _make_section()
        assert section.id.startswith("interpret-section_")

    def test_add_version(self):
        section = _make_section()
        version = InterpretTextVersion(
            version_id=new_id("version"),
            text="Generated prose.",
            source="ai",
            model_commit="abc123",
        )
        section.prose_versions.append(version)
        assert len(section.prose_versions) == 1
        assert section.prose_versions[0].source == "ai"


class TestInterpretationStore:
    def test_empty_store(self):
        store = InterpretationStore()
        assert store.sections == []

    def test_store_with_sections(self):
        store = InterpretationStore(
            sections=[
                _make_section("structural_summary"),
                _make_section("key_findings"),
            ]
        )
        assert len(store.sections) == 2


class TestYamlRoundTrip:
    def test_round_trip(self, tmp_path):
        section = _make_section()
        section.prose = "Some interpretation text."
        section.prose_versions.append(
            InterpretTextVersion(
                version_id=new_id("version"),
                text="Some interpretation text.",
                source="ai",
                model_commit="def456",
            )
        )
        store = InterpretationStore(sections=[section])

        path = tmp_path / "interpretation.yaml"
        dump_model(store, path)

        loaded = load_model(InterpretationStore, path)
        assert len(loaded.sections) == 1
        assert loaded.sections[0].prose == "Some interpretation text."
        assert loaded.sections[0].claims == ["Claim A", "Claim B"]
        assert len(loaded.sections[0].prose_versions) == 1
        assert loaded.sections[0].prose_versions[0].source == "ai"

    def test_empty_store_round_trip(self, tmp_path):
        store = InterpretationStore()
        path = tmp_path / "interpretation.yaml"
        dump_model(store, path)

        loaded = load_model(InterpretationStore, path)
        assert loaded.sections == []
