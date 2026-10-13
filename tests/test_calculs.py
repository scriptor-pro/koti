import unittest
from datetime import date, datetime, timedelta

import calculs

DEBUT = date(2026, 9, 1)


def J(n):
    """Le n-ième jour après le 1er septembre 2026."""
    return DEBUT + timedelta(days=n)


class SerieEnCours(unittest.TestCase):
    def test_faite_aujourdhui(self):
        self.assertEqual(calculs.serie_en_cours({J(3), J(4), J(5)}, J(5)), 3)

    def test_pas_encore_faite_aujourdhui_ne_casse_pas(self):
        self.assertEqual(calculs.serie_en_cours({J(3), J(4)}, J(5)), 2)

    def test_hier_manque_remet_a_zero(self):
        self.assertEqual(calculs.serie_en_cours({J(1), J(2), J(3)}, J(5)), 0)

    def test_rupture_puis_reprise(self):
        self.assertEqual(calculs.serie_en_cours({J(0), J(1), J(3), J(4)}, J(4)), 2)

    def test_aucune_completion(self):
        self.assertEqual(calculs.serie_en_cours(set(), J(5)), 0)


class Record(unittest.TestCase):
    def test_plus_longue_suite(self):
        self.assertEqual(calculs.record({J(0), J(1), J(2), J(4), J(5)}), 3)

    def test_vide(self):
        self.assertEqual(calculs.record(set()), 0)

    def test_jour_isole(self):
        self.assertEqual(calculs.record({J(7)}), 1)


class Taux(unittest.TestCase):
    def test_depuis_le_debut_aujourdhui_fait(self):
        self.assertEqual(calculs.taux({J(0), J(2), J(3)}, J(0), J(3)), (3, 4))

    def test_aujourdhui_non_fait_est_exclu(self):
        self.assertEqual(calculs.taux({J(0), J(2)}, J(0), J(3)), (2, 3))

    def test_fenetre_de_sept_jours(self):
        dates = {J(n) for n in range(0, 20)} - {J(15)}
        self.assertEqual(calculs.taux(dates, J(0), J(19), fenetre=7), (6, 7))

    def test_fenetre_plus_longue_que_l_anciennete(self):
        self.assertEqual(calculs.taux({J(0), J(1)}, J(0), J(1), fenetre=30), (2, 2))

    def test_premier_jour_non_fait(self):
        self.assertEqual(calculs.taux(set(), J(0), J(0)), (0, 0))


class Calendrier(unittest.TestCase):
    def test_etats(self):
        self.assertEqual(
            calculs.calendrier({J(0), J(2)}, J(0), J(3)),
            [["2026-09-01", "fait"], ["2026-09-02", "manque"], ["2026-09-03", "fait"], ["2026-09-04", "attente"]],
        )


class HeureMoyenne(unittest.TestCase):
    def test_moyenne_simple(self):
        self.assertEqual(calculs.heure_moyenne(["09:00", "11:00"]), ("10:00", 2))

    def test_autour_de_minuit(self):
        self.assertEqual(calculs.heure_moyenne(["23:50", "00:10"]), ("00:00", 2))

    def test_heures_vides_exclues(self):
        self.assertEqual(calculs.heure_moyenne(["", "10:04"]), ("10:04", 1))

    def test_aucune_heure(self):
        self.assertIsNone(calculs.heure_moyenne(["", ""]))
        self.assertIsNone(calculs.heure_moyenne([]))

    def test_heures_opposees_sans_moyenne_definie(self):
        self.assertIsNone(calculs.heure_moyenne(["06:00", "18:00"]))


