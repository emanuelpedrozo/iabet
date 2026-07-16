"""Normalização e mescla de métricas de time (API Futebol + API-Sports)."""


def _merge_dicts(base: dict, incoming: dict) -> dict:
    result = dict(base)
    for key, value in incoming.items():
        if key in {"source", "sources"}:
            continue
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def merge_metrics(base: dict | None, incoming: dict | None) -> dict:
    """Mescla JSON de providers sem apagar chaves do outro.

    Dicts aninhados entram em merge recursivo; escalares do *incoming* prevalecem.
    Aliases flat (EN) só são preenchidos se ainda faltarem.
    """
    result = _merge_dicts(dict(base or {}), dict(incoming or {}))
    sources: set[str] = set()
    for blob in (base, incoming):
        if not blob:
            continue
        if blob.get("source"):
            sources.add(str(blob["source"]))
        for item in blob.get("sources") or []:
            sources.add(str(item))
    result.pop("source", None)
    if sources:
        result["sources"] = sorted(sources)
    else:
        result.pop("sources", None)
    return backfill_flat(result)


def backfill_flat(metrics: dict) -> dict:
    """Preenche aliases EN só quando ainda não existem (não sobrescreve)."""
    out = dict(metrics)
    fin = out.get("finalizacao") or {}
    if out.get("total_shots") is None and fin.get("total") is not None:
        out["total_shots"] = fin["total"]
    if out.get("shots_on_goal") is None and fin.get("no_gol") is not None:
        out["shots_on_goal"] = fin["no_gol"]
    if out.get("corner_kicks") is None and out.get("escanteios") is not None:
        out["corner_kicks"] = out["escanteios"]
    if out.get("fouls") is None and out.get("faltas") is not None:
        out["fouls"] = out["faltas"]
    return out


def enrich_api_futebol_metrics(metrics: dict | None) -> dict:
    """Marca origem API Futebol; aliases flat entram no merge via backfill_flat."""
    raw = dict(metrics or {})
    raw["source"] = "api_futebol"
    return raw


def number(value):
    if isinstance(value, str):
        value = value.replace("%", "")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def team_metric(metrics: dict | None, match_metadata: dict | None, key: str, *, is_home: bool):
    """Lê uma métrica unificando chaves flat (API-Sports) e aninhadas (API Futebol)."""
    data = metrics or {}
    aliases = {
        "total_shots": (data.get("finalizacao") or {}).get("total"),
        "shots_on_goal": (data.get("finalizacao") or {}).get("no_gol"),
        "corner_kicks": data.get("escanteios"),
        "fouls": data.get("faltas"),
    }
    value = data.get(key)
    if value is None:
        value = aliases.get(key)
    if key in {"yellow_cards", "red_cards"} and value is None:
        side = "mandante" if is_home else "visitante"
        cards = ((match_metadata or {}).get("api_futebol") or {}).get("cards") or {}
        card_key = "amarelo" if key == "yellow_cards" else "vermelho"
        if card_key in cards:
            value = len(((cards.get(card_key) or {}).get(side)) or [])
    return number(value)
