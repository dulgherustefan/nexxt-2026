"""Pasul 0: ce regiune și ce modele Claude merg cu cheia Bedrock.

Cheia se încarcă doar în mediu. Rezultatul (var/bedrock_probe.json) conține statusuri,
coduri de eroare și latențe, niciodată cheia sau headerele.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from versoml.config import get_settings
from versoml.secrets import install_log_redaction, key_format, load_bedrock_key, redact

REGIONS = ["us-east-1", "us-west-2", "eu-central-1", "eu-west-1", "eu-north-1"]
PRIMARY = ["anthropic.claude-haiku-4-5", "anthropic.claude-sonnet-5", "anthropic.claude-opus-5-5"]
FALLBACK = ["anthropic.claude-opus-4-8", "anthropic.claude-sonnet-5-5", "anthropic.claude-haiku-5-5"]


def _call(client, model: str) -> dict:
    import anthropic

    started = time.perf_counter()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=16,
            messages=[{"role": "user", "content": "Răspunde cu un singur cuvânt: ok"}],
        )
        text = "".join(getattr(b, "text", "") for b in response.content).strip()
        return {"ok": True, "ms": round((time.perf_counter() - started) * 1000), "reply": text[:20],
                "model_served": getattr(response, "model", model)}
    except anthropic.APIStatusError as exc:
        return {"ok": False, "status": exc.status_code, "error": type(exc).__name__,
                "detail": redact(str(exc))[:240]}
    except anthropic.APIConnectionError as exc:
        return {"ok": False, "status": None, "error": "APIConnectionError", "detail": redact(str(exc))[:160]}
    except Exception as exc:  # noqa: BLE001 - raportăm orice eroare, fără să oprim sonda
        return {"ok": False, "status": None, "error": type(exc).__name__, "detail": redact(str(exc))[:160]}


def probe_bedrock(regions: list[str] | None = None, full: bool = False) -> dict:
    from anthropic import AnthropicBedrockMantle

    install_log_redaction()
    settings = get_settings()
    has_key = load_bedrock_key()
    report: dict = {"checked_at": datetime.now(timezone.utc).isoformat(), "key": key_format(), "regions": {}}
    if not has_key:
        report["verdict"] = "Lipsește cheia: pune-o în API_KEY.txt sau în AWS_BEARER_TOKEN_BEDROCK."
        return report

    ordered = list(dict.fromkeys([settings.aws_region, *(regions or REGIONS)]))
    best: tuple[str, list[str]] | None = None
    for region in ordered:
        client = AnthropicBedrockMantle(aws_region=region, max_retries=0, timeout=25)
        results = {}
        first = _call(client, PRIMARY[0])
        results[PRIMARY[0]] = first
        if first["ok"] or first.get("status") in (400, 403, 404, 429):
            for model in PRIMARY[1:] + FALLBACK:
                results[model] = _call(client, model)
        report["regions"][region] = results
        working = [m for m, r in results.items() if r["ok"]]
        if working and (best is None or len(working) > len(best[1])):
            best = (region, working)
        if best and all(m in best[1] for m in PRIMARY) and not full:
            break

    if best:
        region, working = best
        pick = {
            "opus": next((m for m in ["anthropic.claude-opus-5-5", "anthropic.claude-opus-4-8"] if m in working), None),
            "sonnet": next((m for m in ["anthropic.claude-sonnet-5-5", "anthropic.claude-sonnet-5"] if m in working), None),
            "haiku": next((m for m in ["anthropic.claude-haiku-5-5", "anthropic.claude-haiku-4-5"] if m in working), None),
        }
        report["recommended"] = {"region": region, **pick}
        report["verdict"] = f"Merge în {region}: {', '.join(working)}"
    else:
        report["verdict"] = "Niciun model nu a răspuns. Vezi erorile pe regiuni."

    out = settings.var_dir / "bedrock_probe.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys

    result = probe_bedrock(full="--full" in sys.argv)
    print(json.dumps(result, ensure_ascii=False, indent=2))
