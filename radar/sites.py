"""Background site previews: dossier -> writer brief -> local template -> automatic checks."""
import html
import re
import shutil
import threading
import traceback
from pathlib import Path
from string import Template
from urllib.parse import quote
from .domain import instagram_url, safe_url, text
from .writers import FONTS, PHOTO_USES, TEMPLATES, Cancelled, SiteError, offline_brief

TEMPLATE_DIR = Path(__file__).resolve().parent / "site_templates"
OBJECTIVES = {"contato": "Chamar para conversar", "visita": "Visitar o local", "marca": "Conhecer a marca"}
FONT_STACKS = {
    "moderna": "'Segoe UI', 'Helvetica Neue', Arial, system-ui, sans-serif",
    "classica": "Georgia, 'Times New Roman', serif",
    "elegante": "'Palatino Linotype', Palatino, 'Book Antiqua', Georgia, serif",
    "amigavel": "'Trebuchet MS', 'Segoe UI', Verdana, system-ui, sans-serif",
}
HEX = re.compile(r"#[0-9a-fA-F]{6}")
SITE_ID = re.compile(r"[0-9a-f]{32}")
FILE_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,80}")


def phone_links(phone):
    """tel: for any phone; WhatsApp only for Brazilian mobile numbers (DDD + 9 digits starting with 9)."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    digits = digits.lstrip("0")
    if len(digits) not in (10, 11):
        return (f"tel:{digits}" if digits else None), None
    mobile = len(digits) == 11 and digits[2] == "9"
    return f"tel:+55{digits}", (f"https://wa.me/55{digits}" if mobile else None)


def build_dossier(lead, campaign, options):
    city = (lead.get("city") or (campaign or {}).get("config", {}).get("city", "")).split(",")[0].strip()
    confirmed = lead.get("instagram_status") == "confirmed"
    return {
        "nome": lead["name"], "categoria": lead.get("category") or None,
        "nicho": (campaign or {}).get("config", {}).get("niche"), "cidade": city or None, "bairro": lead.get("borough") or None,
        "tem_endereco": bool(lead.get("address")), "tem_telefone": bool(lead.get("phone")),
        "nota": lead.get("rating"), "avaliacoes": lead.get("reviews"),
        "tem_site_atual": bool(lead.get("website")),
        "instagram_confirmado": lead.get("instagram") if confirmed else None,
        "descricao_publica_instagram": next((c.get("description") for c in lead.get("instagram_candidates") or [] if confirmed and c.get("url") == lead.get("instagram")), None),
        "objetivo_do_site": OBJECTIVES[options["objective"]],
        "instrucoes_do_operador": options.get("instructions") or None,
        "dados_ficticios": lead.get("source") == "demo",
    }


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return .2126 * r + .7152 * g + .0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + .05) / (lb + .05)


def clip(value, limit):
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[:limit - 1].rsplit(" ", 1)[0] + "…"


def normalize_brief(brief, dossier, photos=()):
    """Accept only known enums, bounded text and valid colors; fall back to the offline brief."""
    base = offline_brief(dossier)
    brief = brief if isinstance(brief, dict) else {}
    design, content = brief.get("design") or {}, brief.get("conteudo") or {}
    palette = {k: v if isinstance(v, str) and HEX.fullmatch(v) else base["design"]["paleta"][k] for k, v in {**base["design"]["paleta"], **(design.get("paleta") or {})}.items() if k in base["design"]["paleta"]}
    highlights = [{"titulo": clip(h.get("titulo"), 40), "texto": clip(h.get("texto"), 180)} for h in content.get("destaques") or [] if isinstance(h, dict) and h.get("titulo") and h.get("texto")][:4]
    photo_plan = [{"arquivo": p["arquivo"], "uso": p.get("uso"), "texto_alternativo": clip(p.get("texto_alternativo"), 160)} for p in brief.get("fotos") or []
                  if isinstance(p, dict) and p.get("arquivo") in photos and p.get("uso") in PHOTO_USES]
    pick = lambda value, allowed, default: value if value in allowed else default
    return {
        "analise": {k: clip((brief.get("analise") or {}).get(k), 200) for k in ("publico", "posicionamento", "tom")},
        "design": {"template": pick(design.get("template"), TEMPLATES, base["design"]["template"]), "paleta": palette,
                   "fonte_titulos": pick(design.get("fonte_titulos"), FONTS, base["design"]["fonte_titulos"]),
                   "fonte_texto": pick(design.get("fonte_texto"), FONTS, base["design"]["fonte_texto"])},
        "conteudo": {"titulo": clip(content.get("titulo") or base["conteudo"]["titulo"], 70),
                     "subtitulo": clip(content.get("subtitulo") or base["conteudo"]["subtitulo"], 160),
                     "sobre": clip(content.get("sobre") or base["conteudo"]["sobre"], 600),
                     "destaques": highlights if len(highlights) >= 2 else base["conteudo"]["destaques"],
                     "chamada": clip(content.get("chamada") or base["conteudo"]["chamada"], 120),
                     "meta_descricao": clip(content.get("meta_descricao") or base["conteudo"]["meta_descricao"], 155)},
        "fotos": photo_plan,
        "afirmacoes_a_confirmar": [clip(a, 200) for a in brief.get("afirmacoes_a_confirmar") or [] if isinstance(a, str) and a.strip()][:12],
    }


def fix_palette(palette):
    """Enforce WCAG AA for body text and pick readable button text. Returns (palette, button_text, notes)."""
    palette, notes = dict(palette), []
    if contrast(palette["texto"], palette["fundo"]) < 4.5:
        palette["texto"] = max(("#161616", "#fafafa"), key=lambda c: contrast(c, palette["fundo"]))
        notes.append("Cor do texto ajustada para contraste AA.")
    if contrast(palette["texto"], palette["suave"]) < 4.5:
        palette["suave"] = palette["fundo"]
        notes.append("Fundo alternativo ajustado para contraste AA.")
    button = max(("#ffffff", "#161616"), key=lambda c: contrast(c, palette["destaque"]))
    if contrast(button, palette["destaque"]) < 4.5:
        palette["destaque"] = "#1d4f43" if luminance(palette["fundo"]) > .5 else "#f0c75e"
        button = max(("#ffffff", "#161616"), key=lambda c: contrast(c, palette["destaque"]))
        notes.append("Cor dos botões ajustada para contraste AA.")
    return palette, button, notes


def render(lead, brief, options, out):
    """Write index.html and style.css. Every value is escaped; links are built only from validated data."""
    e = lambda value: html.escape(str(value), quote=True)
    design, content = brief["design"], brief["conteudo"]
    palette, button_text, notes = fix_palette(design["paleta"])
    tel, whatsapp = phone_links(lead.get("phone"))
    city = (lead.get("city") or "").split(",")[0].strip()
    maps = safe_url(lead.get("maps_url")) or ("https://www.google.com/maps/search/?api=1&query=" + quote(f"{lead['name']} {lead.get('address') or ''} {city}".strip()) if lead.get("address") else None)
    instagram = instagram_url(lead.get("instagram")) if lead.get("instagram_status") == "confirmed" else None
    actions = {"contato": [("WhatsApp", whatsapp), ("Ligar", tel), ("Como chegar", maps), ("Instagram", instagram)],
               "visita": [("Como chegar", maps), ("WhatsApp", whatsapp), ("Ligar", tel), ("Instagram", instagram)],
               "marca": [("Instagram", instagram), ("WhatsApp", whatsapp), ("Como chegar", maps), ("Ligar", tel)]}[options["objective"]]
    actions = [(label, url) for label, url in actions if url][:3]
    external = ' target="_blank" rel="noopener"'
    buttons = "".join(f'<a class="btn{" btn-primary" if i == 0 else ""}" href="{e(url)}"{"" if url.startswith("tel:") else external}>{e(label)}</a>' for i, (label, url) in enumerate(actions))
    photos = {p["uso"]: p for p in reversed(brief["fotos"]) if p["uso"] != "nao_usar"}
    cover = photos.get("capa")
    gallery = [p for p in brief["fotos"] if p["uso"] == "galeria"][:6]
    rating = ""
    if lead.get("rating") is not None and lead.get("reviews"):
        score = f"{lead['rating']:.1f}".replace(".", ",")
        rating = f'<section class="rating" aria-label="Avaliações"><p><strong>{e(score)}</strong> <span aria-hidden="true">★</span> no Google</p><p class="muted">{e(lead["reviews"])} avaliações públicas</p></section>'
    visit = [f'<p>{e(lead["address"])}</p>'] if lead.get("address") else []
    if lead.get("phone"):
        visit.append(f'<p><a href="{e(tel)}">{e(lead["phone"])}</a></p>' if tel else f'<p>{e(lead["phone"])}</p>')
    values = {
        "lang": "pt-BR", "title": e(f'{lead["name"]} · {content["subtitulo"]}'), "description": e(content["meta_descricao"]),
        "template": e(design["template"]), "name": e(lead["name"]), "headline": e(content["titulo"]),
        "kicker": e(" · ".join(x for x in (lead.get("borough"), city) if x) or lead.get("category") or ""), "subtitle": e(content["subtitulo"]),
        "buttons": buttons, "about": e(content["sobre"]),
        "cover": f'<img class="cover" src="assets/{e(cover["arquivo"])}" alt="{e(cover["texto_alternativo"])}">' if cover else "",
        "highlights": "".join(f'<article class="card"><h3>{e(h["titulo"])}</h3><p>{e(h["texto"])}</p></article>' for h in content["destaques"]),
        "gallery": ('<section class="gallery" aria-label="Fotos">' + "".join(f'<img src="assets/{e(p["arquivo"])}" alt="{e(p["texto_alternativo"])}" loading="lazy">' for p in gallery) + "</section>") if gallery else "",
        "rating": rating, "visit": ('<section class="visit" id="visite"><h2>Visite</h2>' + "".join(visit) + (f'<p><a href="{e(maps)}" target="_blank" rel="noopener">Abrir no mapa</a></p>' if maps else "") + "</section>") if visit else "",
        "cta": e(content["chamada"]),
        "instagram": f'<a href="{e(instagram)}" target="_blank" rel="noopener">Instagram</a>' if instagram else "",
    }
    page = Template((TEMPLATE_DIR / "page.html").read_text(encoding="utf-8")).substitute(values)
    css = Template((TEMPLATE_DIR / "style.css").read_text(encoding="utf-8")).substitute(
        bg=palette["fundo"], fg=palette["texto"], accent=palette["destaque"], soft=palette["suave"], on_accent=button_text,
        title_font=FONT_STACKS[design["fonte_titulos"]], body_font=FONT_STACKS[design["fonte_texto"]])
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "style.css").write_text(css, encoding="utf-8")
    return page, palette, notes


def run_checks(lead, page, palette, notes, brief):
    checks = [{"ok": not re.search(r"<script|\son\w+\s*=|javascript:", page, re.I), "text": "Sem scripts nem eventos no HTML."}]
    for key, label in (("name", "Nome"), ("address", "Endereço"), ("phone", "Telefone")):
        if lead.get(key):
            checks.append({"ok": html.escape(lead[key], quote=True) in page, "text": f"{label} igual ao cadastro."})
    checks.append({"ok": contrast(palette["texto"], palette["fundo"]) >= 4.5, "text": f"Contraste do texto {contrast(palette['texto'], palette['fundo']):.1f}:1 (mínimo 4,5)."})
    checks += [{"ok": True, "text": note} for note in notes]
    pending = len(brief["afirmacoes_a_confirmar"])
    checks.append({"ok": pending == 0, "text": f"{pending} afirmação(ões) para confirmar com o cliente." if pending else "Nenhuma afirmação pendente."})
    return checks


def validate_site_options(data, writers, default_engine):
    engine = data.get("engine") or default_engine
    if engine not in writers:
        raise ValueError("Motor de geração inválido.")
    if not writers[engine].available():
        raise ValueError(f"O motor “{writers[engine].label}” não está disponível neste computador.")
    objective = data.get("objective") or "contato"
    if objective not in OBJECTIVES:
        raise ValueError("Objetivo inválido.")
    return engine, {"objective": objective, "instructions": text(data.get("instructions"), 600)}


class SiteWorker:
    def __init__(self, store, writers, root):
        self.store, self.writers, self.root = store, writers, Path(root)
        self.stopped = threading.Event()

    def path(self, sid):
        if not SITE_ID.fullmatch(sid or ""):
            raise ValueError("Site inválido.")
        return self.root / sid

    def file(self, sid, name):
        """Resolve a preview file without allowing traversal outside the site directory."""
        if not SITE_ID.fullmatch(sid or ""):
            return None
        if name in ("", "index.html"):
            name = "index.html"
        parts = name.split("/")
        if len(parts) > 2 or (len(parts) == 2 and parts[0] != "assets") or not FILE_NAME.fullmatch(parts[-1]):
            return None
        target = (self.path(sid) / name).resolve()
        return target if target.is_file() and self.path(sid).resolve() in target.parents and target.name not in {"prompt.txt", "claude.out", "claude.err"} else None

    def remove_files(self, sid):
        shutil.rmtree(self.path(sid), ignore_errors=True)

    def start(self):
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while not self.stopped.is_set():
            sid = self.store.queued_site()
            if sid:
                self.run(sid)
            else:
                self.stopped.wait(.5)

    def check(self, sid):
        site = self.store.site(sid)
        if not site or site["cancel_requested"] or self.stopped.is_set():
            raise Cancelled()

    def run(self, sid):
        site = self.store.site(sid)
        if not site:
            return
        lead = self.store.lead(site["lead_id"])
        campaign = self.store.campaign(site["campaign_id"]) if site["campaign_id"] else None
        writer = self.writers[site["engine"]]
        out = self.path(sid)
        try:
            self.check(sid)
            self.store.update_site(sid, state="running", progress=10, message="Preparando os dados da empresa…")
            out.mkdir(parents=True, exist_ok=True)
            dossier = build_dossier(lead, campaign, site["options"])
            photos = []
            self.check(sid)
            self.store.update_site(sid, progress=30, message="Escrevendo textos com Claude…" if writer.name != "offline" else "Montando textos padrão…")
            raw, usage = writer.write(dossier, photos, out, lambda: bool((self.store.site(sid) or {}).get("cancel_requested")) or self.stopped.is_set())
            self.check(sid)
            self.store.update_site(sid, progress=80, message="Montando a página…", usage=usage)
            brief = normalize_brief(raw, dossier, photos)
            page, palette, notes = render(lead, brief, site["options"], out)
            checks = run_checks(lead, page, palette, notes, brief)
            for scratch in ("prompt.txt", "claude.out", "claude.err"):
                (out / scratch).unlink(missing_ok=True)
            failed = [c for c in checks[:-1] if not c["ok"]]
            self.store.update_site(sid, state="partial" if failed else "completed", progress=100, brief=brief, checks=checks,
                                   message="Prévia pronta, com verificações a revisar." if failed else "Prévia pronta.")
        except Cancelled:
            self.store.update_site(sid, state="cancelled", message="Geração cancelada.")
        except (SiteError, ValueError) as exc:
            self.store.update_site(sid, state="failed", message=str(exc))
        except Exception:
            traceback.print_exc()
            self.store.update_site(sid, state="failed", message="Falha interna ao gerar o site. Consulte o terminal.")
