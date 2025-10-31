import json, time
import random
from jsonschema import validate

class CapabilityClient:
    def __init__(self, contract_path: str):
        self.contract = json.load(open(contract_path))
        self.schema = self.contract.get("request_schema", {"type":"object"})
        self.timeout_ms = self.contract.get("timeout_ms", 3000)

    async def execute(self, name: str, payload: dict):
        validate(instance=payload, schema=self.schema)
        time.sleep(0.05)

        # Medical capabilities
        if name == "medical.assess_pain":
            return self._assess_pain(payload)
        elif name == "medical.code_blue":
            return self._code_blue(payload)
        elif name == "medical.check_oxygen":
            return self._check_oxygen(payload)
        elif name == "medical.trauma_assessment":
            return self._trauma_assessment(payload)
        elif name == "medical.fall_protocol":
            return self._fall_protocol(payload)
        elif name == "medical.fever_protocol":
            return self._fever_protocol(payload)

        # Default appointment system capability
        doctor = payload.get("doctor") or "any provider"
        return {"message": f"Availability for {doctor}: Tue 10:00, Wed 14:00"}

    def _assess_pain(self, payload: dict) -> dict:
        """Mock pain assessment."""
        location = payload.get("location", "unspecified area")
        level = payload.get("level", "moderate")

        # Simple heuristic for urgency
        try:
            level_int = int(level)
            urgency = "high" if level_int >= 8 else "medium"
        except (ValueError, TypeError):
            urgency = "high" if "severe" in str(level).lower() else "medium"

        return {
            "status": "ok",
            "message": f"Pain assessed in {location}",
            "data": {
                "urgency": urgency,
                "wait_time": 5 if urgency == "high" else 15
            }
        }

    def _code_blue(self, payload: dict) -> dict:
        """Mock cardiac emergency response."""
        return {
            "status": "ok",
            "message": "Emergency team alerted",
            "data": {"eta": 2}
        }

    def _check_oxygen(self, payload: dict) -> dict:
        """Mock oxygen level check."""
        # Simulate varying oxygen levels
        oxygen_level = random.randint(85, 98)

        return {
            "status": "ok",
            "message": f"Oxygen level: {oxygen_level}%",
            "data": {"oxygen_level": oxygen_level}
        }

    def _trauma_assessment(self, payload: dict) -> dict:
        """Mock trauma severity assessment."""
        mechanism = payload.get("mechanism", "unknown")
        bleeding = payload.get("bleeding", "no")

        # Simple trauma level logic
        if "car" in str(mechanism).lower() or bleeding == "yes":
            trauma_level = 1  # Highest priority
            response_plan = "Immediate imaging and blood work"
        else:
            trauma_level = 2
            response_plan = "Preparing for imaging"

        return {
            "status": "ok",
            "message": f"Trauma assessed: Level {trauma_level}",
            "data": {
                "trauma_level": trauma_level,
                "response_plan": response_plan
            }
        }

    def _fall_protocol(self, payload: dict) -> dict:
        """Mock geriatric fall assessment."""
        location = payload.get("location", "unknown")

        # Simulate head injury detection
        head_injury = "yes" if random.random() < 0.3 else "no"

        return {
            "status": "ok",
            "message": f"Fall assessment complete",
            "data": {
                "head_injury": head_injury,
                "wait_time": 10 if head_injury == "yes" else 20
            }
        }

    def _fever_protocol(self, payload: dict) -> dict:
        """Mock fever assessment."""
        temp = payload.get("temp")

        # Parse temperature if provided
        try:
            temp_value = int(temp) if temp else 99
        except (ValueError, TypeError):
            temp_value = 99

        return {
            "status": "ok",
            "message": f"Fever protocol initiated",
            "data": {
                "temp": temp_value,
                "wait_time": 10 if temp_value >= 103 else 30
            }
        }
