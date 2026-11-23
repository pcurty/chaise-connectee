import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections import deque
from datetime import datetime

import requests
from dotenv import load_dotenv

from app.theme import LIGNES_TABLE, RACINE

BINAIRE = RACINE / "target" / "release" / "chaise"
PORT_DASHBOARD = 8501
URL_DASHBOARD = f"http://localhost:{PORT_DASHBOARD}"
URL_SANTE = f"{URL_DASHBOARD}/_stcore/health"
DOSSIER_EXPORTS = RACINE / "exports"
TIMEOUT_HTTP = 8
PAUSE_LECTURE = 5
PAUSE_HISTORIQUE = 15
TAILLE_RECENTES = 60
LIMITE_EXPORT = 1000

ARRETE = "arrete"
PREPARATION = "preparation"
MARCHE = "marche"
ARRET = "arret"


def vers_date(texte: str) -> datetime:
    propre = re.sub(r"(\.\d{6})\d+", r"\1", texte).replace("Z", "+00:00")
    return datetime.fromisoformat(propre).astimezone()


def traduire_erreur(message: str) -> str:
    if "401" in message or "403" in message:
        return "Clé Supabase refusée. Vérifie le fichier .env."
    if "404" in message:
        return "Table introuvable. Exécute schema.sql dans Supabase."
    if "variable d'environnement" in message or "valeur d'exemple" in message:
        return "Fichier .env manquant ou incomplet."
    return message.removeprefix("Erreur fatale : ")[:120] or "Le programme s'est arrêté."


def decrire_commande(commande: dict) -> str:
    nom = commande.get("commande")
    if nom == "aleatoire":
        return "Mode aléatoire"
    if nom == "intervalle":
        return f"Envoi toutes les {commande['secondes']} s"
    if commande.get("occupee"):
        return f"Manuel : occupée, {commande['poids']:.1f} kg, {commande['temperature']:.1f} °C"
    return f"Manuel : vide, {commande['temperature']:.1f} °C"


class Journal:
    def __init__(self, capacite: int = 500):
        self.verrou = threading.Lock()
        self.evenements = deque(maxlen=capacite)
        self.compteur = 0

    def ajouter(self, source, cible, famille, action, detail="", statut=None, duree=None, niveau="info"):
        with self.verrou:
            self.compteur += 1
            self.evenements.append(
                {
                    "id": self.compteur,
                    "instant": time.monotonic(),
                    "heure": datetime.now().strftime("%H:%M:%S"),
                    "source": source,
                    "cible": cible,
                    "famille": famille,
                    "action": action,
                    "detail": detail,
                    "statut": statut,
                    "duree": duree,
                    "niveau": niveau,
                }
            )

    def lire(self) -> list:
        with self.verrou:
            return list(self.evenements)


