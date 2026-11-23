import os
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

RAFRAICHISSEMENT = timedelta(seconds=5)
DELAI_HORS_LIGNE = timedelta(seconds=30)
TIMEOUT_HTTP = 10
POIDS_MAX = 150
TEMPERATURE_MIN = 10
TEMPERATURE_MAX = 40
COULEUR_POIDS = "#2563eb"
COULEUR_TEMPERATURE = "#ea580c"
COULEUR_OCCUPATION = "#059669"


@st.cache_resource
def creer_session() -> tuple[requests.Session, str]:
    load_dotenv()
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    cle = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not url or not cle or "votre-projet" in url or cle == "votre-cle-publique":
        raise RuntimeError("Renseignez SUPABASE_URL et SUPABASE_ANON_KEY dans .env.")
    if cle.startswith("sb_secret_"):
        raise RuntimeError("SUPABASE_ANON_KEY contient une clé secrète.")

    session = requests.Session()
    session.headers["apikey"] = cle
    if cle.startswith("eyJ"):
        session.headers["Authorization"] = f"Bearer {cle}"
    return session, f"{url}/rest/v1"


def lire_derniere_mesure() -> dict | None:
    session, api = creer_session()
    reponse = session.get(
        f"{api}/telemetrie",
        params={"select": "*", "order": "horodatage.desc", "limit": 1},
        timeout=TIMEOUT_HTTP,
    )
    reponse.raise_for_status()
    lignes = reponse.json()
    return lignes[0] if lignes else None


def lire_historique(heures: int) -> pd.DataFrame:
    session, api = creer_session()
    reponse = session.post(
        f"{api}/rpc/telemetrie_historique",
        json={"p_heures": heures},
        timeout=TIMEOUT_HTTP,
    )
    reponse.raise_for_status()
    historique = pd.DataFrame(reponse.json())
    if not historique.empty:
        historique["horodatage"] = pd.to_datetime(historique["horodatage"], utc=True, format="ISO8601")
    return historique


def jauge(titre: str, valeur: float, unite: str, bornes: tuple[int, int], couleur: str) -> go.Figure:
    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=valeur,
            title={"text": titre},
            number={"suffix": f" {unite}", "valueformat": ".1f"},
            gauge={"axis": {"range": bornes}, "bar": {"color": couleur}},
        )
    )
    figure.update_layout(height=260, margin={"l": 30, "r": 30, "t": 60, "b": 10})
    return figure


def courbe(historique: pd.DataFrame, colonne: str, titre: str, unite: str, couleur: str) -> go.Figure:
    figure = go.Figure(
        go.Scatter(
            x=historique["horodatage"],
            y=historique[colonne],
            mode="lines",
            line={"color": couleur, "width": 2},
            hovertemplate=f"%{{x|%H:%M:%S}}<br>%{{y:.1f}} {unite}<extra></extra>",
        )
    )
    figure.update_layout(
        title=titre,
        height=280,
        margin={"l": 50, "r": 20, "t": 50, "b": 40},
        yaxis_title=unite,
    )
    return figure


def afficher_statut(mesure: dict) -> None:
    horodatage = pd.to_datetime(mesure["horodatage"], utc=True, format="ISO8601")
    age = pd.Timestamp.now(tz="UTC") - horodatage

    if age > DELAI_HORS_LIGNE:
        st.warning(f"Capteur hors ligne. Dernière mesure il y a {int(age.total_seconds())} s.")
    elif mesure["statut_occupation"]:
        st.success("Chaise occupée")
    else:
        st.info("Chaise vide")


@st.fragment(run_every=RAFRAICHISSEMENT)
def afficher_donnees(heures: int) -> None:
    try:
        mesure = lire_derniere_mesure()
        historique = lire_historique(heures)
    except (requests.RequestException, RuntimeError) as erreur:
        detail = erreur if isinstance(erreur, RuntimeError) else type(erreur).__name__
        st.error(f"Lecture de Supabase impossible : {detail}")
        return

    if mesure is None:
        st.info("Aucune mesure pour l'instant. Lancez le simulateur avec `cargo run`.")
        return

    afficher_statut(mesure)

    gauche, droite = st.columns(2)
    gauche.plotly_chart(
        jauge("Poids", mesure["poids"], "kg", (0, POIDS_MAX), COULEUR_POIDS),
        key="jauge_poids",
    )
    droite.plotly_chart(
        jauge("Température", mesure["temperature"], "°C", (TEMPERATURE_MIN, TEMPERATURE_MAX), COULEUR_TEMPERATURE),
        key="jauge_temperature",
    )

    st.subheader(f"Historique des {heures} dernières heures")
    if historique.empty:
        st.info("Pas de données sur cette période.")
        return

    historique = historique.assign(occupation_pct=historique["taux_occupation"] * 100)
    st.plotly_chart(
        courbe(historique, "temperature_moyenne", "Température", "°C", COULEUR_TEMPERATURE),
        key="courbe_temperature",
    )
    st.plotly_chart(
        courbe(historique, "poids_moyen", "Poids (quand occupée)", "kg", COULEUR_POIDS),
        key="courbe_poids",
    )
    st.plotly_chart(
        courbe(historique, "occupation_pct", "Taux d'occupation", "%", COULEUR_OCCUPATION),
        key="courbe_occupation",
    )


def main() -> None:
    st.set_page_config(page_title="Chaise connectée", page_icon="🪑", layout="wide")
    st.title("🪑 Chaise connectée")
    heures = st.sidebar.select_slider("Période de l'historique (heures)", options=[1, 3, 6, 12, 24, 48], value=6)
    st.sidebar.caption(f"Actualisation toutes les {int(RAFRAICHISSEMENT.total_seconds())} s")
    afficher_donnees(heures)


if __name__ == "__main__":
    main()
