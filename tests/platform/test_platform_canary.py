"""Canary: registrul ține doar hash-uri; detectarea rezistă la majuscule, separatori, omoglife, inversare."""

from __future__ import annotations

import json
import re
import threading

import pytest

from versoml.wall import CanaryRegistry, token_hash


def test_mint_format_and_hash_only_storage(registry):
    token = registry.mint("LD-0001")
    assert re.fullmatch(r"ZX-[A-Z2-7]{10}", token)
    stored = registry.path.read_text(encoding="utf-8")
    assert token not in stored and token[3:] not in stored and "LD-0001" not in stored
    data = json.loads(stored)
    assert data["hashes"] == [token_hash(token)] and len(registry) == 1


def _variants(token: str) -> list[str]:
    body = token[3:]
    cyrillic = token.replace("A", "\u0410").replace("E", "\u0415").replace("O", "\u041e").replace("X", "\u0425")
    return [
        token,
        token.lower(),
        f"Referința internă ({token}).",
        " ".join(token),
        f"ZX.{body[:3]}-{body[3:6]}_{body[6:]}",
        f"ZX\u2011{body}",                                  # cratimă neseparabilă
        f"Z\u200bX-{body[:5]}\u200b{body[5:]}",             # spații de lățime zero
        f"ZX\u00a0{body}",
        "".join(chr(ord(c) + 0xFEE0) if c.isalnum() else c for c in token),  # caractere fullwidth
        cyrillic,
        token[::-1],
        json.dumps({"nota": f"dosar {token}"}),
        f"ZX-{body[:5]}\n{body[5:]}",
        f"zx {body.lower()}",
    ]


def test_scan_finds_embedded_and_obfuscated_tokens(registry):
    token = registry.mint("LD-0002")
    for text in _variants(token):
        assert registry.scan(text) == 1, text


def test_scan_counts_occurrences_and_ignores_lookalikes(registry):
    token = registry.mint("LD-0003")
    other = CanaryRegistry(registry.path.with_name("altul.json")).mint("LD-9")
    assert registry.scan(f"{token} și iar {token.lower()}") == 2
    changed = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert registry.scan(changed) == 0
    assert registry.scan(token[:-1]) == 0
    assert registry.scan(other) == 0
    assert registry.scan("") == 0 and registry.scan("text fără nimic") == 0


def test_digit_lookalikes_are_folded():
    registry = CanaryRegistry(path=None)
    registry.path = registry.path.with_name("nefolosit.json")  # nu atinge fișierul real
    raw = "ZX-OIBOIBOIBO"
    digest = token_hash(raw)
    assert token_hash("ZX-0180180180") == digest


def test_client_side_instance_sees_tokens_minted_later(registry):
    client_side = CanaryRegistry(registry.path)
    assert client_side.scan("nimic") == 0
    token = registry.mint("LD-0004")
    assert client_side.scan(f"scurgere: {token}") == 1


def test_secret_makes_mint_deterministic(tmp_path):
    a = CanaryRegistry(tmp_path / "a.json", secret=b"secret-aml-demo")
    b = CanaryRegistry(tmp_path / "b.json", secret=b"secret-aml-demo")
    assert a.mint("LD-7") == b.mint("LD-7") != a.mint("LD-8")


def test_concurrent_mints_and_scans_keep_every_hash(registry):
    tokens: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()
    done = threading.Event()

    def writer(i: int) -> None:
        try:
            local = CanaryRegistry(registry.path)
            for j in range(12):
                token = local.mint(f"LD-{i}-{j}")
                with lock:
                    tokens.append(token)
        except BaseException as exc:  # pragma: no cover - raportat mai jos
            errors.append(exc)

    def reader() -> None:
        try:
            local = CanaryRegistry(registry.path)
            while not done.is_set():
                with lock:
                    sample = list(tokens[-3:])
                for token in sample:  # un token odată văzut nu mai dispare
                    assert local.scan(token) == 1
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    writers = [threading.Thread(target=writer, args=(i,)) for i in range(6)]
    readers = [threading.Thread(target=reader) for _ in range(3)]
    for t in writers + readers:
        t.start()
    for t in writers:
        t.join()
    done.set()
    for t in readers:
        t.join()
    assert errors == []
    assert len(CanaryRegistry(registry.path)) == 72
    assert all(registry.scan(t) == 1 for t in tokens)
    assert not list(registry.path.parent.glob("*.tmp")) and not list(registry.path.parent.glob("*.lock"))


def test_register_hash_validates(registry):
    with pytest.raises(ValueError):
        registry.register_hash("nu-e-hash")


def test_an_empty_registry_is_still_used(tmp_path, registry):
    """Regresie: `registry or CanaryRegistry()` înlocuia un registru gol cu cel implicit din var/."""
    from versoml.wall import adversarial_aml_states, check_letter

    assert bool(registry) is True and len(registry) == 0
    states = adversarial_aml_states(1, registry=registry)
    assert len(registry) == 1 and registry.scan(states[0]["leads"][0]["canary"]) == 1
    assert not (tmp_path / "default_wall" / "canary_hashes.json").exists()
    other = CanaryRegistry(tmp_path / "gol.json")
    assert check_letter(f"Ref {states[0]['leads'][0]['canary']}", registry=other).canaries_found == 0
    assert CanaryRegistry().path == tmp_path / "default_wall" / "canary_hashes.json"
