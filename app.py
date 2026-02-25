import requests
from bs4 import BeautifulSoup
import tldextract
import re
import pandas as pd
from urllib.parse import urljoin, urlparse
from io import BytesIO

import streamlit as st

# ============================================================
# 0. CSS GLOBAL (THEME FUTURISTE + GREEN)
# ============================================================

def inject_global_css():
    css = """
    /* Background global en dégradé sombre */
    .stApp {
        background: radial-gradient(circle at top left, #0f172a 0, #020617 40%, #020617 100%);
        color: #e5e7eb;
    }

    /* Si tu veux utiliser une image de planète en fond :
    .stApp {
        background-image: url('https://raw.githubusercontent.com/TobiB86/analyse-carbone-site-3/refs/heads/main/ChatGPT%20Image%2025%20f%C3%A9vr.%202026%2C%2015_26_20.png');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
        color: #e5e7eb;
    }
    */

    /* Titres */
    h1 {
        font-weight: 700 !important;
        letter-spacing: 0.03em;
    }

    h2, h3, h4 {
        color: #e5e7eb !important;
    }

    /* Cartes glassmorphism */
    .glass-card {
        background: rgba(15, 23, 42, 0.9);
        border-radius: 18px;
        padding: 18px 20px;
        border: 1px solid rgba(148, 163, 184, 0.3);
        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
        backdrop-filter: blur(12px);
    }

    /* Formulaire */
    .stForm {
        background: rgba(15, 23, 42, 0.9);
        border-radius: 16px;
        padding: 20px 22px;
        border: 1px solid rgba(148, 163, 184, 0.25);
    }

    /* Inputs */
    .stTextInput > div > div > input,
    .stNumberInput input {
        background: rgba(15,23,42,0.9) !important;
        border-radius: 999px !important;
        border: 1px solid rgba(148,163,184,0.5) !important;
        color: #e5e7eb !important;
    }

    /* Boutons */
    .stButton>button {
        background: linear-gradient(135deg, #22c55e, #2dd4bf);
        color: #020617;
        border-radius: 999px;
        border: none;
        padding: 0.5rem 1.4rem;
        font-weight: 600;
        box-shadow: 0 12px 30px rgba(34, 197, 94, 0.35);
    }
    .stButton>button:hover {
        filter: brightness(1.07);
        box-shadow: 0 16px 40px rgba(34, 197, 94, 0.4);
    }

    /* Tableau */
    .stDataFrame {
        border-radius: 16px;
        overflow: hidden;
        background: rgba(15, 23, 42, 0.95) !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.4rem 1rem;
        border-radius: 999px;
        background-color: rgba(15,23,42,0.6);
        color: #9ca3af;
        border: 1px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(34,197,94,0.15), rgba(45,212,191,0.15));
        border-color: rgba(34,197,94,0.7);
        color: #e5e7eb !important;
    }

    /* Metrics */
    .stMetric {
        background: rgba(15, 23, 42, 0.95);
        border-radius: 16px;
        padding: 0.5rem 0.75rem;
        border: 1px solid rgba(148, 163, 184, 0.35);
    }
    """
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ============================================================
# 1. CONFIGURATION & PARAMÈTRES GLOBAUX
# ============================================================

RSE_KEYWORDS = [
    "rse", "responsabilité sociétale", "responsabilité sociale",
    "responsabilite sociétale", "responsabilite sociale",
    "développement durable", "developpement durable", "durable",
    "environnement", "environnemental", "impact environnemental",
    "transition écologique", "transition ecologique", "transition énergétique",
    "transition energetique",
    "esg", "csr", "sustainability", "sustainable", "sustainable development",
]

CARBON_KEYWORDS = [
    "bilan carbone", "empreinte carbone", "émissions de co2",
    "emissions de co2", "émissions carbone", "emissions carbone",
    "gaz à effet de serre", "gaz a effet de serre",
    "co2", "réduction des émissions", "reduction des emissions",
    "neutralité carbone", "neutralite carbone",
    "décarbonation", "decarbonation",
    "scope 1", "scope 2", "scope 3",
]

