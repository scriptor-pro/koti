import json
import os
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import koti
MATIN = datetime(2026, 10, 13, 10, 4)
TACHES = [{"id": "lecture", "titre": "Lecture", "debut": "2026-10-11", "heure_fixe": None, "notes": "n"}]
COMPLETIONS = [{"date": "2026-10-12", "heure": "09:00", "tache": "lecture"},
               {"date": "2026-10-13", "heure": "10:04", "tache": "lecture"}]
BLOC = re.compile(r'<script type="application/json" id="data-source">\n(.*?)\n</script>', re.DOTALL)


class ConstruireDonnees(unittest.TestCase):
    def test_contenu(self):
        d = koti.construire_donnees(TACHES, COMPLETIONS, MATIN)
        self.assertEqual(d["genere_le"], "2026-10-13T10:04:00")
        self.assertEqual(d["aujourdhui"], "2026-10-13")
        self.assertEqual(d["faites_aujourdhui"], 1)
        self.assertEqual(d["taches"][0]["serie"], 2)
        self.assertEqual(d["suivis"], 1)

    def test_sans_serie_hors_decompte(self):
        dessin = {"id": "dessin", "titre": "Dessin", "debut": "2026-10-11", "heure_fixe": None,
                   "notes": "n", "sans_serie": True}
        completions = COMPLETIONS + [{"date": "2026-10-13", "heure": "11:00", "tache": "dessin"}]
        d = koti.construire_donnees(TACHES + [dessin], completions, MATIN)
        self.assertEqual(d["faites_aujourdhui"], 1)
        self.assertEqual(d["suivis"], 1)
        self.assertEqual(len(d["taches"]), 2)

    def test_bloc_sans_serie_sans_chiffres_de_serie(self):
        dessin = {"id": "dessin", "titre": "Dessin", "debut": "2026-10-09", "heure_fixe": None,
                   "notes": "n", "sans_serie": True}
        d = koti.construire_donnees([dessin], COMPLETIONS[:1], MATIN)
        bloc = json.loads(json.dumps(d))["taches"][0]
        self.assertIsNone(bloc["serie"])
        self.assertIsNone(bloc["record"])
        self.assertIsNone(bloc["taux"])
        self.assertNotIn("manque", json.dumps(d))


class GenererPage(unittest.TestCase):
    GABARIT = 'a<script type="application/json" id="data-source">\n{"taches": []}\n</script>z'

    def test_remplace_le_bloc(self):
        html = koti.generer_page(self.GABARIT, {"taches": [{"id": "lecture"}]})
        self.assertTrue(html.startswith("a<script") and html.endswith("</script>z"))
        self.assertEqual(json.loads(BLOC.search(html).group(1)), {"taches": [{"id": "lecture"}]})

    def test_regeneration_idempotente(self):
        une = koti.generer_page(self.GABARIT, {"taches": [1]})
        self.assertEqual(koti.generer_page(une, {"taches": [1]}), une)

    def test_notes_contenant_une_balise_script(self):
        donnees = {"taches": [{"notes": 'fin </script><script>alert(1)</script> \\ "x"'}]}
        html = koti.generer_page(self.GABARIT, donnees)
        self.assertEqual(html.count("</script>"), 1)
        self.assertEqual(json.loads(BLOC.search(html).group(1)), donnees)

    def test_commentaire_html_et_script_dans_une_note(self):
        donnees = {"taches": [{"notes": "a <!--<script>alert(1)</script> <b>"}]}
        html = koti.generer_page(self.GABARIT, donnees)
        bloc = BLOC.search(html).group(1)
        self.assertNotIn("<", bloc)
        self.assertEqual(json.loads(bloc), donnees)

    def test_bloc_introuvable(self):
        with self.assertRaisesRegex(koti.ErreurCommande, "data-source"):
            koti.generer_page("<html></html>", {})


class EcrirePage(unittest.TestCase):
    def test_gabarit_reel(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            koti.ecrire_page(dossier, TACHES, COMPLETIONS, MATIN)
            html = (dossier / "koti.html").read_text(encoding="utf-8")
        donnees = json.loads(BLOC.search(html).group(1))
        self.assertEqual(donnees["taches"][0]["id"], "lecture")
        self.assertIn("fonts.bunny.net", html)
        self.assertNotIn("fonts.googleapis.com", html)

    def test_gabarit_sans_donnees_et_jamais_modifie(self):
        avant = koti.GABARIT.read_bytes()
        self.assertEqual(json.loads(BLOC.search(avant.decode("utf-8")).group(1)), {})
        with tempfile.TemporaryDirectory() as tmp:
            koti.ecrire_page(Path(tmp), TACHES, COMPLETIONS, MATIN)
        self.assertEqual(koti.GABARIT.read_bytes(), avant)

    def test_dossier_de_donnees_cree_au_besoin(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp) / "a" / "b"
            koti.ecrire_page(dossier, TACHES, COMPLETIONS, MATIN)
            self.assertTrue((dossier / "koti.html").exists())

    def test_dossier_de_donnees_impossible_a_creer(self):
        with tempfile.TemporaryDirectory() as tmp:
            fichier = Path(tmp) / "fichier"
            fichier.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(koti.ErreurCommande, "écriture impossible"):
                koti.ecrire_page(fichier / "sous-dossier", TACHES, COMPLETIONS, MATIN)

    def test_gabarit_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(koti.ErreurCommande, "absent.html introuvable"):
                koti.ecrire_page(Path(tmp), TACHES, COMPLETIONS, MATIN, gabarit=Path(tmp) / "absent.html")

    def test_aucune_fuite_de_referent(self):
        html = koti.GABARIT.read_text(encoding="utf-8")
        self.assertIn('<meta name="referrer" content="no-referrer">', html)

    def test_pas_de_fichier_temporaire_restant(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            koti.ecrire_page(dossier, TACHES, COMPLETIONS, MATIN)
            self.assertEqual([p.name for p in dossier.iterdir()], ["koti.html"])

    def test_luciole_integree_a_la_page(self):
        html = koti.GABARIT.read_text(encoding="utf-8")
        self.assertEqual(html.count("src:url(data:font/woff2;base64,"), 2)
        self.assertNotIn("/*LUCIOLE*/", html)
        self.assertNotIn("url('fonts/", html)
        self.assertIn("font-family:'Luciole', system-ui", html)


class DossierDonnees(unittest.TestCase):
    def test_variable_d_environnement(self):
        with mock.patch.dict(os.environ, {"KOTI_DONNEES": "/tmp/ailleurs"}):
            self.assertEqual(koti.dossier_donnees(), Path("/tmp/ailleurs"))

    def test_tilde_developpe(self):
        with mock.patch.dict(os.environ, {"KOTI_DONNEES": "~/rituels"}):
            self.assertEqual(koti.dossier_donnees(), Path.home() / "rituels")

    def test_variable_vide(self):
        with mock.patch.dict(os.environ, {"KOTI_DONNEES": ""}):
            self.assertEqual(koti.dossier_donnees(), Path.home() / ".local" / "share" / "koti")

    def test_variable_absente(self):
        sans = {k: v for k, v in os.environ.items() if k != "KOTI_DONNEES"}
        with mock.patch.dict(os.environ, sans, clear=True):
            self.assertEqual(koti.dossier_donnees(), Path.home() / ".local" / "share" / "koti")


if __name__ == "__main__":
    unittest.main()
