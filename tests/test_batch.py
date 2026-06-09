"""Tests du BatchRunner unifié — SANS GPU.

On pilote le runner avec des jobs factices (dicts) et des étapes pures Python.
Aucun import lourd (torch, router…) : on vérifie la mécanique d'orchestration.

Couvre :
  * séquentialité (ordre d'exécution déterministe, étapes chaînées) ;
  * tolérance aux pannes (un stage qui lève → job failed, on continue) ;
  * skip_existing (job sauté, ni done ni failed) ;
  * only / limit (filtrage des jobs) ;
  * hooks on_done / on_fail ;
  * contact_sheet produit bien un JPG.
"""
from __future__ import annotations

import pytest

from studio.batch import BatchRunner, BatchReport, contact_sheet


# --------------------------------------------------------------------------- #
# Jobs factices                                                                #
# --------------------------------------------------------------------------- #
def _jobs(n: int) -> list[dict]:
    return [{"name": f"job{i}", "value": i} for i in range(n)]


# --------------------------------------------------------------------------- #
# Pipeline & séquentialité                                                     #
# --------------------------------------------------------------------------- #
def test_pipeline_chaine_les_etapes():
    """La sortie d'une étape devient l'entrée de la suivante (prev->result)."""
    def gen(prev, job, i):
        assert prev is None  # 1re étape : pas de précédent
        return job["value"]

    def double(prev, job, i):
        return prev * 2

    def plus_index(prev, job, i):
        return prev + i  # index 1-based

    runner = BatchRunner(stages=[gen, double, plus_index], verbose=False)
    report = runner.run(_jobs(3))

    assert report.done == 3
    assert report.failed == []
    # value*2 + index(1-based) : 0*2+1, 1*2+2, 2*2+3
    assert report.results == [1, 4, 7]


def test_sequentialite_ordre_et_index():
    """Les jobs sont traités dans l'ordre, 1-based, séquentiellement."""
    ordre = []

    def stage(prev, job, i):
        ordre.append((i, job["name"]))
        return i

    runner = BatchRunner(stages=[stage], verbose=False)
    runner.run(_jobs(4))

    assert ordre == [(1, "job0"), (2, "job1"), (3, "job2"), (4, "job3")]


def test_report_accessible_comme_dict():
    """Le rapport expose l'API cible report['done'/'failed'/'elapsed']."""
    runner = BatchRunner(stages=[lambda p, j, i: 1], verbose=False)
    report = runner.run(_jobs(2))

    assert isinstance(report, BatchReport)
    assert report["done"] == 2
    assert report["failed"] == []
    assert report["elapsed"] >= 0.0
    assert report.get("total") == 2


# --------------------------------------------------------------------------- #
# Tolérance aux pannes                                                         #
# --------------------------------------------------------------------------- #
def test_tolerance_aux_pannes():
    """Un stage qui lève marque le job failed sans interrompre le lot."""
    def gen(prev, job, i):
        if job["name"] == "job1":
            raise RuntimeError("boom GPU")
        return job["name"]

    runner = BatchRunner(stages=[gen], verbose=False)
    report = runner.run(_jobs(3))

    assert report.done == 2
    assert len(report.failed) == 1
    jid, err = report.failed[0]
    assert jid == "job1"
    assert "boom GPU" in err
    # Les jobs sains ont quand même produit leur résultat.
    assert report.results == ["job0", "job2"]


def test_echec_dans_etape_intermediaire():
    """Une panne en milieu de pipeline n'écrit pas de résultat pour ce job."""
    def gen(prev, job, i):
        return job["value"]

    def post(prev, job, i):
        if prev == 1:
            raise ValueError("post échoue")
        return prev

    runner = BatchRunner(stages=[gen, post], verbose=False)
    report = runner.run(_jobs(3))

    assert report.done == 2
    assert [jid for jid, _ in report.failed] == ["job1"]


# --------------------------------------------------------------------------- #
# skip_existing                                                                #
# --------------------------------------------------------------------------- #
def test_skip_existing():
    """skip_existing saute le job : ni done, ni failed, stages non appelés."""
    appeles = []

    def stage(prev, job, i):
        appeles.append(job["name"])
        return 1

    runner = BatchRunner(
        stages=[stage],
        skip_existing=lambda job: job["name"] == "job1",
        verbose=False,
    )
    report = runner.run(_jobs(3))

    assert report.done == 2
    assert report.failed == []
    assert "job1" not in appeles  # le stage n'a pas tourné pour le job sauté


