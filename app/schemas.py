from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    department: str
    active: bool
