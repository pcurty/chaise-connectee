import math
import time

import pygame

from app.composants import Toile
from app.pages import icone, page_communications, page_controle, page_donnees, page_graphiques
from app.services import ARRET, ARRETE, MARCHE, PREPARATION, Dashboard, Journal, LecteurSupabase, Moteur
from app.theme import (
    ALERTE,
    BARRE,
    BON,
    CARTE,
    CARTE_SURVOL,
    CRITIQUE,
    DISCRET,
    FOND,
    FOND_BARRE,
    HAUTEUR,
    INACTIF,
    LARGEUR,
    LIGNE,
    POIDS_MAX,
    POIDS_MIN,
    SECONDAIRE,
    SERIE_OCCUPATION,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    TEXTE,
)

MENU = [
    ("controle", "Contrôle"),
    ("graphiques", "Graphiques"),
    ("donnees", "Données"),
    ("communications", "Communications"),
]


class Application:
    def __init__(self, ecran, dashboard=None):
        self.ecran = ecran
        self.toile = Toile(ecran)
        self.journal = Journal()
        self.moteur = Moteur(self.journal)
        self.lecteur = LecteurSupabase(self.journal)
        self.dashboard = dashboard or Dashboard()
        self.horloge = pygame.time.Clock()
        self.ouvert = True
        self.vue = "controle"
        self.manuel = False
        self.occupee = True
        self.poids = 70.0
        self.temperature = 24.0
        self.intervalle = 5
        self.heures = 6
        self.filtre = "tout"
        self.page_table = 0
        self.filtre_journal = None
        self.defilement = 0
        self.pause_journal = None
        self.notification = None

    def commande(self) -> dict:
        if not self.manuel:
            return {"commande": "aleatoire"}
        return {
            "commande": "manuel",
            "occupee": self.occupee,
            "poids": self.poids,
            "temperature": self.temperature,
        }

    def reglages(self) -> tuple[dict, int]:
        return self.commande(), self.intervalle

    def choisir_mode(self, manuel: bool, mesure) -> None:
        if manuel == self.manuel:
            return
        if manuel and mesure:
            self.occupee = bool(mesure["statut_occupation"])
            if self.occupee:
                self.poids = min(POIDS_MAX, max(POIDS_MIN, round(mesure["poids"] * 2) / 2))
            self.temperature = min(TEMPERATURE_MAX, max(TEMPERATURE_MIN, round(mesure["temperature"] * 2) / 2))
        self.manuel = manuel
        self.moteur.envoyer(self.commande())

    @staticmethod
    def mesure_affichee(instant, lecture):
        if instant["mesure"] is not None:
            return instant["mesure"]
        return lecture["recentes"][-1] if lecture["recentes"] else None

    def exporter(self) -> None:
        self.notifier("Export en cours…", False)
        self.lecteur.exporter(self.filtre, self.notifier)

    def notifier(self, message: str, erreur: bool) -> None:
        self.notification = (message, erreur, time.monotonic() + 5)

    def basculer_pause(self, evenements) -> None:
        self.pause_journal = None if self.pause_journal is not None else list(evenements)
        self.defilement = 0

    def message(self, instant, lecture) -> tuple[str, tuple]:
        etat = instant["etat"]
        if self.dashboard.erreur:
            return self.dashboard.erreur, CRITIQUE
        if etat == ARRETE:
            if instant["erreur"]:
                return instant["erreur"], CRITIQUE
            if lecture["erreur"]:
                return lecture["erreur"], CRITIQUE
            return "Prêt à démarrer.", DISCRET
        if etat == PREPARATION:
            return "Préparation du programme…", DISCRET
        if etat == ARRET:
            return "Arrêt en cours…", DISCRET
        if instant["en_attente"] > 0:
            return f"Connexion perdue. {instant['en_attente']} mesure(s) en attente.", ALERTE
        if instant["recu_a"] is None:
            return "Connexion à la base…", DISCRET
        age = int(time.monotonic() - instant["recu_a"])
        return (f"Envoyé il y a {age} s." if age else "Envoyé à l'instant."), SECONDAIRE

    def dessiner_barre(self, instant, lecture) -> None:
        t = self.toile
        pygame.draw.rect(self.ecran, FOND_BARRE, (0, 0, BARRE, HAUTEUR))
        pygame.draw.line(self.ecran, LIGNE, (BARRE - 1, 0), (BARRE - 1, HAUTEUR))

        logo = pygame.Rect(22, 26, 36, 36)
        t.forme(logo, SERIE_OCCUPATION, 10)
        t.forme(pygame.Rect(logo.x + 11, logo.y + 7, 14, 13), TEXTE, 3)
        t.forme(pygame.Rect(logo.x + 8, logo.y + 21, 20, 3), TEXTE, 1)
        t.forme(pygame.Rect(logo.x + 10, logo.y + 24, 2, 6), TEXTE, 1)
        t.forme(pygame.Rect(logo.x + 24, logo.y + 24, 2, 6), TEXTE, 1)
        t.texte("Chaise", 17, TEXTE, (68, 24), gras=True)
        t.texte("connectée", 12, DISCRET, (68, 46))

        for rang, (nom, libelle) in enumerate(MENU):
            zone = pygame.Rect(14, 96 + rang * 48, BARRE - 28, 42)
            choisi = self.vue == nom
            survole = t.survole(zone, not choisi)
            if choisi:
                t.forme(zone, CARTE_SURVOL, 10)
                t.forme(pygame.Rect(zone.x, zone.y + 10, 3, 22), TEXTE, 1)
            elif survole:
                t.forme(zone, CARTE, 10)
                if t.clic:
                    self.vue = nom
            couleur = TEXTE if choisi else SECONDAIRE
            icone(t, nom, zone.x + 15, zone.y + 12, couleur)
            t.texte(libelle, 14, couleur, (zone.x + 44, zone.centery), "midleft", gras=choisi)

        etat = instant["etat"]
        etats = {
            ARRETE: ("Arrêté", INACTIF),
            PREPARATION: ("Démarrage", ALERTE),
            MARCHE: ("En marche", BON),
            ARRET: ("Arrêt", ALERTE),
        }
        libelle, couleur = etats[etat]
        y = HAUTEUR - 170
        pygame.draw.line(self.ecran, LIGNE, (20, y), (BARRE - 20, y))
        centre = (28, y + 28)
        if etat == MARCHE:
            halo = round(45 + 35 * math.sin(time.monotonic() * 3))
            t.disque(centre, 9, (*BON, halo))
        t.disque(centre, 5, couleur)
        t.texte(libelle, 14, TEXTE, (44, centre[1]), "midleft", gras=True)

        contenu, teinte = self.message(instant, lecture)
        for rang, ligne in enumerate(t.decouper(contenu, 12, BARRE - 42)):
            t.texte(ligne, 12, teinte, (20, y + 48 + rang * 17))

        rectangle = pygame.Rect(20, HAUTEUR - 72, BARRE - 40, 50)
        if etat == ARRETE:
            if t.bouton(rectangle, "Démarrer", "principal", True, 16):
                self.moteur.demarrer(self.reglages)
        elif etat == MARCHE:
            if t.bouton(rectangle, "Arrêter", "danger", True, 16):
                self.moteur.arreter()
        else:
            t.bouton(rectangle, "Démarrage…" if etat == PREPARATION else "Arrêt…", "principal", False, 16)

    def dessiner_notification(self) -> None:
        if self.notification is None:
            return
        message, erreur, fin = self.notification
        if time.monotonic() > fin:
            self.notification = None
            return
        t = self.toile
        largeur = t.police(13, True).size(message)[0] + 36
        rectangle = pygame.Rect(0, 0, largeur, 40)
        rectangle.midbottom = ((BARRE + LARGEUR) // 2, HAUTEUR - 18)
        t.forme(rectangle, CRITIQUE if erreur else TEXTE, 10)
        t.texte(message, 13, TEXTE if erreur else FOND, rectangle.center, "center", gras=True)

    def image(self) -> None:
        t = self.toile
        if not t.lire(pygame.event.get()):
            self.ouvert = False
        instant = self.moteur.instantane()
        self.lecteur.definir(self.vue, self.heures, self.filtre, self.page_table)
        lecture = self.lecteur.instantane()

        self.ecran.fill(FOND)
        change = False
        if self.vue == "controle":
            change = page_controle(self, instant, lecture)
        elif self.vue == "graphiques":
            page_graphiques(self, lecture)
        elif self.vue == "donnees":
            page_donnees(self, lecture)
        else:
            page_communications(self, instant, lecture)
        self.dessiner_barre(instant, lecture)
        self.dessiner_notification()

        if t.terminer():
            change = True
        if change:
            self.moteur.envoyer(self.commande())
        pygame.display.flip()
        self.horloge.tick(40)

    def fermer(self) -> None:
        self.lecteur.fermer()
        self.moteur.fermer()
        self.dashboard.fermer()

    def executer(self) -> None:
        try:
            while self.ouvert:
                self.image()
        finally:
            self.fermer()


def main() -> None:
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Chaise connectée")
    ecran = pygame.display.set_mode((LARGEUR, HAUTEUR))
    try:
        Application(ecran).executer()
    finally:
        pygame.quit()
