"""Tests des règles de correspondance stricte.

    python -m unittest discover -s scripts -p "test_*.py" -t scripts
"""

import unittest

from product_images.matching import ACCEPT, REJECT, REVIEW, Candidate, build_profile, evaluate
from product_images.providers import BraveImageProvider, GoogleCSEProvider

AMZ = "https://m.media-amazon.com/images/I/71abc.jpg"


def verdict(ref, designation, image_url, page_url="", title=""):
    p = build_profile(ref, designation)
    assert p.skip_reason is None, p.skip_reason
    return evaluate(p, Candidate(image_url, page_url, title)).verdict


class ProfileTests(unittest.TestCase):
    def test_modele_principal_ignore_les_specs(self):
        p = build_profile("3440-I5", 'DELL Latitude 3440 i5-1335U 14"FHD 8 Go 512 Go SSD Win 10')
        self.assertEqual(p.brand, "DELL")
        self.assertEqual(p.primary_model, "3440")
        self.assertEqual(p.capacities, {8.0, 512.0})

    def test_capacite_en_teraoctets(self):
        p = build_profile("BX500-1T", "Disque Dur SSD 1To Crucial BX500")
        self.assertEqual(p.capacities, {1000.0})
        self.assertEqual(p.primary_model, "BX500")

    def test_produit_compatible_ignore(self):
        for d in ["EPSON 103 BOUTEILLE D'ENCRE NOIR WORD", "TONER NWC HP 2300A BLACK 230A",
                  "TONER HP 05A NOIR (CE505A) COMP"]:
            self.assertIsNotNone(build_profile("X", d).skip_reason, d)

    def test_generique_sans_marque_ignore(self):
        self.assertIn("sans marque", build_profile("AG1", "Agenda avec serrure").skip_reason)

    def test_plusieurs_marques_ignore(self):
        self.assertIn("ambiguë", build_profile("L-TJ", "ADAPTATEUR SONY LENOVO TETE JAUNE").skip_reason)


class EvaluateTests(unittest.TestCase):
    def test_ssd_bonne_capacite_accepte(self):
        self.assertEqual(verdict("BX500-1T", "Disque Dur SSD 1To Crucial BX500", AMZ,
                                 "https://www.amazon.fr/dp/B07YD5F561",
                                 "Crucial BX500 1To SSD interne 3D NAND SATA 2,5"), ACCEPT)

    def test_ssd_autre_capacite_rejete(self):
        self.assertEqual(verdict("BX500-1T", "Disque Dur SSD 1To Crucial BX500", AMZ,
                                 "https://www.amazon.fr/dp/B07G3KGYZQ",
                                 "Crucial BX500 480Go SSD interne"), REJECT)

    def test_ssd_capacite_non_mentionnee_en_revue(self):
        self.assertEqual(verdict("BX500-1T", "Disque Dur SSD 1To Crucial BX500", AMZ,
                                 "https://www.amazon.fr/dp/X", "Crucial BX500 SSD interne"), REVIEW)

    def test_autre_marque_rejetee(self):
        self.assertEqual(verdict("BX500-1T", "Disque Dur SSD 1To Crucial BX500", AMZ,
                                 "https://www.amazon.fr/dp/X", "Kingston A400 1To SSD"), REJECT)

    def test_autre_modele_rejete(self):
        self.assertEqual(verdict("SAM-A26", "SAMSUNG A26 White 6.7'' 6Go 128Go", "https://images.samsung.com/is/image/samsung/p6pim/us/sm-s731uzkexaa/gallery/us-galaxy-s25-fe.jpg",
                                 "https://www.samsung.com/us/smartphones/galaxy-s25-fe/"), REJECT)

    def test_couleur_differente_rejetee(self):
        self.assertEqual(verdict("103-CY", "EPSON 103 BOUTEILLE D'ENCRE CYAN",
                                 "https://i8.amplience.net/i/epsonemear/103-black.png",
                                 "https://www.epson.eu/en_EU/products/103-ecotank-black-ink-bottle/p/22804"), REJECT)

    def test_couleur_toner_non_confirmee_en_revue(self):
        self.assertEqual(verdict("HPN-12", "TONER HP 12A NOIR", AMZ,
                                 "https://www.amazon.fr/dp/X", "HP 12A toner LaserJet"), REVIEW)

    def test_modele_concatene_dans_url(self):
        self.assertEqual(verdict("HP840G6", "PC PORTABLE HP I5   840G6 8G RAM 256 SSD",
                                 "https://hp.widen.net/content/yacpnxmsos/png/yacpnxmsos.png",
                                 "https://support.hp.com/us-en/product/details/hp-elitebook-840-g6-notebook-pc/26609796"), ACCEPT)

    def test_domaine_non_autorise_rejete(self):
        self.assertEqual(verdict("M185", "LOGITECH Wireless Mouse M185",
                                 "https://upload.wikimedia.org/m185.jpg"), REJECT)

    def test_terme_exclu_rejete(self):
        self.assertEqual(verdict("M185", "LOGITECH Wireless Mouse M185", AMZ, "https://www.amazon.fr/dp/X",
                                 "Logitech M185 en rayon magasin"), REJECT)

    def test_source_compatible_rejetee(self):
        self.assertEqual(verdict("HP-226A", "TONER HP 26A CF226A NOIR", AMZ, "https://www.amazon.fr/dp/X",
                                 "Toner compatible HP 26A CF226A noir"), REJECT)

    def test_modeles_voisins_en_revue(self):
        self.assertEqual(verdict("A56", "SAMSUNG Galaxy A56 5G (8GB | 128 GB)", AMZ, "https://www.amazon.fr/dp/X",
                                 "Samsung Galaxy A56 vs A36 128GB comparatif"), REVIEW)