GREEN_IT_KEYWORDS = [
    "numérique responsable", "numerique responsable",
    "éco-conception", "eco-conception", "eco conception",
    "site éco-conçu", "site eco-concu",
    "green it",
    "hébergement vert", "hebergement vert",
    "hébergement écologique", "hebergement ecologique",
    "data center vert",
    "sobriété numérique", "sobriete numerique",
]

MAX_PAGES = 20
REQUEST_TIMEOUT = 10
USER_AGENT = "CarbonPOCBot/0.1 (+for research & prospecting)"

# Hypothèses pour le modèle carbone (POC)
DEFAULT_WEIGHT_MULTIPLIER = 3.0              # pour approximer HTML + CSS + JS + images
DEFAULT_ENERGY_PER_GB_KWH = 0.5              # kWh consommés par Go de données
DEFAULT_CARBON_INTENSITY_G_PER_KWH = 300.0   # gCO2/kWh (mix électrique moyen)

# Repère pédagogique
WORLD_AVG_GCO2_PER_PAGE = 0.8  # ≈ moyenne mondiale souvent citée


# ============================================================
# 2. UTILITAIRES POUR LE CRAWL
# ============================================================

def normalize_base_url(url: str) -> str:
    """Normalise l'URL (ajout https si besoin, suppression du path)."""
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return base


def is_internal_link(link: str, base_domain: str) -> bool:
    """Vérifie si un lien appartient au même domaine."""
    if not link:
        return False
    parsed = urlparse(link)
    if not parsed.netloc:
        # lien relatif -> interne
        return True
    ext = tldextract.extract(parsed.netloc)
    domain = f"{ext.domain}.{ext.suffix}"
    return domain == base_domain


def fetch_page(url: str):
    """Récupère le HTML d'une page, ou None en cas de problème."""
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            return resp.text
    except Exception:
        pass
    return None


