"""API REST FastAPI : expose le studio sur HTTP.

Lancer :  uvicorn studio.api.app:app --reload
Doc auto : http://localhost:8000/docs
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import get_router
from ..core import Modality, NoProviderAvailable, list_providers

app = FastAPI(title="Content Studio", version="0.1.0")
_router = None


def router():
    global _router
    if _router is None:
        _router = get_router()
    return _router


class GenBody(BaseModel):
    prompt: str
    provider: str | None = None
    seed: int | None = None
    negative_prompt: str | None = None
    params: dict = {}


@app.get("/providers")
def providers():
    return {"providers": list_providers()}


@app.post("/generate/{modality}")
def generate(modality: str, body: GenBody):
    try:
        mod = Modality(modality)
    except ValueError:
        raise HTTPException(400, f"Modalité inconnue: {modality}")
    kwargs = dict(body.params)
    if body.provider:
        kwargs["provider"] = body.provider
    if body.seed is not None:
        kwargs["seed"] = body.seed
    if body.negative_prompt:
        kwargs["negative_prompt"] = body.negative_prompt
    try:
        result = router().generate(mod, body.prompt, **kwargs)
    except NoProviderAvailable as e:
        raise HTTPException(503, str(e))
    return {
        "provider": result.provider,
        "location": result.location.value,
        "text": result.text,
        "paths": [str(p) for p in result.paths],
        "meta": result.meta,
    }


@app.get("/file")
def file(path: str):
    """Récupère un fichier généré (chemin renvoyé par /generate).

    Sécurité : on ne sert QUE des fichiers situés sous output_dir, sinon l'API
    laisserait lire n'importe quel fichier de la machine (path traversal).
    """
    allowed = router().config.output_dir.resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(allowed) or not resolved.is_file():
        raise HTTPException(404, "Fichier introuvable ou hors du dossier de sortie")
    return FileResponse(str(resolved))
