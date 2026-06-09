"""Tests du CŒUR du studio : registre, routeur, config.

Ces tests sont volontairement *légers* : aucun import lourd (torch, diffusers…),
aucun appel réseau. On définit un FakeProvider en dur pour piloter
available()/generate() à la demande, et on manipule directement le registre et
la Config (construite depuis un dict Python, sans toucher au YAML disque).
"""
from __future__ import annotations

import pytest

from studio.config import Config
from studio.core import (
    BaseProvider,
    GenRequest,
    GenResult,
    Location,
    Modality,
    NoProviderAvailable,
    Router,
    list_providers,
    register,
)
# get_provider_class n'est pas réexporté par studio.core : on le prend à la source.
from studio.core.registry import _REGISTRY, get_provider_class


# --------------------------------------------------------------------------- #
# Fixture : isolation du registre global                                       #
# --------------------------------------------------------------------------- #
@pytest.fixture
def clean_registry():
    """Sauvegarde puis restaure le registre global autour de chaque test.

    Le registre (_REGISTRY) est un singleton de module : les vrais providers du
    studio y sont déjà enregistrés au moment de l'import. Pour éviter toute
    collision de @register entre tests (ValueError "déjà enregistré"), on
    travaille sur une copie qu'on restaure ensuite.
    """
    snapshot = dict(_REGISTRY)
    try:
        yield _REGISTRY
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(snapshot)


# --------------------------------------------------------------------------- #
# Fabrique de FakeProvider                                                     #
# --------------------------------------------------------------------------- #
def make_fake(
    *,
    name: str = "fake",
    modality: Modality = Modality.IMAGE,
    location: Location = Location.LOCAL,
    available: bool = True,
    reason: str = "ok",
):
    """Construit une classe FakeProvider sur mesure.

    On génère une classe par appel pour pouvoir varier name/modality/available
    sans interférence, et pour pouvoir l'enregistrer distinctement dans le
    registre nettoyé par la fixture. Les méthodes sont définies dans le corps de
    classe (et non greffées après coup) pour que generate() lève bien le statut
    abstrait — sinon la classe resterait non instanciable.
    """

    class FakeProvider(BaseProvider):
        # Attributs de classe (le décorateur @register les lit).
        pass

    FakeProvider.name = name
    FakeProvider.modality = modality
    FakeProvider.location = location

    # available() configurable, rapide et sans effet de bord.
    def _available(self) -> tuple[bool, str]:
        return available, reason

    # generate() renvoie un GenResult bidon mais valide.
    def _generate(self, req: GenRequest) -> GenResult:
        return GenResult(
            modality=modality,
            provider=name,
            location=location,
            meta={"prompt": req.prompt, "marker": name},
        )

    FakeProvider.available = _available
    FakeProvider.generate = _generate
    # On greffe generate() après coup : il faut donc effacer le statut abstrait
    # hérité de BaseProvider, sinon la classe reste non instanciable.
    FakeProvider.__abstractmethods__ = frozenset()
    # __name__ lisible dans les messages d'erreur du registre.
    FakeProvider.__name__ = f"FakeProvider_{name}"
    return FakeProvider


def make_config(modality: Modality, *, active=None, fallback=None, providers=None) -> Config:
    """Construit une Config depuis un dict Python, sans lire le YAML disque."""
    section: dict = {}
    if active is not None:
        section["active"] = active
    if fallback is not None:
        section["fallback"] = list(fallback)
    if providers is not None:
        section["providers"] = providers
    return Config({modality.value: section})


# --------------------------------------------------------------------------- #
# (1) @register + get_provider_class + list_providers                          #
# --------------------------------------------------------------------------- #
def test_register_and_lookup(clean_registry):
    cls = make_fake(name="fake", modality=Modality.IMAGE)
    returned = register(cls)

    # @register renvoie la classe inchangée (utilisable en décorateur).
    assert returned is cls

    # get_provider_class la retrouve par (modalité, nom).
    assert get_provider_class(Modality.IMAGE, "fake") is cls

    # list_providers la liste (format "modality:name").
    assert "image:fake" in list_providers()
    assert "image:fake" in list_providers(Modality.IMAGE)


def test_register_rejects_missing_name(clean_registry):
    cls = make_fake(name="base")  # 'base' = sentinelle interdite
    with pytest.raises(ValueError):
        register(cls)