def extract_text(html: str) -> str:
    """Extrait le texte brut depuis du HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_candidate_links(base_url: str, html: str, max_links: int = 30):
    """
    Récupère des liens internes en donnant la priorité aux liens
    portant des indices RSE / climat dans l'URL ou l'ancre.
    """
    soup = BeautifulSoup(html, "html.parser")
    ext = tldextract.extract(base_url)
    base_domain = f"{ext.domain}.{ext.suffix}"

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        if not is_internal_link(full_url, base_domain):
            continue

        text = (a.get_text() or "").lower()
        url_lower = full_url.lower()

        score = 0
        for kw in [
            "rse", "responsabilite", "responsabilité",
            "developpement-durable", "developpement durable",
            "durable", "environnement", "carbone", "co2",
            "csr", "sustainab"
        ]:
            if kw in url_lower or kw in text:
                score += 5

        links.append((full_url, score))

    links = sorted(links, key=lambda x: x[1], reverse=True)
    seen = set()
    ranked_links = []
    for u, sc in links:
        if u not in seen:
            ranked_links.append(u)
            seen.add(u)
        if len(ranked_links) >= max_links:
            break

    return ranked_links


# ============================================================
# 3. HÉBERGEUR & GREEN WEB FOUNDATION
# ============================================================

def get_hosting_info(domain: str) -> dict:
    """
    Interroge l'API Green Web Foundation pour savoir si le domaine
    est hébergé chez un fournisseur 'green'.
    """
    try:
        resp = requests.get(
            f"https://api.thegreenwebfoundation.org/api/v3/greencheck/{domain}",
            timeout=5,
        )
        if resp.status_code != 200:
            return {
                "hosting_green": None,
                "hosting_provider": None,
                "hosting_provider_website": None,
            }

        data = resp.json()
        return {
            "hosting_green": bool(data.get("green")),
            "hosting_provider": data.get("hosted_by"),
            "hosting_provider_website": data.get("hosted_by_website"),
        }
    except Exception:
        return {
            "hosting_green": None,
            "hosting_provider": None,
            "hosting_provider_website": None,
        }


# ============================================================
# 4. ANALYSE TEXTE RSE / CARBONE / GREEN IT
# ============================================================

def count_keywords(text: str, keywords) -> int:
    """Compte grossièrement les occurrences de la liste de mots-clés dans le texte."""
    text_lower = text.lower()
    count = 0
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in text_lower:
            count += text_lower.count(kw_lower)
    return count


def analyze_text(text: str) -> dict:
    """Retourne des scores RSE / carbone / numérique responsable sur 0–100."""
    rse_hits = count_keywords(text, RSE_KEYWORDS)
    carbon_hits = count_keywords(text, CARBON_KEYWORDS)
    green_it_hits = count_keywords(text, GREEN_IT_KEYWORDS)

    def score_from_hits(hits: int, max_hits: int = 20) -> int:
        if hits <= 0:
            return 0
        if hits >= max_hits:
            return 100
        return int(hits / max_hits * 100)

    scores = {
        "rse_hits": rse_hits,
        "carbon_hits": carbon_hits,
        "green_it_hits": green_it_hits,
        "rse_score": score_from_hits(rse_hits),
        "carbon_score": score_from_hits(carbon_hits),
        "green_it_score": score_from_hits(green_it_hits),
    }
    return scores


# ============================================================
# 5. ANALYSE STRUCTURELLE D'UNE PAGE
# ============================================================

def analyze_page(html: str, url: str) -> dict:
    """
    Analyse une page :
    - structure (titres, images, scripts, CSS, fonts)
    - texte + scores RSE / climat / green IT
    """
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""

    headings_h1 = len(soup.find_all("h1"))
    headings_h2 = len(soup.find_all("h2"))
    headings_h3 = len(soup.find_all("h3"))

    images = soup.find_all("img")
    scripts = soup.find_all("script")
    stylesheets = [
        l for l in soup.find_all("link", rel=True)
        if "stylesheet" in [r.lower() for r in l.get("rel", [])]
    ]

    num_images = len(images)
    num_scripts = len(scripts)
    num_stylesheets = len(stylesheets)

    html_bytes = len(html.encode("utf-8"))
    html_kb = round(html_bytes / 1024, 1)

    font_families = set()
    for tag in soup.find_all(style=True):
        style = tag["style"].lower()
        match = re.search(r"font-family\\s*:\\s*([^;]+)", style)
        if match:
            font_families.add(match.group(1).strip())

    font_resources = []
    for link in soup.find_all("link", href=True):
        href = link["href"].lower()
        if "fonts.googleapis.com" in href or "font" in href:
            font_resources.append(link["href"])

    num_inline_fonts = len(font_families)
    font_resources = list(set(font_resources))

    text = extract_text(html)
    text_scores = analyze_text(text)

    page_info = {
        "url": url,
        "title": title,
        "html_kb": html_kb,
        "num_images": num_images,
        "num_scripts": num_scripts,
        "num_stylesheets": num_stylesheets,
        "headings_h1": headings_h1,
        "headings_h2": headings_h2,
        "headings_h3": headings_h3,
        "num_inline_fonts": num_inline_fonts,
        "font_resources": font_resources,
        "text": text,
        **text_scores,
    }
    return page_info


# ============================================================
# 6. ANALYSE COMPLÈTE D'UN SITE
# ============================================================

def analyze_website(url: str, max_pages: int = MAX_PAGES) -> dict:
    """
    Crawl léger + agrégation des scores RSE/climat/green IT
    + stats structurelles + info hébergeur.
    """
    base_url = normalize_base_url(url)
    html_home = fetch_page(base_url)

    ext = tldextract.extract(base_url)
    domain = f"{ext.domain}.{ext.suffix}"

    hosting_info = get_hosting_info(domain)

    if not html_home:
        return {
            "domain": domain,
            "url": base_url,
            "error": "Impossible de récupérer la page d'accueil",
            "pages_details": [],
            "hosting_green": hosting_info["hosting_green"],
            "hosting_provider": hosting_info["hosting_provider"],
            "hosting_provider_website": hosting_info["hosting_provider_website"],
        }

    home_info = analyze_page(html_home, base_url)
    candidate_links = find_candidate_links(base_url, html_home, max_links=50)

    visited = set([base_url])
    pages_data = [home_info]

    for link in candidate_links:
        if len(pages_data) >= max_pages:
            break
        if link in visited:
            continue
        visited.add(link)

        html = fetch_page(link)
        if not html:
            continue

        page_info = analyze_page(html, link)
        pages_data.append(page_info)

    total_rse_hits = sum(p["rse_hits"] for p in pages_data)
    total_carbon_hits = sum(p["carbon_hits"] for p in pages_data)
    total_green_it_hits = sum(p["green_it_hits"] for p in pages_data)

    has_bilan_carbone_explicit = any(
        "bilan carbone" in p["text"].lower() for p in pages_data
    )
    has_rse_content = total_rse_hits > 0
    has_carbon_mentions = total_carbon_hits > 0
    has_green_it = total_green_it_hits > 0

    global_rse_score = max(p["rse_score"] for p in pages_data)
    global_carbon_score = max(p["carbon_score"] for p in pages_data)
    global_green_it_score = max(p["green_it_score"] for p in pages_data)

    pages_scanned = len(pages_data)
    total_html_kb = sum(p["html_kb"] for p in pages_data)
    avg_html_kb = round(total_html_kb / pages_scanned, 1) if pages_scanned > 0 else 0.0

    total_images = sum(p["num_images"] for p in pages_data)
    total_scripts = sum(p["num_scripts"] for p in pages_data)
    total_stylesheets = sum(p["num_stylesheets"] for p in pages_data)

    total_h1 = sum(p["headings_h1"] for p in pages_data)
    total_h2 = sum(p["headings_h2"] for p in pages_data)
    total_h3 = sum(p["headings_h3"] for p in pages_data)

    summary_parts = []
    if has_rse_content:
        summary_parts.append("L'entreprise communique sur la RSE / l'environnement.")
    else:
        summary_parts.append("Aucun contenu RSE clair trouvé sur les pages analysées.")

    if has_carbon_mentions:
        if has_bilan_carbone_explicit:
            summary_parts.append("Mention explicite d'un bilan carbone.")
        else:
            summary_parts.append(
                "Mention d'émissions carbone / CO₂, sans bilan carbone clairement identifié."
            )
    else:
        summary_parts.append(
            "Aucune mention significative de carbone / CO₂ trouvée."
        )

    if has_green_it:
        summary_parts.append(
            "Des éléments de numérique responsable / green IT sont mentionnés."
        )
    else:
        summary_parts.append(
            "Pas de mention de numérique responsable / site éco-conçu détectée."
        )

    summary_parts.append(
        f"Crawl de {pages_scanned} pages pour {total_html_kb:.1f} Ko de HTML "
        f"(moyenne {avg_html_kb:.1f} Ko/page)."
    )
    summary = " ".join(summary_parts)

    result = {
        "domain": domain,
        "url": base_url,
        "pages_scanned": pages_scanned,
        "has_rse_content": has_rse_content,
        "has_carbon_mentions": has_carbon_mentions,
        "has_bilan_carbone_explicit": has_bilan_carbone_explicit,
        "has_green_it": has_green_it,
        "global_rse_score": global_rse_score,
        "global_carbon_score": global_carbon_score,
        "global_green_it_score": global_green_it_score,
        "total_rse_hits": total_rse_hits,
        "total_carbon_hits": total_carbon_hits,
        "total_green_it_hits": total_green_it_hits,
        "total_html_kb": total_html_kb,
        "avg_html_kb": avg_html_kb,
        "total_images": total_images,
        "total_scripts": total_scripts,
        "total_stylesheets": total_stylesheets,
        "total_h1": total_h1,
        "total_h2": total_h2,
        "total_h3": total_h3,
        "num_font_resources": len(
            set(fr for p in pages_data for fr in p.get("font_resources", []))
        ),
        "summary": summary,
        "pages_details": pages_data,
        "hosting_green": hosting_info["hosting_green"],
        "hosting_provider": hosting_info["hosting_provider"],
        "hosting_provider_website": hosting_info["hosting_provider_website"],
    }

    return result


# ============================================================
# 7. ESTIMATION CARBONE (POC)
# ============================================================

def estimate_site_carbon(
    site_result: dict,
    monthly_page_views: int,
    weight_multiplier: float = DEFAULT_WEIGHT_MULTIPLIER,
    energy_per_gb_kwh: float = DEFAULT_ENERGY_PER_GB_KWH,
    carbon_intensity_g_per_kwh: float = DEFAULT_CARBON_INTENSITY_G_PER_KWH,
) -> dict:
    """
    Estime l'empreinte carbone :
    - gCO₂/page vue
    - kgCO₂/mois
    - kgCO₂/an

    en ajustant si l'hébergeur est 'vert'.
    """
    avg_html_kb = site_result.get("avg_html_kb")
    if avg_html_kb is None:
        raise ValueError("Le résultat du site ne contient pas 'avg_html_kb'.")

    avg_kb_per_page = avg_html_kb * weight_multiplier
    gb_per_view = avg_kb_per_page / (1024 * 1024)

    hosting_green = site_result.get("hosting_green", None)
    if hosting_green is True:
        # hypothèse : 70 % de l'énergie est renouvelable
        green_factor = 0.7
    else:
        green_factor = 0.0

    effective_carbon_intensity = carbon_intensity_g_per_kwh * (1 - green_factor)

    kwh_per_view = gb_per_view * energy_per_gb_kwh
    gco2_per_view = kwh_per_view * effective_carbon_intensity

    monthly_gco2 = gco2_per_view * monthly_page_views
    monthly_kgco2 = monthly_gco2 / 1000
    yearly_kgco2 = monthly_kgco2 * 12

    return {
        "avg_kb_per_page": round(avg_kb_per_page, 1),
        "gco2_per_page_view": round(gco2_per_view, 4),
        "monthly_kgco2": round(monthly_kgco2, 2),
        "yearly_kgco2": round(yearly_kgco2, 2),
        "assumptions": {
            "monthly_page_views": monthly_page_views,
            "weight_multiplier": weight_multiplier,
            "energy_per_gb_kwh": energy_per_gb_kwh,
            "carbon_intensity_g_per_kwh": carbon_intensity_g_per_kwh,
            "hosting_green": hosting_green,
            "green_factor": green_factor,
        },
    }


# ============================================================
# 8. INTERFACE STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Analyse carbone d'un site web",
    page_icon="🌱",
    layout="centered",
)

inject_global_css()

st.title("🌱🔭 Analyse carbone d'un site web")

st.caption(
    "Outil d'estimation indicatif basé sur des modèles publics (Sustainable Web Design Model). "
    "Les résultats ne constituent pas un bilan carbone officiel et ne peuvent pas être utilisés "
    "comme preuve dans un cadre réglementaire ou de reporting extra-financier."
)

tab1, tab2 = st.tabs(["Analyse d'un site", "Analyse par fichier"])


# ------------------------------------------------------------
# Onglet 1 : analyse unitaire
# ------------------------------------------------------------
with tab1:
    st.subheader("Analyse unitaire")

    with st.form("analyse_form"):
        url_input = st.text_input(
            "URL du site",
            placeholder="https://www.exemple.com",
        )
        monthly_views = st.number_input(
            "Pages vues mensuelles estimées",
            min_value=100,
            max_value=1_000_000,
            value=10_000,
            step=1000,
        )
        submitted = st.form_submit_button("Analyser le site")

    if submitted:
        if not url_input.strip():
            st.error("Merci d'indiquer une URL valide.")
        else:
            with st.spinner("Analyse en cours..."):
                site_result = analyze_website(url_input)

            if "error" in site_result and site_result["pages_details"] == []:
                st.error(site_result["error"])
            else:
                carbon = estimate_site_carbon(
                    site_result, monthly_page_views=monthly_views
                )

                # Résumé global + scores
                st.subheader("Résumé global")
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                st.write(site_result["summary"])

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Score RSE", site_result["global_rse_score"])
                with col2:
                    st.metric("Score climat / CO₂", site_result["global_carbon_score"])
                with col3:
                    st.metric(
                        "Score numérique responsable",
                        site_result["global_green_it_score"],
                    )
                st.markdown("</div>", unsafe_allow_html=True)

                # Hébergeur
                st.markdown("---")
                st.subheader("Hébergement")
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                if site_result.get("hosting_provider"):
                    txt = f"Hébergeur détecté : **{site_result['hosting_provider']}**"
                    if site_result.get("hosting_green") is True:
                        txt += " (référencé comme **hébergeur vert** par The Green Web Foundation)."
                    elif site_result.get("hosting_green") is False:
                        txt += " (pas référencé comme hébergeur vert dans la base The Green Web Foundation)."
                    else:
                        txt += " (information incomplète dans la base The Green Web Foundation)."
                    st.write(txt)
                    if site_result.get("hosting_provider_website"):
                        st.write(
                            f"Site de l'hébergeur : {site_result['hosting_provider_website']}"
                        )
                else:
                    st.write(
                        "Impossible d’identifier l’hébergeur via The Green Web Foundation."
                    )
                st.markdown("</div>", unsafe_allow_html=True)

                # Structure & ressources
                st.markdown("---")
                st.subheader("Structure & ressources (échantillon)")
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)

                col4, col5, col6 = st.columns(3)
                with col4:
                    st.metric("Pages analysées", site_result["pages_scanned"])
                    st.metric(
                        "Total HTML (Ko)", round(site_result["total_html_kb"], 1)
                    )
                with col5:
                    st.metric("Taille moyenne page (Ko)", site_result["avg_html_kb"])
                    st.metric("Images totales", site_result["total_images"])
                with col6:
                    st.metric("Scripts JS", site_result["total_scripts"])
                    st.metric("Feuilles de style", site_result["total_stylesheets"])

                st.markdown("</div>", unsafe_allow_html=True)

                # Estimation carbone
                st.markdown("---")
                st.subheader("Estimation carbone (POC)")
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)

                st.write(
                    f"Sur la base d'un poids moyen estimé de **{carbon['avg_kb_per_page']} Ko/page** "
                    f"(HTML + CSS + JS + images) et d'environ **{monthly_views} pages vues / mois** :"
                )

                col7, col8, col9 = st.columns(3)
                with col7:
                    st.metric("gCO₂ par page vue", carbon["gco2_per_page_view"])
                with col8:
                    st.metric("kgCO₂ par mois", carbon["monthly_kgco2"])
                with col9:
                    st.metric("kgCO₂ par an", carbon["yearly_kgco2"])

                st.markdown(
                    f"""
                    **Repères :**  
                    - 🌍 Moyenne mondiale souvent citée ≈ **{WORLD_AVG_GCO2_PER_PAGE} gCO₂** / page vue  
                    - ✅ Zone *sobre* : viser **< 0,3–0,5 gCO₂** / page vue  
                    """
                )

                st.caption(
                    "⚠️ Estimation basée sur des hypothèses simplifiées "
                    "(poids moyen de page, mix électrique, trafic, hébergeur). "
                    "Elle donne un ordre de grandeur pour comparer des sites "
                    "et initier une démarche de réduction, mais ne remplace pas "
                    "un bilan carbone complet (Bilan Carbone®, GHG Protocol, etc.)."
                )
                st.markdown("</div>", unsafe_allow_html=True)

                # Détails par page
                st.markdown("---")
                st.subheader("Détails des pages analysées")
                pages_df = pd.DataFrame(site_result["pages_details"])
                if not pages_df.empty:
                    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                    st.dataframe(
                        pages_df[
                            [
                                "url",
                                "html_kb",
                                "num_images",
                                "num_scripts",
                                "num_stylesheets",
                                "headings_h1",
                                "headings_h2",
                                "headings_h3",
                                "rse_score",
                                "carbon_score",
                                "green_it_score",
                            ]
                        ]
                    )

                    csv_export = pages_df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📥 Télécharger les détails des pages (CSV)",
                        data=csv_export,
                        file_name=f"analyse_pages_{site_result['domain']}.csv",
                        mime="text/csv",
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

    # petit badge bas de page
    st.markdown(
        """
        <div style='margin-top: 2rem; text-align: center; opacity: 0.7; font-size: 0.8rem;'>
            Prototype d'outil d'estimation d'empreinte carbone numérique – indicatif, non opposable.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# Onglet 2 : analyse batch (fichier CSV / Excel)
