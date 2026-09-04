# Content Studio — Guide Claude Code

Studio unifié de génération IA — **image, musique, SFX, voix, vidéo, texte** — derrière
une seule API, avec bascule local ↔ cloud automatique.
Python 3.11 · Windows · RTX 2080 SUPER (8 Go VRAM) · 100 % local par défaut.

---

## ⚠️ À LIRE AVANT TOUT `pip install`

Cette stack fait cohabiter des paquets aux exigences **contradictoires** (audiocraft
épingle torch 2.1, SDXL veut du torch récent). L'équilibre actuel est le fruit de
plusieurs impasses résolues : il tient par des épingles, pas par chance.

| Fichier | Rôle |
|---|---|
| `requirements.txt` / `requirements-local.txt` | ce qu'on **veut** (intentions) |
| `constraints.txt` | ce qu'on ne peut **pas** bouger, avec la raison de chaque épingle |
| `requirements.lock.txt` | l'état complet **connu-bon** — le filet de retour |

**Trois règles :**
1. **Toujours** passer `-c constraints.txt` à pip. Sans ça, une dépendance transitive
   déplace torch et casse la moitié de la stack.
2. **Jamais** de `pip install -U` global. Montées de version paquet par paquet, avec
   `studio.doctor` + `pytest` après chacune.
3. Avant toute montée risquée, vérifier que le lock est à jour et commité.

**Rollback :** `pip install -r requirements.lock.txt` puis `python -m studio.doctor`.

### Épingles Windows — Smart App Control bloque des DLL non signées

Symptôme type : `ImportError: DLL load failed ... Une stratégie de contrôle
d'application a bloqué ce fichier.` Ce n'est **pas** un problème de compatibilité
Python, c'est l'OS qui refuse la DLL. La correction est toujours la même : redescendre
sur une version à réputation établie.

- `scikit-learn==1.5.2` — la DLL `_isfinite` de ≥1.9 est bloquée. `librosa` en dépend.
- `kiwisolver==1.4.5` — la DLL `_cext` de 1.5.x est bloquée. Chaîne de casse :
  `audiocraft → torchmetrics → matplotlib → kiwisolver`. matplotlib arrive via
  `k-diffusion` (dépendance de Stable Audio).
- `xformers==0.0.29.post3` — seule ABI compatible torch 2.6 ; requise à l'import
  par audiocraft.
- `torch/torchaudio 2.6.0+cu124`, `torchvision==0.21.0+cu124` (doit suivre torch).

---

## Commandes

```powershell
.\.venv\Scripts\Activate.ps1

python -m studio.doctor        # preflight : 12 vérifications. DOIT être vert.
python -m pytest -q            # 155 tests, ~16 s, aucun modèle lourd chargé

python -m studio.cli providers
python -m studio.cli image "chat astronaute, style pixar"
python -m studio.cli game bgm "thème de combat, orgue sombre" --name boss
python scripts/validate_stable_audio.py   # validation en génération RÉELLE
```

`studio.doctor` + `pytest` verts = condition d'acceptation de tout changement
d'environnement. Les tests ne chargent aucun modèle : ils ne prouvent donc **pas**
que la génération marche. Pour ça, il faut générer pour de vrai.

---

## Architecture

```
studio/
├── core/          types.py (GenRequest/GenResult), provider.py (contrat),
│                  registry.py (@register), router.py (active → fallback)
├── providers/     un fichier = un modèle branchable, par modalité
├── assembly/      montage ffmpeg, détourage rembg, chemins ASCII-safe
├── studios/       ContentStudio (shorts montés) · GamedevStudio (assets de jeu)
├── exporters/     godot.py · unity.py · memoria.py (+ EngineProfile = garde-fou)
├── procedural/    primitives déterministes PIL/numpy (zéro modèle)
├── doctor.py      preflight · judge.py  CLIP local · verify.py  linter d'assets
└── cli.py · api/app.py · config.py
```

### Ajouter un modèle
1. Classe héritant de `BaseProvider` (ou `LLMProvider`), décorée `@register`.
2. Définir `name`, `modality`, `location`, `min_vram_gb` ; implémenter
   `generate()` et `available()`.
