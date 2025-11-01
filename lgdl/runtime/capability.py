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

        # EHR capabilities (medical_v2)
        elif name == "ehr.fetch_patient":
            return self._fetch_patient(payload)
        elif name == "ehr.fetch_med_list":
            return self._fetch_med_list(payload)
        elif name == "ehr.fetch_allergies":
            return self._fetch_allergies(payload)
        elif name == "ehr.create_visit":
            return self._create_visit(payload)

        # Auth capabilities (support_v1)
        elif name == "auth.verify_user":
            return self._verify_user(payload)
        elif name == "auth.send_reset_link":
            return self._send_reset_link(payload)
        elif name == "auth.unlock_account":
            return self._unlock_account(payload)
        elif name == "auth.check_2fa_status":
            return self._check_2fa_status(payload)

        # Billing capabilities (support_v1)
        elif name == "billing.get_invoices":
            return self._get_invoices(payload)
        elif name == "billing.get_plan":
            return self._get_plan(payload)
        elif name == "billing.process_refund":
            return self._process_refund(payload)

        # Device capabilities (support_v1)
        elif name == "device.check_status":
            return self._check_device_status(payload)
        elif name == "device.restart_service":
            return self._restart_service(payload)
        elif name == "device.check_connectivity":
            return self._check_connectivity(payload)

        # Default appointment system capability
        doctor = payload.get("doctor") or "any provider"
        return {"message": f"Availability for {doctor}: Tue 10:00, Wed 14:00"}

    def _assess_pain(self, payload: dict) -> dict:
        """Mock pain assessment."""
        location = payload.get("location", "unspecified area")
        # Support both 'level' (legacy) and 'severity' (v1.0 slot name)
        level = payload.get("severity") or payload.get("level", "moderate")
        onset = payload.get("onset", "unknown")

        # Simple heuristic for urgency based on severity
        try:
            level_int = int(float(level)) if level else 5
            if level_int >= 8:
                urgency = "high"
                wait_time = 5
                triage_notes = "High priority - immediate assessment required."
            elif level_int >= 5:
                urgency = "medium"
                wait_time = 30
                triage_notes = "Moderate priority - please wait in triage area."
            else:
                urgency = "low"
                wait_time = 60
                triage_notes = "Low priority - routine evaluation."
        except (ValueError, TypeError):
            urgency = "high" if "severe" in str(level).lower() else "medium"
            wait_time = 15
            triage_notes = "Assessment required."

        return {
            "status": "ok",
            "message": f"Pain assessed: {location}, severity {level}, onset {onset}",
            "data": {
                "urgency": urgency,
                "wait_time": wait_time,
                "triage_notes": triage_notes
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

    # ========== EHR Capabilities (medical_v2) ==========

    def _fetch_patient(self, payload: dict) -> dict:
        """Mock patient record fetch from EHR."""
        patient_id = payload.get("patient_id", "UNKNOWN")

        # Mock patient data
        return {
            "status": "ok",
            "message": f"Patient record retrieved for {patient_id}",
            "data": {
                "patient_id": patient_id,
                "name": "John Doe",
                "dob": "1980-01-15",
                "mrn": "MRN-123456",
                "primary_provider": "Dr. Smith",
                "insurance": "BlueCross PPO"
            }
        }

    def _fetch_med_list(self, payload: dict) -> dict:
        """Mock medication list retrieval."""
        patient_id = payload.get("patient_id", "UNKNOWN")

        # Mock medication list
        return {
            "status": "ok",
            "message": f"Medication list for patient {patient_id}",
            "data": {
                "medications": [
                    {"name": "Lisinopril 10mg", "frequency": "once daily"},
                    {"name": "Metformin 500mg", "frequency": "twice daily"},
                    {"name": "Aspirin 81mg", "frequency": "once daily"}
                ],
                "last_updated": "2025-10-15"
            }
        }

    def _fetch_allergies(self, payload: dict) -> dict:
        """Mock allergy list retrieval."""
        patient_id = payload.get("patient_id", "UNKNOWN")

        return {
            "status": "ok",
            "message": f"Allergy list for patient {patient_id}",
            "data": {
                "allergies": [
                    {"allergen": "Penicillin", "reaction": "Hives"},
                    {"allergen": "Latex", "reaction": "Contact dermatitis"}
                ],
                "no_known_allergies": False
            }
        }

    def _create_visit(self, payload: dict) -> dict:
        """Mock visit creation in EHR system."""
        pain_location = payload.get("pain_location", "unknown")
        pain_severity = payload.get("pain_severity", 0)
        onset_timing = payload.get("onset_timing", "unknown")

        # Mock visit creation
        visit_id = "VISIT-" + str(random.randint(10000, 99999))

        return {
            "status": "ok",
            "message": f"Visit created for {pain_location} pain (severity: {pain_severity}/10)",
            "data": {
                "visit_id": visit_id,
                "pain_location": pain_location,
                "pain_severity": pain_severity,
                "onset_timing": onset_timing,
                "triage_priority": "high" if pain_severity >= 8 else "medium" if pain_severity >= 5 else "low",
                "created_at": "2025-11-01T12:00:00Z"
            }
        }

    # ========== Auth Capabilities (support_v1) ==========

    def _verify_user(self, payload: dict) -> dict:
        """Mock user verification."""
        username = payload.get("username") or payload.get("email", "unknown")

        # Simulate verification (always succeed for demo)
        return {
            "status": "ok",
            "message": f"User {username} verified",
            "data": {
                "user_found": True,
                "account_active": True,
                "user_id": "USER-" + str(random.randint(1000, 9999))
            }
        }

    def _send_reset_link(self, payload: dict) -> dict:
        """Mock sending password reset link."""
        username = payload.get("username") or payload.get("email", "unknown")
        channel = payload.get("channel", "email")

        return {
            "status": "ok",
            "message": f"Reset link sent to {username} via {channel}",
            "data": {
                "sent_to": username,
                "channel": channel,
                "expires_in": "24 hours"
            }
        }

    def _unlock_account(self, payload: dict) -> dict:
        """Mock account unlock."""
        username = payload.get("username", "unknown")

        # Simulate unlock (success 95% of time)
        success = random.random() < 0.95

        if success:
            return {
                "status": "ok",
                "message": f"Account {username} unlocked",
                "data": {
                    "unlocked": True,
                    "security_note": "Password change recommended"
                }
            }
        else:
            return {
                "status": "error",
                "message": f"Unable to unlock {username} - manual review required",
                "data": {"unlocked": False}
            }

    def _check_2fa_status(self, payload: dict) -> dict:
        """Mock 2FA status check."""
        username = payload.get("username", "unknown")

        return {
            "status": "ok",
            "message": f"2FA status for {username}",
            "data": {
                "enabled": random.choice([True, False]),
                "methods": ["sms", "authenticator_app"]
            }
        }

    # ========== Billing Capabilities (support_v1) ==========

    def _get_invoices(self, payload: dict) -> dict:
        """Mock invoice retrieval."""
        account_id = payload.get("account_id", "UNKNOWN")

        return {
            "status": "ok",
            "message": f"Invoices for account {account_id}",
            "data": {
                "invoices": [
                    {"date": "2025-10-01", "amount": "$29.99", "status": "paid"},
                    {"date": "2025-09-01", "amount": "$29.99", "status": "paid"},
                    {"date": "2025-08-01", "amount": "$29.99", "status": "paid"}
                ],
                "invoice_date": "2025-10-01",
                "invoice_amount": "$29.99"
            }
        }

    def _get_plan(self, payload: dict) -> dict:
        """Mock plan details retrieval."""
        account_id = payload.get("account_id", "UNKNOWN")

        return {
            "status": "ok",
            "message": f"Plan details for account {account_id}",
            "data": {
                "plan_name": "Pro Plan",
                "price": "$29.99/month",
                "renewal_date": "2025-11-15",
                "features": ["Unlimited storage", "Priority support", "Advanced analytics"]
            }
        }

    def _process_refund(self, payload: dict) -> dict:
        """Mock refund processing."""
        account_id = payload.get("account_id", "UNKNOWN")
        amount = payload.get("amount", "$29.99")

        return {
            "status": "ok",
            "message": f"Refund processed for account {account_id}",
            "data": {
                "refund_amount": amount,
                "processing_time": "5-7 business days",
                "refund_id": "REF-" + str(random.randint(10000, 99999))
            }
        }

    # ========== Device Capabilities (support_v1) ==========

    def _check_device_status(self, payload: dict) -> dict:
        """Mock platform status check."""
        device_type = payload.get("device_type", "unknown")

        # Simulate occasional platform issues
        operational = random.random() < 0.9

        if operational:
            return {
                "status": "ok",
                "message": f"{device_type} platform operational",
                "data": {
                    "platform_status": "operational",
                    "known_issues": []
                }
            }
        else:
            return {
                "status": "ok",
                "message": f"{device_type} platform experiencing issues",
                "data": {
                    "platform_status": "degraded",
                    "known_issues": ["Slow loading times"],
                    "eta": "30 minutes"
                }
            }

    def _restart_service(self, payload: dict) -> dict:
        """Mock service restart for user session."""
        username = payload.get("username", "unknown")
        device_type = payload.get("device_type", "unknown")

        return {
            "status": "ok",
            "message": f"Restarted session for {username} on {device_type}",
            "data": {
                "session_id": "SESSION-" + str(random.randint(10000, 99999)),
                "restart_time": "2025-10-31T12:00:00Z"
            }
        }

    def _check_connectivity(self, payload: dict) -> dict:
        """Mock connectivity test."""
        device_type = payload.get("device_type", "unknown")

        # Simulate connectivity check
        connected = random.random() < 0.95

        return {
            "status": "ok",
            "message": f"Connectivity test for {device_type}",
            "data": {
                "connected": connected,
                "latency_ms": random.randint(50, 200) if connected else None,
                "recommendation": "Connection stable" if connected else "Check network settings"
            }
        }
