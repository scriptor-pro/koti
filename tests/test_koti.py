import unittest
from datetime import date, datetime

import koti

TACHES = [
    {"id": "etirements", "titre": "Faire les étirements du jour", "debut": "2026-09-03", "heure_fixe": None, "notes": ""},
    {"id": "croquis", "titre": "Croquis — défi quotidien", "debut": "2026-09-03", "heure_fixe": None, "notes": ""},
    {"id": "marche", "titre": "Marche — sortie du jour", "debut": "2026-09-03", "heure_fixe": "12:00", "notes": ""},
    {"id": "carte", "titre": "Carte — défi géographique du jour", "debut": "2026-09-03", "heure_fixe": None, "notes": ""},
    {"id": "lecture", "titre": "Lire un chapitre de roman", "debut": "2026-09-02", "heure_fixe": None, "notes": ""},
]
MATIN = datetime(2026, 10, 13, 10, 4)
APRES_MIDI = datetime(2026, 10, 13, 14, 30)


def ligne(jour, heure, tache):
    return {"date": jour, "heure": heure, "tache": tache}


class TrouverTache(unittest.TestCase):
    def test_identifiant_exact(self):
        self.assertEqual(koti.trouver_tache("croquis", TACHES)["id"], "croquis")

    def test_accents_et_casse(self):
        self.assertEqual(koti.trouver_tache("Étirements", TACHES)["id"], "etirements")

    def test_debut_d_identifiant(self):
        self.assertEqual(koti.trouver_tache("croq", TACHES)["id"], "croquis")

    def test_mots_du_titre(self):
        self.assertEqual(koti.trouver_tache("chapitre de roman", TACHES)["id"], "lecture")
        self.assertEqual(koti.trouver_tache("géographique", TACHES)["id"], "carte")

    def test_identifiant_exact_prime_sur_les_titres(self):
        taches = TACHES + [{"id": "jour", "titre": "Autre", "debut": "2026-09-03", "heure_fixe": None, "notes": ""}]
        self.assertEqual(koti.trouver_tache("jour", taches)["id"], "jour")

    def test_nom_ambigu(self):
        with self.assertRaisesRegex(koti.ErreurCommande, "ambigu.*croquis.*carte"):
            koti.trouver_tache("défi", TACHES)

    def test_nom_inconnu(self):
        with self.assertRaisesRegex(koti.ErreurCommande, "inconnue"):
            koti.trouver_tache("vaisselle", TACHES)

    def test_nom_vide(self):
        with self.assertRaises(koti.ErreurCommande):
            koti.trouver_tache("—", TACHES)


class PreparerCochage(unittest.TestCase):
    def test_cochage_du_jour(self):
        lignes, messages = koti.preparer_cochage(["croquis", "lecture"], TACHES, [], MATIN)
        self.assertEqual(lignes, [ligne("2026-10-13", "10:04", "croquis"), ligne("2026-10-13", "10:04", "lecture")])
        self.assertEqual(len(messages), 2)
        self.assertTrue(all(m.startswith("OK") for m in messages))

    def test_heure_precisee(self):
        lignes, _ = koti.preparer_cochage(["lecture"], TACHES, [], MATIN, heure="08:15")
        self.assertEqual(lignes, [ligne("2026-10-13", "08:15", "lecture")])

    def test_deja_cochee(self):
        deja = [ligne("2026-10-13", "09:00", "lecture")]
        lignes, messages = koti.preparer_cochage(["lecture", "croquis"], TACHES, deja, MATIN)
        self.assertEqual([l["tache"] for l in lignes], ["croquis"])
        self.assertTrue(messages[0].startswith("IGNORÉE"))

    def test_heure_fixe_non_atteinte(self):
        lignes, messages = koti.preparer_cochage(["marche"], TACHES, [], MATIN)
        self.assertEqual(lignes, [])
        self.assertRegex(messages[0], "REFUSÉE.*12:00")

    def test_heure_fixe_atteinte(self):
        lignes, _ = koti.preparer_cochage(["marche"], TACHES, [], APRES_MIDI)
        self.assertEqual(lignes, [ligne("2026-10-13", "14:30", "marche")])

    def test_nom_inconnu_ne_prepare_rien(self):
        with self.assertRaises(koti.ErreurCommande):
            koti.preparer_cochage(["lecture", "vaisselle"], TACHES, [], MATIN)

    def test_meme_tache_nommee_deux_fois(self):
        lignes, _ = koti.preparer_cochage(["lecture", "roman"], TACHES, [], MATIN)
        self.assertEqual(len(lignes), 1)

    def test_veille_declaree_apres_minuit(self):
        apres_minuit = datetime(2026, 10, 14, 0, 20)
        lignes, _ = koti.preparer_cochage(["lecture"], TACHES, [], apres_minuit, jour=date(2026, 10, 13))
        self.assertEqual(lignes, [ligne("2026-10-13", "", "lecture")])

    def test_veille_avec_heure(self):
        lignes, _ = koti.preparer_cochage(["lecture"], TACHES, [], MATIN, jour=date(2026, 10, 12), heure="23:40")
        self.assertEqual(lignes, [ligne("2026-10-12", "23:40", "lecture")])

    def test_heure_fixe_non_appliquee_a_une_date_passee(self):
        lignes, _ = koti.preparer_cochage(["marche"], TACHES, [], MATIN, jour=date(2026, 10, 12))
        self.assertEqual(len(lignes), 1)

    def test_date_future_refusee(self):
        with self.assertRaisesRegex(koti.ErreurCommande, "future"):
            koti.preparer_cochage(["lecture"], TACHES, [], MATIN, jour=date(2026, 10, 14))