3. Ajouter le module à `studio/providers/__init__.py` et une entrée dans
   `config/providers.yaml`.

Rien d'autre ne bouge : le routeur découvre la classe seul.

### Règle capitale du routeur
Le routeur bascule sur le `fallback` **uniquement** si `available()` renvoie `False`.
Si `generate()` lève, l'erreur **remonte** — on ne masque pas un bug derrière un repli.
Conséquence : ne jamais passer un provider en `active` sans l'avoir validé en
génération réelle.

`available()` doit rester **rapide et sans effet de bord** : elle est appelée avant
chaque tentative. Ne jamais y charger un modèle.

---

## Modalités et modèles actifs

| Modalité | Provider actif | Notes |
|---|---|---|
| Image | `sdxl-local` | ~20 s / image 1024², DPM++ Karras 20 steps |
| Musique | `stableaudio-music` | 44,1 kHz stéréo, **120 s max**, 30 s en ~15 s |
| SFX | `stableaudio-sfx` | 44,1 kHz stéréo, tourne aussi sur CPU |
| Voix | `kokoro-local` | français = `ff_siwis` (**pas** `af_heart`, anglaise) |
| Vidéo | `fal-video` | cloud : trop lourd sur 8 Go |
| LLM | `anthropic` | fallback `ollama` |

### Pièges Stable Audio 3
- Modèles **gated** sur HuggingFace : accepter la licence sur **chaque** page
  + `HF_TOKEN` dans `.env`.
- **La version PyPI (0.0.19) est antérieure à SA3** et échoue sur
  `local_add_cond_dim`. Installer depuis git, avec `--no-deps` (l'extra `pypesq` ne
  compile pas) et `--ignore-requires-python` (le pyproject exige <3.11 ; 3.11.9
  fonctionne). Recette complète dans `requirements-local.txt`.
- **Graine explicite obligatoire** : la lib tire `np.random.randint(0, 2**32-1)`
  sans `dtype` → « high is out of bounds for int32 » sous Windows. Le provider passe
  la graine lui-même. Ne **pas** patcher `site-packages`.
- Le modèle rend `seconds_total` **+ ~6 s** ; le provider coupe à la durée demandée.
- `max_duration` musique = 120 s = `sample_size` mesuré. Les 6:20 annoncés
  concernent la variante **medium**, pas la small.

---

## Exporters

`EngineProfile` décrit ce qu'une cible accepte **réellement** — garde-fou né d'un cas
vécu : des spritesheets 2D générées pour des personnages qui étaient des modèles 3D.

- **GodotExporter** — sprites PNG, audio ogg/wav, arbo `assets/`.
- **UnityExporter** — arbo `Assets/`. Deux partis pris propres à Unity :
  - **pas** de conversion WAV → OGG (le WAV est la source, la compression est un
    réglage d'import appliqué au build) ;
  - réglages via un **AssetPostprocessor C#** déposé dans `Assets/Editor/`, pas via
    des `.meta` écrits à la main (format versionné, un champ manquant = import faux
    en silence). Les constantes de chemin du C# doivent rester alignées sur celles de
    l'exporter — un test le vérifie.
- **MemoriaExporter** — mods FF9.

La racine du projet cible est **toujours** un paramètre. Jamais de chemin Steam ou de
projet codé en dur.

---

## Conventions

- Commentaires et docstrings **en français**. On explique le *pourquoi*, pas le *quoi*.
- Imports lourds (torch, diffusers, stable_audio_tools) **paresseux**, jamais au
  niveau module : `studio/providers/__init__.py` doit rester importable sans GPU.
- Les tests ne chargent aucun modèle. La validation réelle vit dans `scripts/`.
- Chemins ASCII-safe (`studio/assembly/paths.py`) : espaces et accents cassent ffmpeg
  sous Windows.
- Ne pas dupliquer les helpers de `studio/procedural/shapes.py`.
- `.env` n'est jamais commité (clés API, `HF_TOKEN`).
