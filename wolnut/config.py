import os
from typing import Dict, List, Optional
import yaml
from pydantic import BaseModel, Field, model_validator


class NutSource(BaseModel):
    hostname: str = "127.0.0.1"
    port: int = 3493


class WakeOnConfig(BaseModel):
    restore_delay_sec: int = Field(default=30, ge=0)
    min_battery_percent: int = Field(default=25, ge=0, le=100)
    client_timeout_sec: int = Field(default=600, ge=0)
    reattempt_delay: int = Field(default=30, ge=0)


class ClientConfig(BaseModel):
    name: str
    host: str
    mac: str
    ups: str  # Must map to a key inside the `nut` dictionary


class WolNutConfig(BaseModel):
    nut: Dict[str, NutSource] = Field(..., min_length=1)
    master_ups: Optional[str] = None
    status_file: str = "/config/wolnut_state.json"
    wake_on: WakeOnConfig = Field(default_factory=WakeOnConfig)
    clients: List[ClientConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ups_references(self) -> "WolNutConfig":
        # 1. Validate master_ups exists if defined
        if self.master_ups and self.master_ups not in self.nut:
            raise ValueError(
                f"master_ups '{self.master_ups}' is not defined in the 'nut' configuration block."
            )

        # 2. Validate that each client's assigned UPS exists
        for client in self.clients:
            if client.ups not in self.nut:
                raise ValueError(
                    f"Client '{client.name}' references UPS '{client.ups}', "
                    f"which does not exist in the 'nut' configuration block."
                )

        return self


def load_config(config_path: str = "/config/config.yaml") -> WolNutConfig:
    """Loads and validates the YAML configuration file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
        
    with open(config_path, "r") as f:
        raw_yaml = yaml.safe_load(f) or {}
        
    return WolNutConfig.model_validate(raw_yaml)
