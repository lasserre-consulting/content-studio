# 🎬 Content Studio

Studio unifié de génération IA — **image, vidéo, musique, SFX, voix, texte** — derrière une seule API, avec **bascule local ↔ cloud automatique**.

Conçu pour tourner sur une machine modeste (RTX 2080 SUPER, 8 Go VRAM) avec fallback cloud pour ce qui ne tient pas en local (vidéo HD).

**Deux niveaux :**
- 🔧 le **moteur** (`core` + `providers`) — génère un fichier pour une modalité.
- 🎛️ les **studios** (`studios`) — orchestrent plusieurs générations + montage en un livrable fini, pensés pour être pilotés en boucle (production autonome) :
  - **ContentStudio** → shorts verticaux montés (Insta / TikTok / YouTube).
  - **GamedevStudio** → batchs d'assets de jeu (sprites, BGM, SFX, voix) + ré-itération.

## Idée centrale : changer d'IA = changer une ligne

Tout le routage se pilote depuis **`config/providers.yaml`**. Pour chaque modalité, tu déclares le provider `active` et une chaîne de `fallback` :

```yaml
image:
  active: sdxl-local       # tourne sur ton GPU
  fallback: [fal-image]    # bascule cloud (Flux) si le local est indispo
llm:
  active: anthropic
  fallback: [ollama]       # LLM local si pas de clé API
```

- Le **routeur** essaie `active`, puis chaque `fallback`, en appelant `available()` sur chacun (clé API ? modèle présent ? assez de VRAM ?).
- Tu peux aussi forcer ponctuellement : `router.image("...", provider="fal-image")`.

## Ajouter un nouveau modèle (plug-in)

1. Crée une classe qui hérite de `BaseProvider` (ou `LLMProvider`), décorée `@register`.
2. Renseigne `name`, `modality`, `location`, et implémente `generate()` + `available()`.
3. Ajoute son chemin dans `studio/providers/__init__.py` et une entrée dans le YAML.

Le reste du code ne change pas — le routeur la découvre seule.

## Installation

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # cœur + providers cloud (léger)

# Providers locaux GPU (lourd) — installe torch CUDA d'abord :
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements-local.txt

copy .env.example .env                    # renseigne tes clés
```

> ⚠️ **ffmpeg requis** pour l'audio/vidéo : `winget install ffmpeg` (ou choco).

## Utilisation

```powershell
python -m studio.cli providers                 # liste les providers chargés
python -m studio.cli image "chat astronaute, style pixar"
python -m studio.cli tts "Bonjour, ceci est un test"
python -m studio.cli music "boss épique, orchestral sombre"
python -m studio.cli llm "améliore ce prompt: chat" --provider ollama
```

### Studios (pipelines complets)

```powershell
# Studio Contenu — un script → un MP4 vertical monté (voix + visuels + musique + sous-titres)
python -m studio.cli content short "Saviez-vous que les poulpes ont trois cœurs ?" --title poulpes
python -m studio.cli content short "@mon_script.txt" --title doc --no-music

# Studio Jeu — assets prêts pour Godot, dans le dossier du projet
python -m studio.cli game sprite "vieille sorcière, chapeau pointu" --name morra --variants 4
python -m studio.cli game bgm   "thème de combat épique, orgue sombre" --name boss
python -m studio.cli game sfx   "bruit de potion qui bout" --name potion
python -m studio.cli game voice "Bienvenue, aventurier." --name pnj_intro --out "C:\jeux\repaire\assets"
```

En Python (pilotage par un agent) :
```python
from studio import content_studio, game_studio

short = content_studio().short("Mon script...", title="essai")
print(short.video, short.notes)                 # MP4 monté + diagnostics

game = game_studio(r"C:\jeux\repaire\assets")    # écrit direct dans le projet
paths = game.sprite("goblin presseur", name="goblin", variants=6)  # 6 variantes à trier
```

API REST :
```powershell
uvicorn studio.api.app:app --reload
# → http://localhost:8000/docs
```

Python :
```python
from studio import get_router
r = get_router()
res = r.image("un dragon de glace")
print(res.path)                # chemin du PNG généré
print(r.llm("idée de SFX pour une potion"))
```

## Ce qui tient sur 8 Go de VRAM

| Modalité | Local (8 Go) | Cloud fallback |
|---|---|---|
| Image | ✅ SDXL | Flux via fal.ai |
| Voix / TTS | ✅ Kokoro (même sans GPU) | — |
| Musique | ✅ MusicGen | — |
| SFX | ✅ AudioGen | — |
| Vidéo | 🔴 trop lourd | ✅ Kling/Veo via fal.ai |
| Texte / LLM | ✅ Ollama | Anthropic / OpenAI |

## Architecture

```
studio/
├── core/          # le cœur agnostique
│   ├── types.py       GenRequest / GenResult / Modality
│   ├── provider.py    contrat BaseProvider / LLMProvider
│   ├── registry.py    @register + résolution par (modalité, nom)
│   └── router.py      sélection active→fallback, bascule local/cloud
├── providers/     # un fichier = un modèle branchable
│   ├── llm/  image/  video/  music/  sfx/  tts/
├── assembly/     # montage ffmpeg : image→vidéo, mux voix+musique, sous-titres
│   └── ffmpeg.py
├── studios/      # orchestration métier (pipelines pilotables par un agent)
│   ├── base.py        Studio : variations, best_of, repli gracieux
│   ├── content.py     ContentStudio : script → MP4 vertical monté
│   └── gamedev.py     GamedevStudio : batch d'assets de jeu + ré-itération
├── api/app.py     # FastAPI
├── cli.py         # ligne de commande
└── config.py      # charge providers.yaml + .env
```