class TexteListe(unittest.TestCase):
    def test_liste(self):
        completions = [
            ligne("2026-10-12", "09:00", "croquis"),
            ligne("2026-10-13", "10:04", "croquis"),
        ]
        texte = koti.texte_liste(TACHES, completions, MATIN)
        lignes = texte.splitlines()
        self.assertEqual(lignes[0], "koti — 2026-10-13, 10:04")
        self.assertEqual(lignes[1], "☐ etirements — Faire les étirements du jour · série 0")
        self.assertEqual(lignes[2], "☑ croquis — Croquis — défi quotidien · faite à 10:04 · série 2 · en moyenne à 09:32")
        self.assertEqual(lignes[3], "☐ marche — Marche — sortie du jour · pas avant 12:00 · série 0")
        self.assertEqual(lignes[-1], "1 sur 5 faites, 3 cochables maintenant.")

    def test_liste_avec_rituel_sans_serie(self):
        dessin = {"id": "dessin", "titre": "Dessin — session du jour", "debut": "2026-09-04",
                   "heure_fixe": None, "notes": "", "sans_serie": True}
        taches = TACHES[:2] + [dessin]
        completions = [
            ligne("2026-10-10", "16:00", "dessin"),
            ligne("2026-10-12", "16:44", "dessin"),
            ligne("2026-10-13", "10:04", "croquis"),
        ]
        lignes = koti.texte_liste(taches, completions, MATIN).splitlines()
        self.assertEqual(lignes[3], "☐ dessin — Dessin — session du jour · 2 sessions · en moyenne à 16:22")
        self.assertEqual(lignes[-1], "1 sur 2 faites, 2 cochables maintenant.")
        apres = completions + [ligne("2026-10-13", "10:30", "dessin")]
        lignes = koti.texte_liste(taches, apres, MATIN).splitlines()
        self.assertEqual(lignes[3], "☑ dessin — Dessin — session du jour · faite à 10:30 · 3 sessions · en moyenne à 14:37")
        self.assertEqual(lignes[-1], "1 sur 2 faites, 1 cochables maintenant.")

    def test_liste_session_au_singulier_et_a_zero(self):
        dessin = {"id": "dessin", "titre": "Dessin", "debut": "2026-09-04",
                   "heure_fixe": None, "notes": "", "sans_serie": True}
        self.assertEqual(koti.texte_liste([dessin], [], MATIN).splitlines()[1], "☐ dessin — Dessin · 0 session")
        un = [ligne("2026-10-12", "", "dessin")]
        self.assertEqual(koti.texte_liste([dessin], un, MATIN).splitlines()[1], "☐ dessin — Dessin · 1 session")


if __name__ == "__main__":
    unittest.main()
