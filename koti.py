#!/usr/bin/env python3
# koti — suivi de rituels quotidiens
# Copyright (C) 2026 scriptor-pro
# SPDX-License-Identifier: GPL-3.0-or-later
"""koti — suivi des tâches quotidiennes.

Usage : koti                      liste du jour (☑ faite / ☐ à faire, série, heure moyenne)
        koti fait NOM [NOM ...] [--heure HH:MM] [--date AAAA-MM-JJ] [--no-upload]
        koti page [--no-upload] [--configure-cache]
  fait    ajoute les complétions au journal, puis régénère et publie la page une seule fois.
  page    régénère et publie la page sans rien cocher.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

DOSSIER_CODE = Path(__file__).resolve().parent
if str(DOSSIER_CODE) not in sys.path:
    sys.path.insert(0, str(DOSSIER_CODE))

import calculs  # noqa: E402
import donnees  # noqa: E402
import publication  # noqa: E402
import sauvegarde  # noqa: E402


class ErreurCommande(Exception):
    pass


GABARIT = DOSSIER_CODE / "gabarit.html"


def dossier_donnees():
    """Le dossier des données : $KOTI_DONNEES s'il est défini et non vide, sinon ~/.local/share/koti."""
    choisi = os.environ.get("KOTI_DONNEES")
    return Path(choisi).expanduser() if choisi else Path.home() / ".local" / "share" / "koti"


def normaliser(texte):
    """Minuscules, sans accents, ponctuation remplacée par des espaces simples."""
    sans_accents = "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).split())


def trouver_tache(nom, taches):
    """La tâche désignée par nom : identifiant exact, sinon début d'identifiant ou mots du titre."""
    cle = normaliser(nom)
    if not cle:
        raise ErreurCommande(f"Nom de tâche vide : « {nom} ».")
    for t in taches:
        if normaliser(t["id"]) == cle:
            return t
    candidats = [
        t for t in taches
        if normaliser(t["id"]).startswith(cle) or f" {cle}" in f" {normaliser(t['titre'])}"
    ]
    if len(candidats) == 1:
        return candidats[0]
    if not candidats:
        connues = ", ".join(t["id"] for t in taches)
        raise ErreurCommande(f"Tâche inconnue : « {nom} ». Tâches connues : {connues}.")
    raise ErreurCommande(f"Nom ambigu : « {nom} » peut désigner {', '.join(t['id'] for t in candidats)}.")


def preparer_cochage(noms, taches, completions, maintenant, jour=None, heure=None):
    """Lignes à ajouter au journal et messages à afficher.

    Lève ErreurCommande, sans rien préparer, si un nom est inconnu ou ambigu ou si la date est future.
    Sans jour : aujourd'hui, à l'heure de déclaration. Avec jour et sans heure : heure vide.
    """
    aujourdhui = maintenant.date()
    cible = jour or aujourdhui
    if cible > aujourdhui:
        raise ErreurCommande(f"Date future refusée : {cible.isoformat()}.")
    if heure is None:
        heure = maintenant.strftime("%H:%M") if jour is None else ""
    choisies = []
    for nom in noms:
        t = trouver_tache(nom, taches)
        if t not in choisies:
            choisies.append(t)
    iso = cible.isoformat()
    deja = {c["tache"] for c in completions if c["date"] == iso}
    lignes, messages = [], []
    for t in choisies:
        if t["id"] in deja:
            messages.append(f"IGNORÉE — {t['id']} : déjà cochée le {iso}.")
        elif cible == aujourdhui and t.get("heure_fixe") and maintenant.strftime("%H:%M") < t["heure_fixe"]:
            messages.append(f"REFUSÉE — {t['id']} : pas avant {t['heure_fixe']}.")
        else:
            lignes.append({"date": iso, "heure": heure, "tache": t["id"]})
            messages.append(f"OK — {t['id']} cochée ({iso}{', ' + heure if heure else ''}).")
    return lignes, messages


def texte_liste(taches, completions, maintenant):
    """La liste du jour, telle qu'affichée par « koti » sans argument."""
    sorties = [f"koti — {maintenant.strftime('%Y-%m-%d, %H:%M')}"]
    faites = cochables = suivis = 0
    for t in taches:
        s = calculs.statistiques(t, completions, maintenant)
        details = []
        if not s["sans_serie"]:
            suivis += 1
        if s["fait_aujourdhui"]:
            if not s["sans_serie"]:
                faites += 1
            details.append(f"faite à {s['heure_du_jour']}" if s["heure_du_jour"] else "faite")
        elif s["cochable"]:
            cochables += 1
        else:
            details.append(f"pas avant {s['heure_fixe']}")
        if s["sans_serie"]:
            details.append(f"{s['total']} session{'s' if s['total'] > 1 else ''}")
        else:
            details.append(f"série {s['serie']}")
        if s["heure_moyenne"]:
            details.append(f"en moyenne à {s['heure_moyenne']}")
        case = "☑" if s["fait_aujourdhui"] else "☐"
        sorties.append(f"{case} {s['id']} — {s['titre']} · " + " · ".join(details))
    sorties.append(f"{faites} sur {suivis} faites, {cochables} cochables maintenant.")
    return "\n".join(sorties)


