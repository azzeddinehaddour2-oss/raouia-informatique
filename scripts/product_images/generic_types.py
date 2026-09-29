"""Articles SANS MARQUE : photo d'illustration du TYPE d'objet.

Règle (demande du 28/09/2026) : un article générique (stylo, rame de papier,
câble HDMI sans marque...) ne reçoit jamais la photo d'un produit de marque.
Il reçoit une photo neutre et propre qui montre EXACTEMENT le type d'objet
et ses attributs visibles (couleur, kraft/blanc, transparent...), affichée
sur le site avec la mention « Photo d'illustration ».

Garde-fous :
  * « pur générique » uniquement : chaque mot de la désignation doit être
    un mot de type/attribut connu (vocabulaire ci-dessous). Un mot inconnu
    (marque locale DELI, SICLA, code modèle XO-4470...) = l'article a une
    identité propre -> pas d'illustration générique, il relève de la
    recherche par marque (règle « Canson -> la source doit dire Canson »).
  * types dont l'aspect dépend du modèle (toner, tambour, chargeur de PC
    portable, écran de rechange...) : jamais d'illustration.
  * une illustration = un fichier par clé de type (ex. 'stylo-bille-bleu'),
    validé visuellement puis réutilisé par tous les articles de ce type.
"""

import re
from dataclasses import dataclass

from .matching import detect_brands, normalize_text, tokenize

# --------------------------------------------------------------------------
# Couleurs visibles (clé d'image distincte par couleur)
# --------------------------------------------------------------------------

COLOUR_WORDS = [  # (clé, motifs) — l'ordre compte : "BLEU CIEL" avant "BLEU"
    ("bleu-ciel", r"BLEU\s+CIEL|BLEU\s+CLAIR"),
    ("bleu-fonce", r"BLEU\s+(FONCE|NUIT|MARINE)"),
    ("noir", r"NOIRE?S?|BLACK"),
    ("bleu", r"BLEUE?S?|BLUE"),
    ("rouge", r"ROUGES?|RED"),
    ("vert", r"VERTE?S?|GREEN"),
    ("jaune", r"JAUNES?|YELLOW"),
    ("orange", r"ORANGES?"),
    ("rose", r"ROSES?|ROUSE|PINK"),
    ("violet", r"VIOLETT?E?S?|PURPLE"),
    ("blanc", r"BLANC(HE)?S?|WHITE"),
    ("gris", r"GRIS|GREY|GRAY"),
    ("marron", r"MARRON|BROWN"),
    ("bordeaux", r"BORDEAUX"),
    ("transparent", r"TRANSPAR[AE]NTE?S?|CRISTAL"),
    ("kraft", r"KRAFT"),
    ("multicolore", r"MULTI\s?COULEURS?|MULTICOLOU?R|\d+\s*COULEURS?|\d+\s*CLR|\d+\s*COLOU?RS?|COLORE?S?"),
]
_COLOUR_RX = [(k, re.compile(r"(?<![A-Z])(" + p + r")(?![A-Z])")) for k, p in COLOUR_WORDS]


def colours_of(designation: str) -> list[str]:
    t = normalize_text(designation)
    found = []
    for key, rx in _COLOUR_RX:
        if rx.search(t):
            found.append(key)
            t = rx.sub(" ", t)
    return found


# --------------------------------------------------------------------------
# Types d'objets
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TypeRule:
    key: str                 # préfixe de clé d'image
    label: str               # libellé affiché
    pattern: str             # regex sur la désignation normalisée
    queries: tuple           # requêtes pour les banques d'images libres
    colour: bool = False     # la couleur fait partie de la clé d'image
    require_colour: bool = False  # sans couleur connue -> pas d'illustration


def R(key, label, pattern, queries, colour=False, require_colour=False):
    return TypeRule(key, label, pattern, tuple(queries), colour, require_colour)


