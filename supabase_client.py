"""
supabase_client.py

Petit client utilitaire pour parler avec Supabase
(tables : sites, site_history).

Utilise :
- SUPABASE_URL
- SUPABASE_SERVICE_KEY

à définir dans les variables d'environnement (ou st.secrets sur Streamlit).
"""

import os
from typing import List, Dict, Any, Optional

from supabase import create_client, Client


# -------------------------------------------------------------------
# Initialisation du client Supabase
# -------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError(
        "Les variables SUPABASE_URL et SUPABASE_SERVICE_KEY doivent être définies "
        "(dans vos variables d'environnement ou dans les secrets Streamlit)."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# -------------------------------------------------------------------
# Fonctions utilitaires pour la table `sites`
# -------------------------------------------------------------------

def list_sites() -> List[Dict[str, Any]]:
    """
    Retourne la liste de tous les sites enregistrés,
    triés du plus récent au plus ancien.
    """
    res = (
        supabase.table("sites")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def add_site(
    name: str,
    url: str,
    siret: Optional[str] = None,
    traffic_mensuel: int = 10_000,
    categorie: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Ajoute un site dans la table `sites`.

    Retourne la ligne insérée.
    """
    row = {
        "name": name,
        "url": url,
        "siret": siret,
        "traffic_mensuel": traffic_mensuel,
        "categorie": categorie,
    }

    res = supabase.table("sites").insert(row).execute()
    return res.data[0] if res.data else None


def get_site(site_id: str) -> Optional[Dict[str, Any]]:
    """
    Récupère un site par son id.
    """
    res = (
        supabase.table("sites")
        .select("*")
        .eq("id", site_id)
        .single()
        .execute()
    )
    return res.data


# -------------------------------------------------------------------
# Fonctions utilitaires pour la table `site_history`
# -------------------------------------------------------------------

def add_site_history(
    site_id: str,
    site_result: Dict[str, Any],
    carbon: Dict[str, Any],
    issues: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Enregistre une nouvelle analyse dans `site_history` pour un site donné.

    - `site_result` : dictionnaire retourné par analyze_website(...)
    - `carbon`      : dictionnaire retourné par estimate_site_carbon(...)
    - `issues`      : liste de textes décrivant les points à surveiller (optionnel)
    """
    if issues is None:
        issues = []

    row = {
        "site_id": site_id,
        "pages_scanned": site_result.get("pages_scanned"),
        "avg_total_kb": site_result.get("avg_total_kb"),
        "gco2_page": carbon.get("gco2_per_page_view"),
        "gco2_mois": carbon.get("monthly_kgco2"),
        "gco2_an": carbon.get("yearly_kgco2"),
        "rse_score": site_result.get("global_rse_score"),
        "carbon_score": site_result.get("global_carbon_score"),
        "green_it_score": site_result.get("global_green_it_score"),
        "is_green_hosting": site_result.get("hosting_green"),
        "issues_detected": issues,
    }

    res = supabase.table("site_history").insert(row).execute()
    return res.data[0] if res.data else None


def get_site_history(site_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Récupère l'historique (les X dernières analyses) pour un site donné.
    """
    res = (
        supabase.table("site_history")
        .select("*")
        .eq("site_id", site_id)
        .order("date", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []
