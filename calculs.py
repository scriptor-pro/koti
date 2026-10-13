# koti — suivi de rituels quotidiens
# Copyright (C) 2026 scriptor-pro
# SPDX-License-Identifier: GPL-3.0-or-later
"""Calculs de koti : fonctions pures, sans accès disque ni horloge."""
import math
from datetime import date, timedelta

UN_JOUR = timedelta(days=1)


def serie_en_cours(dates, aujourdhui):
    """Jours consécutifs faits, en remontant depuis aujourd'hui s'il est fait, sinon depuis hier."""
    jour = aujourdhui if aujourdhui in dates else aujourdhui - UN_JOUR
    n = 0
    while jour in dates:
        n += 1
        jour -= UN_JOUR
    return n


def record(dates):
    """Plus longue suite de jours consécutifs faits."""
    meilleur = 0
    for d in dates:
        if d - UN_JOUR in dates:
            continue
        n = 1
        while d + n * UN_JOUR in dates:
            n += 1
        meilleur = max(meilleur, n)
    return meilleur


def taux(dates, debut, aujourdhui, fenetre=None):
    """(jours faits, jours écoulés) depuis debut, ou sur les `fenetre` derniers jours.

    Aujourd'hui n'entre dans la période que s'il est fait.
    """
    fin = aujourdhui if aujourdhui in dates else aujourdhui - UN_JOUR
    depart = debut if fenetre is None else max(debut, fin - (fenetre - 1) * UN_JOUR)
    if fin < depart:
        return (0, 0)
    return (sum(1 for d in dates if depart <= d <= fin), (fin - depart).days + 1)


def calendrier(dates, debut, aujourdhui, sans_serie=False):
    """Un jour par entrée de debut à aujourd'hui : [date ISO, "fait" | "manque" | "attente"].

    Sans série, les jours non faits sont "neutre" : ni manque ni attente.
    """
    jours = []
    jour = debut
    while jour <= aujourdhui:
        if jour in dates:
            etat = "fait"
        elif sans_serie:
            etat = "neutre"
        elif jour == aujourdhui:
            etat = "attente"
        else:
            etat = "manque"
        jours.append([jour.isoformat(), etat])
        jour += UN_JOUR
    return jours


def heure_moyenne(heures):
    """Moyenne circulaire d'heures "HH:MM" : ("HH:MM", nombre d'heures prises en compte) ou None.

    Les chaînes vides sont exclues. None aussi quand la moyenne n'est pas définie
    (heures qui s'annulent, par exemple 06:00 et 18:00).
    """
    minutes = [int(h[:2]) * 60 + int(h[3:5]) for h in heures if h]
    if not minutes:
        return None
    angles = [2 * math.pi * m / 1440 for m in minutes]
    s = sum(math.sin(a) for a in angles)
    c = sum(math.cos(a) for a in angles)
    if math.hypot(s, c) < 1e-6 * len(minutes):
        return None
    moyenne = round(math.atan2(s, c) * 1440 / (2 * math.pi)) % 1440
    return (f"{moyenne // 60:02d}:{moyenne % 60:02d}", len(minutes))


def statistiques(tache, completions, maintenant):
    """Tout ce que la liste et la page affichent pour un rituel."""
    aujourdhui = maintenant.date()
    iso = aujourdhui.isoformat()
    lignes = [c for c in completions if c["tache"] == tache["id"] and c["date"] <= iso]
    dates = {date.fromisoformat(c["date"]) for c in lignes}
    debut = min([date.fromisoformat(tache["debut"]), aujourdhui, *dates])
    fait = aujourdhui in dates
    heure_fixe = tache.get("heure_fixe")
    moyenne = heure_moyenne([c["heure"] for c in lignes])
    sans_serie = bool(tache.get("sans_serie"))
    return {
        "id": tache["id"],
        "titre": tache["titre"],
        "notes": tache.get("notes") or "",
        "heure_fixe": heure_fixe,
        "fait_aujourdhui": fait,
        "heure_du_jour": next((c["heure"] for c in lignes if c["date"] == iso), ""),
        "cochable": not fait and not (heure_fixe and maintenant.strftime("%H:%M") < heure_fixe),
        "sans_serie": sans_serie,
        "serie": None if sans_serie else serie_en_cours(dates, aujourdhui),
        "record": None if sans_serie else record(dates),
        "total": len(dates),
        "taux": None if sans_serie else {
            "sept": list(taux(dates, debut, aujourdhui, 7)),
            "trente": list(taux(dates, debut, aujourdhui, 30)),
            "tout": list(taux(dates, debut, aujourdhui)),
        },
        "heure_moyenne": moyenne[0] if moyenne else None,
        "nb_heures": moyenne[1] if moyenne else 0,
        "calendrier": calendrier(dates, debut, aujourdhui, sans_serie),
    }
