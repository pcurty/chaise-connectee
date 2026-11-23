import math
import time

import pygame

from app.services import ARRET, ARRETE, MARCHE, PREPARATION, vers_date
from app.theme import (
    ALERTE,
    BON,
    CARTE,
    CARTE_SURVOL,
    CONTENU_H,
    CONTENU_L,
    CONTENU_X,
    CONTENU_Y,
    CRITIQUE,
    DISCRET,
    FOND,
    INACTIF,
    INTERVALLES,
    LIGNE,
    LIGNES_TABLE,
    MARGE,
    PERIODES,
    PISTE,
    POIDS_MAX,
    POIDS_MIN,
    SECONDAIRE,
    SERIE_OCCUPATION,
    SERIE_POIDS,
    SERIE_TEMPERATURE,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    TEXTE,
)

NOEUDS = {
    "capteurs": ("Capteurs", "simulés"),
    "rust": ("Simulateur", "Rust"),
    "supabase": ("Supabase", "PostgreSQL"),
    "interface": ("Application", "Pygame"),
}
FAMILLES = {"commande": SERIE_POIDS, "capteur": SERIE_OCCUPATION, "base": SERIE_TEMPERATURE}
FILTRES_JOURNAL = [None, "commande", "capteur", "base"]
FILTRES_TABLE = ["tout", "occupee", "vide"]
DUREE_PAQUET = 0.7
RETARDS = {("rust", "supabase"): 0.35, ("supabase", "rust"): 0.7, ("rust", "interface"): 1.05}


def en_tete(app, titre, sous_titre):
    t = app.toile
    t.texte(titre, 26, TEXTE, (CONTENU_X, 26), gras=True)
    t.texte(sous_titre, 14, DISCRET, (CONTENU_X, 62))


