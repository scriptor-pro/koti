import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import publication


class UrlSignee(unittest.TestCase):
    def test_format_bunny(self):
        url = publication.generer_url_signee("cle-secrete", "koti.example.com", "/koti.html", 1900000000)
        self.assertEqual(url, "https://koti.example.com/koti.html?token=DE7k8AXe9WHPSDp2TzrJXQ&expires=1900000000")


class Publier(unittest.TestCase):
    def test_sans_configuration_ne_fait_rien(self):
        sortie = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(sortie):
            publication.publier(Path(tmp))
        self.assertIn("publication ignorée", sortie.getvalue())

    def test_configuration_illisible(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".bunny_config.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(publication.ErreurPublication, "illisible"):
                publication.publier(Path(tmp))

    def test_configuration_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".bunny_config.json").write_text('{"storage_endpoint": "x"}', encoding="utf-8")
            with self.assertRaisesRegex(publication.ErreurPublication, "storage_access_key"):
                publication.publier(Path(tmp))


CONFIG = {
    "storage_endpoint": "https://storage.exemple.test/zone-factice",
    "storage_access_key": "CLE-STOCKAGE-FACTICE",
    "pull_zone": "zone-factice",
    "public_hostname": "koti.exemple.test",
    "token_auth_security_key": "cle-token-factice",
    "remote_filename": "koti.html",
    "token_validity_seconds": 864000,
}


def ecrire_config(dossier, config=CONFIG):
    (dossier / ".bunny_config.json").write_text(json.dumps(config), encoding="utf-8")
    (dossier / "koti.html").write_text("<html></html>", encoding="utf-8")


class ReponseFactice:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PublierAvecReseauSimule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        ecrire_config(self.dossier)

    def test_envoi_et_purge_reussis(self):
        sortie = io.StringIO()
        with mock.patch("publication.subprocess.run") as run, \
                mock.patch("publication.urllib.request.urlopen", return_value=ReponseFactice()) as ouvrir, \
                mock.patch.dict(os.environ, {"BUNNY_API_KEY": "CLE-API-FACTICE"}), \
                contextlib.redirect_stdout(sortie):
            run.return_value.stdout = "201"
            publication.publier(self.dossier)
        texte = sortie.getvalue()
        self.assertIn("koti.html publié", texte)
        self.assertIn("https://koti.exemple.test/koti.html?token=", texte)
        self.assertIn("cache CDN purgé", texte)
        argv = run.call_args[0][0]
        self.assertIn("https://storage.exemple.test/zone-factice/koti.html", argv)
        self.assertIn("--max-time", argv)
        ouvrir.assert_called_once()

    def test_envoi_refuse(self):
        with mock.patch("publication.subprocess.run") as run, \
                mock.patch("publication.urllib.request.urlopen") as ouvrir, \
                mock.patch.dict(os.environ, {"BUNNY_API_KEY": "CLE-API-FACTICE"}):
            run.return_value.stdout = "401"
            with self.assertRaises(publication.ErreurPublication) as ctx:
                publication.publier(self.dossier)
        self.assertIn("401", str(ctx.exception))
        self.assertNotIn("CLE-API-FACTICE", str(ctx.exception))
        self.assertNotIn("CLE-STOCKAGE-FACTICE", str(ctx.exception))
        ouvrir.assert_not_called()

    def test_curl_absent(self):
        with mock.patch("publication.subprocess.run", side_effect=FileNotFoundError("curl")):
            with self.assertRaisesRegex(publication.ErreurPublication, "curl"):
                publication.publier(self.dossier)

    def test_purge_expiree(self):
        with mock.patch("publication.urllib.request.urlopen", side_effect=TimeoutError("délai")), \
                mock.patch.dict(os.environ, {"BUNNY_API_KEY": "CLE-API-FACTICE"}):
            with self.assertRaisesRegex(publication.ErreurPublication, "purge CDN"):
                publication.purger_cache("https://koti.exemple.test/koti.html")

    def test_edge_rule_reseau_en_panne(self):
        with mock.patch("publication.urllib.request.urlopen", side_effect=OSError("réseau")), \
                mock.patch.dict(os.environ, {"BUNNY_API_KEY": "CLE-API-FACTICE"}):
            with self.assertRaisesRegex(publication.ErreurPublication, "Edge Rule"):
                publication.assurer_edge_rule(self.dossier)


class ChargerConfig(unittest.TestCase):
    def charger(self, contenu):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".bunny_config.json").write_text(contenu, encoding="utf-8")
            return publication.charger_config(Path(tmp))

    def test_valeur_json_qui_n_est_pas_un_objet(self):
        with self.assertRaisesRegex(publication.ErreurPublication, "objet JSON"):
            self.charger("[]")

    def test_duree_de_validite_non_entiere(self):
        with self.assertRaisesRegex(publication.ErreurPublication, "token_validity_seconds"):
            self.charger(json.dumps({**CONFIG, "token_validity_seconds": "abc"}))

    def test_fichier_illisible(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".bunny_config.json").mkdir()
            with self.assertRaisesRegex(publication.ErreurPublication, "illisible"):
                publication.charger_config(Path(tmp))


class CleApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.maison = Path(self.tmp.name)

    def lire(self, variable=""):
        with mock.patch("publication.Path.home", return_value=self.maison), \
                mock.patch.dict(os.environ, {"BUNNY_API_KEY": variable}):
            return publication._lire_cle_api()

    def ecrire_fichier(self, contenu):
        dossier = self.maison / ".config" / "koti"
        dossier.mkdir(parents=True)
        (dossier / "bunny.env").write_text(contenu, encoding="utf-8")

    def test_fichier_de_koti(self):
        self.ecrire_fichier('export BUNNY_API_KEY="CLE-FICHIER"\n')
        self.assertEqual(self.lire(), "CLE-FICHIER")

    def test_variable_prioritaire_sur_le_fichier(self):
        self.ecrire_fichier("BUNNY_API_KEY=CLE-FICHIER\n")
        self.assertEqual(self.lire("CLE-VARIABLE"), "CLE-VARIABLE")

    def test_aucune_cle(self):
        self.assertIsNone(self.lire())

    def test_message_sans_cle_nomme_le_nouvel_emplacement(self):
        erreurs = io.StringIO()
        with mock.patch("publication.Path.home", return_value=self.maison), \
                mock.patch.dict(os.environ, {"BUNNY_API_KEY": ""}), contextlib.redirect_stderr(erreurs):
            publication.purger_cache("https://koti.example.com/koti.html")
        self.assertIn("~/.config/koti/bunny.env", erreurs.getvalue())


if __name__ == "__main__":
    unittest.main()