class Moteur:
    def __init__(self, journal: Journal):
        self.journal = journal
        self.verrou = threading.Lock()
        self.etat = ARRETE
        self.mesure = None
        self.recu_a = None
        self.en_attente = 0
        self.erreur = None
        self.processus = None
        self.arret_demande = False
        self.fil = None
        self.reussis = 0
        self.echecs = 0
        self.latences = deque(maxlen=30)

    def instantane(self) -> dict:
        with self.verrou:
            latence = sum(self.latences) / len(self.latences) if self.latences else None
            return {
                "etat": self.etat,
                "mesure": self.mesure,
                "recu_a": self.recu_a,
                "en_attente": self.en_attente,
                "erreur": self.erreur,
                "reussis": self.reussis,
                "echecs": self.echecs,
                "latence": latence,
            }

    def demarrer(self, fournir_reglages) -> None:
        with self.verrou:
            if self.etat != ARRETE:
                return
            self.etat = PREPARATION
            self.mesure = None
            self.recu_a = None
            self.en_attente = 0
            self.erreur = None
            self.arret_demande = False
        self.journal.ajouter("interface", "rust", "commande", "Démarrage", "Lancement du simulateur")
        self.fil = threading.Thread(target=self._executer, args=(fournir_reglages,), daemon=True)
        self.fil.start()

    def envoyer(self, commande: dict) -> None:
        with self.verrou:
            if self.etat != MARCHE:
                return
            self._ecrire(commande)
        self.journal.ajouter("interface", "rust", "commande", "Commande", decrire_commande(commande))

    def arreter(self) -> None:
        with self.verrou:
            if self.etat == PREPARATION:
                self.arret_demande = True
                return
            if self.etat != MARCHE:
                return
            self.etat = ARRET
            self.arret_demande = True
            processus = self.processus
            try:
                processus.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass
        self.journal.ajouter("interface", "rust", "commande", "Arrêt", "Fermeture du canal de commandes")
        threading.Thread(target=self._forcer_arret, args=(processus,), daemon=True).start()

    def fermer(self) -> None:
        self.arreter()
        if self.fil is not None:
            self.fil.join(timeout=8)

    def _ecrire(self, commande: dict) -> None:
        try:
            self.processus.stdin.write(json.dumps(commande) + "\n")
            self.processus.stdin.flush()
        except (AttributeError, BrokenPipeError, OSError, ValueError):
            pass

    @staticmethod
    def _forcer_arret(processus) -> None:
        try:
            processus.wait(timeout=4)
        except subprocess.TimeoutExpired:
            processus.terminate()
            try:
                processus.wait(timeout=2)
            except subprocess.TimeoutExpired:
                processus.kill()

    def _terminer(self, erreur=None) -> None:
        with self.verrou:
            self.etat = ARRETE
            self.processus = None
            self.erreur = erreur
        if erreur:
            self.journal.ajouter("rust", "interface", "commande", "Erreur", erreur, niveau="erreur")
        else:
            self.journal.ajouter("rust", "interface", "commande", "Arrêté", "Simulateur arrêté")

    def _executer(self, fournir_reglages) -> None:
        cargo = shutil.which("cargo") or str(os.path.expanduser("~/.cargo/bin/cargo"))
        try:
            compilation = subprocess.run(
                [cargo, "build", "--release", "--quiet"],
                cwd=RACINE,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            self._terminer("Cargo est introuvable. Installe Rust.")
            return
        if compilation.returncode != 0:
            self._terminer("La compilation du programme a échoué.")
            return

        with self.verrou:
            if self.arret_demande:
                self.etat = ARRETE
                return
            commande, intervalle = fournir_reglages()
            environnement = dict(os.environ, INTERVALLE_SECONDES=str(intervalle))
            try:
                processus = subprocess.Popen(
                    [str(BINAIRE), "--pilote"],
                    cwd=RACINE,
                    env=environnement,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
            except OSError:
                self.etat = ARRETE
                self.erreur = "Impossible de lancer le programme."
                return
            self.processus = processus
            self.etat = MARCHE
            self._ecrire(commande)
        self.journal.ajouter("interface", "rust", "commande", "Commande", decrire_commande(commande))

        erreurs = []
        lecteur = threading.Thread(target=self._lire_erreurs, args=(processus, erreurs), daemon=True)
        lecteur.start()

        for ligne in processus.stdout:
            try:
                self._traiter(json.loads(ligne))
            except (ValueError, KeyError, TypeError):
                continue

        code = processus.wait()
        lecteur.join(timeout=1)
        with self.verrou:
            demande = self.arret_demande
        fatales = [ligne for ligne in erreurs if ligne.startswith("Erreur fatale")]
        if code != 0 and not demande:
            self._terminer(traduire_erreur(fatales[-1] if fatales else ""))
        else:
            self._terminer()

    def _traiter(self, donnees: dict) -> None:
        if "accuse" in donnees:
            self.journal.ajouter("rust", "interface", "commande", "Accusé", f"Commande « {donnees['accuse']} » appliquée")
            return

        mesure = donnees["mesure"]
        en_attente = int(donnees["en_attente"])
        envoi = donnees["envoi"]
        etat = "occupée" if mesure["statut_occupation"] else "vide"
        resume = f"{etat}, {mesure['poids']:.1f} kg, {mesure['temperature']:.1f} °C"

        with self.verrou:
            self.mesure = mesure
            self.en_attente = en_attente
            if envoi["reussi"]:
                self.reussis += 1
                self.latences.append(envoi["duree_ms"])
                if en_attente == 0:
                    self.recu_a = time.monotonic()
            else:
                self.echecs += 1

        self.journal.ajouter("capteurs", "rust", "capteur", "Mesure", resume)
        self.journal.ajouter("rust", "supabase", "base", "POST", f"{envoi['mesures']} mesure(s), {envoi['octets']} octets")
        statut = envoi["statut"]
        if envoi["reussi"]:
            self.journal.ajouter("supabase", "rust", "base", "Réponse", "Mesures enregistrées", statut, envoi["duree_ms"])
        else:
            detail = f"Échec, {en_attente} mesure(s) gardée(s)"
            self.journal.ajouter("supabase", "rust", "base", "Réponse", detail, statut, envoi["duree_ms"], "erreur")
        self.journal.ajouter("rust", "interface", "capteur", "Télémétrie", resume)

    @staticmethod
    def _lire_erreurs(processus, erreurs: list) -> None:
        for ligne in processus.stderr:
            erreurs.append(ligne.strip())
            del erreurs[:-20]


class LecteurSupabase:
    def __init__(self, journal: Journal):
        self.journal = journal
        self.verrou = threading.Lock()
        self.reveil = threading.Event()
        self.actif = True
        self.vue = "controle"
        self.heures = 6
        self.filtre = "tout"
        self.page = 0
        self.recentes = []
        self.historique = []
        self.historique_fin = None
        self.historique_heures = None
        self.historique_a = 0.0
        self.lignes = []
        self.total = 0
        self.table_cle = None
        self.erreur = None
        self.joignable = None
        load_dotenv(RACINE / ".env")
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        cle = os.getenv("SUPABASE_ANON_KEY", "").strip()
        self.session = requests.Session()
        self.session.headers["apikey"] = cle
        if cle.startswith("eyJ"):
            self.session.headers["Authorization"] = f"Bearer {cle}"
        self.configure = bool(self.url and cle and "votre-projet" not in self.url and cle != "votre-cle-publique")
        if not self.configure:
            self.erreur = "Fichier .env manquant ou incomplet."
        threading.Thread(target=self._boucle, daemon=True).start()

    def definir(self, vue: str, heures: int, filtre: str, page: int) -> None:
        with self.verrou:
            change = (vue, heures, filtre, page) != (self.vue, self.heures, self.filtre, self.page)
            self.vue, self.heures, self.filtre, self.page = vue, heures, filtre, page
        if change:
            self.reveil.set()

    def rafraichir(self) -> None:
        with self.verrou:
            self.historique_a = 0.0
        self.reveil.set()

    def instantane(self) -> dict:
        with self.verrou:
            return {
                "recentes": list(self.recentes),
                "historique": list(self.historique),
                "historique_fin": self.historique_fin,
                "historique_heures": self.historique_heures,
                "lignes": list(self.lignes),
                "total": self.total,
                "table_cle": self.table_cle,
                "erreur": self.erreur,
                "joignable": self.joignable,
            }

    def fermer(self) -> None:
        self.actif = False
        self.reveil.set()

    def exporter(self, filtre: str, terminer) -> None:
        threading.Thread(target=self._exporter, args=(filtre, terminer), daemon=True).start()

    def _boucle(self) -> None:
        while self.actif:
            if self.configure:
                with self.verrou:
                    vue, heures, filtre, page = self.vue, self.heures, self.filtre, self.page
                try:
                    if vue in ("controle", "communications"):
                        self._lire_recentes()
                    elif vue == "graphiques":
                        self._lire_historique(heures)
                    elif vue == "donnees":
                        self._lire_table(filtre, page)
                except requests.RequestException:
                    pass
            self.reveil.wait(PAUSE_LECTURE)
            self.reveil.clear()

    def _requete(self, methode: str, chemin: str, libelle: str, **options):
        self.journal.ajouter("interface", "supabase", "base", methode, libelle)
        debut = time.monotonic()
        try:
            reponse = self.session.request(methode, f"{self.url}/rest/v1/{chemin}", timeout=TIMEOUT_HTTP, **options)
        except requests.RequestException:
            duree = int((time.monotonic() - debut) * 1000)
            self.journal.ajouter("supabase", "interface", "base", "Réponse", "Base injoignable", None, duree, "erreur")
            with self.verrou:
                self.joignable = False
                self.erreur = "Base de données injoignable."
            raise
        duree = int((time.monotonic() - debut) * 1000)
        reussi = reponse.ok
        detail = f"{len(reponse.content)} octets reçus" if reussi else "Requête refusée"
        self.journal.ajouter("supabase", "interface", "base", "Réponse", detail, reponse.status_code, duree, "info" if reussi else "erreur")
        with self.verrou:
            self.joignable = reussi
            self.erreur = None if reussi else traduire_erreur(str(reponse.status_code))
        reponse.raise_for_status()
        return reponse

    def _lire_recentes(self) -> None:
        with self.verrou:
            derniere = self.recentes[-1]["horodatage"] if self.recentes else None
        parametres = {"select": "*", "order": "horodatage.desc", "limit": TAILLE_RECENTES}
        if derniere:
            parametres["horodatage"] = f"gt.{derniere}"
        lignes = self._requete("GET", "telemetrie", "Dernières mesures", params=parametres).json()
        if lignes:
            with self.verrou:
                self.recentes = (self.recentes + list(reversed(lignes)))[-TAILLE_RECENTES:]

    def _lire_historique(self, heures: int) -> None:
        with self.verrou:
            frais = self.historique_heures == heures and time.monotonic() - self.historique_a < PAUSE_HISTORIQUE
        if frais:
            return
        lignes = self._requete(
            "POST",
            "rpc/telemetrie_historique",
            f"Historique sur {heures} h",
            json={"p_heures": heures},
        ).json()
        points = [
            {
                "t": vers_date(ligne["horodatage"]).timestamp(),
                "poids": ligne["poids_moyen"],
                "temperature": ligne["temperature_moyenne"],
                "occupation": ligne["taux_occupation"] * 100,
            }
            for ligne in lignes
        ]
        with self.verrou:
            self.historique = points
            self.historique_fin = time.time()
            self.historique_heures = heures
            self.historique_a = time.monotonic()

    def _lire_table(self, filtre: str, page: int) -> None:
        parametres = {"select": "*", "order": "horodatage.desc"}
        if filtre != "tout":
            parametres["statut_occupation"] = f"eq.{'true' if filtre == 'occupee' else 'false'}"
        debut = page * LIGNES_TABLE
        entetes = {"Prefer": "count=exact", "Range": f"{debut}-{debut + LIGNES_TABLE - 1}"}
        reponse = self._requete("GET", "telemetrie", f"Tableau, page {page + 1}", params=parametres, headers=entetes)
        plage = reponse.headers.get("content-range", "*/0").split("/")[-1]
        total = int(plage) if plage.isdigit() else 0
        with self.verrou:
            if (self.filtre, self.page) == (filtre, page):
                self.lignes = reponse.json()
                self.total = total
                self.table_cle = (filtre, page)

    def _exporter(self, filtre: str, terminer) -> None:
        parametres = {"select": "*", "order": "horodatage.desc", "limit": LIMITE_EXPORT}
        if filtre != "tout":
            parametres["statut_occupation"] = f"eq.{'true' if filtre == 'occupee' else 'false'}"
        try:
            lignes = self._requete("GET", "telemetrie", "Export CSV", params=parametres).json()
            DOSSIER_EXPORTS.mkdir(exist_ok=True)
            chemin = DOSSIER_EXPORTS / f"telemetrie_{datetime.now():%Y%m%d_%H%M%S}.csv"
            with open(chemin, "w", newline="", encoding="utf-8") as fichier:
                sortie = csv.writer(fichier)
                sortie.writerow(["horodatage", "statut_occupation", "poids", "temperature"])
                for ligne in lignes:
                    sortie.writerow([ligne["horodatage"], ligne["statut_occupation"], ligne["poids"], ligne["temperature"]])
            terminer(f"{len(lignes)} lignes exportées dans exports/{chemin.name}", False)
        except (requests.RequestException, OSError):
            terminer("L'export a échoué.", True)


class Dashboard:
    def __init__(self):
        self.processus = None
        self.ouverture = False
        self.erreur = None

    def ouvrir(self) -> None:
        if self.ouverture:
            return
        self.ouverture = True
        self.erreur = None
        threading.Thread(target=self._ouvrir, daemon=True).start()

    def fermer(self) -> None:
        if self.processus is None or self.processus.poll() is not None:
            return
        self.processus.terminate()
        try:
            self.processus.wait(timeout=4)
        except subprocess.TimeoutExpired:
            self.processus.kill()

    @staticmethod
    def _est_pret() -> bool:
        try:
            with urllib.request.urlopen(URL_SANTE, timeout=1) as reponse:
                return reponse.status == 200
        except (urllib.error.URLError, OSError):
            return False

    @staticmethod
    def _ouvrir_navigateur() -> None:
        if shutil.which("explorer.exe"):
            subprocess.Popen(["explorer.exe", URL_DASHBOARD], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open(URL_DASHBOARD)

    def _ouvrir(self) -> None:
        try:
            if not self._est_pret():
                if self.processus is None or self.processus.poll() is not None:
                    self.processus = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "streamlit",
                            "run",
                            "dashboard.py",
                            "--server.headless=true",
                            f"--server.port={PORT_DASHBOARD}",
                            "--browser.gatherUsageStats=false",
                        ],
                        cwd=RACINE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                limite = time.monotonic() + 60
                while not self._est_pret():
                    if self.processus.poll() is not None or time.monotonic() > limite:
                        self.erreur = "Le dashboard n'a pas pu démarrer."
                        return
                    time.sleep(0.4)
            self._ouvrir_navigateur()
        except OSError:
            self.erreur = "Le dashboard n'a pas pu démarrer."
        finally:
            self.ouverture = False