def test_register_rejects_duplicate(clean_registry):
    register(make_fake(name="dup", modality=Modality.IMAGE))
    with pytest.raises(ValueError):
        register(make_fake(name="dup", modality=Modality.IMAGE))


def test_get_provider_class_unknown_raises(clean_registry):
    with pytest.raises(KeyError):
        get_provider_class(Modality.IMAGE, "nexistepas")


# --------------------------------------------------------------------------- #
# (2) Router : ordre active -> fallback, saute les indisponibles               #
# --------------------------------------------------------------------------- #
def test_router_skips_unavailable_uses_fallback(clean_registry):
    # 'primary' indisponible -> doit basculer sur 'secondary'.
    register(make_fake(name="primary", modality=Modality.IMAGE, available=False,
                       reason="pas de clé API"))
    register(make_fake(name="secondary", modality=Modality.IMAGE, available=True))

    cfg = make_config(Modality.IMAGE, active="primary", fallback=["secondary"])
    router = Router(cfg)

    res = router.generate(Modality.IMAGE, "un chocobo")
    assert res.provider == "secondary"
    assert res.meta["marker"] == "secondary"
    assert res.meta["prompt"] == "un chocobo"


def test_router_prefers_active_when_available(clean_registry):
    register(make_fake(name="primary", modality=Modality.IMAGE, available=True))
    register(make_fake(name="secondary", modality=Modality.IMAGE, available=True))

    cfg = make_config(Modality.IMAGE, active="primary", fallback=["secondary"])
    router = Router(cfg)

    # active dispo -> on ne touche pas au fallback.
    assert router.generate(Modality.IMAGE, "test").provider == "primary"


def test_router_caches_instance(clean_registry):
    register(make_fake(name="cached", modality=Modality.IMAGE, available=True))
    cfg = make_config(Modality.IMAGE, active="cached")
    router = Router(cfg)

    inst1 = router._instance(Modality.IMAGE, "cached")
    inst2 = router._instance(Modality.IMAGE, "cached")
    # Le routeur réutilise la même instance (un modèle local n'est chargé qu'une fois).
    assert inst1 is inst2


# --------------------------------------------------------------------------- #
# (3) Aucun provider dispo -> NoProviderAvailable                              #
# --------------------------------------------------------------------------- #
def test_router_raises_when_none_available(clean_registry):
    register(make_fake(name="a", modality=Modality.IMAGE, available=False, reason="indispo a"))
    register(make_fake(name="b", modality=Modality.IMAGE, available=False, reason="indispo b"))

    cfg = make_config(Modality.IMAGE, active="a", fallback=["b"])
    router = Router(cfg)

    with pytest.raises(NoProviderAvailable):
        router.generate(Modality.IMAGE, "rien ne marche")


def test_router_raises_when_nothing_configured(clean_registry):
    cfg = make_config(Modality.IMAGE)  # chaîne vide
    router = Router(cfg)
    with pytest.raises(NoProviderAvailable):
        router.generate(Modality.IMAGE, "vide")


# --------------------------------------------------------------------------- #
# (3 bis) Robustesse : un provider qui CASSE ne doit pas tuer le fallback       #
# --------------------------------------------------------------------------- #
def _register_broken(kind: str, name: str):
    """Enregistre un provider qui lève soit dans __init__, soit dans available()."""
    class Broken(BaseProvider):
        pass

    Broken.name = name
    Broken.modality = Modality.IMAGE
    Broken.location = Location.LOCAL

    if kind == "init":
        def _init(self, **config):
            raise RuntimeError("boom à l'instanciation (ex: ImportError de torch)")
        Broken.__init__ = _init
    elif kind == "available":
        def _available(self):
            raise RuntimeError("boom dans available()")
        Broken.available = _available

    Broken.generate = lambda self, req: GenResult(
        modality=Modality.IMAGE, provider=name, location=Location.LOCAL)
    Broken.__abstractmethods__ = frozenset()
    Broken.__name__ = f"Broken_{name}"
    register(Broken)


def test_router_survives_provider_init_raising(clean_registry):
    # active explose à l'__init__ -> on bascule sur le fallback sain.
    _register_broken("init", "explosif")
    register(make_fake(name="sain", modality=Modality.IMAGE, available=True))
    router = Router(make_config(Modality.IMAGE, active="explosif", fallback=["sain"]))
    assert router.generate(Modality.IMAGE, "x").provider == "sain"


