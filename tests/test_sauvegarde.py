import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sauvegarde


def git(dossier, *arguments):
    return subprocess.run(["git", "-C", str(dossier), *arguments],
                          capture_output=True, text=True, check=True).stdout


def initialiser_depot(dossier):
    git(dossier, "init", "-q")
    git(dossier, "config", "user.name", "Essai")
    git(dossier, "config", "user.email", "essai@example.com")
    git(dossier, "config", "commit.gpgsign", "false")


@unittest.skipUnless(shutil.which("git"), "git absent")
class Enregistrer(unittest.TestCase):
    def setUp(self):
        # La configuration git de l'utilisateur (hooksPath, signature…) ne doit pas changer le résultat.
        isolation = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
        isolation.start()
        self.addCleanup(isolation.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        (self.dossier / "taches.json").write_text('{"taches": []}', encoding="utf-8")
        (self.dossier / "completions.csv").write_text("date,heure,tache\n", encoding="utf-8")

    def enregistrer(self, message="fait : lecture (2026-10-13)"):
        erreurs = io.StringIO()
        with contextlib.redirect_stderr(erreurs):
            sauvegarde.enregistrer(self.dossier, message)
        return erreurs.getvalue()

    def test_sans_depot_ne_fait_rien(self):
        self.assertEqual(self.enregistrer(), "")
        self.assertFalse((self.dossier / ".git").exists())

    def test_premier_commit_dans_un_depot_vide(self):
        initialiser_depot(self.dossier)
        self.assertEqual(self.enregistrer(), "")
        self.assertEqual(git(self.dossier, "log", "--format=%s").strip(), "fait : lecture (2026-10-13)")
        self.assertEqual(git(self.dossier, "ls-files").split(), ["completions.csv", "taches.json"])

    def test_sans_changement_pas_de_commit(self):
        initialiser_depot(self.dossier)
        self.enregistrer()
        self.assertEqual(self.enregistrer("page"), "")
        self.assertEqual(git(self.dossier, "rev-list", "--count", "HEAD").strip(), "1")

    def test_changement_du_journal_commite(self):
        initialiser_depot(self.dossier)
        self.enregistrer()
        with (self.dossier / "completions.csv").open("a", encoding="utf-8") as f:
            f.write("2026-10-13,10:04,lecture\n")
        self.enregistrer("fait : lecture (2026-10-13)")
        self.assertEqual(git(self.dossier, "rev-list", "--count", "HEAD").strip(), "2")
        self.assertEqual(git(self.dossier, "status", "--porcelain").strip(), "")

    def test_page_et_secrets_jamais_suivis(self):
        initialiser_depot(self.dossier)
        (self.dossier / "koti.html").write_text("<html></html>", encoding="utf-8")
        (self.dossier / ".bunny_config.json").write_text('{"storage_access_key": "CLE-FACTICE"}', encoding="utf-8")
        self.enregistrer()
        self.assertEqual(git(self.dossier, "ls-files").split(), ["completions.csv", "taches.json"])

    def test_git_absent_avertit_sans_lever(self):
        initialiser_depot(self.dossier)
        with mock.patch("sauvegarde.subprocess.run", side_effect=FileNotFoundError(2, "No such file", "git")):
            erreurs = self.enregistrer()
        self.assertIn("AVERTISSEMENT — sauvegarde git non faite", erreurs)

    def test_commit_refuse_avertit_sans_lever(self):
        initialiser_depot(self.dossier)
        crochet = self.dossier / ".git" / "hooks" / "pre-commit"
        crochet.parent.mkdir(exist_ok=True)
        crochet.write_text("#!/bin/sh\necho refus-du-crochet >&2\nexit 1\n", encoding="utf-8")
        crochet.chmod(0o755)
        erreurs = self.enregistrer()
        self.assertIn("AVERTISSEMENT — sauvegarde git non faite", erreurs)
        self.assertIn("refus-du-crochet", erreurs)

    def test_commit_limite_aux_fichiers_de_donnees(self):
        initialiser_depot(self.dossier)
        (self.dossier / "koti.html").write_text("<html></html>", encoding="utf-8")
        git(self.dossier, "add", "koti.html")
        self.enregistrer()
        self.assertEqual(git(self.dossier, "show", "--name-only", "--format=", "HEAD").split(),
                         ["completions.csv", "taches.json"])

    def test_git_dir_herite_ne_detourne_pas_le_commit(self):
        initialiser_depot(self.dossier)
        autre_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(autre_tmp.cleanup)
        autre = Path(autre_tmp.name)
        initialiser_depot(autre)
        with mock.patch.dict(os.environ, {"GIT_DIR": str(autre / ".git")}):
            self.assertEqual(self.enregistrer(), "")
        # Les vérifications se font hors du bloc : git n'y hérite plus de GIT_DIR.
        self.assertEqual(git(self.dossier, "rev-list", "--count", "HEAD").strip(), "1")
        self.assertEqual(git(autre, "rev-list", "--count", "--all").strip(), "0")

    def test_sortie_de_git_non_utf8_n_leve_pas(self):
        initialiser_depot(self.dossier)
        crochet = self.dossier / ".git" / "hooks" / "pre-commit"
        crochet.parent.mkdir(exist_ok=True)
        crochet.write_text("#!/bin/sh\nprintf '\\377\\376 refus\\n' >&2\nexit 1\n", encoding="utf-8")
        crochet.chmod(0o755)
        erreurs = self.enregistrer()
        self.assertIn("AVERTISSEMENT — sauvegarde git non faite", erreurs)

    def test_aucun_fichier_de_donnees(self):
        initialiser_depot(self.dossier)
        (self.dossier / "taches.json").unlink()
        (self.dossier / "completions.csv").unlink()
        self.assertEqual(self.enregistrer(), "")


if __name__ == "__main__":
    unittest.main()
