from pydantic import BaseModel, ConfigDict


class AppBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