# Ordre = priorité (le premier motif qui correspond gagne).
TYPES = [
    # --- Écriture ---------------------------------------------------------
    R("marqueur-tableau", "Marqueur pour tableau blanc",
      r"MARQUEUR.*(TABLEAU|WHITE ?BOARD)|WHITE ?BOARD.*MARQUEUR",
      ["whiteboard marker", "dry erase marker"], colour=True, require_colour=True),
    R("marqueur-permanent", "Marqueur permanent", r"MARQU?EUR.*PERMANENT|PERMANENT.*MARQUEUR",
      ["permanent marker"], colour=True, require_colour=True),
    R("surligneur", "Surligneur fluorescent", r"FLUORESCENT|SURLIGNEUR|HIGH ?LIGHTER",
      ["highlighter pen"], colour=True, require_colour=True),
    R("stylo-bille", "Stylo à bille", r"STYLO\s+(A\s+)?BILLE|STYLOS?\s+BILLE|BALLPOINT",
      ["ballpoint pen"], colour=True, require_colour=True),
    R("crayon-couleur", "Crayons de couleur", r"CRAYONS?\s+(DE\s+)?COULEURS?",
      ["colored pencils", "colour pencils"]),
    R("crayon-papier", "Crayon à papier", r"CRAYONS?\s+(A\s+)?PAPP?IER|CRAYON\s+HB|\bHB\s*2\b",
      ["graphite pencil HB", "pencil"]),
    R("porte-mine", "Porte-mine", r"PORTE.?MINE|MECHANICAL PENCIL", ["mechanical pencil"]),
    R("gomme", "Gomme", r"^GOMMES?\b", ["eraser rubber white"], colour=True),
    R("taille-crayon", "Taille-crayon", r"TAILLE.?CRAYON|AILLE CRY?ON", ["pencil sharpener"]),
    R("craie", "Craies", r"CRAIES?", ["chalk sticks"], colour=True),
    R("correcteur", "Correcteur", r"CORRECTEUR|BLANCO|TIPPEX", ["correction tape", "correction fluid"]),
    # --- Classement / papeterie ------------------------------------------
    R("classeur-anneaux", "Classeur à anneaux", r"^CLASSEUR\b.*ANNEAUX", ["ring binder"],
      colour=True, require_colour=True),
    R("classeur-levier", "Classeur à levier", r"^CLASSEUR\b.*LEVIER", ["lever arch file"],
      colour=True, require_colour=True),
    R("chemise-rabat", "Chemise à rabats", r"CHEMISE\s+A\s+RABAT", ["document folder with flaps"],
      colour=True, require_colour=True),
    R("chemise-cartonnee", "Chemise cartonnée", r"CHEMISE\s+CARTONN", ["manila folder", "cardboard file folder"],
      colour=True, require_colour=True),
    R("pochette-perforee", "Pochettes perforées", r"CHEMISE\s+PERFOR|POCHETTES?\s+PERFOR|SHEET PROTECTOR",
      ["sheet protector punched pocket"]),
    R("enveloppe-bouton", "Enveloppe plastique à bouton", r"ENVELOPPE\s+PLASTIQUE",
      ["plastic document envelope snap button"], colour=True, require_colour=True),
    R("enveloppe-pochette", "Enveloppe pochette", r"^ENVELOPPES?\b.*POCHETTE", ["envelope"], colour=True,
      require_colour=True),
    R("enveloppe", "Enveloppe", r"^ENVELOPPES?\b", ["envelope"], colour=True, require_colour=True),
    R("boite-archive-carton", "Boîte d'archives en carton", r"BOITE\s+(A\s+)?ARCHIVES?\s+CARTON|ARCHIVES?.*CARTON",
      ["archive box cardboard"]),
    R("boite-archive-plastique", "Boîte d'archives en plastique", r"BOITE\s+(A\s+)?ARCHIVES?\s+PLASTIQUE",
      ["plastic archive box file"], colour=True, require_colour=True),
    R("intercalaires", "Intercalaires", r"INTERC?ALAIRES?", ["file dividers index tabs"]),
    R("ramette-a4", "Ramette de papier A4", r"RAMETTE.*A4|PAPIER\s+A4\s+(80|75|70)", ["ream of paper", "paper ream"],
      colour=True),
    R("ramette-a3", "Ramette de papier A3", r"RAMETTE.*A3", ["ream of paper", "paper ream"], colour=True),
    R("ramette-a5", "Ramette de papier A5", r"RAMETTE.*A5", ["ream of paper", "paper ream"], colour=True),
    R("papier-couleur", "Papier couleur", r"PAPIER\s+(EN\s+)?COULEUR", ["colored paper sheets"], colour=True),
    R("papier-calque", "Papier calque", r"PAPIER\s+CALQUE", ["tracing paper"]),
    R("papier-carbone", "Papier carbone", r"PAPIER\s+CARBONE", ["carbon paper"]),
    R("papier-millimetre", "Papier millimétré", r"MILL?IMETRIQUE|MILLIMETRE", ["graph paper millimeter"]),
    R("papier-thermique", "Rouleau de papier thermique",
      r"PAPIER\s+(DE\s+CAISSE\s+)?THERMIQUE|ROULEAU\s+(DE\s+CAISSE\s+)?THERMIQUE",
      ["thermal paper roll"]),
    R("papier-crepon", "Papier crépon", r"PAPIER\s+CREPON", ["crepe paper roll"], colour=True),
    R("cahier", "Cahier", r"^CAHIERS?\b", ["exercise book notebook"], colour=True),
    R("bloc-steno", "Bloc sténo", r"BLOC.*STENO", ["steno pad", "stenographer notebook"]),
    R("bloc-notes", "Bloc-notes", r"BLOC\s+NOTES?", ["notepad", "writing pad"]),
    R("bloc-cube", "Bloc cube (notes repositionnables)", r"BLOC\s+CUBE|POST.?IT|POSTITE",
      ["sticky notes cube", "memo cube"], colour=True, require_colour=True),
    R("etiquettes-a4", "Planche d'étiquettes adhésives A4", r"ETIQUETTES?\s+ADHESIVE|AUTOCOLLANTES?\s+\d+\s+FEUILLES",
      ["adhesive labels sheet A4"]),
    R("fiche-bristol", "Fiches bristol", r"FICHE.*BRISTOL", ["index cards"], colour=True),
    R("registre", "Registre", r"^REGISTRE\b", ["ledger book"], colour=True),
    R("repertoire", "Répertoire alphabétique", r"^REPERTOIRE\b", ["address book alphabetical index"]),
    R("agenda", "Agenda", r"^AGENDA\b", ["diary planner"], colour=True),
    R("porte-vues", "Porte-vues", r"PORTE\s+DOCUMENTS?\s+\d+\s+VUES|PORTE.?VUES", ["display book clear pockets"],
      colour=True),
    R("porte-bloc", "Porte-bloc à pince", r"^(PORTE\s+)?BLOC\s+A\s+PINCE(?!.*DOUBLE)|CLIPBOARD", ["clipboard"], colour=True),
    R("couverture-cahier", "Protège-cahier", r"COUVERTURE\s+(GRAND|PETIT)\s+CAHIER|PROTEGE.?CAHIER",
      ["book cover plastic notebook cover"], colour=True),
    R("papier-paperboard", "Papier pour tableau de conférence", r"PAPIER\s+POUR\s+TABLEAU|FLIP\s?CHART",
      ["flip chart paper pad"]),
    R("papier-photo", "Papier photo", r"PAPIER\s+PHOTO", ["photo paper glossy"]),
    # --- Petit matériel de bureau ---------------------------------------
    R("agrafes", "Agrafes", r"^AGRAF(E|ES)\b", ["staples box", "staples"]),
    R("agrafeuse", "Agrafeuse", r"^AGRAFEUSE\b", ["stapler"]),
    R("arrache-agrafes", "Arrache-agrafes", r"ARRACHE.?AGRAFES?|DEAGRAF", ["staple remover"]),
    R("perforateur", "Perforateur", r"PERFOR(EUSE|ATEUR|ATRICE)", ["hole punch"]),
    R("trombones", "Trombones", r"TROMBONN?ES?", ["paper clips"], colour=True),
    R("pince-double-clip", "Pinces double clip", r"BINDER\s+CLIPS?|DOUBLE\s+CLIP", ["binder clips"], colour=True),
    R("punaises", "Punaises", r"PUNAISES?", ["thumbtacks push pins"]),
    R("elastiques", "Élastiques", r"BRACELETS?\s+ELASTIQUES?|ELASTIQUES?", ["rubber bands"]),
    R("ciseaux", "Ciseaux", r"^CISEAUX?\b", ["scissors office"]),
    R("cutter", "Cutter", r"^CUTTER\b", ["utility knife cutter"]),
    R("regle", "Règle", r"^REGLE\b", ["ruler"], colour=True),
    R("rapporteur", "Rapporteur", r"^RAPPORTEUR\b", ["protractor"], colour=True),
    R("equerre", "Équerre", r"^EQUERRE\b", ["set square"], colour=True),
    R("compas", "Compas", r"^COMPAS", ["drawing compass"], colour=True),
    R("colle-baton", "Colle en bâton", r"COLLE\s+(EN\s+)?(BATON|STICK)|GLUE STICK", ["glue stick"]),
    R("colle-liquide", "Colle liquide", r"COLLE\s+LIQUIDE", ["white glue bottle"]),
    R("ruban-adhesif", "Ruban adhésif", r"^(SCOTCH|RUBAN\s+ADHESIF)\b", ["adhesive tape roll"],
      colour=True),
    R("ruban-emballage", "Ruban adhésif d'emballage", r"SCOTCH\s+(D\s*)?EMBALLAGE|EMBALLAGE", ["packing tape"],
      colour=True),
    R("devidoir", "Dévidoir de ruban adhésif", r"DEVIDOIR", ["tape dispenser"]),
    R("brosse-tableau", "Brosse pour tableau blanc", r"BROSSE.*TABLEAU|BROSSE\s+EPONGE", ["whiteboard eraser"]),
    R("tableau-blanc", "Tableau blanc", r"^TABLEAU\s+(BLANC|MAGNETIQUE)", ["whiteboard"]),
    R("tableau-liege", "Tableau en liège", r"^TABLEAU\s+(EN\s+)?LIEGE", ["cork board", "cork notice board"]),
    R("poubelle-metal", "Corbeille à papier en métal", r"^POUBELLE\s+METAL", ["metal waste paper basket", "mesh wastebasket"],
      colour=True, require_colour=True),
    R("porte-stylo", "Pot à crayons", r"^PORTE\s+STYLOS?$", ["pencil holder", "pen holder desk"]),
    R("baguettes-reliure", "Baguettes à relier", r"BAGUETTES?", ["slide binder bars", "binding bars"],
      colour=True, require_colour=True),
    R("spirales-reliure", "Spirales de reliure", r"^SPIRALE?S?\b|RELIURE\s+SPIRALE", ["plastic binding combs"],
      colour=True),
    R("couverture-reliure", "Couvertures de reliure", r"COUVERTURES?\s+PVC", ["binding covers"], colour=True),
    R("pochette-plastification", "Pochettes de plastification", r"POCHETTES?\s+(DE\s+|A\s+)?PLASTIFI",
      ["laminating pouches"]),
    R("porte-badge", "Porte-badge", r"PORTE.?BADGE", ["badge holder"]),
    R("tampon-encreur", "Tampon encreur", r"BOITE\s+A\s+TAMPON|TAMPON\s+ENCREUR", ["ink stamp pad"],
      colour=True, require_colour=True),
    R("encre-tampon", "Encre pour tampon", r"ENCRE\s+A\s+TAMPONS?|ENCRE\s+TAMPON", ["stamp pad ink bottle"],
      colour=True, require_colour=True),
    R("gouache", "Gouache", r"GOUACHE", ["gouache paint tubes"]),
    R("pate-modeler", "Pâte à modeler", r"PATE\s+A\s+MODELER", ["modelling clay"]),
    R("calculatrice", "Calculatrice", r"CALCULATRICE", ["calculator"]),
    # --- Informatique : câbles & accessoires (aspect standard) -----------
    R("cable-hdmi", "Câble HDMI", r"CABLE\s+HDMI|HDMI\s+CABLE|HDTV\s+CABLE|CABLE\s+HDTV", ["HDMI cable"]),
    R("cable-vga", "Câble VGA", r"CABLE\s+VGA", ["VGA cable"]),
    R("cable-displayport", "Câble DisplayPort", r"CABLE\s+DISPLAY", ["DisplayPort cable"]),
    R("cable-reseau", "Câble réseau RJ45", r"CABLE\s+(RESEAU|RJ\s?45)|RJ\s?45\s+CABLE|CABLE\s+ETHERNET",
      ["ethernet cable RJ45", "patch cable"], colour=True),
    R("cable-rj11", "Câble téléphonique RJ11", r"CABLE\s+RJ\s?11|CABLE\s+TELEPHONIQUE", ["telephone cable RJ11"]),
    R("cable-alimentation-c13", "Câble d'alimentation PC de bureau (C13)", r"CABLE\s+[IA]LIMENTATION\s+PC\s+BUREAU",
      ["IEC C13 power cord", "computer power cord"]),
    R("cable-alimentation-c5", "Câble d'alimentation PC portable (C5, trèfle)", r"CABLE\s+[IA]LIMENTATION\s+PC\s+PORTABLE",
      ["C5 power cord cloverleaf", "IEC C5 cable"]),
    R("cable-alimentation-c7", "Câble d'alimentation 2 broches (C7, en 8)", r"CABLE\s+[IA]LIMENTATION\s+2P\b",
      ["C7 power cord figure 8", "IEC C7 cable"]),
    R("cable-imprimante", "Câble USB imprimante (USB-A / USB-B)", r"CABLE\s+IMPRIM[AE]NTE", ["USB printer cable"]),
    R("cable-usb-c-c", "Câble USB-C vers USB-C", r"CABLE\s+(USB\s+)?TYPE.?C\s+(TO\s+)?TYPE.?C",
      ["USB-C to USB-C cable", "USB-C cable"]),
    R("cable-usb-a-c", "Câble USB-A vers USB-C", r"CABLE\s+USB\s+(TO\s+)?TYPE.?C\b",
      ["USB-A to USB-C cable", "USB type C cable"]),
    R("cable-jack", "Câble audio jack 3,5 mm", r"CABLE\s+(AUX\s+)?JACK|CABLE\s+AUX", ["3.5mm audio cable"]),
    R("cable-rca", "Câble RCA", r"CABLE\s+RCA|CABLE\s+AV\b", ["RCA cable"]),
    R("cable-coaxial", "Câble coaxial", r"COAXIAL", ["coaxial cable"]),
    R("multiprise", "Multiprise", r"MULTIPRISES?|RALLONGE", ["power strip"]),
    R("cle-usb", "Clé USB", r"^CLE\s+USB\b", ["USB flash drive"]),
    R("souris", "Souris filaire USB", r"^SOURIS\s+(USB|FILAIRE)", ["computer mouse usb"]),
    R("clavier", "Clavier USB", r"^CLAVIER\s+USB", ["computer keyboard usb"]),
    R("souris-sans-fil", "Souris sans fil", r"^SOURIS\s+SANS\s+FIL", ["wireless mouse"]),
    R("hub-usb", "Hub USB 4 ports", r"(USB\s+)?HUB\s+(USB\s+)?\d\.0\s+4\s?PORTS?", ["USB hub 4 port"]),
    R("tapis-souris", "Tapis de souris", r"TAPIS\s+(DE\s+)?SOURIS|MOUSE\s+PAD", ["mouse pad"]),
    R("cd-r", "CD-R vierge", r"^CD.?R\b", ["CD-R disc"]),
    R("dvd-r", "DVD-R vierge", r"^DVD.?R\b", ["DVD-R disc"]),
    R("pile-aa", "Piles AA", r"PIL+ES?\b.*\bAA\b(?!A)|\bLR6\b", ["AA battery"]),
    R("pile-aaa", "Piles AAA", r"PIL+ES?\b.*\bAAA\b|\bLR03\b", ["AAA battery"]),
    R("pile-9v", "Pile 9 V", r"PIL+ES?\b.*\b9V\b|\b6LR61\b", ["9 volt battery"]),
    R("pile-bouton", "Pile bouton lithium", r"CR\s?2032|CR\s?2025|CR\s?2016", ["CR2032 coin cell"]),
    # --- Entretien / consommables divers ----------------------------------
    R("gants-nitrile", "Gants nitrile", r"GANTS?\s+(EN\s+)?NITRILE", ["nitrile gloves"], colour=True,
      require_colour=True),
    R("balai", "Balai", r"^BALAIS?\b", ["broom"]),
    R("serpillere", "Serpillière", r"SERPIL+I?ERE", ["floor cloth mop cloth"]),
    R("papier-hygienique", "Papier hygiénique", r"PAPIER\s+HYG", ["toilet paper roll"]),
    R("essuie-mains", "Essuie-mains papier", r"ESSUIE.?MAINS?", ["paper towel roll"]),
    R("mouchoirs", "Mouchoirs en papier", r"MOUCHOIRS?", ["facial tissues box"]),
    R("gobelets", "Gobelets jetables", r"GOBL?ETS?", ["disposable cups"], colour=True),
    R("fourchettes", "Fourchettes en plastique", r"FOURCHETTES?", ["plastic forks"], colour=True),
    R("cuilleres", "Cuillères en plastique", r"CUILLERES?", ["plastic spoons"], colour=True),
    R("extincteur-poudre", "Extincteur à poudre portatif", r"EXTINCTEURS?.*POUDRE(?!.*\b([2-9]\d|1[3-9])\s*KG)",
      ["fire extinguisher powder"]),
    R("extincteur-co2", "Extincteur CO2", r"EXTINCTEURS?.*CO2", ["CO2 fire extinguisher"]),
    R("gilet-hv", "Gilet haute visibilité", r"^GILET\b", ["high visibility vest"], colour=True, require_colour=True),
    R("sac-a-dos", "Sac à dos", r"^SAC\s+A\s+DOS\b", ["backpack"], colour=True, require_colour=True),
    R("rouleau-kraft", "Rouleau de papier kraft", r"ROULEAUX?\s+(DE\s+)?PAPIER\s+KRAFT", ["kraft paper roll"]),
]
_TYPE_RX = [(t, re.compile(t.pattern)) for t in TYPES]