MOTIF_DONNEES = re.compile(
    r'(<script type="application/json" id="data-source">\n)(.*?)(\n</script>)',
    re.DOTALL,
)


def construire_donnees(taches, completions, maintenant):
    """Le contenu du bloc de données de la page."""
    stats = [calculs.statistiques(t, completions, maintenant) for t in taches]
    return {
        "genere_le": maintenant.strftime("%Y-%m-%dT%H:%M:%S"),
        "aujourdhui": maintenant.date().isoformat(),
        "faites_aujourdhui": sum(1 for s in stats if s["fait_aujourdhui"] and not s["sans_serie"]),
        "suivis": sum(1 for s in stats if not s["sans_serie"]),
        "taches": stats,
    }


def generer_page(html, donnees):
    """Remplace le bloc data-source de la page par les données fournies."""
    m = MOTIF_DONNEES.search(html)
    if not m:
        raise ErreurCommande("Bloc data-source introuvable dans gabarit.html.")
    # Tout « < » est échappé (\u003c, JSON valide) : ni </script> ni <!--<script ne peuvent perturber l'analyseur HTML.
    bloc = json.dumps(donnees, ensure_ascii=False, indent=1).replace("<", "\\u003c")
    return html[: m.start(2)] + bloc + html[m.end(2):]


