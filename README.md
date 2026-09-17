# RENTDZ — plateforme de location de voitures pour l'Algérie

**Votre route commence ici.**

Plateforme full-stack qui met en relation des sociétés de location algériennes et
leurs clients : catalogue, moteur de réservation, portail loueur, console
d'administration, documents privés, paiements et notifications.

* Marché : Algérie · Devise : **DZD (DA)** · Fuseau : **Africa/Algiers**
* Langues : **français** (défaut), **arabe** (RTL réel), **anglais**
* Aucune dépendance externe : **Python 3.11+ et rien d'autre**

---

## 1. Démarrage rapide

```bash
python manage.py migrate          # crée la base et les rôles
python manage.py seed             # données de démonstration (dev uniquement)
python manage.py serve            # http://127.0.0.1:8000
```

Comptes de démonstration (mot de passe commun `RentDZ2026!`) :

| Rôle | Identifiant |
|---|---|
| Super administrateur | `admin@rentdz.dz` |
| Loueur (flotte) | `loueur1.demo@rentdz.test` |
| Client | `amine.demo@rentdz.test` |
| Support | `support.demo@rentdz.test` |
| Finance | `finance.demo@rentdz.test` |

Pour un administrateur réel : `python manage.py createadmin`.

### Commandes

| Commande | Rôle |
|---|---|
| `migrate [--fresh]` | Applique le schéma (49 tables, 50 index) |
| `seed` | Données de démonstration (refusé si `APP_ENV=production`) |
| `purge-demo` | Supprime toute donnée marquée démo |
| `createadmin` | Crée / réinitialise un super administrateur |
| `serve` | Démarre le serveur |
| `test` | Lance toute la suite de tests |
| `check` | Diagnostic de configuration et de mise en production |
| `release-holds` | Libère les réservations non confirmées expirées (cron) |
| `purge-documents` | Applique la durée de conservation des documents (cron) |
| `flush-outbox` | Tente l'envoi des e-mails en file |

Tâches planifiées recommandées : `release-holds` toutes les 5 min,
`flush-outbox` toutes les minutes, `purge-documents` une fois par jour.

---

## 2. Architecture

```
app/
  config.py            Configuration par variables d'environnement
  db.py                Accès SQLite (WAL, FK, transactions BEGIN IMMEDIATE)
  schema.sql           Schéma relationnel complet
  security.py          Hachage, jetons, CSRF, validation, RBAC
  http.py              Routage, sessions, en-têtes, gestion d'erreurs
  i18n.py              FR / AR / EN + formats algériens
  services/            Logique métier (aucune logique dans l'UI)
    availability.py    Disponibilité et verrous de calendrier
    booking_service.py Moteur de réservation
    pricing.py         Moteur tarifaire
    payment/           Interface PaymentProvider + implémentations
    ...
  api/                 API JSON /api/v1 (95 points de terminaison)
  web/                 Pages rendues côté serveur (45 routes)
  static/              CSS et JavaScript
  seeds/               Géographie algérienne + données de démonstration
tests/                 7 suites, 640 vérifications
```

Séparation stricte : les vues n'accèdent jamais à la base directement, les
services ne connaissent pas HTTP, aucun secret ne quitte le serveur.

---

## 3. Garantie anti-double-réservation

Le point le plus critique du produit. Trois niveaux :

1. **Base de données** — la table `vehicle_day_locks` porte une contrainte
   `UNIQUE (vehicle_id, day)`. Une réservation insère une ligne par jour occupé
   (du jour de départ au jour de retour inclus). Deux périodes qui se
   chevauchent sont donc **impossibles**, quelle que soit l'application.
2. **Transaction** — la création se fait dans un unique `BEGIN IMMEDIATE`, qui
   prend le verrou d'écriture avant toute lecture décisive.
3. **Application** — l'état du véhicule est relu à l'intérieur de la
   transaction ; un `IntegrityError` est traduit en `409 dates_unavailable`.

