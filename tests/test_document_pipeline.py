"""A extracao tabular nunca aprova automaticamente fatos financeiros."""
from cotacoes.document_pipeline import collect_candidate_tables


class DummyTable:
    def extract(self):
        return [
            ["Código", "Vencimento", "Indexador"],
            ["24L1853110", "04/2035", "IPCA+"],
        ]


class DummyPage:
    def find_tables(self):
        class Result:
            tables = [DummyTable()]
        return Result()


def test_candidate_table_is_unverified():
    candidates = collect_candidate_tables(DummyPage())
    assert len(candidates) == 1
    assert candidates[0]["rows"][1][0] == "24L1853110"
    assert candidates[0]["review_status"] == "unverified_pdf_extraction"


def test_fallback_for_unavailable_table_extraction():
    assert collect_candidate_tables(object()) == []


def test_cap_cells_and_rows_for_untrusted_pdfs():
    class Wide:
        def extract(self):
            return [["x" * 400] * 25 for _ in range(210)]
    class Page:
        def find_tables(self):
            class Result:
                tables = [Wide()]
            return Result()
    candidates = collect_candidate_tables(Page())
    assert len(candidates[0]["rows"]) == 200
    assert len(candidates[0]["rows"][0]) == 20
    assert len(candidates[0]["rows"][0][0]) == 300
    assert candidates[0]["truncated"] is True