def ecrire_page(dossier, taches, completions, maintenant, gabarit=GABARIT):
    """Écrit dossier/koti.html à partir du gabarit, qui n'est jamais modifié."""
    try:
        html = gabarit.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ErreurCommande(f"{gabarit} introuvable.") from None
    nouveau = generer_page(html, construire_donnees(taches, completions, maintenant))
    chemin = dossier / "koti.html"
    # Écriture atomique : la page précédente reste entière tant que la nouvelle n'est pas complète.
    temporaire = chemin.with_name(chemin.name + ".tmp")
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        temporaire.write_text(nouveau, encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError as exc:
        raise ErreurCommande(f"{chemin} : écriture impossible ({exc.strerror or type(exc).__name__}).") from None
    finally:
        try:
            temporaire.unlink(missing_ok=True)
        except OSError:
            pass
    print(f"OK — koti.html régénéré ({len(taches)} rituels).")


def _analyser(valeur, motif, attendu):
    """La valeur d'une option --heure ou --date, validée ; None si l'option est absente."""
    if valeur is None:
        return None
    try:
        analysee = datetime.strptime(valeur, motif)
    except ValueError:
        raise ErreurCommande(f"Valeur invalide « {valeur} », attendu {attendu}.") from None
    return analysee


EXEMPLES = """\
Exemples (« lecture » et « marche » sont des noms de rituels fictifs) :
  koti                                   liste du jour
  koti fait lecture marche               cocher deux rituels, maintenant
  koti fait lecture --heure 08:15        cocher en précisant l'heure réelle
  koti fait marche --date 2026-10-12     cocher pour un jour passé
  koti page                              régénérer et republier la page
"""


class _AideEnFrancais(argparse.RawDescriptionHelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, actions, groups, prefix="utilisation : ")


def _texte_rituels(dossier):
    """La liste des rituels pour l'aide ; chaîne vide si taches.json est absent ou illisible."""
    try:
        taches = donnees.lire_taches(dossier / "taches.json")
    except donnees.ErreurDonnees:
        return ""
    largeur = max(len(t["id"]) for t in taches)
    lignes = ["Rituels :"]
    for t in taches:
        precision = f" (pas avant {t['heure_fixe']})" if t.get("heure_fixe") else ""
        lignes.append(f"  {t['id']:<{largeur}}  {t['titre']}{precision}")
    return "\n".join(lignes) + "\n"


def _nouvel_analyseur(sous, nom, **options):
    """Un analyseur (principal si sous est None, sinon sous-commande) à l'aide en français."""
    options.update(formatter_class=_AideEnFrancais, add_help=False)
    analyseur = sous.add_parser(nom, **options) if sous else argparse.ArgumentParser(prog=nom, **options)
    # argparse ajoute « : » au titre ; l'espace finale donne la ponctuation française.
    analyseur._positionals.title = "arguments "
    analyseur._optionals.title = "options "
    analyseur.add_argument("-h", "--help", action="help", help="afficher cette aide et quitter")
    return analyseur


def _construire_analyseur(dossier):
    analyseur = _nouvel_analyseur(
        None, "koti",
        description="Suivi des tâches quotidiennes.\n"
                    "Sans commande, affiche la liste du jour : ☑ faite / ☐ à faire, série en cours, heure moyenne.",
        epilog="\n".join(filter(None, [EXEMPLES, _texte_rituels(dossier)])),
    )
    sous = analyseur.add_subparsers(dest="commande", title="commandes ", metavar="{fait,page}", prog="koti")

    fait = _nouvel_analyseur(
        sous, "fait", help="cocher une ou plusieurs tâches, puis régénérer et publier la page",
        description="Ajoute les complétions au journal, puis régénère et publie la page une seule fois.\n"
                    "Une tâche déjà cochée ce jour-là est ignorée ; un nom inconnu ou ambigu annule toute la commande.",
    )
    fait.add_argument("noms", nargs="+", metavar="NOM",
                      help="rituel à cocher : identifiant, début d'identifiant ou mots du titre "
                           "(sans tenir compte des accents ni de la casse)")
    fait.add_argument("--heure", metavar="HH:MM",
                      help="heure à inscrire ; par défaut l'heure de déclaration (maintenant)")
    fait.add_argument("--date", metavar="AAAA-MM-JJ",
                      help="cocher pour un jour passé ; sans --heure, l'heure reste vide")
    fait.add_argument("--no-upload", action="store_true", help="ne pas publier la page")

    page = _nouvel_analyseur(
        sous, "page", help="régénérer et publier la page, sans rien cocher",
        description="Régénère la page à partir du journal et la publie, sans rien cocher.",
    )
    page.add_argument("--no-upload", action="store_true", help="ne pas publier la page")
    page.add_argument("--configure-cache", action="store_true",
                      help="poser l'Edge Rule bunny « Cache-Control: no-cache » sur la page "
                           "(une fois, ou après recréation de la pull zone)")
    return analyseur


def _verifier_taches(dossier):
    """Explique comment commencer quand le dossier de données n'a pas encore de taches.json."""
    chemin = dossier / "taches.json"
    try:
        chemin.stat()
    except (FileNotFoundError, NotADirectoryError):
        raise ErreurCommande(
            f"{chemin} introuvable. Pour commencer avec les rituels d'exemple :\n"
            f"  mkdir -p {dossier} && cp {DOSSIER_CODE / 'taches.exemple.json'} {chemin}"
        ) from None
    except OSError:
        pass  # lire_taches signalera le fichier illisible


def main(argv=None, dossier=None, maintenant=None):
    maintenant = maintenant or datetime.now()
    dossier = dossier or dossier_donnees()
    args = _construire_analyseur(dossier).parse_args(argv)

    try:
        _verifier_taches(dossier)
        taches = donnees.lire_taches(dossier / "taches.json")
        completions = donnees.lire_completions(dossier / "completions.csv")
        if args.commande is None:
            print(texte_liste(taches, completions, maintenant))
            return 0
        message = "page"
        if args.commande == "fait":
            heure = _analyser(args.heure, "%H:%M", "HH:MM")
            jour = _analyser(args.date, "%Y-%m-%d", "AAAA-MM-JJ")
            lignes, messages = preparer_cochage(
                args.noms, taches, completions, maintenant,
                jour=jour.date() if jour else None,
                heure=heure.strftime("%H:%M") if heure else None,
            )
            if not lignes:
                print("\n".join(messages))
                print("Rien à cocher — aucun fichier modifié.")
                return 1
            # Écrire d'abord : « OK … cochée » ne doit s'afficher que si le journal est à jour.
            donnees.ajouter_completions(dossier / "completions.csv", lignes)
            print("\n".join(messages))
            completions = completions + lignes
            message = f"fait : {', '.join(l['tache'] for l in lignes)} ({lignes[0]['date']})"
        # Avant la page et la publication : un échec en aval ne laisse pas le journal sans sauvegarde.
        sauvegarde.enregistrer(dossier, message)
        ecrire_page(dossier, taches, completions, maintenant)
        sys.stdout.flush()
        if args.commande == "page" and args.configure_cache:
            publication.assurer_edge_rule(dossier)
        if not args.no_upload:
            publication.publier(dossier)
        return 0
    except (ErreurCommande, donnees.ErreurDonnees, publication.ErreurPublication) as exc:
        print(f"ERREUR — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