Maintenances et dates bloquées utilisent la **même** table : un blocage ne peut
pas chevaucher une réservation, et inversement.

Test : 8 clients réservent simultanément le même véhicule aux mêmes dates.
Résultat vérifié — **1 succès, 7 conflits propres, 0 verrou orphelin**.

Convention : le jour de restitution reste occupé (préparation du véhicule).
Une réservation adjacente commence donc le lendemain du retour.

---

## 4. Sécurité

* Mots de passe : PBKDF2-SHA256, 260 000 itérations, sel par utilisateur
* Sessions : jeton aléatoire, **haché** en base, cookie `HttpOnly` + `SameSite`
* CSRF : double soumission, jeton lié à la session
* RBAC : 8 rôles, 32 permissions, **vérifiées côté serveur sur chaque route**
* Isolation : une ressource d'autrui renvoie `404`, jamais `403` (pas de fuite d'existence)
* Anti-énumération : messages de connexion et de réinitialisation identiques
* Limitation de débit : connexion, inscription, réinitialisation, réservation
* Requêtes SQL **exclusivement** paramétrées
* Sortie HTML systématiquement échappée ; JSON en `<script>` neutralisé (`\u003c`)
* En-têtes : CSP restrictive, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`
* Uploads validés par **octets magiques**, jamais par extension
* Aucun numéro de carte ni CVV n'est stocké
* Journal d'audit en écriture seule (aucune route d'écriture exposée)

### Documents personnels

Permis et pièces d'identité sont stockés **hors de tout répertoire servi**, sous
un nom aléatoire, en `0600`. Un téléchargement exige **trois** conditions :
session valide **+** droit d'accès **+** jeton signé à courte durée (5 min par
défaut). Chaque accès, autorisé ou refusé, est journalisé. La durée de
conservation est paramétrable et appliquée par `purge-documents`.

---

## 5. Tarification

Calculée **côté serveur** et figée sur la réservation (une hausse de tarif
ultérieure ne modifie jamais une réservation existante).

Paliers dégressifs (mois > semaine > jour), tarif week-end (vendredi/samedi),
règles saisonnières, jours fériés, remises longue durée et réservation
anticipée, codes promo (%, montant fixe, plafond, minimum, limites globale et
par client), services optionnels, frais d'agence et d'aéroport, caution,
commission plateforme.

**Aucun taux légal n'est codé en dur.** TVA, frais de service, commission et
politique d'annulation sont des paramètres modifiables dans la console
d'administration.

---

## 6. Paiements

Interface `PaymentProvider` unique, sans logique spécifique à un fournisseur.

| Moyen | Type | État sans identifiants |
|---|---|---|
| Espèces à la prise en charge | hors ligne | **opérationnel** |
| Virement / versement bancaire | hors ligne | **opérationnel** |
| Carte CIB / Edahabia (SATIM) | en ligne | configuration requise |
| Stripe (cartes internationales) | en ligne | configuration requise |
| PayPal | en ligne | configuration requise |

Un fournisseur non configuré **refuse explicitement** la transaction : il ne
simule jamais un paiement réussi. Les webhooks sont vérifiés par signature et
idempotents (`UNIQUE(provider_code, event_id)`). Les paiements portent une clé
d'idempotence : un double envoi ne crée pas deux encaissements.

États : `pending`, `processing`, `paid`, `partially_paid`, `failed`,
`refunded`, `partially_refunded`, `cancelled`.

---

## 7. Notifications

L'in-app est toujours réel. E-mail, SMS et WhatsApp passent par une file
(`notification_outbox`) : sans fournisseur configuré, le message est marqué
`unconfigured` et visible dans la console. **Rien n'est jamais annoncé comme
envoyé sans l'avoir été.**

---

## 8. Interface

Design sur mesure (aucun framework CSS) : tokens, cartes, squelettes de
chargement, états vides, dialogues de confirmation, notifications.

* **Mobile natif** : navigation dédiée, cibles tactiles ≥ 44 px, tableaux
  transformés en cartes, points de rupture 1080 / 960 / 720 px
* **RTL réel** : propriétés logiques CSS (`margin-inline`, `inset-inline`…), la
  mise en page s'inverse réellement en arabe
* **Accessibilité** : HTML sémantique, lien d'évitement, labels, ARIA, focus
  visible, `prefers-reduced-motion`
* **SEO** : pages publiques rendues côté serveur, meta + Open Graph, JSON-LD
  (`Product`, `BreadcrumbList`, `CollectionPage`), `robots.txt`, `sitemap.xml`,
  URLs `/vehicules/<slug>` et `/location/<wilaya>`

---

## 9. Données algériennes

Les **58 wilayas** (avec noms arabes), un échantillon de communes, les agences
et les **9 aéroports** principaux (Alger ALG, Oran ORN, Constantine CZL,
Annaba AAE, Tlemcen, Sétif, Béjaïa, Ghardaïa, Ouargla) avec supplément
configurable. Ajouter une wilaya ou une agence se fait en base, sans toucher au
code. Téléphones : `05/06/07XXXXXXXX`, `+213…`, fixes `0[1-4]…`.

---

## 10. Tests

```bash
python manage.py test               # tout
python manage.py test booking       # une suite
```

Les tests démarrent un **vrai serveur HTTP** sur une base jetable et le
sollicitent par le réseau, avec cookies et CSRF. Aucun mock.

| Suite | Vérifications | Couverture |
|---|---|---|
| `test_auth` | 51 | Inscription, connexion, sessions, réinitialisation, suspension |
| `test_booking` | 85 | Chevauchements, concurrence, maintenance, expiration, transitions |
| `test_pricing` | 89 | Paliers, week-end, TVA, remises, promos, remboursements |
| `test_security` | 190 | IDOR, élévation de privilèges, CSRF, injection, XSS, documents, paiements |
| `test_ui` | 153 | Rendu, RTL, SEO, états vides, accessibilité, responsive |
| `test_performance` | 57 | Index, plans de requête, N+1, pagination, poids des réponses |
| `test_e2e` | 115 | Parcours client, loueur et administrateur complets |
| **Total** | **740** | |

---

## 11. Mise en production

```bash
python manage.py check              # diagnostic complet
```

À faire impérativement :

1. `APP_ENV=production`, `DEBUG=false`, `DEMO_MODE=false`
2. `AUTH_SECRET` défini (le serveur refuse de démarrer sans, en production)
3. `COOKIE_SECURE=true` derrière HTTPS, `APP_URL` en `https://`
4. `python manage.py purge-demo` si la base a été amorcée en démo
5. `python manage.py createadmin` pour un administrateur réel
6. Placer un reverse proxy (nginx / Caddy) devant : TLS, compression, cache statique
7. Programmer `release-holds`, `flush-outbox`, `purge-documents`
8. Sauvegarder `storage/` (base **et** documents)
9. `python manage.py test` doit passer intégralement

Les données de démonstration sont marquées `is_demo = 1` : `seed` est refusé en
production et `purge-demo` les élimine sans toucher aux données réelles.

---

## 12. État de la V1

**Livré et testé** — authentification et rôles, recherche et filtres,
disponibilité temps réel, fiche véhicule, tarification, réservation en 6 étapes,
espace client, portail loueur (flotte, photos, calendrier, réservations,
revenus), console d'administration (validation loueurs et véhicules,
utilisateurs, documents, paiements, remboursements, avis, promos, audit,
paramètres), documents privés, notifications, avis, support, contrat de location
imprimable, données de démonstration, 740 vérifications automatisées.

**Architecture prête, activation à venir (V2)** — inspections
départ/retour et gestion des dommages (tables et statuts en place),
PDF serveur, SMS/WhatsApp, paiement en ligne (dès réception des identifiants
marchands), PWA, fidélité et parrainage.

Rien n'est simulé : aucun bouton inerte, aucun paiement fictif, aucun envoi
annoncé sans fournisseur.