# Types dont l'aspect dépend du modèle précis : jamais d'illustration.
MODEL_DEPENDENT = re.compile(
    r"\b(TONER|DRUM|TAMBOUR|CARTOUCHE|RIBBON|DEVELOPPEUR|FOUR|FUSER|CHARGEUR|ADAPTATEUR|ADAPTER|ADAPTOR|"
    r"BATTERIE|BATTERY|ECRAN|CLAVIER\s+(MAC|PORTABLE|PC\s+PORTABLE)|KIT|PIECE|COQUE|GLASS|INCASSABLE|"
    r"LICENCE|IMPRESSION|PERSONNALISE|BANDEROLE|AFFICHE|DEPLIANT|MENU|CARNET\s+CEC|FT\s)")

# --------------------------------------------------------------------------
# Vocabulaire « générique » autorisé (tout autre mot = identité propre)
# --------------------------------------------------------------------------

GENERIC_WORDS = set("""
A AU AUX AVEC DE DES DU D EN ET L LA LE LES POUR SUR SANS PAR TO OF FOR IN X N NO REF RF
PIECE PIECES PCS PC PS P PAQUET BOITE BTE CTN DETAIL DETAILS UNITE LOT FEUILLES FEUILLE F PAGES PAGE
STYLO STYLOS BILLE CRAYON CRAYONS PAPIER PAPPIER COULEUR COULEURS COLOR COLOUR HB MINE PORTE
GOMME GOMMES BLANCHE TAILLE CRAIE CRAIES SANS POUSSIERE CORRECTEUR TAPE
MARQUEUR MARQUEURS PERMANENT TABLEAU WHITE BOARD RECHARGEABLE RECHARGABLE POINTE FINE MOYENNE LARGE
FLUORESCENT FLUORESCENTS SURLIGNEUR HIGHLIGHTER
CLASSEUR LEVIER ANNEAUX DOS CHEMISE CHEMISES RABAT RABATS CARTONNEE CARTONNE CARTONNES CARTON
PERFORE PERFOREE PERFOREES POCHETTE POCHETTES MIC MICRONS ENVELOPPE ENVELOPPES POCHETTES
PLASTIQUE PLASTIQUES BOUTON PRESSION BOITE ARCHIVE ARCHIVES INTERCALAIRES INTERCALAIRE
RAMETTE RAMETTES CALQUE CARBONE MILLIMETRIQUE THERMIQUE CAISSE CREPON ROULEAU ROULEAUX
CAHIER CAHIERS PIQUE GRAND PETIT GRANDE PETITE FORMAT GF PF BLOC NOTE NOTES STENO SPIRAL SPIRALE CUBE
ETIQUETTE ETIQUETTES ADHESIVE ADHESIVES AUTOCOLLANTES MULTI USAGES FICHE FICHES BRISTOL BRISTOLE REGISTRE
AGRAFE AGRAFES AGRAFEUSE MAIN PINCE ARRACHE PERFOREUSE PERFORATEUR TROMBONE TROMBONES TROMBONNES
BINDER CLIPS CLIP DOUBLE PUNAISES BRACELET BRACELETS ELASTIQUE ELASTIQUES CISEAUX CISEAU CUTTER REGLE
EQUERRE COMPAS COLLE BATON STICK LIQUIDE SCOTCH RUBAN ADHESIF EMBALLAGE DEVIDOIR BROSSE EPONGE
BAGUETTES BAGUETTE COUVERTURE COUVERTURES PVC PLASTIFICATION BADGE TAMPON TAMPONS ENCREUR ENCRE
GOUACHE PATE MODELER CALCULATRICE PANIER PANNIER COURRIER COURIER CORBEILLE ETAGE ETAGES METAL METALLIQUE
CABLE HDMI HDTV VGA DISPLAY DISPLAYPORT PORT RESEAU RJ45 RJ11 TELEPHONIQUE ALIMENTATION ILIMENTATION SECTEUR
IMPRIMANTE IMPRIMENTE USB TYPE TYP C JACK AUX AUDIO RCA AV COAXIAL CCTV MULTIPRISE MULTIPRISES RALLONGE
PRISE PRISES CLE SOURIS FILAIRE CLAVIER TAPIS CD R DVD VIERGE PILE PILES PILLE ALKALINE ALCALINE LITHIUM
HIGH QUALITY SPEED PREMIUM STANDARD NORMAL ULTRAHD ULTRA HD K CAT CAT5 CAT5E CAT6 CAT6A MALE
GANTS GANT NITRILE JETABLE JETABLES BALAI BALAIS SERPILLERE SERPILIERE HYGIENIQUE HYGIENNIQUE HYG
ESSUIE MAINS MOUCHOIR MOUCHOIRS MOUCHOIRE GOBELET GOBELETS GOBLET FOURCHETTE FOURCHETTES CUILLERE CUILLERES
EXTINCTEUR EXTINCTEURS POUDRE ABC CO2 GILET HI VIS HAUTE VISIBILITE
NOIR NOIRE NOIRS BLACK BLEU BLEUE BLEUS BLUE CIEL CLAIR FONCE NUIT MARINE ROUGE ROUGES RED VERT VERTE VERTS GREEN
JAUNE JAUNES YELLOW ORANGE ROSE ROSES ROUSE PINK VIOLET VIOLETTE PURPLE BLANC BLANCS WHITE GRIS GREY GRAY
MARRON BROWN BORDEAUX TRANSPARENT TRANSPARENTE TRANSPARANT KRAFT MULTICOULEUR MULTICOULEURS MULTICOLOR CLR
MM CM M G KG L ML CL GR GRS V MAH FT
AGENDA SPIRALE DOCUMENT DOCUMENTS VUES MAGNETIQUE LIEGE POUBELLE RAPPORTEUR REPERTOIRE Z TICKET
HUB PORTS 4PORT SAC DOS FIL PHOTO CAHIER BUREAU PORTABLE STENO CONFERENCE KRAFT
""".split())

