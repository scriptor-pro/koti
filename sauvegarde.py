# koti — suivi de rituels quotidiens
# Copyright (C) 2026 scriptor-pro
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sauvegarde des données : commit git local dans le dossier de données."""
import os
import subprocess
import sys

FICHIERS = ("taches.json", "completions.csv")

# Variables qui rediraient git vers un autre dépôt que le dossier de données.
VARIABLES_GIT = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_COMMON_DIR", "GIT_PREFIX")


def _git(dossier, *arguments):
    environnement = {k: v for k, v in os.environ.items() if k not in VARIABLES_GIT}
    return subprocess.run(["git", "-C", str(dossier), *arguments], capture_output=True, text=True,
                          errors="replace", stdin=subprocess.DEVNULL, env=environnement)


def enregistrer(dossier, message):
    """Committe taches.json et completions.csv si le dossier de données est un dépôt git.

    Sans dépôt, ou sans changement, ne fait rien. Un échec de git est signalé sur la sortie
    d'erreur sans lever d'exception : la sauvegarde ne doit jamais empêcher un cochage.
    """
    if not (dossier / ".git").exists():
        return
    presents = [f for f in FICHIERS if (dossier / f).exists()]
    if not presents:
        return
    try:
        resultat = _git(dossier, "add", "--", *presents)
        if resultat.returncode == 0:
            # 0 : rien à committer ; 1 : des changements ; autre : erreur de git.
            resultat = _git(dossier, "diff", "--cached", "--quiet", "--", *presents)
            if resultat.returncode == 0:
                return
            if resultat.returncode == 1:
                resultat = _git(dossier, "commit", "-q", "-m", message, "--", *presents)
    except (OSError, ValueError) as exc:
        print(f"AVERTISSEMENT — sauvegarde git non faite : {getattr(exc, 'strerror', None) or type(exc).__name__}.", file=sys.stderr)
        return
    if resultat.returncode != 0:
        detail = " ".join((resultat.stderr or resultat.stdout).split()) or f"code {resultat.returncode}"
        print(f"AVERTISSEMENT — sauvegarde git non faite : {detail}", file=sys.stderr)
