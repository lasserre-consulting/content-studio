"""BatchRunner unifié — factorise le pattern de génération par lots du studio.

Les six scripts ``scripts/generate_*`` partagent tous la même mécanique :

    lire un manifeste (liste de jobs)
      -> pour chaque job, enchaîner N étapes :
           générer via le router GPU
           -> post-traiter (détourage / conversion / tuilage)
           -> écrire au chemin de sortie
      -> SÉQUENTIEL (un seul GPU, pas de parallélisme)
      -> TOLÉRANT AUX PANNES (un job en échec est journalisé, on continue)
      -> options de filtrage (--only / --limit / --skip-existing)
      -> résumé final (n/total, durée, échecs)
      -> souvent une planche-contact pour la QA visuelle.

Ce module extrait cette abstraction sans dépendre du router ni des autres
modules récents : il est PUR Python + PIL (uniquement pour ``contact_sheet``).
L'intégration concrète (brancher ``router.generate`` dans une étape) se fait
côté appelant, qui passe ses propres fonctions d'étape au runner.

Concepts :
  * ``Job``    : un sac de données décrivant UNE unité de travail.
  * ``stage``  : un appelable ``stage(prev_result, job, index) -> result``.
                 La sortie d'une étape devient l'entrée de la suivante (pipeline).
  * ``BatchRunner`` : enchaîne les étapes sur chaque job, séquentiellement,
                 en isolant les pannes.

Exemple :
    from studio.batch import BatchRunner, Job

    def gen(prev, job, i):       # 1re étape : reçoit prev=None
        return router.generate(...).path
    def write(src, job, i):      # étape suivante : reçoit le résultat précédent
        shutil.copyfile(src, job["out_path"]); return job["out_path"]

    runner = BatchRunner(
        stages=[gen, write],
        skip_existing=lambda job: Path(job["out_path"]).exists(),
    )
    report = runner.run(jobs, only="ozma", limit=5)
    # -> {"done": 5, "failed": [(id, err), ...], "elapsed": 42.0, "total": 5}
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

# --------------------------------------------------------------------------- #
# Type d'un job et alias de callbacks                                          #
# --------------------------------------------------------------------------- #
# Un Job est volontairement souple : la plupart des scripts manipulent des
# dicts issus d'un manifeste JSON. On accepte donc n'importe quel objet ; le
# runner n'a besoin que de savoir l'IDENTIFIER (pour les logs/échecs) et de le
# passer tel quel aux étapes.
Job = Any

# Une étape : (résultat_précédent, job, index) -> nouveau_résultat.
# La 1re étape reçoit prev=None. index est 1-based (cohérent avec les scripts).
Stage = Callable[[Any, Job, int], Any]

# Callbacks de filtrage / hooks.
SkipExisting = Callable[[Job], bool]
JobId = Callable[[Job], str]
OnDone = Callable[[Job, Any], None]
OnFail = Callable[[Job, BaseException], None]


def force_utf8() -> None:
    """Force stdout/stderr en UTF-8 (console Windows souvent en cp1252).

    Réutilise le pattern ``_force_utf8`` présent dans tous les scripts : sans
    ça, les libellés accentués et les symboles (✓/✗/→) plantent à l'affichage.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _default_job_id(job: Job) -> str:
    """Identifiant d'un job pour les logs et la liste d'échecs.

    On essaie, dans l'ordre, les clés usuelles des manifestes
    (``name`` / ``id`` / ``out_path``), sinon on retombe sur ``str(job)``.
    """
    if isinstance(job, dict):
        for key in ("name", "id", "out_path"):
            value = job.get(key)
            if value:
                return str(value)
    return str(job)


