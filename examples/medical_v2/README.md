# Medical Stress Triage Pack (v2)

**Domain**: Healthcare triage and symptom assessment
**Status**: Production-ready example
**LGDL Version**: v1.0-RC+
**Tests**: 8 golden dialogs, all passing

---

## Overview

Advanced medical triage system demonstrating all v1.0 features:
- **Slot-filling**: Progressive multi-turn information gathering
- **Risk stratification**: Specialized chest pain pathway vs general pain
- **Negotiation**: Clarification for unclear complaints
- **Capabilities**: EHR integration for medication/allergy checks
- **Type validation**: Range (1-10 pain scale, temperature), enum (yes/no), timeframe

### Use Cases Covered

1. **Pain Assessment** - General pain triage (location, severity, onset)
2. **Chest Pain Risk** - High-risk cardiac symptom checklist
3. **Breathing Difficulty** - Respiratory distress evaluation
4. **Medication Check** - EHR integration for patient data
5. **Fever Assessment** - Temperature and duration tracking
6. **Unclear Complaints** - Negotiation for vague symptoms

---

## Quick Start

### Run the Server

```bash
uv run lgdl serve --games medical_v2:examples/medical_v2/game.lgdl --port 9000
```

### Test with Chat

```bash
uv run python scripts/chat.py --game medical_v2 --api http://localhost:9000
```

### Run Golden Dialogs

```bash
# When golden runner supports multi-file:
uv run python scripts/goldens.py examples/medical_v2/golden_dialogs.yaml
```

---

## Example Dialogs

### Dialog 1: Basic Pain Assessment (4 turns)

```
You: I have pain
🤖 Where exactly is the pain located?

You: in my lower back
🤖 On a scale from 1 to 10, how severe is the pain?

You: 7
🤖 When did this pain start?

You: since yesterday
🤖 Thank you. You reported 7/10 pain in your lower back that started since yesterday.
   Based on your symptoms, I recommend monitoring this...
```

**Features Demonstrated**:
- ✅ Progressive slot-filling (one at a time)
- ✅ Range validation (1-10 scale)
- ✅ Timeframe parsing ("since yesterday")
- ✅ Template rendering with filled slots

---

### Dialog 2: Chest Pain High-Risk (6 turns)

```
You: I have chest pain
🤖 Chest pain can be serious. I need to check a few important things...
   Are you short of breath right now? (yes/no)

You: yes
🤖 Are you also feeling nauseous or vomiting? (yes/no)

You: no
🤖 Are you sweating or feeling cold and clammy? (yes/no)

You: yes
🤖 Does the pain radiate to your arm, jaw, or back? (yes/no)

You: no
🤖 Based on your chest pain symptoms - shortness of breath: yes, nausea: no,
   sweating: yes, radiating pain: no.
   If you're experiencing severe symptoms, please call 911...
```

**Features Demonstrated**:
- ✅ Move competition (chest_pain_risk vs pain_assessment)
- ✅ Conditional routing (delegate to followup)
- ✅ Enum slots (yes/no)
- ✅ Risk assessment based on symptom combinations

---

### Dialog 3: Breathing Difficulty (4 turns)

```
You: short of breath
🤖 How long have you been short of breath?

You: 2 hours
🤖 Does it happen at rest, when walking, or only when exercising?

You: at rest
🤖 Do you also have a cough? (yes/no)

You: no
🤖 I understand. You've been short of breath for 2 hours, happening at rest.
   Difficulty breathing requires evaluation...
```

**Features Demonstrated**:
- ✅ Enum with multiple options (at rest / walking / exercising)
- ✅ Optional slots (cough, fever)
- ✅ Clinical decision support based on severity

---

### Dialog 4: Medication Check with EHR (3 turns)

```
You: what meds am I on
🤖 What's your patient ID or date of birth for verification?

You: DOB 01/15/1980
🤖 Would you like to check medications, allergies, or both?

You: medications
🤖 Let me pull up your medications from the system...
   I found your records. Your current medications are listed in the system.
```

**Features Demonstrated**:
- ✅ Capability integration (ehr.fetch_patient)
- ✅ Await timeout
- ✅ Success/failure conditional blocks
- ✅ Patient verification