# ------------------------------------------------------------
with tab2:
    st.subheader("Analyse de plusieurs sites (batch)")

    uploaded_file = st.file_uploader(
        "Importer un fichier d'URL (.csv ou .xlsx)",
        type=["csv", "xlsx"],
    )

    default_batch_views = st.number_input(
        "Pages vues mensuelles estimées par site (hypothèse moyenne)",
        min_value=100,
        max_value=1_000_000,
        value=10_000,
        step=1000,
    )

    if uploaded_file is not None:
        try:
            if uploaded_file.name.lower().endswith(".csv"):
                df_in = pd.read_csv(uploaded_file)
            else:
                df_in = pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Impossible de lire le fichier : {e}")
            df_in = None

        if df_in is not None:
            url_col = None
            for candidate in ["url", "URL", "site", "Site"]:
                if candidate in df_in.columns:
                    url_col = candidate
                    break

            if url_col is None:
                st.error(
                    "Aucune colonne 'url', 'URL', 'site' ou 'Site' trouvée dans le fichier."
                )
            else:
                urls = df_in[url_col].dropna().astype(str).tolist()
                st.write(f"{len(urls)} URL détectées. Lancement de l'analyse...")

                results = []
                progress = st.progress(0)
                status = st.empty()

                for i, u in enumerate(urls):
                    status.text(f"Analyse de {u} ({i+1}/{len(urls)})")
                    try:
                        site_res = analyze_website(u)
                        if "error" in site_res and site_res["pages_details"] == []:
                            row = {
                                "url": u,
                                "error": site_res["error"],
                            }
                        else:
                            carbon_res = estimate_site_carbon(
                                site_res,
                                monthly_page_views=default_batch_views,
                            )
                            row = {
                                "url": site_res["url"],
                                "domain": site_res["domain"],
                                "pages_scanned": site_res["pages_scanned"],
                                "avg_html_kb": site_res["avg_html_kb"],
                                "total_images": site_res["total_images"],
                                "global_rse_score": site_res["global_rse_score"],
                                "global_carbon_score": site_res["global_carbon_score"],
                                "global_green_it_score": site_res[
                                    "global_green_it_score"
                                ],
                                "hosting_green": site_res.get("hosting_green"),
                                "hosting_provider": site_res.get("hosting_provider"),
                                "gco2_per_page_view": carbon_res[
                                    "gco2_per_page_view"
                                ],
                                "yearly_kgco2": carbon_res["yearly_kgco2"],
                            }
                        results.append(row)
                    except Exception as e:
                        results.append({"url": u, "error": str(e)})

                    progress.progress((i + 1) / len(urls))

                status.empty()
                progress.empty()

                if results:
                    df_out = pd.DataFrame(results)
                    st.success("Analyse batch terminée.")
                    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                    st.dataframe(df_out)

                    # Export CSV
                    csv_data = df_out.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "📥 Télécharger les résultats (CSV)",
                        data=csv_data,
                        file_name="analyse_batch_sites.csv",
                        mime="text/csv",
                    )

                    # Export Excel
                    buffer = BytesIO()
                    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                        df_out.to_excel(writer, index=False, sheet_name="Résultats")
                    buffer.seek(0)
                    st.download_button(
                        "📥 Télécharger les résultats (Excel)",
                        data=buffer,
                        file_name="analyse_batch_sites.xlsx",
                        mime=(
                            "application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet"
                        ),
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

                st.caption(
                    "Pour les analyses batch, seuls des résultats chiffrés sont affichés. "
                    "Aucun commentaire détaillé par site n'est généré pour éviter un rapport trop volumineux."
                )
