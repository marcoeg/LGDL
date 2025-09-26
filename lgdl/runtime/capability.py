import json, time
from jsonschema import validate

class CapabilityClient:
    def __init__(self, contract_path: str):
        self.contract = json.load(open(contract_path))
        self.schema = self.contract.get("request_schema", {"type":"object"})
        self.timeout_ms = self.contract.get("timeout_ms", 3000)

    async def execute(self, name: str, payload: dict):
        validate(instance=payload, schema=self.schema)
        time.sleep(0.05)
        doctor = payload.get("doctor") or "any provider"
        return {"message": f"Availability for {doctor}: Tue 10:00, Wed 14:00"}
