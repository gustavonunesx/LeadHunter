"""Pure validation, identity, and explainable scoring rules."""
import hashlib
import math
import re
import statistics
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

SERVICES = {"google": "Presença no Google", "website": "Criação de site", "marketing": "Marketing digital"}
STAGES = {"new", "reviewing", "contacted", "interested", "discarded", "do_not_contact"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalized(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return None
        return value.strip()
    except ValueError:
        return None


def instagram_url(value):
    url = safe_url(value)
    if not url:
        return None
    p = urlparse(url)
    if p.hostname not in ("instagram.com", "www.instagram.com"):
        return None
    parts = p.path.strip("/").split("/")
    if len(parts) != 1 or parts[0].lower() in {"p", "reel", "reels", "explore", "stories", "accounts", "direct"}:
        return None
    if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", parts[0]):
        return None
    return f"https://www.instagram.com/{parts[0]}/"


def number(value, minimum=0, maximum=10000000, integer=False):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Número inválido.")
    n = float(value)
    if not math.isfinite(n) or not minimum <= n <= maximum or (integer and n != int(n)):
        raise ValueError("Número fora do intervalo permitido.")
    return int(n) if integer else n


def text(value, limit=200, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError("Campo de texto inválido.")
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise ValueError(f"Preencha o texto com até {limit} caracteres.")
    return value


def validate_campaign(data):
    if not isinstance(data, dict):
        raise ValueError("Campanha inválida.")
    niche = text(data.get("niche"), 100, True)
    city = text(data.get("city"), 100, True)
    source = data.get("source", "demo")
    if source not in {"demo", "live", "import"}:
        raise ValueError("Origem inválida.")
    service = data.get("service", "google")
    if service not in SERVICES:
        raise ValueError("Serviço inválido.")
    limit = number(data.get("limit", 10), 1, 50, True)
    if limit is None:
        raise ValueError("Informe a quantidade de empresas.")
    keywords = data.get("keywords") or [f"{niche} {city}"]
    if isinstance(keywords, str):
        keywords = keywords.splitlines()
    if not isinstance(keywords, list):
        raise ValueError("Termos inválidos.")
    keywords = list(dict.fromkeys(text(k, 180, True) for k in keywords if k))
    if not 1 <= len(keywords) <= 3:
        raise ValueError("Use de um a três termos de busca.")
    coordinates = data.get("coordinates") or []
    if isinstance(coordinates, str):
        coordinates = [s.strip() for s in coordinates.splitlines() if s.strip()]
    if not isinstance(coordinates, list) or len(coordinates) > 3:
        raise ValueError("Use até três pontos de busca.")
    points = []
    for point in coordinates:
        parts = text(point, 60, True).replace(" ", "").split(",")
        if len(parts) != 3:
            raise ValueError("Ponto deve ser latitude,longitude,zoom (ex.: -22.0174,-47.8909,14z).")
        lat = number(parts[0], -90, 90)
        lon = number(parts[1], -180, 180)
        zoom = number(parts[2].removesuffix("z"), 3, 21, True)
        points.append(f"{lat},{lon},{zoom}z")
    return {"niche": niche, "city": city, "source": source, "service": service, "limit": limit,
            "keywords": keywords, "coordinates": points, "enrich": data.get("enrich", True) is True,
            "use_jev": data.get("use_jev", True) is True}


def identity(lead, source):
    group = "demo" if source == "demo" else "real"
    place = lead.get("place_id")
    key = f"place:{place}" if place else "address:" + "|".join(normalized(lead.get(k)) for k in ("name", "address", "city"))
    return hashlib.sha256(f"{group}:{key}".encode()).hexdigest()[:32]


def local_fit(lead, niche):
    stop = {"de", "do", "da", "loja", "lojas", "em", "e", "para", "a", "o", "empresa", "servicos"}
    tokens = set(normalized(niche).split()) - stop
    haystack = normalized(" ".join(str(lead.get(k) or "") for k in ("name", "category")))
    if tokens and all(t in haystack for t in tokens):
        return {"choice": "match", "confidence": None, "method": "rules", "model": None}
    return {"choice": "unknown", "confidence": None, "method": "rules", "model": None}


def score_lead(lead, observations, fit, service, peer_median=None):
    fit = fit or {"choice": "unknown", "method": "rules"}
    matched = fit.get("choice") == "match" and (fit.get("method") == "rules" or (fit.get("confidence") or 0) >= .8)
    excluded = fit.get("choice") == "no_match" and (fit.get("confidence") or 0) >= .8
    reasons = []
    score = 0

    def add(points, reason):
        nonlocal score
        score += points
        reasons.append({"points": points, "text": reason})

    ranks = [o["rank"] for o in observations if isinstance(o.get("rank"), (int, float)) and o["rank"] > 0]
    median = statistics.median(ranks) if ranks else None
    if matched:
        add(25, "Categoria compatível com o nicho solicitado.")
    if lead.get("phone") or lead.get("instagram_status") == "confirmed":
        add(15, "Há um contato comercial informado ou Instagram confirmado.")
    if service == "website":
        if lead.get("website_checked") and not lead.get("website"):
            add(35, "A fonte não informou site; verificar se há oportunidade de criação.")
    elif median is not None:
        pts = 35 if median > 10 else 20 if median > 3 else 0
        if pts:
            add(pts, f"Posição mediana {median:g} nas buscas observadas; avaliar descoberta local.")
    reviews = lead.get("reviews")
    if peer_median is not None and reviews is not None and reviews < peer_median:
        add(15, f"{reviews} avaliações, abaixo da mediana {peer_median:g} da amostra comparável.")
    if lead.get("rating") is not None and lead["rating"] >= 4 and reviews is not None and reviews >= 5:
        add(10, "Nota de pelo menos 4 com cinco ou mais avaliações.")
    visibility = "not_measured" if median is None else "top" if median <= 3 else "middle" if median <= 10 else "low"
    priority = "excluded" if excluded else "review" if not matched else "high" if score >= 70 else "medium" if score >= 40 else "low"
    completeness = round(100 * sum(lead.get(k) is not None and lead.get(k) != "" for k in ("name", "category", "address", "phone", "website", "rating", "reviews", "instagram")) / 8)
    return {"score": score, "priority": priority, "reasons": reasons, "rank_median": median,
            "rank_samples": len(ranks), "visibility": visibility, "completeness": completeness,
            "fit": fit, "version": "v1", "peer_median": peer_median}
