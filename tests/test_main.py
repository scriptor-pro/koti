import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import koti
MATIN = datetime(2026, 10, 13, 10, 4)
TACHES = {"taches": [
    {"id": "lecture", "titre": "Lecture du soir", "debut": "2026-10-11", "heure_fixe": None, "notes": ""},
    {"id": "marche", "titre": "Marche", "debut": "2026-10-11", "heure_fixe": "12:00", "notes": ""},
]}
JOURNAL = "date,heure,tache\n2026-10-12,09:00,lecture\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        (self.dossier / "taches.json").write_text(json.dumps(TACHES, ensure_ascii=False), encoding="utf-8")
        (self.dossier / "completions.csv").write_text(JOURNAL, encoding="utf-8")

    def lancer(self, *argv):
        sortie, erreurs = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreurs):
            code = koti.main(list(argv), dossier=self.dossier, maintenant=MATIN)
        return code, sortie.getvalue(), erreurs.getvalue()

    def journal(self):
        return (self.dossier / "completions.csv").read_text(encoding="utf-8")


class Main(Base):
    def test_liste_par_defaut(self):
        code, sortie, _ = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("☐ lecture — Lecture du soir · série 1", sortie)
        self.assertEqual(self.journal(), JOURNAL)

    def test_fait_ecrit_regenere_et_ignore_la_publication_sans_config(self):
        code, sortie, _ = self.lancer("fait", "lecture")
        self.assertEqual(code, 0)
        self.assertEqual(self.journal(), JOURNAL + "2026-10-13,10:04,lecture\n")
        self.assertIn("OK — lecture cochée (2026-10-13, 10:04).", sortie)
        self.assertIn("koti.html régénéré", sortie)
        self.assertIn("publication ignorée", sortie)
        self.assertIn('"serie": 2', (self.dossier / "koti.html").read_text(encoding="utf-8"))

    def test_echec_de_publication_laisse_le_journal_ecrit(self):
        config = {"storage_endpoint": "https://storage.exemple.test/zone", "storage_access_key": "CLE-FACTICE",
                  "pull_zone": "zone", "public_hostname": "koti.exemple.test",
                  "token_auth_security_key": "jeton-factice", "remote_filename": "koti.html",
                  "token_validity_seconds": 864000}
        (self.dossier / ".bunny_config.json").write_text(json.dumps(config), encoding="utf-8")
        with mock.patch("publication.subprocess.run") as run, \
                mock.patch("publication._lire_cle_api", return_value=None):
            run.return_value.stdout = "401"
            code, sortie, erreurs = self.lancer("fait", "lecture")
        self.assertEqual(code, 1)
        self.assertIn("OK — lecture cochée", sortie)
        self.assertIn("ERREUR", erreurs)
        self.assertNotIn("CLE-FACTICE", erreurs)
        self.assertEqual(self.journal(), JOURNAL + "2026-10-13,10:04,lecture\n")

    def test_fait_avec_heure_et_date(self):
        code, _, _ = self.lancer("fait", "lecture", "--date", "2026-10-11", "--heure", "21:30", "--no-upload")
        self.assertEqual(code, 0)
        self.assertEqual(self.journal(), JOURNAL + "2026-10-11,21:30,lecture\n")

    def test_nom_inconnu_n_ecrit_rien(self):
        code, _, erreurs = self.lancer("fait", "lecture", "vaisselle")
        self.assertEqual(code, 1)
        self.assertIn("ERREUR", erreurs)
        self.assertEqual(self.journal(), JOURNAL)

    def test_rien_a_cocher(self):
        code, sortie, _ = self.lancer("fait", "marche")
        self.assertEqual(code, 1)
        self.assertIn("REFUSÉE", sortie)
        self.assertIn("Rien à cocher", sortie)
        self.assertEqual(self.journal(), JOURNAL)

    def test_heure_invalide(self):
        code, _, erreurs = self.lancer("fait", "lecture", "--heure", "9h30")
        self.assertEqual(code, 1)
        self.assertIn("9h30", erreurs)
        self.assertEqual(self.journal(), JOURNAL)

    def test_date_invalide(self):
        code, _, erreurs = self.lancer("fait", "lecture", "--date", "hier")
        self.assertEqual(code, 1)
        self.assertIn("hier", erreurs)

    def test_page_sans_cocher(self):
        code, sortie, _ = self.lancer("page", "--no-upload")
        self.assertEqual(code, 0)
        self.assertIn("koti.html régénéré", sortie)
        self.assertNotIn("publication", sortie)
        self.assertEqual(self.journal(), JOURNAL)

    def test_journal_corrompu(self):
        (self.dossier / "completions.csv").write_text(JOURNAL + "2026-10-13,9h30,lecture\n", encoding="utf-8")
        code, _, erreurs = self.lancer("fait", "lecture")
        self.assertEqual(code, 1)
        self.assertIn("ligne 3", erreurs)

    def test_taches_absentes_indique_comment_commencer(self):
        (self.dossier / "taches.json").unlink()
        code, _, erreurs = self.lancer()
        self.assertEqual(code, 1)
        self.assertIn("introuvable", erreurs)
        self.assertIn("taches.exemple.json", erreurs)
        self.assertIn(str(self.dossier / "taches.json"), erreurs)

    def test_premier_usage_avec_l_exemple(self):
        neuf = self.dossier / "neuf"
        neuf.mkdir()
        (neuf / "taches.json").write_bytes((koti.DOSSIER_CODE / "taches.exemple.json").read_bytes())
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            self.assertEqual(koti.main([], dossier=neuf, maintenant=MATIN), 0)
            self.assertEqual(koti.main(["fait", "lecture", "--no-upload"], dossier=neuf, maintenant=MATIN), 0)
        self.assertIn("☐ lecture — Lire un chapitre · série 0", sortie.getvalue())
        self.assertEqual((neuf / "completions.csv").read_text(encoding="utf-8"),
                         "date,heure,tache\n2026-10-13,10:04,lecture\n")
        self.assertTrue((neuf / "koti.html").exists())

    def test_dossier_de_donnees_par_la_variable_d_environnement(self):
        sortie = io.StringIO()
        with mock.patch.dict(os.environ, {"KOTI_DONNEES": str(self.dossier)}), contextlib.redirect_stdout(sortie):
            code = koti.main([], maintenant=MATIN)
        self.assertEqual(code, 0)
        self.assertIn("☐ lecture — Lecture du soir · série 1", sortie.getvalue())

    def test_page_ecrite_dans_le_dossier_de_donnees(self):
        code, _, _ = self.lancer("page", "--no-upload")
        self.assertEqual(code, 0)
        self.assertIn('"id": "lecture"', (self.dossier / "koti.html").read_text(encoding="utf-8"))

    def depot(self):
        # La configuration git de l'utilisateur ne doit pas changer le résultat.
        isolation = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
        isolation.start()
        self.addCleanup(isolation.stop)
        for arguments in (("init", "-q"), ("config", "user.name", "Essai"),
                          ("config", "user.email", "essai@example.com"), ("config", "commit.gpgsign", "false")):
            subprocess.run(["git", "-C", str(self.dossier), *arguments], check=True, capture_output=True)

    def sujets(self):
        return subprocess.run(["git", "-C", str(self.dossier), "log", "--format=%s"],
                              check=True, capture_output=True, text=True).stdout.splitlines()

    @unittest.skipUnless(shutil.which("git"), "git absent")
    def test_cochage_commite_dans_le_depot_de_donnees(self):
        self.depot()
        code, _, erreurs = self.lancer("fait", "lecture", "--no-upload")
        self.assertEqual(code, 0)
        self.assertEqual(erreurs, "")
        self.assertEqual(self.sujets(), ["fait : lecture (2026-10-13)"])

    @unittest.skipUnless(shutil.which("git"), "git absent")
    def test_page_commite_les_changements_de_taches(self):
        self.depot()
        self.lancer("fait", "lecture", "--no-upload")
        modifiees = {"taches": TACHES["taches"] + [
            {"id": "yoga", "titre": "Yoga", "debut": "2026-10-13", "heure_fixe": None, "notes": ""}]}
        (self.dossier / "taches.json").write_text(json.dumps(modifiees, ensure_ascii=False), encoding="utf-8")
        code, _, _ = self.lancer("page", "--no-upload")
        self.assertEqual(code, 0)
        self.assertEqual(self.sujets(), ["page", "fait : lecture (2026-10-13)"])

    @unittest.skipUnless(shutil.which("git"), "git absent")
    def test_commit_fait_meme_si_la_publication_echoue(self):
        self.depot()
        with mock.patch("koti.publication.publier", side_effect=koti.publication.ErreurPublication("panne")):
            code, _, erreurs = self.lancer("fait", "lecture")
        self.assertEqual(code, 1)
        self.assertIn("panne", erreurs)
        self.assertEqual(self.sujets(), ["fait : lecture (2026-10-13)"])

    @unittest.skipUnless(shutil.which("git"), "git absent")
    def test_echec_de_sauvegarde_ne_change_pas_le_code_de_sortie(self):
        self.depot()
        crochet = self.dossier / ".git" / "hooks" / "pre-commit"
        crochet.parent.mkdir(exist_ok=True)
        crochet.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        crochet.chmod(0o755)
        code, sortie, erreurs = self.lancer("fait", "lecture", "--no-upload")
        self.assertEqual(code, 0)
        self.assertIn("AVERTISSEMENT", erreurs)
        self.assertIn("koti.html régénéré", sortie)
        self.assertEqual(self.journal(), JOURNAL + "2026-10-13,10:04,lecture\n")

    @unittest.skipIf(os.geteuid() == 0, "sans objet pour root")
    def test_dossier_sans_permission_donne_une_erreur_propre(self):
        self.addCleanup(os.chmod, self.dossier, 0o700)
        os.chmod(self.dossier, 0)
        code, _, erreurs = self.lancer()
        self.assertEqual(code, 1)
        self.assertIn("ERREUR", erreurs)
        self.assertNotIn("Traceback", erreurs)

    def test_journal_illisible_donne_une_erreur_propre(self):
        (self.dossier / "completions.csv").unlink()
        (self.dossier / "completions.csv").mkdir()
        code, _, erreurs = self.lancer("fait", "lecture", "--no-upload")
        self.assertEqual(code, 1)
        self.assertIn("ERREUR", erreurs)

    def test_ecriture_impossible_n_annonce_pas_le_cochage(self):
        with mock.patch("koti.donnees.ajouter_completions",
                        side_effect=koti.donnees.ErreurDonnees("écriture impossible")):
            code, sortie, erreurs = self.lancer("fait", "lecture", "--no-upload")
        self.assertEqual(code, 1)
        self.assertIn("ERREUR", erreurs)
        self.assertNotIn("OK — lecture cochée", sortie)


