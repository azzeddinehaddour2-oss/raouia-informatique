# RAOUIA INFORMATIQUE — Design System (Tailwind CSS)

Configuration utilisée telle quelle dans `index.html` via `tailwind.config` (CDN)
et transposable dans `tailwind.config.js` pour un build de production.

```js
tailwind.config = {
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#0B2447', // marine — header, hero, footer, titres
          light:   '#19376D', // ardoise — sections alternées, cartes sombres
          lighter: '#2B4C87', // hover sur fonds sombres
        },
        secondary: {
          DEFAULT: '#19376D',
        },
        accent: {
          DEFAULT: '#F59E0B', // ambre — CTA uniquement
          hover:   '#D97706', // état hover des CTA
          active:  '#B45309', // état active/pressed
        },
        success: '#059669',
        whatsapp: '#25D366',
        neutral: {
          50:  '#F8FAFC', // fonds de sections
          100: '#F1F5F9',
          200: '#E2E8F0', // bordures
          400: '#94A3B8', // texte atténué sur fond sombre
          600: '#475569', // texte secondaire
          700: '#334155', // corps de texte
          900: '#0F172A', // titres sur fond clair
        },
      },
      fontFamily: {
        heading: ['Georgia', '"Times New Roman"', 'serif'],
        body: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Arial', 'sans-serif'],
      },
      borderRadius: {
        card: '0.75rem',  // cartes
        btn:  '0.375rem', // boutons
        field:'0.375rem', // champs de formulaire
      },
      boxShadow: {
        card:        '0 1px 3px rgba(11,36,71,.08), 0 1px 2px rgba(11,36,71,.04)',
        'card-hover':'0 12px 24px -8px rgba(11,36,71,.18), 0 4px 8px rgba(11,36,71,.06)',
        cta:         '0 4px 14px rgba(245,158,11,.35)',
        float:       '0 8px 30px rgba(11,36,71,.25)',
      },
      maxWidth: { site: '76rem' }, // 1216px — conteneur principal
    },
  },
}
```

## Grille responsive
- Mobile (< 640px) : 4 colonnes — `grid-cols-4`, gouttière 16px, marge 16px.
- Tablette (≥ 768px) : 8 colonnes — `md:grid-cols-8`, gouttière 24px.
- Desktop (≥ 1024px) : 12 colonnes — `lg:grid-cols-12`, gouttière 32px, conteneur `max-w-site`.

## États interactifs (conventions)
- Boutons CTA : `bg-accent hover:bg-accent-hover active:bg-accent-active transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`
- Cartes : `shadow-card hover:shadow-card-hover hover:-translate-y-1 transition-all duration-300`
- Liens nav : `hover:text-accent transition-colors duration-200` + soulignement animé (`after:` scale-x)
- Champs : `border-neutral-200 focus:border-primary focus:ring-2 focus:ring-primary/20`

## Accessibilité (WCAG 2.2 AA — ratios vérifiés)
- Texte blanc `#FFFFFF` sur primary `#0B2447` : ratio ≈ 14,9:1 ✔
- Texte `#0B2447` sur accent `#F59E0B` : ratio ≈ 7,2:1 ✔ (les CTA ambre utilisent du texte marine, pas blanc)
- Corps `#334155` sur blanc : ratio ≈ 9,7:1 ✔
- `#94A3B8` sur `#0B2447` : ratio ≈ 5,9:1 ✔ (texte atténué footer/hero)
- Focus visible sur tous les éléments interactifs, cibles tactiles ≥ 44px, `aria-label` sur icônes seules, landmarks (`header/nav/main/footer`), skip-link.