# --------------------------------------------------------------------------- #
# only / limit                                                                 #
# --------------------------------------------------------------------------- #
def test_only_filtre_par_sous_chaine():
    vus = []
    runner = BatchRunner(stages=[lambda p, j, i: vus.append(j["name"])], verbose=False)
    runner.run(_jobs(12), only="job1")  # job1, job10, job11

    assert sorted(vus) == ["job1", "job10", "job11"]


def test_limit_tronque_la_liste():
    runner = BatchRunner(stages=[lambda p, j, i: 1], verbose=False)
    report = runner.run(_jobs(10), limit=3)
    assert report.total == 3
    assert report.done == 3


def test_only_puis_limit():
    """only s'applique avant limit."""
    vus = []
    runner = BatchRunner(stages=[lambda p, j, i: vus.append(j["name"])], verbose=False)
    runner.run(_jobs(30), only="job2", limit=2)  # candidats: job2,job20..29 -> 2 premiers
    assert vus == ["job2", "job20"]


# --------------------------------------------------------------------------- #
# Hooks                                                                        #
# --------------------------------------------------------------------------- #
def test_hooks_on_done_on_fail():
    done_calls, fail_calls = [], []

    def gen(prev, job, i):
        if job["name"] == "job0":
            raise RuntimeError("nope")
        return job["name"]

    runner = BatchRunner(
        stages=[gen],
        on_done=lambda job, res: done_calls.append((job["name"], res)),
        on_fail=lambda job, exc: fail_calls.append((job["name"], str(exc))),
        verbose=False,
    )
    runner.run(_jobs(2))

    assert done_calls == [("job1", "job1")]
    assert fail_calls == [("job0", "nope")]


def test_on_fail_defaillant_ne_casse_pas_le_run():
    """Un hook on_fail qui lève ne doit pas interrompre le lot."""
    def gen(prev, job, i):
        raise RuntimeError("x")

    def mauvais_hook(job, exc):
        raise ValueError("hook cassé")

    runner = BatchRunner(stages=[gen], on_fail=mauvais_hook, verbose=False)
    report = runner.run(_jobs(2))
    assert len(report.failed) == 2  # run terminé malgré le hook défaillant


# --------------------------------------------------------------------------- #
# Validation API                                                              #
# --------------------------------------------------------------------------- #
def test_stages_vide_leve():
    with pytest.raises(ValueError):
        BatchRunner(stages=[])


def test_job_id_par_defaut_sur_out_path():
    """Sans clé name/id, l'identifiant retombe sur out_path."""
    vus = []
    runner = BatchRunner(stages=[lambda p, j, i: 1],
                         on_done=lambda j, r: vus.append(None), verbose=False)
    report = runner.run([{"out_path": "a/b.png"}], only="b.png")
    assert report.done == 1


# --------------------------------------------------------------------------- #
# contact_sheet                                                                #
# --------------------------------------------------------------------------- #
def test_contact_sheet_produit_un_jpg(tmp_path):
    from PIL import Image

    # 3 PNG RGBA (avec transparence partielle) à miniaturiser.
    srcs = []
    for i in range(3):
        p = tmp_path / f"img{i}.png"
        im = Image.new("RGBA", (300, 200), (255 * (i % 2), 100, 50, 180))
        im.save(p)
        srcs.append(p)

    out = tmp_path / "sheet.jpg"
    result = contact_sheet(srcs, out, cols=2, thumb=64, checker=True)

    assert result == out
    assert out.exists()
    # Vérifie que c'est bien un JPEG lisible avec une grille de 2 colonnes.
    with Image.open(out) as sheet:
        assert sheet.format == "JPEG"
        assert sheet.width > 64  # au moins 2 colonnes de vignettes


def test_contact_sheet_sans_checker(tmp_path):
    from PIL import Image

    p = tmp_path / "a.png"
    Image.new("RGBA", (100, 100), (0, 0, 0, 255)).save(p)
    out = tmp_path / "s.jpg"
    contact_sheet([p], out, checker=False)
    assert out.exists()


def test_contact_sheet_ignore_images_illisibles(tmp_path):
    from PIL import Image

    bon = tmp_path / "ok.png"
    Image.new("RGBA", (50, 50), (10, 20, 30, 255)).save(bon)
    casse = tmp_path / "broken.png"
    casse.write_text("pas une image")

    out = tmp_path / "s.jpg"
    contact_sheet([bon, casse], out)  # ne doit pas lever
    assert out.exists()


def test_contact_sheet_aucune_image_valide_leve(tmp_path):
    casse = tmp_path / "broken.png"
    casse.write_text("nope")
    with pytest.raises(ValueError):
        contact_sheet([casse], tmp_path / "s.jpg")
