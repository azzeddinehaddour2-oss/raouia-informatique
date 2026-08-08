# RAOUIA INFORMATIQUE — Architecture SEO & Balisage

## 1. Arborescence complète (Sitemap)

```
raouia-informatique.ma/
├── /                                        Accueil — "Services informatiques entreprises Mohammedia"
├── /services/
│   ├── /services/materiel-informatique/     Vente matériel & informatique professionnelle
│   ├── /services/maintenance-informatique/  Maintenance & contrats
│   │   ├── /services/maintenance-informatique/infogerance/
│   │   ├── /services/maintenance-informatique/audit-conseil/
│   │   └── /services/maintenance-informatique/assurance-informatique/
│   ├── /services/reseaux-serveurs/          Réseaux & Serveurs
│   │   ├── /services/reseaux-serveurs/wifi-professionnel/
│   │   ├── /services/reseaux-serveurs/cloud/
│   │   ├── /services/reseaux-serveurs/microsoft-365/
│   │   └── /services/reseaux-serveurs/google-workspace/
│   ├── /services/cybersecurite/             Cybersécurité
│   │   ├── /services/cybersecurite/sauvegarde/
│   │   └── /services/cybersecurite/firewall/
│   ├── /services/securite-physique/         Sécurité physique
│   │   ├── /services/securite-physique/videosurveillance/   (caméras IP)
│   │   ├── /services/securite-physique/alarmes/
│   │   └── /services/securite-physique/controle-acces/
│   └── /services/solutions-bureau/          Solutions de bureau
│       ├── /services/solutions-bureau/telephonie-ip/
│       ├── /services/solutions-bureau/impression-photocopieurs/
│       └── /services/solutions-bureau/consommables/
├── /etudes-de-cas/                          + 1 URL par cas : /etudes-de-cas/{slug}/
├── /a-propos/                               Histoire, équipe, valeurs
├── /contact/                                Formulaire + NAP + carte
├── /devis-audit/                            Landing conversion "Demander un audit"
└── /blog/                                   SEO éditorial : /blog/{slug}/
```

Pages locales SEO complémentaires (maillage) : `/informatique-entreprise-mohammedia/`, `/informatique-entreprise-casablanca/`.

Règles : URLs en français, kebab-case, ≤ 4 niveaux ; fil d'Ariane BreadcrumbList sur toutes les pages internes ; canonical auto-référentes ; sitemap.xml + robots.txt.

## 2. Structure Hn de la page d'accueil

```
H1  Services informatiques pour entreprises à Mohammedia & Casablanca
 ├─ H2  Ils nous font confiance                              (logos clients)
 ├─ H2  Nos services informatiques professionnels
 │   ├─ H3  Informatique professionnelle & vente de matériel
 │   ├─ H3  Maintenance & contrats d'infogérance
 │   ├─ H3  Réseaux, serveurs & cloud
 │   ├─ H3  Cybersécurité
 │   ├─ H3  Sécurité physique & vidéosurveillance
 │   └─ H3  Solutions de bureau & impression
 ├─ H2  Pourquoi choisir RAOUIA INFORMATIQUE ?
 │   ├─ H3  Un interlocuteur unique pour tout votre SI
 │   ├─ H3  Des engagements de service contractuels
 │   └─ H3  Une expertise certifiée, une proximité locale
 ├─ H2  Études de cas : des résultats mesurables
 │   ├─ H3  {Cas client 1} / H3 {Cas 2} / H3 {Cas 3}
 ├─ H2  Ce que disent nos clients
 └─ H2  Demandez votre audit informatique gratuit          (contact)
```

## 3. JSON-LD LocalBusiness + Service (Schema.org)

Voir le bloc `<script type="application/ld+json">` intégré dans `index.html`.
Type principal : `LocalBusiness` (Schema.org n'a pas de type ITService ; on utilise
LocalBusiness + `makesOffer` de type `Service` avec `serviceType`, ce qui est la
pratique validée par Google pour les prestataires IT).
NAP à compléter : adresse exacte, téléphone, GPS — marqués `À COMPLÉTER` dans le code.