@dataclass
class BatchReport:
    """Résumé d'un run. Se comporte AUSSI comme un dict (rétrocompat API cible).

    L'énoncé attend ``report["done"]`` / ``report["failed"]`` / ``report["elapsed"]``.
    On expose donc à la fois des attributs (ergonomie) et un accès par clé.
    """

    done: int = 0
    total: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    elapsed: float = 0.0
    results: list[Any] = field(default_factory=list)  # résultats finals des jobs OK

    # -- accès façon dict ---------------------------------------------------- #
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def as_dict(self) -> dict[str, Any]:
        return {
            "done": self.done,
            "total": self.total,
            "failed": self.failed,
            "elapsed": self.elapsed,
        }


class BatchRunner:
    """Exécute une liste de jobs à travers un pipeline d'étapes, séquentiellement.

    Args:
        stages: étapes du pipeline. Chaque étape ``stage(prev, job, index)``
            reçoit le résultat de l'étape précédente (None pour la première) et
            renvoie le résultat passé à la suivante. La sortie de la dernière
            étape est conservée dans ``report.results``.
        skip_existing: callback optionnel ``job -> bool``. Si elle renvoie True,
            le job est ignoré (compté ni en done ni en failed).
        job_id: callback optionnel ``job -> str`` pour nommer le job (logs/échecs).
            Par défaut : clé ``name``/``id``/``out_path`` du dict, sinon str(job).
        on_done: hook optionnel ``(job, result) -> None`` après un job réussi.
        on_fail: hook optionnel ``(job, exc) -> None`` après un job en échec.
        verbose: si True (défaut), journalise la progression sur stdout.
    """

    def __init__(
        self,
        stages: Sequence[Stage],
        *,
        skip_existing: Optional[SkipExisting] = None,
        job_id: Optional[JobId] = None,
        on_done: Optional[OnDone] = None,
        on_fail: Optional[OnFail] = None,
        verbose: bool = True,
    ) -> None:
        if not stages:
            raise ValueError("BatchRunner exige au moins une étape (stage).")
        self.stages = list(stages)
        self.skip_existing = skip_existing
        self.job_id = job_id or _default_job_id
        self.on_done = on_done
        self.on_fail = on_fail
        self.verbose = verbose

    # ------------------------------------------------------------------ #
    # Filtrage des jobs                                                   #
    # ------------------------------------------------------------------ #
    def _filter(
        self,
        jobs: Iterable[Job],
        only: Optional[str],
        limit: Optional[int],
    ) -> list[Job]:
        """Applique ``only`` (sous-chaîne sur l'identifiant) puis ``limit``.

        ``skip_existing`` n'est PAS appliqué ici : il l'est au moment du run,
        pour que sa logique (souvent un test de présence de fichier) reflète
        l'état réel à l'exécution.
        """
        selected = list(jobs)
        if only:
            selected = [j for j in selected if only in self.job_id(j)]
        if limit is not None:
            selected = selected[:limit]
        return selected

    # ------------------------------------------------------------------ #
    # Exécution                                                           #
    # ------------------------------------------------------------------ #
    def _run_job(self, job: Job, index: int, total: int) -> Any:
        """Fait passer un job par toutes les étapes. Lève si une étape échoue."""
        result: Any = None
        for stage in self.stages:
            result = stage(result, job, index)
        return result

    def run(
        self,
        jobs: Iterable[Job],
        *,
        only: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> BatchReport:
        """Exécute le lot et renvoie un :class:`BatchReport`.

        Séquentiel (un seul GPU) et tolérant aux pannes : une exception dans
        n'importe quelle étape marque le job comme échoué (journalisé dans
        ``report.failed``) et le run continue avec le job suivant.
        """
        selected = self._filter(jobs, only, limit)
        total = len(selected)
        report = BatchReport(total=total)
        t_start = time.time()

        if self.verbose:
            print(f"{total} jobs à traiter", flush=True)

        for i, job in enumerate(selected, 1):
            jid = self.job_id(job)

            # skip_existing : on saute sans compter (ni done ni failed).
            if self.skip_existing is not None and self.skip_existing(job):
                if self.verbose:
                    print(f"[{i}/{total}] ⏭ {jid} (déjà présent)", flush=True)
                continue

            t0 = time.time()
            try:
                result = self._run_job(job, i, total)
                report.done += 1
                report.results.append(result)
                if self.on_done is not None:
                    self.on_done(job, result)
                if self.verbose:
                    print(f"[{i}/{total}] ✓ {jid}  ({time.time()-t0:.0f}s)", flush=True)
            except Exception as exc:  # on continue malgré un échec isolé
                report.failed.append((jid, str(exc)))
                if self.on_fail is not None:
                    # Le hook ne doit pas casser le run : on l'isole.
                    try:
                        self.on_fail(job, exc)
                    except Exception:  # noqa: BLE001 — best effort sur le hook
                        pass
                if self.verbose:
                    print(f"[{i}/{total}] ✗ {jid} — {exc}", flush=True)

        report.elapsed = time.time() - t_start

        if self.verbose:
            print(
                f"\nTerminé : {report.done}/{total} en {report.elapsed/60:.1f} min."
                f" Échecs : {len(report.failed)}",
                flush=True,
            )
            for jid, err in report.failed:
                print(f"  ✗ {jid} : {err}", flush=True)

        return report


# --------------------------------------------------------------------------- #
# Planche-contact (QA visuelle)                                                #
# --------------------------------------------------------------------------- #
def _checker_tile(size: int, cell: int = 16) -> "Any":
    """Vignette de fond damier (rend la transparence visible). Renvoie une Image."""
    from PIL import Image

    bg = Image.new("RGB", (size, size), (40, 40, 48))
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if (x // cell + y // cell) % 2:
                bg.paste((70, 70, 82), (x, y, x + cell, y + cell))
    return bg


def contact_sheet(
    paths: Sequence[Any],
    out: Any,
    *,
    cols: int = 5,
    thumb: int = 256,
    checker: bool = True,
    pad: int = 8,
    quality: int = 88,
) -> Any:
    """Compose une planche-contact JPG à partir d'une liste d'images.

    Reprend la logique des planches-contact des scripts (``_contact_sheets``) :
    chaque image est miniaturisée et centrée dans une cellule, sur un fond
    damier (par défaut) pour rendre visible la transparence des PNG détourés.

    Args:
        paths: chemins des images sources (PNG/JPG…). Les images en échec
            d'ouverture sont ignorées (tolérance aux pannes, comme le reste).
        out: chemin de sortie du JPG.
        cols: nombre de colonnes de la grille.
        thumb: taille (px) du côté d'une vignette carrée.
        checker: si True, fond damier ; sinon fond uni sombre.
        pad: marge (px) entre/around les cellules.
        quality: qualité JPEG.

    Returns:
        Le chemin ``out`` (Path) effectivement écrit.

    Raises:
        ValueError: si aucune image valide n'a pu être chargée.
    """
    from pathlib import Path

    from PIL import Image

    out = Path(out)

    # Chargement tolérant : on ignore ce qui ne s'ouvre pas.
    images = []
    for p in paths:
        try:
            images.append(Image.open(p).convert("RGBA"))
        except Exception:  # noqa: BLE001 — image illisible : on saute
            continue
    if not images:
        raise ValueError("contact_sheet : aucune image valide à composer.")

    rows = (len(images) + cols - 1) // cols
    sheet = Image.new(
        "RGB",
        (cols * (thumb + pad) + pad, rows * (thumb + pad) + pad),
        (24, 24, 30),
    )

    for i, im in enumerate(images):
        im.thumbnail((thumb, thumb), Image.LANCZOS)
        cell = _checker_tile(thumb) if checker else Image.new("RGB", (thumb, thumb), (40, 40, 48))
        # Collage avec masque alpha pour préserver la transparence sur le damier.
        cell.paste(im, ((thumb - im.width) // 2, (thumb - im.height) // 2), im)
        r, c = divmod(i, cols)
        sheet.paste(cell, (pad + c * (thumb + pad), pad + r * (thumb + pad)))

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=quality)
    return out


__all__ = [
    "BatchRunner",
    "BatchReport",
    "Job",
    "Stage",
    "contact_sheet",
    "force_utf8",
]
