import json
import tempfile
import unittest
from pathlib import Path

import donnees

TACHES = {"taches": [
    {"id": "lecture", "titre": "Lecture", "debut": "2026-09-02", "heure_fixe": None, "notes": ""},
    {"id": "marche", "titre": "Marche", "debut": "2026-09-03", "heure_fixe": "12:00", "notes": ""},
]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        self.taches = self.dossier / "taches.json"
        self.csv = self.dossier / "completions.csv"

    def ecrire_taches(self, contenu):
        self.taches.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")


class LireTaches(Base):
    def test_lecture(self):
        self.ecrire_taches(TACHES)
        self.assertEqual([t["id"] for t in donnees.lire_taches(self.taches)], ["lecture", "marche"])

    def test_fichier_absent(self):
        with self.assertRaisesRegex(donnees.ErreurDonnees, "introuvable"):
            donnees.lire_taches(self.taches)

    def test_json_invalide(self):
        self.taches.write_text("{pas du json", encoding="utf-8")
        with self.assertRaisesRegex(donnees.ErreurDonnees, "illisible"):
            donnees.lire_taches(self.taches)

    def test_identifiant_en_double(self):
        self.ecrire_taches({"taches": [TACHES["taches"][0], TACHES["taches"][0]]})
        with self.assertRaisesRegex(donnees.ErreurDonnees, "en double"):
            donnees.lire_taches(self.taches)

    def test_champ_manquant(self):
        self.ecrire_taches({"taches": [{"id": "lecture", "titre": "Lecture"}]})
        with self.assertRaisesRegex(donnees.ErreurDonnees, "debut"):
            donnees.lire_taches(self.taches)

    def test_heure_fixe_invalide(self):
        self.ecrire_taches({"taches": [dict(TACHES["taches"][1], heure_fixe="midi")]})
        with self.assertRaisesRegex(donnees.ErreurDonnees, "heure_fixe"):
            donnees.lire_taches(self.taches)

    def test_taches_json_est_un_repertoire(self):
        self.taches.mkdir()
        with self.assertRaisesRegex(donnees.ErreurDonnees, "illisible"):
            donnees.lire_taches(self.taches)

    def test_debut_n_est_pas_une_chaine(self):
        self.ecrire_taches({"taches": [dict(TACHES["taches"][0], debut=20260902)]})
        with self.assertRaisesRegex(donnees.ErreurDonnees, "debut"):
            donnees.lire_taches(self.taches)

    def test_heure_fixe_n_est_pas_une_chaine(self):
        self.ecrire_taches({"taches": [dict(TACHES["taches"][1], heure_fixe=12)]})
        with self.assertRaisesRegex(donnees.ErreurDonnees, "heure_fixe"):
            donnees.lire_taches(self.taches)

    def test_sans_serie_n_est_pas_un_booleen(self):
        self.ecrire_taches({"taches": [dict(TACHES["taches"][0], sans_serie="oui")]})
        with self.assertRaisesRegex(donnees.ErreurDonnees, "sans_serie.*lecture"):
            donnees.lire_taches(self.taches)

    def test_sans_serie_booleen_accepte(self):
        self.ecrire_taches({"taches": [dict(TACHES["taches"][0], sans_serie=True)]})
        self.assertTrue(donnees.lire_taches(self.taches)[0]["sans_serie"])

    def test_id_n_est_pas_une_chaine(self):
        self.ecrire_taches({"taches": [dict(TACHES["taches"][0], id=["lecture"])]})
        with self.assertRaisesRegex(donnees.ErreurDonnees, "id"):
            donnees.lire_taches(self.taches)

    def test_fichier_d_exemple_valide(self):
        exemple = Path(__file__).resolve().parent.parent / "taches.exemple.json"
        self.assertEqual([t["id"] for t in donnees.lire_taches(exemple)], ["lecture", "marche", "dessin"])


class LireCompletions(Base):
    def test_lecture(self):
        self.csv.write_text("date,heure,tache\n2026-09-02,,lecture\n2026-09-03,12:05,marche\n", encoding="utf-8")
        self.assertEqual(donnees.lire_completions(self.csv), [
            {"date": "2026-09-02", "heure": "", "tache": "lecture"},
            {"date": "2026-09-03", "heure": "12:05", "tache": "marche"},
        ])

    def test_fichier_absent_vaut_journal_vide(self):
        self.assertEqual(donnees.lire_completions(self.csv), [])

    def test_entete_inattendu(self):
        self.csv.write_text("date,heure,id_tache\n", encoding="utf-8")
        with self.assertRaisesRegex(donnees.ErreurDonnees, "en-tête"):
            donnees.lire_completions(self.csv)

    def test_heure_mal_formee_avec_numero_de_ligne(self):
        self.csv.write_text("date,heure,tache\n2026-09-02,,lecture\n2026-09-03,9h30,lecture\n", encoding="utf-8")
        with self.assertRaisesRegex(donnees.ErreurDonnees, "ligne 3.*9h30"):
            donnees.lire_completions(self.csv)

    def test_date_mal_formee_avec_numero_de_ligne(self):
        self.csv.write_text("date,heure,tache\n13/10/2026,,lecture\n", encoding="utf-8")
        with self.assertRaisesRegex(donnees.ErreurDonnees, "ligne 2.*13/10/2026"):
            donnees.lire_completions(self.csv)

    def test_tache_vide(self):
        self.csv.write_text("date,heure,tache\n2026-09-02,,\n", encoding="utf-8")
        with self.assertRaisesRegex(donnees.ErreurDonnees, "ligne 2"):
            donnees.lire_completions(self.csv)

    def test_lignes_vides_ignorees(self):
        self.csv.write_text("date,heure,tache\n2026-09-02,,lecture\n\n", encoding="utf-8")
        self.assertEqual(len(donnees.lire_completions(self.csv)), 1)

    def test_utf8_invalide(self):
        self.csv.write_bytes(b"date,heure,tache\n2026-09-02,,caf\xe9\n")
        with self.assertRaisesRegex(donnees.ErreurDonnees, "illisible"):
            donnees.lire_completions(self.csv)


class EcrireCompletions(Base):
    LIGNE = {"date": "2026-09-04", "heure": "10:04", "tache": "lecture"}

    def test_ajout(self):
        self.csv.write_text("date,heure,tache\n2026-09-02,,lecture\n", encoding="utf-8")
        donnees.ajouter_completions(self.csv, [self.LIGNE])
        self.assertEqual(self.csv.read_text(encoding="utf-8"),
                         "date,heure,tache\n2026-09-02,,lecture\n2026-09-04,10:04,lecture\n")

    def test_ajout_sans_retour_a_la_ligne_final(self):
        self.csv.write_text("date,heure,tache\n2026-09-02,,lecture", encoding="utf-8")
        donnees.ajouter_completions(self.csv, [self.LIGNE])
        self.assertEqual(self.csv.read_text(encoding="utf-8"),
                         "date,heure,tache\n2026-09-02,,lecture\n2026-09-04,10:04,lecture\n")

    def test_ajout_cree_le_journal_avec_son_en_tete(self):
        donnees.ajouter_completions(self.csv, [self.LIGNE])
        self.assertEqual(self.csv.read_text(encoding="utf-8"), "date,heure,tache\n2026-09-04,10:04,lecture\n")

    def test_ajout_cree_le_dossier(self):
        chemin = self.dossier / "a" / "b" / "completions.csv"
        donnees.ajouter_completions(chemin, [self.LIGNE])
        self.assertEqual(donnees.lire_completions(chemin), [self.LIGNE])

    def test_ajout_impossible(self):
        fichier = self.dossier / "fichier"
        fichier.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(donnees.ErreurDonnees, "écriture impossible"):
            donnees.ajouter_completions(fichier / "completions.csv", [self.LIGNE])


if __name__ == "__main__":
    unittest.main()