def test_router_survives_available_raising(clean_registry):
    # available() qui lève est traité comme une indisponibilité -> fallback.
    _register_broken("available", "capricieux")
    register(make_fake(name="sain2", modality=Modality.IMAGE, available=True))
    router = Router(make_config(Modality.IMAGE, active="capricieux", fallback=["sain2"]))
    assert router.generate(Modality.IMAGE, "x").provider == "sain2"


# --------------------------------------------------------------------------- #
# Config : tolérance aux valeurs null du YAML                                   #
# --------------------------------------------------------------------------- #
def test_config_tolerates_null_fallback_and_providers():
    # YAML avec 'fallback:' et 'providers:' laissés vides => null en Python.
    cfg = Config({"image": {"active": "a", "fallback": None, "providers": None}})
    assert cfg.chain(Modality.IMAGE) == ["a"]
    assert cfg.provider_settings(Modality.IMAGE, "a") == {}


def test_config_tolerates_null_provider_block():
    # Un bloc provider présent mais vide (null) ne doit pas planter.
    cfg = Config({"image": {"active": "a", "providers": {"a": None}}})
    assert cfg.provider_settings(Modality.IMAGE, "a") == {}


# --------------------------------------------------------------------------- #
# (4) Provider explicite court-circuite la config                             #
# --------------------------------------------------------------------------- #
def test_explicit_provider_overrides_config(clean_registry):
    register(make_fake(name="cfg_active", modality=Modality.IMAGE, available=True))
    register(make_fake(name="forced", modality=Modality.IMAGE, available=True))

    # La config pointe sur 'cfg_active', mais on force 'forced' à l'appel.
    cfg = make_config(Modality.IMAGE, active="cfg_active", fallback=["cfg_active"])
    router = Router(cfg)

    res = router.generate(Modality.IMAGE, "force", provider="forced")
    assert res.provider == "forced"


def test_explicit_provider_not_silently_fallenback(clean_registry):
    # Un provider explicite indisponible ne doit PAS retomber sur la config :
    # la liste de candidats est réduite à [provider], donc NoProviderAvailable.
    register(make_fake(name="forced_down", modality=Modality.IMAGE, available=False,
                       reason="forcé mais indispo"))
    register(make_fake(name="cfg_active", modality=Modality.IMAGE, available=True))

    cfg = make_config(Modality.IMAGE, active="cfg_active")
    router = Router(cfg)

    with pytest.raises(NoProviderAvailable):
        router.generate(Modality.IMAGE, "x", provider="forced_down")


# --------------------------------------------------------------------------- #
# Config : chain() / provider_settings()                                       #
# --------------------------------------------------------------------------- #
def test_config_chain_dedup_and_order():
    cfg = make_config(Modality.IMAGE, active="a", fallback=["b", "a", "c"])
    # active en tête, doublon 'a' éliminé en gardant l'ordre.
    assert cfg.chain(Modality.IMAGE) == ["a", "b", "c"]


def test_config_chain_without_active():
    cfg = make_config(Modality.IMAGE, fallback=["x", "y"])
    assert cfg.chain(Modality.IMAGE) == ["x", "y"]


def test_config_provider_settings_passed_to_constructor(clean_registry):
    # Les réglages de providers.yaml doivent arriver dans self.config du provider.
    register(make_fake(name="settable", modality=Modality.IMAGE, available=True))
    cfg = make_config(
        Modality.IMAGE,
        active="settable",
        providers={"settable": {"steps": 30, "model": "sdxl"}},
    )
    router = Router(cfg)
    inst = router._instance(Modality.IMAGE, "settable")
    assert inst.config.get("steps") == 30
    assert inst.config.get("model") == "sdxl"


def test_config_provider_settings_empty_when_absent():
    cfg = make_config(Modality.IMAGE, active="x")
    assert cfg.provider_settings(Modality.IMAGE, "x") == {}


# --------------------------------------------------------------------------- #
# GenResult.path                                                               #
# --------------------------------------------------------------------------- #
def test_genresult_path_helper(tmp_path):
    p = tmp_path / "out.png"
    res = GenResult(modality=Modality.IMAGE, provider="fake", location=Location.LOCAL,
                    paths=[p])
    assert res.path == p
    # Sans fichier produit : None.
    empty = GenResult(modality=Modality.IMAGE, provider="fake", location=Location.LOCAL)
    assert empty.path is None
