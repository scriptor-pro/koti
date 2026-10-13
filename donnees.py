# koti — suivi de rituels quotidiens
# Copyright (C) 2026 scriptor-pro
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lecture et écriture des données de koti : taches.json et completions.csv."""
import csv
import json
from datetime import datetime

COLONNES = ["date", "heure", "tache"]


class ErreurDonnees(Exception):
    pass


def _date_valide(texte):
    try:
        return datetime.strptime(texte, "%Y-%m-%d").strftime("%Y-%m-%d") == texte
    except ValueError:
        return False


def _heure_valide(texte):
    try:
        return datetime.strptime(texte, "%H:%M").strftime("%H:%M") == texte
    except ValueError:
        return False


def lire_taches(chemin):
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErreurDonnees(f"{chemin} introuvable.") from None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ErreurDonnees(f"{chemin} illisible : {exc}") from None
    taches = data.get("taches") if isinstance(data, dict) else None
    if not isinstance(taches, list) or not taches:
        raise ErreurDonnees(f"{chemin} : liste « taches » absente ou vide.")
    vus = set()
    for t in taches:
        # Vérifier que t est un dictionnaire
        if not isinstance(t, dict):
            raise ErreurDonnees(f"{chemin} : champ « id » manquant dans {t!r}.")

        # Vérifier que les champs requis existent et sont des chaînes non vides
        for cle in ("id", "titre", "debut"):
            value = t.get(cle)
            if not isinstance(value, str) or not value:
                raise ErreurDonnees(f"{chemin} : champ « {cle} » manquant dans {t!r}.")

        # Vérifier le type de heure_fixe s'il est présent et non None
        heure_fixe = t.get("heure_fixe")
        if heure_fixe is not None and not isinstance(heure_fixe, str):
            raise ErreurDonnees(f"{chemin} : heure_fixe doit être une chaîne pour {t['id']}.")

        # Vérifier que sans_serie, s'il est présent, est un booléen
        if "sans_serie" in t and not isinstance(t["sans_serie"], bool):
            raise ErreurDonnees(f"{chemin} : sans_serie doit être un booléen pour {t['id']}.")

        # Valider les formats
        if not _date_valide(t["debut"]):
            raise ErreurDonnees(f"{chemin} : debut invalide pour {t['id']} : « {t['debut']} » (attendu AAAA-MM-JJ).")
        if heure_fixe and not _heure_valide(heure_fixe):
            raise ErreurDonnees(f"{chemin} : heure_fixe invalide pour {t['id']} : « {heure_fixe} » (attendu HH:MM).")

        # Vérifier les doublons
        if t["id"] in vus:
            raise ErreurDonnees(f"{chemin} : identifiant « {t['id']} » en double.")
        vus.add(t["id"])
    return taches


def lire_completions(chemin):
    try:
        f = chemin.open(encoding="utf-8", newline="")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise ErreurDonnees(f"{chemin} illisible : {exc}") from None

    try:
        with f:
            lecteur = csv.reader(f)
            entete = next(lecteur, None)
            if entete != COLONNES:
                raise ErreurDonnees(f"{chemin} : en-tête inattendu {entete!r}, attendu {COLONNES!r}.")
            lignes = []
            for champs in lecteur:
                if not champs:
                    continue
                numero = lecteur.line_num
                if len(champs) != 3:
                    raise ErreurDonnees(f"{chemin}, ligne {numero} : 3 champs attendus, {len(champs)} trouvés.")
                jour, heure, tache = (c.strip() for c in champs)
                if not _date_valide(jour):
                    raise ErreurDonnees(f"{chemin}, ligne {numero} : date invalide « {jour} » (attendu AAAA-MM-JJ).")
                if heure and not _heure_valide(heure):
                    raise ErreurDonnees(f"{chemin}, ligne {numero} : heure invalide « {heure} » (attendu HH:MM ou vide).")
                if not tache:
                    raise ErreurDonnees(f"{chemin}, ligne {numero} : tâche manquante.")
                lignes.append({"date": jour, "heure": heure, "tache": tache})
    except (UnicodeDecodeError, csv.Error, OSError) as exc:
        raise ErreurDonnees(f"{chemin} illisible : {exc}") from None
    return lignes


def ajouter_completions(chemin, lignes):
    """Ajoute des lignes en fin de journal, sans le réécrire ; le crée avec son en-tête s'il n'existe pas."""
    try:
        try:
            contenu = chemin.read_bytes()
        except FileNotFoundError:
            contenu = None
            chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("a", encoding="utf-8", newline="") as f:
            ecrivain = csv.writer(f, lineterminator="\n")
            if contenu is None:
                ecrivain.writerow(COLONNES)
            elif contenu and not contenu.endswith(b"\n"):
                f.write("\n")
            for l in lignes:
                ecrivain.writerow([l["date"], l["heure"], l["tache"]])
    except OSError as exc:
        raise ErreurDonnees(f"{chemin} : écriture impossible ({exc.strerror or type(exc).__name__}).") from None
