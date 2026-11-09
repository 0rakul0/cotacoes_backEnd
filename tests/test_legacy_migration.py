"""Testes de selecao do snapshot legado; sem rede nem execucao de codigo antigo."""
from scripts.migrate_legacy import eligible, sources


def test_source_pins():
    items = sources()
    assert len(items) == 7
    assert len({i["repository"] for i in items}) == 7
    assert all(len(i["sha"]) == 40 for i in items)


def test_allow_selected_financial_materials():
    assert eligible("TimesSeriesAgent", "src/agent_noticia.py")
    assert eligible("TimesSeriesAgent", "modelos/transformer_petr4.pt")
    assert eligible("TimesSeriesAgent", "data/resultado_comparacao_modelos.csv")
    assert eligible("TimesSeriesAgent", "artigo/main.tex")
    assert eligible("cotacaopython", "datamine.py")
    assert eligible("cotacaopython", "statistica/hist/MXRF11.csv")
    assert eligible("cotacaopython", "statistica/financa.ipynb")
    assert eligible("Projeto_ciencia_de_dados_acoes", "data/Cotacoes.xlsx")
    assert eligible("cienciaDeDados", "dataAnalitycsParte4.py")
    assert eligible("notificacao_com_python", "AlertPython.py")
    assert eligible("cotacoes_frontend_react", "index.html")


def test_reject_sensitive_or_generated_files():
    assert not eligible("cotacaopython", "bi/minha_carteira.xlsx")
    assert not eligible("cotacaopython", "util/conn/settings.py")
    assert not eligible("TimesSeriesAgent", "img/mvp_online_petr4.html")
    assert not eligible("TimesSeriesAgent", ".idea/project.xml")
    assert not eligible("TimesSeriesAgent", "test/../../.env")
    assert not eligible("cotacaopython", "chromedriver105/chromedriver.exe")
    assert not eligible("cienciaDeDados", "data/house_prices.csv")


def test_preserved_snapshot_integrity():
    from scripts.migrate_legacy import MANIFEST, verify
    assert MANIFEST.is_file(), "Snapshot legado ausente da master."
    verify()
