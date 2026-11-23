from datetime import datetime
from pathlib import Path

import pygame

from app.theme import (
    CARTE,
    CARTE_SURVOL,
    CRITIQUE,
    DISCRET,
    FOND,
    INACTIF,
    LIGNE,
    PISTE,
    POLICES,
    SECONDAIRE,
    TEXTE,
)


class Toile:
    def __init__(self, ecran):
        self.ecran = ecran
        self.souris = (0, 0)
        self.clic = False
        self.relache = False
        self.molette = 0
        self.glisse = None
        self.survol = False
        self.curseur_systeme = pygame.SYSTEM_CURSOR_ARROW
        self.formes = {}
        self.polices = {}
        self.textes = {}
        self.courbes = {}
        self.chemins = next(
            (triplet for triplet in POLICES if all(Path(chemin).exists() for chemin in triplet)),
            (None, None, None),
        )

    def lire(self, evenements) -> bool:
        self.clic = False
        self.relache = False
        self.molette = 0
        self.survol = False
        ouvert = True
        for evenement in evenements:
            if evenement.type == pygame.QUIT:
                ouvert = False
            elif evenement.type == pygame.MOUSEMOTION:
                self.souris = evenement.pos
            elif evenement.type == pygame.MOUSEBUTTONDOWN and evenement.button == 1:
                self.souris = evenement.pos
                self.clic = True
            elif evenement.type == pygame.MOUSEBUTTONUP and evenement.button == 1:
                self.souris = evenement.pos
                self.relache = True
            elif evenement.type == pygame.MOUSEWHEEL:
                self.molette += evenement.y
        return ouvert

    def terminer(self) -> bool:
        fin_glisse = self.relache and self.glisse is not None
        if fin_glisse:
            self.glisse = None
        curseur = pygame.SYSTEM_CURSOR_HAND if self.survol or self.glisse else pygame.SYSTEM_CURSOR_ARROW
        if curseur != self.curseur_systeme:
            self.curseur_systeme = curseur
            try:
                pygame.mouse.set_cursor(curseur)
            except pygame.error:
                pass
        return fin_glisse

    def police(self, taille: int, gras: bool = False, mono: bool = False) -> pygame.font.Font:
        cle = (taille, gras, mono)
        if cle not in self.polices:
            chemin = self.chemins[2 if mono else 1 if gras else 0]
            self.polices[cle] = pygame.font.Font(chemin, taille)
        return self.polices[cle]

    def rendu(self, contenu, taille, couleur, gras=False, mono=False):
        cle = (contenu, taille, couleur, gras, mono)
        if cle not in self.textes:
            if len(self.textes) > 1500:
                self.textes.clear()
            self.textes[cle] = self.police(taille, gras, mono).render(contenu, True, couleur)
        return self.textes[cle]

    def texte(self, contenu, taille, couleur, position, ancre="topleft", gras=False, mono=False):
        surface = self.rendu(str(contenu), taille, couleur, gras, mono)
        rectangle = surface.get_rect(**{ancre: position})
        self.ecran.blit(surface, rectangle)
        return rectangle

    def ajuster(self, contenu, taille, largeur, gras=False, mono=False) -> str:
        police = self.police(taille, gras, mono)
        if police.size(contenu)[0] <= largeur:
            return contenu
        while contenu and police.size(contenu + "…")[0] > largeur:
            contenu = contenu[:-1]
        return contenu + "…"

    def decouper(self, contenu, taille, largeur, maximum=2) -> list:
        police = self.police(taille)
        lignes, courante = [], ""
        for mot in contenu.split():
            essai = f"{courante} {mot}".strip()
            if police.size(essai)[0] <= largeur:
                courante = essai
            else:
                if courante:
                    lignes.append(courante)
                courante = mot
        if courante:
            lignes.append(courante)
        if len(lignes) > maximum:
            lignes = lignes[:maximum]
            lignes[-1] = self.ajuster(lignes[-1] + " …", taille, largeur)
        return lignes

    def forme(self, rectangle, couleur, rayon):
        largeur, hauteur = rectangle.size
        if largeur <= 0 or hauteur <= 0:
            return
        rayon = min(rayon, largeur // 2, hauteur // 2)
        cle = (largeur, hauteur, tuple(couleur), rayon)
        if cle not in self.formes:
            if len(self.formes) > 1500:
                self.formes.clear()
            grande = pygame.Surface((largeur * 3, hauteur * 3), pygame.SRCALPHA)
            base = tuple(couleur[:3])
            grande.fill((*base, 0))
            pygame.draw.rect(grande, (*base, couleur[3] if len(couleur) > 3 else 255), grande.get_rect(), border_radius=rayon * 3)
            self.formes[cle] = pygame.transform.smoothscale(grande, (largeur, hauteur))
        self.ecran.blit(self.formes[cle], rectangle)

    def disque(self, centre, rayon, couleur):
        zone = pygame.Rect(0, 0, rayon * 2, rayon * 2)
        zone.center = (round(centre[0]), round(centre[1]))
        self.forme(zone, couleur, rayon)

    def carte(self, rectangle, titre=None):
        self.forme(rectangle, LIGNE, 14)
        self.forme(rectangle.inflate(-2, -2), CARTE, 13)
        if titre:
            self.texte(titre, 13, DISCRET, (rectangle.x + 20, rectangle.y + 16), gras=True)

    def survole(self, rectangle, actif=True) -> bool:
        resultat = actif and rectangle.collidepoint(self.souris)
        if resultat:
            self.survol = True
        return resultat

    def bouton(self, rectangle, libelle, style="principal", actif=True, taille=15):
        styles = {
            "principal": (TEXTE, FOND, (255, 255, 252)),
            "danger": (CRITIQUE, TEXTE, (224, 76, 76)),
            "secondaire": (PISTE, TEXTE, (60, 60, 56)),
            "discret": (CARTE, SECONDAIRE, CARTE_SURVOL),
        }
        fond, couleur, fond_survol = styles[style]
        if not actif:
            fond, couleur = PISTE, DISCRET
        survole = self.survole(rectangle, actif)
        self.forme(rectangle, fond_survol if survole else fond, 10)
        self.texte(libelle, taille, couleur, rectangle.center, "center", gras=True)
        return survole and self.clic

    def segments(self, rectangle, options, selection, actif=True, taille=14):
        self.forme(rectangle, PISTE, 9)
        largeur = rectangle.width / len(options)
        resultat = selection
        for index, option in enumerate(options):
            gauche = round(rectangle.x + index * largeur)
            droite = round(rectangle.x + (index + 1) * largeur)
            zone = pygame.Rect(gauche, rectangle.y, droite - gauche, rectangle.height)
            choisi = index == selection
            if not choisi and self.survole(zone, actif) and self.clic:
                resultat = index
            if choisi:
                self.forme(zone.inflate(-6, -6), TEXTE if actif else (70, 70, 66), 7)
                couleur = FOND if actif else SECONDAIRE
            else:
                couleur = SECONDAIRE if actif else INACTIF
            self.texte(option, taille, couleur, zone.center, "center", gras=choisi)
        return resultat

    def curseur(self, identifiant, x, y, largeur, valeur, minimum, maximum, pas, actif, couleur):
        piste = pygame.Rect(x, y - 2, largeur, 4)
        zone = piste.inflate(18, 28)
        if self.survole(zone, actif) and self.clic:
            self.glisse = identifiant
        if actif and self.glisse == identifiant:
            ratio = min(1.0, max(0.0, (self.souris[0] - piste.x) / piste.width))
            valeur = round((minimum + ratio * (maximum - minimum)) / pas) * pas
        self.forme(piste, PISTE, 2)
        if valeur is None:
            return valeur
        ratio = (min(maximum, max(minimum, valeur)) - minimum) / (maximum - minimum)
        position = piste.x + round(ratio * piste.width)
        self.forme(pygame.Rect(piste.x, piste.y, position - piste.x, 4), couleur if actif else INACTIF, 2)
        if actif:
            self.disque((position, y), 10, CARTE)
            self.disque((position, y), 8, TEXTE)
        return valeur

    def etincelle(self, rectangle, valeurs, couleur, minimum, maximum):
        if len(valeurs) < 2:
            return
        cle = ("etincelle", rectangle.size, tuple(couleur), tuple(valeurs), minimum, maximum)
        if cle not in self.courbes:
            if len(self.courbes) > 60:
                self.courbes.clear()
            largeur, hauteur = rectangle.width * 2, rectangle.height * 2
            surface = pygame.Surface((largeur, hauteur), pygame.SRCALPHA)
            surface.fill((*couleur, 0))
            etendue = max(maximum - minimum, 1e-6)
            points = [
                (
                    round(index / (len(valeurs) - 1) * (largeur - 4)) + 2,
                    round(hauteur - 3 - (min(maximum, max(minimum, valeur)) - minimum) / etendue * (hauteur - 6)),
                )
                for index, valeur in enumerate(valeurs)
            ]
            pygame.draw.polygon(surface, (*couleur, 34), [(points[0][0], hauteur), *points, (points[-1][0], hauteur)])
            pygame.draw.lines(surface, couleur, False, points, 4)
            self.courbes[cle] = pygame.transform.smoothscale(surface, rectangle.size)
        self.ecran.blit(self.courbes[cle], rectangle)

    def graphique(self, rectangle, points, cle_valeur, titre, unite, couleur, bornes, debut, fin):
        self.carte(rectangle)
        self.texte(titre, 14, TEXTE, (rectangle.x + 20, rectangle.y + 13), gras=True)
        zone = pygame.Rect(rectangle.x + 58, rectangle.y + 42, rectangle.width - 80, rectangle.height - 72)
        minimum, maximum = bornes
        y_de = lambda valeur: zone.bottom - (min(maximum, max(minimum, valeur)) - minimum) / (maximum - minimum) * zone.height
        x_de = lambda instant: zone.x + (instant - debut) / max(fin - debut, 1) * zone.width

        for index in range(3):
            valeur = minimum + (maximum - minimum) * index / 2
            y = round(y_de(valeur))
            pygame.draw.line(self.ecran, LIGNE, (zone.x, y), (zone.right, y))
            self.texte(f"{valeur:.0f}", 12, DISCRET, (zone.x - 10, y), "midright")
        self.texte(unite, 12, DISCRET, (rectangle.right - 20, rectangle.y + 16), "topright")

        for index in range(5):
            instant = debut + (fin - debut) * index / 4
            x = round(x_de(instant))
            etiquette = datetime.fromtimestamp(instant).strftime("%H:%M")
            ancre = "midtop" if 0 < index < 4 else ("topleft" if index == 0 else "topright")
            self.texte(etiquette, 12, DISCRET, (x, zone.bottom + 7), ancre)

        visibles = [(p["t"], p[cle_valeur]) for p in points if debut <= p["t"] <= fin]
        if not visibles:
            self.texte("Pas de données sur cette période", 13, DISCRET, zone.center, "center")
            return

        cle = ("graphique", titre, zone.size, tuple(visibles), debut, fin)
        if cle not in self.courbes:
            if len(self.courbes) > 60:
                self.courbes.clear()
            self.courbes[cle] = self._tracer(zone, visibles, couleur, x_de, y_de)
        self.ecran.blit(self.courbes[cle], zone)

        if zone.inflate(10, 10).collidepoint(self.souris):
            instant, valeur = min(visibles, key=lambda point: abs(x_de(point[0]) - self.souris[0]))
            x, y = round(x_de(instant)), round(y_de(valeur))
            pygame.draw.line(self.ecran, DISCRET, (x, zone.y), (x, zone.bottom))
            self.disque((x, y), 7, CARTE)
            self.disque((x, y), 5, couleur)
            libelle = f"{datetime.fromtimestamp(instant):%H:%M:%S}   {valeur:.1f} {unite}"
            largeur = self.police(13, True).size(libelle)[0] + 20
            bulle = pygame.Rect(0, 0, largeur, 30)
            bulle.midbottom = (x, max(zone.y + 32, y - 12))
            bulle.clamp_ip(rectangle.inflate(-8, -8))
            self.forme(bulle, PISTE, 8)
            self.texte(libelle, 13, TEXTE, bulle.center, "center", gras=True)

    @staticmethod
    def _tracer(zone, visibles, couleur, x_de, y_de):
        surface = pygame.Surface((zone.width * 2, zone.height * 2), pygame.SRCALPHA)
        surface.fill((*couleur, 0))
        ecarts = sorted(b[0] - a[0] for a, b in zip(visibles, visibles[1:]))
        seuil = ecarts[len(ecarts) // 2] * 2.5 if ecarts else 0
        morceaux, courant = [], [visibles[0]]
        for precedent, point in zip(visibles, visibles[1:]):
            if point[0] - precedent[0] > seuil:
                morceaux.append(courant)
                courant = []
            courant.append(point)
        morceaux.append(courant)
        for morceau in morceaux:
            traces = [
                (round((x_de(t) - zone.x) * 2), round((y_de(v) - zone.y) * 2))
                for t, v in morceau
            ]
            if len(traces) == 1:
                pygame.draw.circle(surface, couleur, traces[0], 5)
                continue
            fond = [(traces[0][0], zone.height * 2), *traces, (traces[-1][0], zone.height * 2)]
            pygame.draw.polygon(surface, (*couleur, 30), fond)
            pygame.draw.lines(surface, couleur, False, traces, 4)
        return pygame.transform.smoothscale(surface, zone.size)