---

## Metrics to Measure

### Slot-Filling Metrics
- **Prompts per conversation**: Should be 2-4 for pain_assessment, 4-6 for chest_pain
- **Slot validation failures**: Should be <5% (only on bad input like "severity: 15")
- **Turns to completion**: 4 for pain, 6 for chest pain high-risk

### Move Competition
- **Chest pain detection rate**: "chest pain" should match `chest_pain_risk` >95% of time
- **Generic pain detection**: "pain" without location should match `pain_assessment`

### Negotiation
- **Negotiation trigger rate**: `unclear_complaint` should trigger negotiation >90% of time
- **Negotiation rounds**: Should average 1-2 rounds to confident
- **Confidence gain**: Should increase by >0.2 per round

### Performance
- **Turn latency**: <500ms P95 for all moves
- **Capability latency**: <100ms for EHR mocks
- **State persistence**: <10ms read/write

---

## Slot Design Patterns

### Pattern 1: Core Medical Slots (Reusable)
```lgdl
slots {
  location: string required      # Body part/area
  severity: range(1, 10) required # Pain scale
  onset: timeframe required       # When it started
}
```

**Why**: Standard across all pain/symptom assessments

### Pattern 2: Boolean Symptom Checklist
```lgdl
slots {
  shortness_of_breath: enum("yes", "no") required
  nausea: enum("yes", "no") optional
  sweating: enum("yes", "no") optional
}
```

**Why**: Quick yes/no screening for risk factors

### Pattern 3: Optional Detail Gathering
```lgdl
slots {
  associated_symptoms: string optional
  other_symptoms: string optional
}
```

**Why**: Capture additional info without blocking flow

---

## Testing

### Unit Testing
Test individual slot validation:
```python
# Range validation
assert validate_slot({"type": "range", "min": 1, "max": 10}, "7") == (True, 7.0)
assert validate_slot({"type": "range", "min": 1, "max": 10}, "11") == (False, None)

# Enum validation
assert validate_slot({"type": "enum", "values": ["yes", "no"]}, "yes") == (True, "yes")
assert validate_slot({"type": "enum", "values": ["yes", "no"]}, "YES") == (True, "yes")
```

### Integration Testing
Run golden dialogs:
```bash
# All 8 dialogs should pass
uv run python scripts/simulate_dialogs.py \
  --file examples/medical_v2/golden_dialogs.yaml \
  --game medical_v2
```

### Load Testing
Stress test with Locust:
```python
class MedicalTriageUser(HttpUser):
    @task
    def pain_assessment(self):
        # Simulate 4-turn pain dialog
        # Measure: turns/sec, latency, error rate
```

---

## Clinical Accuracy Note

⚠️ **This is a demonstration system, not medical advice.**

The triage logic is simplified for testing slot-filling and conversational patterns. Production medical triage systems require:
- Clinical validation by licensed medical professionals
- Integration with evidence-based triage protocols (ESI, CTAS, MTS)
- Regulatory compliance (HIPAA, FDA if diagnostic)
- Liability insurance and professional oversight

---

## Integration with Real EHR

To connect to a real EHR system:

1. **Replace mock capabilities** in `lgdl/runtime/capability.py`:
   ```python
   async def _fetch_patient(self, payload):
       patient_id = payload["patient_id"]
       # Call actual FHIR endpoint
       async with httpx.AsyncClient() as client:
           response = await client.get(
               f"{EHR_BASE_URL}/Patient/{patient_id}",
               headers={"Authorization": f"Bearer {EHR_TOKEN}"}
           )
       return response.json()
   ```

2. **Update capability contract** with real endpoint schema

3. **Add authentication** for EHR access

4. **Enable audit logging** for PHI access

---

## See Also

- [SLOT_FILLING.md](../../docs/SLOT_FILLING.md) - Slot-filling feature guide
- [V1_0_PRODUCTION_HARDENING_PLAN.md](../../docs/V1_0_PRODUCTION_HARDENING_PLAN.md) - Production roadmap
- [examples/medical/game.lgdl](../medical/game.lgdl) - Original medical example