# Tokens chiffrés autorisés : dimensions, grammage, formats, longueurs...
SPEC_OK = re.compile(
    r"^(\d+([.,]\d+)?(MM|CM|M|G|GR|GRS|KG|L|ML|CL|V|P|F|PCS|MIC|K)"
    r"|\d{1,3}([.,]\d+)?|20[1-3]\d"          # petits nombres, millésime d'agenda
    r"|\d+X\d+(X\d+)?|A[0-6]\+?|CAT\d[A-Z]?|RJ\d\d|[2-9]P|\d\.0)$")
# Code article/modèle écrit avec tiret (XO-4470, A-808-4, 6800-12) : identité propre.
CODE_CHUNK = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)+")


def _residue(designation: str) -> list[str]:
    out = []
    for chunk in CODE_CHUNK.findall(normalize_text(designation)):
        joined = chunk.replace("-", "")
        if not re.search(r"\d", chunk) or SPEC_OK.match(joined):
            continue
        if re.search(r"\d{3,}", chunk) or (re.search(r"[A-Z]", chunk) and re.search(r"\d", chunk)):
            out.append(chunk)
    toks = tokenize(designation.replace("*", " X ").replace("/", " "))
    for t in toks:
        if t in GENERIC_WORDS:
            continue
        t2 = re.sub(r"[.,]", "", t)
        if SPEC_OK.match(t) or SPEC_OK.match(t2):
            continue
        out.append(t)
    return out


