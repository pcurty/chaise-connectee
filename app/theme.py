from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

LARGEUR = 1180
HAUTEUR = 760
BARRE = 228
MARGE = 28
CONTENU_X = BARRE + MARGE
CONTENU_L = LARGEUR - CONTENU_X - MARGE
CONTENU_Y = 100
CONTENU_H = HAUTEUR - CONTENU_Y - MARGE

FOND = (20, 20, 19)
FOND_BARRE = (15, 15, 14)
CARTE = (26, 26, 25)
CARTE_SURVOL = (36, 36, 34)
PISTE = (46, 46, 43)
LIGNE = (44, 44, 41)
TEXTE = (240, 239, 236)
SECONDAIRE = (195, 194, 183)
DISCRET = (142, 141, 132)
INACTIF = (96, 96, 90)

SERIE_POIDS = (57, 135, 229)
SERIE_TEMPERATURE = (217, 89, 38)
SERIE_OCCUPATION = (25, 158, 112)

BON = (12, 163, 12)
ALERTE = (250, 178, 25)
CRITIQUE = (208, 59, 59)

POIDS_MIN = 0
POIDS_MAX = 150
TEMPERATURE_MIN = 10
TEMPERATURE_MAX = 40
INTERVALLES = [1, 2, 5, 10]
PERIODES = [1, 6, 24, 48]
LIGNES_TABLE = 12

POLICES = [
    (
        "/mnt/c/Windows/Fonts/segoeui.ttf",
        "/mnt/c/Windows/Fonts/seguisb.ttf",
        "/mnt/c/Windows/Fonts/consola.ttf",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ),
]
