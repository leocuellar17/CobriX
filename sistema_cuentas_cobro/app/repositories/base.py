"""Repositorio base genérico tipado con operaciones CRUD reutilizables."""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import EntityNotFoundException
from app.db.database import Base


ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Implementa operaciones CRUD genéricas sobre modelos SQLAlchemy 2.0."""

    def __init__(self, db: Session, model: type[ModelType]) -> None:
        self.db = db
        self.model = model

    def get_by_id(self, entity_id: int) -> Optional[ModelType]:
        """Obtiene una entidad por su llave primaria o retorna None."""
        return self.db.get(self.model, entity_id)

    def get_or_404(self, entity_id: int, entity_name: str) -> ModelType:
        """Obtiene una entidad por ID o lanza EntityNotFoundException."""
        obj = self.get_by_id(entity_id)
        if obj is None:
            raise EntityNotFoundException(entity_name, entity_id)
        return obj

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> list[ModelType]:
        """Lista entidades con paginación y filtros exactos opcionales."""
        stmt = select(self.model)
        for field, value in filters.items():
            if hasattr(self.model, field):
                stmt = stmt.where(getattr(self.model, field) == value)
        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.scalars(stmt).all())

    def create(
        self,
        obj_data: dict[str, Any] | BaseModel,
        *,
        commit: bool = True,
    ) -> ModelType:
        """Crea y persiste una nueva entidad a partir de dict o BaseModel."""
        data = (
            obj_data.model_dump()
            if isinstance(obj_data, BaseModel)
            else dict(obj_data)
        )
        db_obj = self.model(**data)
        self.db.add(db_obj)
        if commit:
            self.db.commit()
            self.db.refresh(db_obj)
        else:
            self.db.flush()
        return db_obj

    def update(
        self,
        db_obj: ModelType,
        obj_data: dict[str, Any] | BaseModel,
        *,
        commit: bool = True,
        exclude_unset: bool = True,
    ) -> ModelType:
        """Actualiza los atributos de una entidad existente."""
        changes = (
            obj_data.model_dump(exclude_unset=exclude_unset)
            if isinstance(obj_data, BaseModel)
            else dict(obj_data)
        )
        for field, value in changes.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        if commit:
            self.db.commit()
            self.db.refresh(db_obj)
        else:
            self.db.flush()
        return db_obj

    def delete(self, db_obj: ModelType, *, commit: bool = True) -> None:
        """Elimina físicamente una entidad de la base de datos."""
        self.db.delete(db_obj)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
