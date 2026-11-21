import hashlib

from app.data_gen.catalog import BY_CODE
from app.data_gen.faults_gen import generate, write_files


def test_generator_is_deterministic(tmp_path):
    assert generate() == generate()
    a = write_files(tmp_path / "a")
    b = write_files(tmp_path / "b")
    assert a == b
    for name in ("SYNTHETIC_machines.json", "SYNTHETIC_fault_records.json"):
        ha = hashlib.sha256((tmp_path / "a" / name).read_bytes()).hexdigest()
        hb = hashlib.sha256((tmp_path / "b" / name).read_bytes()).hexdigest()
        assert ha == hb
        assert "SYNTHETIC" in (tmp_path / "a" / name).read_text()


def test_generated_shape():
    machines, records = generate()
    assert len(machines) == 10 and len(records) == 300
    assert {r["fault_code"] for r in records if r["fault_code"]} <= set(BY_CODE)
    assert any(r["root_cause"] == "undetermined" for r in records)  # ambiguous
    assert any((r["notes"] or "").startswith("INCOMPLETE") for r in records)  # incomplete
    for r in records:
        if r["fault_code"]:
            assert r["root_cause"] in {c.category for c in BY_CODE[r["fault_code"]].causes}


def test_different_seed_differs():
    assert generate(1)[1] != generate(2)[1]