class Statistiques(unittest.TestCase):
    TACHE = {"id": "marche", "titre": "Marche", "debut": "2026-09-01", "heure_fixe": "12:00", "notes": "n"}

    def completions(self):
        return [
            {"date": "2026-09-01", "heure": "", "tache": "marche"},
            {"date": "2026-09-02", "heure": "12:10", "tache": "marche"},
            {"date": "2026-09-03", "heure": "12:30", "tache": "marche"},
            {"date": "2026-09-03", "heure": "08:00", "tache": "lecture"},
        ]

    def test_avant_l_heure_fixe(self):
        s = calculs.statistiques(self.TACHE, self.completions(), datetime(2026, 9, 4, 10, 0))
        self.assertFalse(s["fait_aujourdhui"])
        self.assertFalse(s["cochable"])
        self.assertEqual(s["serie"], 3)
        self.assertEqual(s["record"], 3)
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["taux"], {"sept": [3, 3], "trente": [3, 3], "tout": [3, 3]})
        self.assertEqual(s["heure_moyenne"], "12:20")
        self.assertEqual(s["nb_heures"], 2)
        self.assertEqual(s["calendrier"][-1], ["2026-09-04", "attente"])

    def test_apres_l_heure_fixe(self):
        s = calculs.statistiques(self.TACHE, self.completions(), datetime(2026, 9, 4, 12, 0))
        self.assertTrue(s["cochable"])

    def test_faite_aujourdhui(self):
        s = calculs.statistiques(self.TACHE, self.completions(), datetime(2026, 9, 3, 13, 0))
        self.assertTrue(s["fait_aujourdhui"])
        self.assertEqual(s["heure_du_jour"], "12:30")
        self.assertFalse(s["cochable"])

    def test_completion_anterieure_au_debut_etend_le_calendrier(self):
        tache = dict(self.TACHE, debut="2026-09-02")
        s = calculs.statistiques(tache, self.completions(), datetime(2026, 9, 3, 13, 0))
        self.assertEqual(s["calendrier"][0][0], "2026-09-01")

    def test_completion_future_ignoree(self):
        completions = self.completions() + [{"date": "2026-09-09", "heure": "", "tache": "marche"}]
        s = calculs.statistiques(self.TACHE, completions, datetime(2026, 9, 3, 13, 0))
        self.assertEqual(s["total"], 3)

    def test_sans_heure_fixe_ni_heure(self):
        tache = {"id": "yoga", "titre": "Yoga", "debut": "2026-09-01", "heure_fixe": None, "notes": ""}
        s = calculs.statistiques(tache, [], datetime(2026, 9, 1, 9, 0))
        self.assertTrue(s["cochable"])
        self.assertIsNone(s["heure_moyenne"])
        self.assertEqual(s["nb_heures"], 0)
        self.assertEqual(s["taux"]["tout"], [0, 0])

    def test_rituel_ordinaire_n_est_pas_sans_serie(self):
        s = calculs.statistiques(self.TACHE, self.completions(), datetime(2026, 9, 4, 10, 0))
        self.assertIs(s["sans_serie"], False)

    def test_sans_serie(self):
        tache = dict(self.TACHE, sans_serie=True)
        s = calculs.statistiques(tache, self.completions(), datetime(2026, 9, 5, 13, 0))
        self.assertIs(s["sans_serie"], True)
        self.assertIsNone(s["serie"])
        self.assertIsNone(s["record"])
        self.assertIsNone(s["taux"])
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["heure_moyenne"], "12:20")
        self.assertEqual(s["calendrier"], [
            ["2026-09-01", "fait"], ["2026-09-02", "fait"], ["2026-09-03", "fait"],
            ["2026-09-04", "neutre"], ["2026-09-05", "neutre"],
        ])

    def test_sans_serie_aujourdhui_fait(self):
        tache = dict(self.TACHE, sans_serie=True)
        s = calculs.statistiques(tache, self.completions(), datetime(2026, 9, 3, 13, 0))
        self.assertTrue(s["fait_aujourdhui"])
        self.assertEqual(s["calendrier"][-1], ["2026-09-03", "fait"])


if __name__ == "__main__":
    unittest.main()
