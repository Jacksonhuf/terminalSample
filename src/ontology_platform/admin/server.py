"""FastAPI server for ontology management and visualization."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ontology_platform.admin.manager import OntologyManager
from ontology_platform.ontology.schema import (
    ActionDef,
    LinkDef,
    ObjectTypeDef,
    OntologyDef,
)

STATIC_DIR = Path(__file__).parent / "static"


class CreateOntologyRequest(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0"


def create_app(ontology_dir: str | Path | None = None) -> FastAPI:
    base_dir = Path(ontology_dir) if ontology_dir else Path(__file__).parent.parent.parent.parent / "examples"
    manager = OntologyManager(base_dir)

    app = FastAPI(
        title="Ontology Admin",
        description="本体定义管理与可视化",
        version="0.1.0",
    )

    # --- API ---

    @app.get("/api/ontologies")
    def list_ontologies():
        return {"ontologies": manager.list_ontologies(), "directory": str(manager.directory)}

    @app.get("/api/ontologies/{name}")
    def get_ontology(name: str):
        try:
            ontology = manager.load(name)
            return ontology.model_dump()
        except FileNotFoundError:
            raise HTTPException(404, f"Ontology not found: {name}")

    @app.post("/api/ontologies")
    def create_ontology(req: CreateOntologyRequest):
        try:
            ontology = OntologyDef(name=req.name, description=req.description, version=req.version)
            path = manager.create(ontology)
            return {"message": "created", "path": str(path), "ontology": ontology.model_dump()}
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.put("/api/ontologies/{name}")
    def update_ontology(name: str, data: dict):
        try:
            ontology = OntologyDef.model_validate(data)
            if ontology.name != name:
                raise HTTPException(400, "Ontology name in body must match URL")
            path = manager.save(ontology)
            return {"message": "saved", "path": str(path), "ontology": ontology.model_dump()}
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/ontologies/{name}")
    def delete_ontology(name: str):
        if not manager.delete(name):
            raise HTTPException(404, f"Ontology not found: {name}")
        return {"message": "deleted", "name": name}

    @app.get("/api/ontologies/{name}/graph")
    def get_graph(name: str):
        try:
            return manager.to_graph(name)
        except FileNotFoundError:
            raise HTTPException(404, f"Ontology not found: {name}")

    # Object type CRUD
    @app.post("/api/ontologies/{name}/object-types")
    def add_object_type(name: str, obj_type: ObjectTypeDef):
        ontology = _load_or_404(manager, name)
        if ontology.get_object_type(obj_type.name):
            raise HTTPException(409, f"Object type already exists: {obj_type.name}")
        ontology.object_types.append(obj_type)
        manager.save(ontology)
        return obj_type.model_dump()

    @app.put("/api/ontologies/{name}/object-types/{type_name}")
    def update_object_type(name: str, type_name: str, obj_type: ObjectTypeDef):
        ontology = _load_or_404(manager, name)
        idx = _find_index(ontology.object_types, type_name, "name")
        if idx is None:
            raise HTTPException(404, f"Object type not found: {type_name}")
        ontology.object_types[idx] = obj_type
        manager.save(ontology)
        return obj_type.model_dump()

    @app.delete("/api/ontologies/{name}/object-types/{type_name}")
    def delete_object_type(name: str, type_name: str):
        ontology = _load_or_404(manager, name)
        idx = _find_index(ontology.object_types, type_name, "name")
        if idx is None:
            raise HTTPException(404, f"Object type not found: {type_name}")
        ontology.object_types.pop(idx)
        manager.save(ontology)
        return {"message": "deleted", "name": type_name}

    # Link CRUD
    @app.post("/api/ontologies/{name}/links")
    def add_link(name: str, link: LinkDef):
        ontology = _load_or_404(manager, name)
        if ontology.get_link(link.name):
            raise HTTPException(409, f"Link already exists: {link.name}")
        ontology.links.append(link)
        manager.save(ontology)
        return link.model_dump()

    @app.delete("/api/ontologies/{name}/links/{link_name}")
    def delete_link(name: str, link_name: str):
        ontology = _load_or_404(manager, name)
        idx = _find_index(ontology.links, link_name, "name")
        if idx is None:
            raise HTTPException(404, f"Link not found: {link_name}")
        ontology.links.pop(idx)
        manager.save(ontology)
        return {"message": "deleted", "name": link_name}

    # Action CRUD
    @app.post("/api/ontologies/{name}/actions")
    def add_action(name: str, action: ActionDef):
        ontology = _load_or_404(manager, name)
        if ontology.get_action(action.name):
            raise HTTPException(409, f"Action already exists: {action.name}")
        ontology.actions.append(action)
        manager.save(ontology)
        return action.model_dump()

    @app.delete("/api/ontologies/{name}/actions/{action_name}")
    def delete_action(name: str, action_name: str):
        ontology = _load_or_404(manager, name)
        idx = _find_index(ontology.actions, action_name, "name")
        if idx is None:
            raise HTTPException(404, f"Action not found: {action_name}")
        ontology.actions.pop(idx)
        manager.save(ontology)
        return {"message": "deleted", "name": action_name}

    # --- Static UI pages ---

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/editor")
    def editor_page():
        return FileResponse(STATIC_DIR / "editor.html")

    @app.get("/visualize")
    def visualize_page():
        return FileResponse(STATIC_DIR / "visualize.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


def _load_or_404(manager: OntologyManager, name: str) -> OntologyDef:
    try:
        return manager.load(name)
    except FileNotFoundError:
        raise HTTPException(404, f"Ontology not found: {name}")


def _find_index(items: list, name: str, attr: str) -> int | None:
    for i, item in enumerate(items):
        if getattr(item, attr) == name:
            return i
    return None