def dessiner_chaise(t, cx, cy, occupee, phase):
    bois = SERIE_OCCUPATION if occupee else (84, 84, 78)
    pied = (70, 70, 65)
    if occupee:
        halo = 30 + round(10 * (math.sin(phase * 2.2) + 1))
        t.disque((cx, cy - 8), 92, (*SERIE_OCCUPATION, halo // 3))
        t.disque((cx, cy - 8), 72, (*SERIE_OCCUPATION, halo // 2))
    t.forme(pygame.Rect(cx - 44, cy - 78, 88, 74), bois, 14)
    t.forme(pygame.Rect(cx - 34, cy - 68, 68, 54), CARTE, 9)
    if occupee:
        t.disque((cx, cy - 58), 15, TEXTE)
        t.forme(pygame.Rect(cx - 25, cy - 40, 50, 42), TEXTE, 16)
    t.forme(pygame.Rect(cx - 58, cy, 116, 16), bois, 7)
    t.forme(pygame.Rect(cx - 50, cy + 16, 9, 48), pied, 4)
    t.forme(pygame.Rect(cx + 41, cy + 16, 9, 48), pied, 4)


def tuile(t, rectangle, titre, valeur, couleur, valeurs, minimum, maximum):
    t.carte(rectangle, titre)
    t.texte(valeur, 30, TEXTE if valeur != "—" else INACTIF, (rectangle.x + 20, rectangle.y + 40), gras=True)
    zone = pygame.Rect(rectangle.x + 16, rectangle.y + 88, rectangle.width - 32, rectangle.height - 104)
    pygame.draw.line(t.ecran, LIGNE, (zone.x, zone.bottom), (zone.right, zone.bottom))
    if len(valeurs) >= 2:
        t.etincelle(zone, valeurs, couleur, minimum, maximum)
    else:
        t.texte("En attente de mesures", 12, DISCRET, zone.center, "center")


def petit_chiffre(t, x, y, largeur, titre, valeur, couleur=TEXTE):
    t.texte(titre, 12, DISCRET, (x, y))
    t.texte(ajuster_valeur(t, valeur, largeur), 20, couleur, (x, y + 19), gras=True)


def ajuster_valeur(t, valeur, largeur):
    return t.ajuster(str(valeur), 20, largeur, gras=True)


def page_controle(app, instant, lecture):
    t = app.toile
    en_tete(app, "Contrôle", "Pilote la chaise et observe ses valeurs en direct")
    mesure = app.mesure_affichee(instant, lecture)
    change = panneau_reglages(app, instant, mesure)

    x = CONTENU_X + 346
    largeur = CONTENU_L - 346
    occupee = bool(mesure["statut_occupation"]) if mesure else None
    heros = pygame.Rect(x, CONTENU_Y, largeur, 262)
    t.carte(heros)
    dessiner_chaise(t, heros.x + 130, heros.y + 132, bool(occupee), time.monotonic())
    tx = heros.x + 262
    t.texte("État de la chaise", 13, DISCRET, (tx, heros.y + 62), gras=True)
    if occupee is None:
        libelle, couleur = "Aucune donnée", INACTIF
    elif occupee:
        libelle, couleur = "Occupée", SERIE_OCCUPATION
    else:
        libelle, couleur = "Vide", DISCRET
    t.disque((tx + 7, heros.y + 109), 7, couleur)
    t.texte(libelle, 32, TEXTE, (tx + 24, heros.y + 86), gras=True)
    t.texte(origine_mesure(instant, mesure), 13, SECONDAIRE, (tx, heros.y + 142))
    t.texte("Mode " + ("manuel" if app.manuel else "aléatoire"), 13, DISCRET, (tx, heros.y + 164))

    recentes = lecture["recentes"]
    poids = [ligne["poids"] for ligne in recentes]
    temperatures = [ligne["temperature"] for ligne in recentes]
    largeur_tuile = (largeur - 16) // 2
    y = heros.bottom + 16
    tuile(
        t,
        pygame.Rect(x, y, largeur_tuile, 254),
        "Poids",
        f"{mesure['poids']:.1f} kg" if mesure else "—",
        SERIE_POIDS,
        poids,
        POIDS_MIN,
        POIDS_MAX,
    )
    tuile(
        t,
        pygame.Rect(x + largeur_tuile + 16, y, largeur_tuile, 254),
        "Température",
        f"{mesure['temperature']:.1f} °C" if mesure else "—",
        SERIE_TEMPERATURE,
        temperatures,
        TEMPERATURE_MIN,
        TEMPERATURE_MAX,
    )

    bas = pygame.Rect(x, y + 270, largeur, CONTENU_H - 262 - 16 - 270)
    t.carte(bas)
    colonne = (largeur - 40) // 3
    latence = f"{instant['latence']:.0f} ms" if instant["latence"] is not None else "—"
    petit_chiffre(t, bas.x + 20, bas.y + 14, colonne - 10, "Envois réussis", instant["reussis"])
    petit_chiffre(t, bas.x + 20 + colonne, bas.y + 14, colonne - 10, "Temps de réponse", latence)
    attente = instant["en_attente"]
    petit_chiffre(t, bas.x + 20 + 2 * colonne, bas.y + 14, colonne - 10, "En attente", attente, ALERTE if attente else TEXTE)
    return change


def origine_mesure(instant, mesure):
    if not mesure:
        return "Démarre le simulateur pour commencer"
    if instant["mesure"] is not None and instant["etat"] == MARCHE:
        return "Mesure en direct"
    age = max(0, time.time() - vers_date(mesure["horodatage"]).timestamp())
    if age < 60:
        return f"Dernière mesure il y a {int(age)} s"
    if age < 3600:
        return f"Dernière mesure il y a {int(age // 60)} min"
    if age < 86400:
        return f"Dernière mesure il y a {int(age // 3600)} h"
    return f"Dernière mesure il y a {int(age // 86400)} j"


def panneau_reglages(app, instant, mesure):
    t = app.toile
    carte = pygame.Rect(CONTENU_X, CONTENU_Y, 330, CONTENU_H)
    t.carte(carte, "Source des données")
    x = carte.x + 20
    largeur = carte.width - 40

    mode = t.segments(pygame.Rect(x, carte.y + 44, largeur, 40), ["Aléatoire", "Manuel"], int(app.manuel))
    app.choisir_mode(bool(mode), mesure)
    manuel = app.manuel
    aide = "Le programme invente des valeurs réalistes." if not manuel else "Tu choisis les valeurs envoyées à la base."
    t.texte(aide, 13, DISCRET, (x, carte.y + 94))

    pygame.draw.line(t.ecran, LIGNE, (x, carte.y + 130), (x + largeur, carte.y + 130))
    t.texte("Présence", 14, TEXTE if manuel else DISCRET, (x, carte.y + 150))
    if manuel:
        occupee = app.occupee
    else:
        occupee = bool(mesure["statut_occupation"]) if mesure else None
    selection = -1 if occupee is None else int(occupee)
    choix = t.segments(pygame.Rect(x, carte.y + 176, largeur, 38), ["Vide", "Occupée"], selection, manuel)
    change = False
    if manuel and bool(choix) != app.occupee:
        app.occupee = bool(choix)
        change = True

    poids_actif = manuel and app.occupee
    if manuel:
        poids = app.poids if app.occupee else 0.0
        temperature = app.temperature
    else:
        poids = mesure["poids"] if mesure else None
        temperature = mesure["temperature"] if mesure else None

    y = carte.y + 246
    t.texte("Poids", 14, TEXTE if poids_actif else DISCRET, (x, y - 10))
    t.texte("—" if poids is None else f"{poids:.1f} kg", 15, TEXTE if poids is not None else INACTIF, (x + largeur, y - 10), "topright", gras=True)
    nouveau = t.curseur("poids", x + 4, y + 30, largeur - 8, poids, POIDS_MIN, POIDS_MAX, 0.5, poids_actif, SERIE_POIDS)
    if poids_actif:
        app.poids = float(nouveau)

    y = carte.y + 326
    t.texte("Température", 14, TEXTE if manuel else DISCRET, (x, y - 10))
    t.texte("—" if temperature is None else f"{temperature:.1f} °C", 15, TEXTE if temperature is not None else INACTIF, (x + largeur, y - 10), "topright", gras=True)
    nouvelle = t.curseur("temperature", x + 4, y + 30, largeur - 8, temperature, TEMPERATURE_MIN, TEMPERATURE_MAX, 0.5, manuel, SERIE_TEMPERATURE)
    if manuel:
        app.temperature = float(nouvelle)

    pygame.draw.line(t.ecran, LIGNE, (x, carte.y + 392), (x + largeur, carte.y + 392))
    t.texte("Fréquence d'envoi", 14, TEXTE, (x, carte.y + 412))
    options = [f"{secondes} s" for secondes in INTERVALLES]
    index = t.segments(pygame.Rect(x, carte.y + 438, largeur, 38), options, INTERVALLES.index(app.intervalle))
    if INTERVALLES[index] != app.intervalle:
        app.intervalle = INTERVALLES[index]
        app.moteur.envoyer({"commande": "intervalle", "secondes": app.intervalle})

    t.texte(f"Une mesure toutes les {app.intervalle} s", 13, DISCRET, (x, carte.y + 488))
    if manuel and instant["etat"] != MARCHE:
        t.texte("Tes valeurs partiront au démarrage.", 13, DISCRET, (x, carte.y + 510))
    if t.bouton(pygame.Rect(x, carte.bottom - 62, largeur, 42), "Ouvrir le dashboard web", "secondaire", not app.dashboard.ouverture, 14):
        app.dashboard.ouvrir()
    return change


def page_graphiques(app, lecture):
    t = app.toile
    en_tete(app, "Graphiques", "Historique enregistré dans la base")
    options = [f"{heures} h" for heures in PERIODES]
    selecteur = pygame.Rect(CONTENU_X + CONTENU_L - 280, 34, 280, 38)
    index = t.segments(selecteur, options, PERIODES.index(app.heures))
    app.heures = PERIODES[index]

    fin = lecture["historique_fin"] or time.time()
    debut = fin - app.heures * 3600
    points = lecture["historique"] if lecture["historique_heures"] == app.heures else []
    hauteur = (CONTENU_H - 28) // 3
    series = [
        ("temperature", "Température", "°C", SERIE_TEMPERATURE, (TEMPERATURE_MIN, TEMPERATURE_MAX)),
        ("poids", "Poids quand la chaise est occupée", "kg", SERIE_POIDS, (POIDS_MIN, POIDS_MAX)),
        ("occupation", "Taux d'occupation", "%", SERIE_OCCUPATION, (0, 100)),
    ]
    for rang, (cle, titre, unite, couleur, bornes) in enumerate(series):
        rectangle = pygame.Rect(CONTENU_X, CONTENU_Y + rang * (hauteur + 14), CONTENU_L, hauteur)
        t.graphique(rectangle, points, cle, titre, unite, couleur, bornes, debut, fin)


def page_donnees(app, lecture):
    t = app.toile
    total = lecture["total"]
    en_tete(app, "Données", f"{total} mesure(s)" + ("" if app.filtre == "tout" else " pour ce filtre"))
    selecteur = pygame.Rect(CONTENU_X + CONTENU_L - 460, 34, 300, 38)
    selection = FILTRES_TABLE.index(app.filtre)
    choix = t.segments(selecteur, ["Toutes", "Occupée", "Vide"], selection)
    if choix != selection:
        app.filtre = FILTRES_TABLE[choix]
        app.page_table = 0
    if t.bouton(pygame.Rect(CONTENU_X + CONTENU_L - 146, 34, 146, 38), "Exporter CSV", "secondaire", True, 14):
        app.exporter()

    carte = pygame.Rect(CONTENU_X, CONTENU_Y, CONTENU_L, CONTENU_H)
    t.carte(carte)
    colonnes = [carte.x + 24, carte.x + 300, carte.right - 260, carte.right - 24]
    y = carte.y + 16
    t.texte("Date et heure", 13, DISCRET, (colonnes[0], y), gras=True)
    t.texte("Présence", 13, DISCRET, (colonnes[1], y), gras=True)
    t.texte("Poids", 13, DISCRET, (colonnes[2], y), "topright", gras=True)
    t.texte("Température", 13, DISCRET, (colonnes[3], y), "topright", gras=True)
    pygame.draw.line(t.ecran, LIGNE, (carte.x + 1, carte.y + 46), (carte.right - 2, carte.y + 46))

    hauteur_ligne = 44
    lignes = lecture["lignes"] if lecture["table_cle"] == (app.filtre, app.page_table) else []
    for rang, ligne in enumerate(lignes[:LIGNES_TABLE]):
        zone = pygame.Rect(carte.x + 1, carte.y + 47 + rang * hauteur_ligne, carte.width - 2, hauteur_ligne)
        if zone.collidepoint(t.souris):
            pygame.draw.rect(t.ecran, CARTE_SURVOL, zone)
        centre = zone.centery
        date = vers_date(ligne["horodatage"]).strftime("%d/%m/%Y  %H:%M:%S")
        t.texte(date, 14, TEXTE, (colonnes[0], centre), "midleft")
        occupee = ligne["statut_occupation"]
        t.disque((colonnes[1] + 5, centre), 5, SERIE_OCCUPATION if occupee else INACTIF)
        t.texte("Occupée" if occupee else "Vide", 14, TEXTE if occupee else SECONDAIRE, (colonnes[1] + 20, centre), "midleft")
        t.texte(f"{ligne['poids']:.2f} kg", 14, TEXTE, (colonnes[2], centre), "midright")
        t.texte(f"{ligne['temperature']:.2f} °C", 14, TEXTE, (colonnes[3], centre), "midright")
        if rang < LIGNES_TABLE - 1:
            pygame.draw.line(t.ecran, LIGNE, (carte.x + 20, zone.bottom), (carte.right - 20, zone.bottom))
    if not lignes:
        message = "Chargement…" if lecture["table_cle"] != (app.filtre, app.page_table) else "Aucune mesure"
        t.texte(message, 14, DISCRET, carte.center, "center")

    pages = max(1, math.ceil(total / LIGNES_TABLE))
    app.page_table = min(app.page_table, pages - 1)
    bas = carte.bottom - 44
    t.texte(f"Page {app.page_table + 1} sur {pages}", 13, DISCRET, (carte.x + 24, bas + 16), "midleft")
    if t.bouton(pygame.Rect(carte.right - 216, bas, 96, 32), "Précédent", "secondaire", app.page_table > 0, 13):
        app.page_table -= 1
    if t.bouton(pygame.Rect(carte.right - 112, bas, 92, 32), "Suivant", "secondaire", app.page_table < pages - 1, 13):
        app.page_table += 1
    if carte.collidepoint(t.souris) and t.molette:
        app.page_table = max(0, min(pages - 1, app.page_table - t.molette))


def positions_noeuds(carte):
    haut = carte.y + 58
    return {
        "capteurs": (carte.x + 104, haut),
        "rust": (carte.x + 372, haut),
        "supabase": (carte.right - 104, haut),
        "interface": ((carte.x + 372 + carte.right - 104) // 2, carte.bottom - 44),
    }


def lien(t, a, b, libelle, actif, decalage=(0, -12)):
    couleur = DISCRET if actif else PISTE
    pygame.draw.aaline(t.ecran, couleur, a, b)
    milieu = ((a[0] + b[0]) / 2 + decalage[0], (a[1] + b[1]) / 2 + decalage[1])
    t.texte(libelle, 11, DISCRET, milieu, "center")


def noeud(t, centre, nom, actif, couleur):
    rectangle = pygame.Rect(0, 0, 156, 58)
    rectangle.center = centre
    t.forme(rectangle, couleur if actif else LIGNE, 12)
    t.forme(rectangle.inflate(-3, -3), CARTE_SURVOL if actif else CARTE, 11)
    titre, sous_titre = NOEUDS[nom]
    t.disque((rectangle.x + 18, rectangle.centery), 4, couleur if actif else INACTIF)
    t.texte(titre, 14, TEXTE if actif else SECONDAIRE, (rectangle.x + 32, rectangle.y + 8), gras=True)
    t.texte(sous_titre, 12, DISCRET, (rectangle.x + 32, rectangle.y + 30))


def page_communications(app, instant, lecture):
    t = app.toile
    en_tete(app, "Communications", "Tous les échanges entre les composants, en direct")
    evenements = app.journal.lire()
    maintenant = time.monotonic()

    schema = pygame.Rect(CONTENU_X, CONTENU_Y, CONTENU_L, 222)
    t.carte(schema)
    positions = positions_noeuds(schema)
    en_marche = instant["etat"] == MARCHE
    joignable = lecture["joignable"]
    decale = lambda p, d: (p[0] + d[0], p[1] + d[1])
    lien(t, positions["capteurs"], positions["rust"], "mesures", en_marche)
    lien(t, positions["rust"], positions["supabase"], "HTTPS · POST", en_marche)
    lien(t, positions["rust"], positions["interface"], "stdin / stdout", en_marche, (-52, 4))
    lien(t, positions["interface"], positions["supabase"], "HTTPS · GET", bool(joignable), (52, 4))

    for evenement in evenements[-60:]:
        retard = 0 if evenement["famille"] == "commande" else RETARDS.get((evenement["source"], evenement["cible"]), 0)
        age = maintenant - evenement["instant"] - retard
        if age < 0 or age > DUREE_PAQUET or evenement["source"] not in positions or evenement["cible"] not in positions:
            continue
        p = age / DUREE_PAQUET
        p = p * p * (3 - 2 * p)
        a, b = positions[evenement["source"]], positions[evenement["cible"]]
        centre = (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)
        couleur = CRITIQUE if evenement["niveau"] == "erreur" else FAMILLES[evenement["famille"]]
        t.disque(centre, 8, CARTE)
        t.disque(centre, 6, couleur)

    noeud(t, positions["capteurs"], "capteurs", en_marche, SERIE_OCCUPATION)
    noeud(t, positions["rust"], "rust", en_marche, BON)
    couleur_base = BON if joignable else CRITIQUE if joignable is False else INACTIF
    noeud(t, positions["supabase"], "supabase", joignable is not None, couleur_base)
    noeud(t, positions["interface"], "interface", True, BON)

    y = schema.bottom + 14
    bande = pygame.Rect(CONTENU_X, y, CONTENU_L, 68)
    t.carte(bande)
    colonne = (CONTENU_L - 40) // 4
    latence = f"{instant['latence']:.0f} ms" if instant["latence"] is not None else "—"
    petit_chiffre(t, bande.x + 20, bande.y + 10, colonne - 12, "Messages", app.journal.compteur)
    petit_chiffre(t, bande.x + 20 + colonne, bande.y + 10, colonne - 12, "Envois réussis", instant["reussis"])
    petit_chiffre(t, bande.x + 20 + 2 * colonne, bande.y + 10, colonne - 12, "Échecs", instant["echecs"], CRITIQUE if instant["echecs"] else TEXTE)
    petit_chiffre(t, bande.x + 20 + 3 * colonne, bande.y + 10, colonne - 12, "Temps de réponse", latence)

    carte = pygame.Rect(CONTENU_X, bande.bottom + 14, CONTENU_L, CONTENU_Y + CONTENU_H - bande.bottom - 14)
    journal(app, carte, evenements)


def journal(app, carte, evenements):
    t = app.toile
    t.carte(carte, "Journal")
    selection = FILTRES_JOURNAL.index(app.filtre_journal)
    choix = t.segments(pygame.Rect(carte.right - 500, carte.y + 8, 380, 30), ["Tout", "Commandes", "Capteurs", "Base"], selection, taille=12)
    if choix != selection:
        app.filtre_journal = FILTRES_JOURNAL[choix]
        app.defilement = 0
    if t.bouton(pygame.Rect(carte.right - 108, carte.y + 8, 92, 30), "Reprendre" if app.pause_journal is not None else "Pause", "secondaire", True, 12):
        app.basculer_pause(evenements)

    source = app.pause_journal if app.pause_journal is not None else evenements
    liste = [e for e in reversed(source) if app.filtre_journal is None or e["famille"] == app.filtre_journal]
    hauteur = 23
    haut = carte.y + 46
    capacite = max(1, (carte.bottom - haut - 8) // hauteur)
    maximum = max(0, len(liste) - capacite)
    if carte.collidepoint(t.souris) and t.molette:
        app.defilement -= t.molette * 3
    app.defilement = max(0, min(maximum, app.defilement))

    x = carte.x + 20
    for rang, evenement in enumerate(liste[app.defilement : app.defilement + capacite]):
        y = haut + rang * hauteur + hauteur // 2
        erreur = evenement["niveau"] == "erreur"
        t.disque((x + 3, y), 3, CRITIQUE if erreur else FAMILLES[evenement["famille"]])
        t.texte(evenement["heure"], 12, DISCRET, (x + 14, y), "midleft", mono=True)
        route = f"{NOEUDS[evenement['source']][0]} → {NOEUDS[evenement['cible']][0]}"
        t.texte(t.ajuster(route, 12, 196), 12, SECONDAIRE, (x + 86, y), "midleft")
        t.texte(evenement["action"], 12, TEXTE, (x + 292, y), "midleft", gras=True)
        t.texte(t.ajuster(evenement["detail"], 12, 300), 12, SECONDAIRE, (x + 376, y), "midleft")
        if evenement["statut"] is not None:
            t.texte(evenement["statut"], 12, CRITIQUE if erreur else SECONDAIRE, (carte.right - 92, y), "midright", mono=True)
        if evenement["duree"] is not None:
            t.texte(f"{evenement['duree']} ms", 12, DISCRET, (carte.right - 20, y), "midright", mono=True)
    if not liste:
        t.texte("Aucun échange pour l'instant", 13, DISCRET, ((carte.x + carte.right) // 2, (haut + carte.bottom) // 2), "center")


def icone(t, nom, x, y, couleur):
    if nom == "controle":
        for rang, position in enumerate((12, 5, 10)):
            ligne = y + 3 + rang * 6
            pygame.draw.line(t.ecran, couleur, (x, ligne), (x + 16, ligne), 2)
            t.disque((x + position, ligne), 3, couleur)
    elif nom == "graphiques":
        points = [(x, y + 15), (x + 5, y + 8), (x + 10, y + 12), (x + 16, y + 3)]
        pygame.draw.lines(t.ecran, couleur, False, points, 2)
    elif nom == "donnees":
        pygame.draw.rect(t.ecran, couleur, (x, y + 1, 16, 16), 2, border_radius=3)
        pygame.draw.line(t.ecran, couleur, (x, y + 7), (x + 15, y + 7), 2)
        pygame.draw.line(t.ecran, couleur, (x + 7, y + 7), (x + 7, y + 15), 2)
    else:
        pygame.draw.line(t.ecran, couleur, (x + 3, y + 14), (x + 8, y + 4), 2)
        pygame.draw.line(t.ecran, couleur, (x + 8, y + 4), (x + 14, y + 14), 2)
        pygame.draw.line(t.ecran, couleur, (x + 3, y + 14), (x + 14, y + 14), 2)
        for point in ((x + 3, y + 14), (x + 8, y + 4), (x + 14, y + 14)):
            t.disque(point, 3, couleur)


__all__ = [
    "ARRET",
    "ARRETE",
    "MARCHE",
    "MARGE",
    "PREPARATION",
    "FOND",
    "icone",
    "page_communications",
    "page_controle",
    "page_donnees",
    "page_graphiques",
]
