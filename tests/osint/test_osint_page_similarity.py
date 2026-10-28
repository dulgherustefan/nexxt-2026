"""M4: asemănarea paginii cu login-ul Banca Demo."""

from __future__ import annotations

from versoml.osint.base import fixture_text
from versoml.osint.page_similarity import page_similarity, page_similarity_url, simhash, simhash_similarity

UNRELATED = """<!doctype html><html lang="ro"><head><meta charset="utf-8"><title>Rețetă: ciorbă de legume</title>
<style>body{font-family:Georgia;background:#fdf6e3;color:#333}</style></head>
<body><header><h1>Bucătăria de duminică</h1></header>
<article><h2>Ciorbă de legume</h2><p>Ingrediente: morcovi, cartofi, ceapă, țelină, roșii și leuștean.</p>
<ol><li>Taie legumele mărunt.</li><li>Fierbe-le 30 de minute la foc mic.</li><li>Adaugă leușteanul la final.</li></ol></article>
<form action="/cauta"><input name="q" type="search" placeholder="Caută rețete"><button>Caută</button></form>
<footer>Bucătăria de duminică, blog personal de rețete</footer></body></html>"""

OTHER_LOGIN = """<!doctype html><html><head><title>Webmail Exemplu</title><style>body{background:#e8f0fe;color:#202124}</style>
</head><body><div class="card"><h2>Conectează-te la e-mail</h2><form action="/login" method="post">
<input name="email" type="email" placeholder="Adresa de e-mail"><input name="pass" type="password" placeholder="Parola">
<button>Mai departe</button></form></div></body></html>"""


def test_fake_page_imitates_reference():
    result = page_similarity(fixture_text("fetch_page/livrare-bancademo.example.html"),
                             url="https://livrare-bancademo.example/autentificare")
    assert result.ok and result.data["score"] >= 0.7 and result.signal == "rosu"
    assert set(result.data["components"]) == {"text", "forms", "dom", "style"}
    assert result.data["components"]["forms"] == 1.0
    assert "livrare-bancademo.example" in result.summary


def test_unrelated_page_is_low():
    result = page_similarity(UNRELATED)
    assert result.data["score"] <= 0.3 and result.signal == "neutru"


def test_other_login_page_is_not_red():
    result = page_similarity(OTHER_LOGIN)
    assert result.data["score"] < 0.7 and result.signal != "rosu"


def test_reference_matches_itself_and_legit_domain_is_green():
    html = fixture_text("reference/bancademo_login.html")
    assert page_similarity(html).data["score"] == 1.0
    legit = page_similarity(html, url="https://bancademo.example/autentificare")
    assert legit.signal == "verde"


def test_unknown_reference_and_empty_html_fail_soft():
    assert page_similarity("<html></html>", reference="nu_exista").ok is False
    assert page_similarity("   ").ok is False


def test_simhash_similarity_scale():
    tokens = "banca demo autentificare parola utilizator".split()
    assert simhash_similarity(simhash(tokens), simhash(tokens)) == 1.0
    assert simhash_similarity(simhash(tokens), simhash("ciorba de legume cu leustean".split())) < 0.6


async def test_page_similarity_url_on_fixture(no_network):
    result = await page_similarity_url("https://livrare-bancademo.example/confirmare?id=7731")
    assert result.tool == "page_similarity_url" and result.mode == "fixture"
    assert result.signal == "rosu" and result.data["score"] >= 0.7