# Familles de connecteurs : un câble qui en cite deux est un adaptateur
# (DisplayPort -> HDMI...) dont la photo d'un câble simple serait fausse.
CONNECTORS = [(f, re.compile(p)) for f, p in [
    ("hdmi", r"HDMI|HDTV"), ("vga", r"\bVGA\b"), ("displayport", r"DISPLAY"),
    ("rj45", r"RJ\s?45|RESEAU"), ("rj11", r"RJ\s?11|TELEPHONIQUE"), ("usb-c", r"TYPE.?C\b|USB.?C\b"),
    ("usb", r"\bUSB\b(?!.?C\b)"), ("rca", r"\bRCA\b|\bAV\b"), ("jack", r"JACK|\bAUX\b"),
]]
ALLOWED_CONNECTORS = {"cable-usb-a-c": {"usb", "usb-c"}, "cable-imprimante": {"usb"}}


@dataclass
class GenericMatch:
    key: str | None          # clé d'image, ex. 'stylo-bille-bleu'
    rule: TypeRule | None
    colours: list
    reason: str              # motif si pas d'illustration


def classify_generic(designation: str) -> GenericMatch:
    """Clé d'illustration pour un article pur générique, ou motif du refus."""
    up = normalize_text(designation)
    if detect_brands(designation):
        return GenericMatch(None, None, [], "article de marque : photo exacte de la marque exigée")
    if MODEL_DEPENDENT.search(up):
        return GenericMatch(None, None, [], "aspect dépendant du modèle : pas d'illustration générique")
    rule = next((t for t, rx in _TYPE_RX if rx.search(up)), None)
    if not rule:
        return GenericMatch(None, None, [], "type d'objet non répertorié")
    if rule.key.startswith("cable-"):
        fams = {f for f, rx in CONNECTORS if rx.search(up)}
        if len(fams - ALLOWED_CONNECTORS.get(rule.key, set())) > 1:
            return GenericMatch(None, rule, [], f"câble adaptateur ({' / '.join(sorted(fams))}) : aspect spécifique")
    residue = _residue(designation)
    if residue:
        return GenericMatch(None, rule, [], f"mots propres à l'article ({' '.join(residue[:4])}) : marque/modèle probable")
    cols = colours_of(designation)
    if rule.require_colour and not cols:
        return GenericMatch(None, rule, cols, "couleur non précisée : impossible de garantir l'aspect")
    if len(cols) > 1 and "multicolore" not in cols:
        return GenericMatch(None, rule, cols, f"plusieurs couleurs citées ({', '.join(cols)})")
    key = rule.key
    if rule.colour and cols:
        key += "-" + cols[0]
    return GenericMatch(key, rule, cols, "")