class Aide(Base):
    def aide(self, *argv):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), self.assertRaises(SystemExit) as sortie_systeme:
            koti.main(list(argv), dossier=self.dossier, maintenant=MATIN)
        self.assertEqual(sortie_systeme.exception.code, 0)
        return sortie.getvalue()

    @staticmethod
    def sur_une_ligne(texte):
        """Le texte sans ses retours à la ligne, argparse coupant les phrases selon la largeur du terminal."""
        return " ".join(texte.split())

    def test_aide_generale(self):
        texte = self.aide("--help")
        self.assertIn("utilisation : koti", texte)
        self.assertIn("Sans commande, affiche la liste du jour", texte)
        self.assertIn("koti fait lecture marche", texte)
        self.assertIn("koti fait marche --date", texte)
        self.assertIn("afficher cette aide", texte)
        for anglais in ("usage:", "positional arguments", "show this help", "options:"):
            self.assertNotIn(anglais, texte)

    def test_aide_generale_liste_les_rituels(self):
        texte = self.aide("-h")
        self.assertIn("Rituels :", texte)
        self.assertRegex(texte, r"lecture\s+Lecture du soir")
        self.assertRegex(texte, r"marche\s+Marche \(pas avant 12:00\)")

    def test_aide_generale_sans_donnees(self):
        (self.dossier / "taches.json").unlink()
        texte = self.aide("--help")
        self.assertIn("utilisation : koti", texte)
        self.assertNotIn("Rituels :", texte)

    def test_aide_de_fait(self):
        texte = self.sur_une_ligne(self.aide("fait", "--help"))
        self.assertIn("utilisation : koti fait", texte)
        self.assertNotIn("utilisation : utilisation", texte)
        self.assertIn("identifiant, début d'identifiant ou mots du titre", texte)
        self.assertIn("heure de déclaration", texte)
        self.assertIn("jour passé", texte)
        self.assertIn("ne pas publier", texte)
        self.assertNotIn("show this help", texte)

    def test_aide_de_page(self):
        texte = self.sur_une_ligne(self.aide("page", "--help"))
        self.assertIn("utilisation : koti page", texte)
        self.assertNotIn("utilisation : utilisation", texte)
        self.assertIn("ne pas publier", texte)
        self.assertIn("Edge Rule bunny", texte)


if __name__ == "__main__":
    unittest.main()
