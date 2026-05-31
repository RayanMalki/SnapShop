# Snap & Shop

Photo d'un produit → **Gemini Vision** l'identifie → **Shopify UCP** trouve le produit chez un marchand → lien panier (`continue_url`).

> Pas de compilation. Backend = Python (FastAPI). Frontend = HTML/JS statique.

## Structure

```
├── backend/     # FastAPI : POST /scan, GET /health, GET /cart/current
├── web/         # UI de test webcam (Phase 1)
└── ios/         # App SwiftUI Login + Cart (Phase 2+, voir ios/README.md)
```

Plan complet : [HACKATHON_PLAN.md](./HACKATHON_PLAN.md)

---

## Prérequis

- **Python 3.10+** (testé sur 3.11)
- Une **clé Gemini** : https://aistudio.google.com/apikey

---

## Démarrage (1re fois)

### 1. Cloner + venv + dépendances

```bash
git clone <url-du-repo> SnapShop
cd SnapShop/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurer la clé Gemini

Le `.env` se met **à la racine du repo** (pas dans `backend/`).

```bash
cd ..                  # revenir à la racine
cp .env.example .env
```

Ouvre `.env` et colle ta clé : `GEMINI_API_KEY=AIza...`
**Laisse `UCP_AGENT_PROFILE_URL=` vide** (sinon la recherche UCP casse).

---

## Lancer l'app (à chaque fois)

Ouvre **2 terminaux**.

### Terminal 1 — Backend (port 8000)

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Les logs (vision, UCP, erreurs) s'affichent ici en direct.

### Terminal 2 — Frontend (port 8080)

```bash
cd web
python3 -m http.server 8080
```

Puis ouvre **http://localhost:8080** → *Start camera* → *Capture & scan*.

---

## Vérifier que ça marche

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/scan -F "file=@une_photo.jpg"
# JSON avec vision + product + continue_url
```

<<<<<<< HEAD
`/scan` requires a valid `GEMINI_API_KEY` to analyze the image.
=======
---
>>>>>>> 53af6870e18062e0fc1650e5a5a7b11baa7d0649

## Pipeline d'un scan

1. **Gemini** analyse la photo → attributs + `query_precise` / `query_broad`
2. **UCP** `search_catalog(query)` → jusqu'à 8 produits candidats
3. **Gemini (re-ranking visuel)** compare la photo aux images candidates → choisit le meilleur
   (fallback : ranking par mots-clés si l'appel échoue)
4. **UCP** `create_cart` → `continue_url` (lien panier marchand)

> ⚠️ 2 appels Gemini par scan → attention au quota du free tier.

---

## Pièges fréquents

| Symptôme | Cause / fix |
|---|---|
| Toujours le même t-shirt bleu mock | `GEMINI_API_KEY` vide ou quota dépassé (voir logs Terminal 1) |
| `No product found from UCP search` | `UCP_AGENT_PROFILE_URL` non vide dans `.env` → **vide-le** |
| Modif du `.env` sans effet | Le `.env` n'est lu **qu'au démarrage** → redémarre le Terminal 1 (`--reload` ne recharge que les `.py`) |
| `429 RESOURCE_EXHAUSTED` | Quota Gemini journalier atteint → attendre, ou changer de clé |

---

## iOS (Phase 2)

Voir `ios/README.md`. Mettre `APIConfig.baseURL = http://<IP-du-Mac-serveur>:8000`
(`ipconfig getifaddr en0` pour trouver l'IP). Le Mac qui fait tourner le backend et l'iPhone doivent être sur le **même Wi-Fi**.
