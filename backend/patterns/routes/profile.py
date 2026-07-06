"""Home profile API: user-declared routine CRUD."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from patterns.logic import profile_service
from patterns.models.profile import UserRoutine, UserRoutineCreate

router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/{household_id}/routines", response_model=UserRoutine, status_code=201)
def add_routine(household_id: str, body: UserRoutineCreate) -> UserRoutine:
    """Declare a new user-defined routine for the home."""
    return profile_service.create_routine(household_id, body)


@router.get("/{household_id}/routines")
def list_routines(household_id: str) -> dict:
    """Return all user-declared routines for the home."""
    routines = profile_service.list_routines(household_id)
    return {
        "household_id": household_id,
        "count": len(routines),
        "routines": [r.model_dump(mode="json") for r in routines],
    }


@router.delete("/{household_id}/routines/{routine_id}", status_code=200)
def delete_routine(household_id: str, routine_id: str) -> dict:
    """Remove a user-declared routine."""
    profile_service.delete_routine(household_id, routine_id)
    return {"deleted": routine_id}