class RegressionTests(unittest.TestCase):
    """Cas réels rencontrés sur le catalogue (dry-run du 28/09/2026)."""

    def test_specs_ne_sont_pas_des_modeles(self):
        cases = {
            "TP-LINK 150MBPS TL-WN725N": "WN725N",
            "TP-LINK AC1200 WIFI ROUTER C64 SANS FIL GIGABIT": "C64",
            "TOSHIBA DISQUE DUR HDD 3.5 S300 4 TO": "S300",
            "HP Series 7 Pro 23.8 inch FHD Monitor - 724pf 36M": "724PF",
            'HP Ecran S3 Pro 322pe FHD 21.45"': "322PE",
            "IMPRIMANTE HP LASER 107W": "107W",
            "TONER HP 12A NOIR": "12A",
        }
        for designation, expected in cases.items():
            self.assertEqual(build_profile("X", designation).primary_model, expected, designation)

    def test_capacite_128G(self):
        p = build_profile("SAM-A15", 'SAMSUNG Smartphone A15 6.5" MT6789V/CD 4Go 128G Android 4G')
        self.assertEqual(p.capacities, {4.0, 128.0})

    def test_reference_constructeur_forte(self):
        # '415A' absent mais 'W2030A' (référence HP exacte) présent -> prouvé
        self.assertEqual(verdict("W2030A", "TONER HP 415A NOIR W2030A", AMZ, "https://www.amazon.fr/dp/X",
                                 "HP 415A W2030A Toner Noir Authentique"), ACCEPT)

    def test_compatible_imprimante_ne_suffit_pas(self):
        # 'M404' = imprimante compatible, pas le toner lui-même -> pas une preuve
        self.assertEqual(verdict("59AHP", "HP 59A Black Original LaserJet Toner Cartridge pour M404 & M428",
                                 AMZ, "https://www.amazon.fr/dp/X", "HP LaserJet Pro M404dn imprimante"), REJECT)

    def test_copie_et_packs_ignores(self):
        for d in ["TONER HP 26A CF226A NOIR COPIE ORIGINAL", "Toner HP 207A Cyan W2211A Diamond",
                  "HP 800 G3 EliteDesk 6 th Core i5- 8Go 256Go SSD +ecran HP E23"]:
            self.assertIsNotNone(build_profile("X", d).skip_reason, d)

    def test_reference_constructeur_rivale_en_revue(self):
        self.assertEqual(verdict("CE314A", "TONER HP 126A NOIR CE314A", AMZ, "https://www.amazon.fr/dp/X",
                                 "HP 126A CE310A Black Original LaserJet Toner"), REVIEW)

    def test_page_redirigee_ne_prouve_rien(self):
        # URL demandée = 130A, mais la page lue est celle du 137A
        p = build_profile("HPB-130", "HP 130A Cyan Original LaserJet Toner Cartridge")
        c = Candidate("https://ssl-product-images.www8-hp.com/digmedialib/prodimg/lowres/c1.png",
                      "https://www.hp.com/in-en/shop/hp-130a-cyan-original-laserjet-toner-cartridge-cf351a.html",
                      "HP 137A Black Original LaserJet Toner Cartridge", provider="page")
        self.assertEqual(evaluate(p, c).verdict, REJECT)

    def test_pack_rejete_pour_article_unitaire(self):
        self.assertEqual(verdict("CAN-446", "CARTOUCHE CANON CL446 COULEUR", "https://ma.jumia.is/unsafe/fit-in/680x680/product/1.jpg",
                                 "https://www.jumia.ma/x-123.html", "Canon Pack PG-445 + CL-446 Couleur - Cartouche d'origine"), REJECT)

    def test_marques_papeterie(self):
        self.assertEqual(build_profile("BIC-B", "STYLO BIC CRISTAL BLEU").brand, "BIC")


class ProviderParsingTests(unittest.TestCase):
    def test_brave(self):
        c = BraveImageProvider.parse({"results": [{"title": "T", "url": "https://p",
                                                   "properties": {"url": "https://i.jpg", "width": 900, "height": 800}}]})
        self.assertEqual((c[0].image_url, c[0].page_url, c[0].width), ("https://i.jpg", "https://p", 900))

    def test_google(self):
        c = GoogleCSEProvider.parse({"items": [{"title": "T", "link": "https://i.jpg",
                                                "image": {"contextLink": "https://p", "width": 900, "height": 800}}]})
        self.assertEqual((c[0].image_url, c[0].page_url, c[0].height), ("https://i.jpg", "https://p", 800))


if __name__ == "__main__":
    unittest.main()
