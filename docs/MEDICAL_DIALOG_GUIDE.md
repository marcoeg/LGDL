# Guide to Writing Medical Dialogs in LGDL

**A Practical Guide for Healthcare Professionals**

Version: 2.0 (Phases 1-3 Complete)
Last Updated: November 2025
Audience: Medical doctors, nurses, healthcare administrators

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Quick Start](#2-quick-start-your-first-medical-dialog)
3. [Core Concepts](#3-core-concepts)
4. [Slot-Filling (Progressive Information Gathering)](#4-slot-filling-progressive-information-gathering)
5. [Vocabulary & Natural Language](#5-vocabulary--natural-language-phase-1--2)
6. [Capabilities (System Integration)](#6-capabilities-system-integration)
7. [Complete Working Examples](#7-complete-working-examples)
8. [Medical Vocabulary Library](#8-medical-vocabulary-library)
9. [Best Practices for Medical Domains](#9-best-practices-for-medical-domains)
10. [Testing Your Dialogs](#10-testing-your-dialogs)
11. [Troubleshooting](#11-troubleshooting)
12. [Reference](#12-reference)

---

## 1. Introduction

### What is LGDL?

LGDL (Language-Game Definition Language) is a declarative language for creating safe, deterministic conversational AI for healthcare.

**Key Differences from Traditional Chatbots:**

| Traditional Chatbot | LGDL |
|---------------------|------|
| ❌ Unpredictable responses | ✅ Deterministic templates |
| ❌ Guesses when uncertain | ✅ Asks for clarification |
| ❌ Black box decisions | ✅ Explicit confidence scores |
| ❌ Can't improve | ✅ Learns from successful conversations |
| ❌ Complex to audit | ✅ Simple, readable game files |

**Why This Matters in Healthcare:**
- **Safety**: Every response is pre-defined by medical professionals
- **Auditability**: Complete conversation logic in readable files
- **Compliance**: HIPAA-compliant by design (no data sent to LLM except for matching)
- **Quality**: Learns what works in practice with human oversight

---

### What You Can Build

**Symptom Triage** → Route patients to appropriate care level
**Intake Automation** → Collect medical history before appointments
**Post-Visit Follow-up** → Check recovery progress
**Medication Reminders** → Confirm adherence, detect issues
**Appointment Scheduling** → Book based on symptoms and availability
**L1 Support** → Answer common questions, escalate complex cases

---

## 2. Quick Start: Your First Medical Dialog

Let's create a simple pain triage system in 5 minutes.

### Step 1: Create Your Game File

**File**: `my_first_game.lgdl`

```lgdl
game pain_triage {
  description: "Simple pain assessment and triage"

  moves {
    move assess_pain {
      slots {
        location: string required
        severity: range(1, 10) required
      }

      when user says something like: [
        "I have pain",
        "I'm in pain",
        "something hurts"
      ]
      confidence: medium

      when slot location is missing {
        prompt slot: "Where exactly is the pain located?"
      }

      when slot severity is missing {
        prompt slot: "On a scale from 1 to 10, how severe is the pain?"
      }

      when all_slots_filled {
        respond with: "Thank you. You've reported {severity}/10 pain in your {location}. Based on this, I recommend monitoring. If the pain worsens or new symptoms develop, seek immediate care."
      }
    }

    move chest_pain_alert {
      when user says something like: [
        "chest pain",
        "my chest hurts",
        "pain in my chest"
      ]
      confidence: high

      when confident {
        respond with: "Chest pain requires immediate evaluation. Please call 911 or go to the nearest emergency room right away. Do not drive yourself."
      }
    }
  }
}
```

### Step 2: Test It

```bash
# Validate syntax
uv run lgdl validate my_first_game.lgdl

# Start server
uv run lgdl serve --games pain:my_first_game.lgdl

# In another terminal, start chat
uv run python scripts/chat.py --game pain
```

### Step 3: Have a Conversation

```
You: I have pain
Assistant: Where exactly is the pain located?

You: my chest
[Slot filled: location = "my chest"]
Assistant: On a scale from 1 to 10, how severe is the pain?

You: 8
[Slot filled: severity = 8.0]
Assistant: Thank you. You've reported 8/10 pain in your my chest. Based on this, I recommend monitoring. If the pain worsens or new symptoms develop, seek immediate care.
```

**What Just Happened:**
1. ✅ Pattern matched: "I have pain" → `assess_pain` move
2. ✅ Progressive slot-filling: Asked for location, then severity
3. ✅ Template response: Filled {severity} and {location} variables
4. ✅ Complete conversation in 3 turns

**Congratulations! You just created your first medical dialog.** 🎉

---

## 3. Core Concepts

### Concept 1: Patterns (How Patients Express Intent)

Patients say the same thing in many ways. Patterns capture these variations.

**Example - Expressing Pain:**
```lgdl
when user says something like: [
  "I have pain",           // Direct statement
  "I'm in pain",           // Alternative phrasing
  "something hurts",       // Casual phrasing
  "I'm hurting",           // Present progressive
  "it hurts",              // Informal
  "I have discomfort"      // Medical terminology
]
```

**Pattern Variables** (capture specifics):
```lgdl
when user says something like: [
  "pain in my {location}",     // Captures: "pain in my chest" → location="chest"
  "{location} hurts",          // Captures: "head hurts" → location="head"
  "my {location} is hurting"   // Captures: "my stomach is hurting" → location="stomach"
]
```

**Best Practice**: Include 5-10 common phrasings per intent.

---

### Concept 2: Confidence (When to Ask for Clarification)

Confidence determines if the system is sure enough to proceed.

**Confidence Levels:**
```lgdl
confidence: high      // 80%+ required (for safety-critical)
confidence: medium    // 50%+ required (general use)
confidence: low       // 20%+ required (exploratory)
```

**Example - Safety-Critical (High Confidence)**:
```lgdl
move chest_pain_emergency {
  when user says something like: [
    "chest pain",
    "my chest hurts"
  ]
  confidence: high    // Must be very sure before alerting emergency

  when confident {
    respond with: "Chest pain requires immediate attention. Please call 911."
  }

  when uncertain {
    negotiate "To ensure I understand correctly: are you experiencing chest pain right now? (yes/no)" until confident
  }
}
```

**Example - General (Medium Confidence)**:
```lgdl
move general_pain {
  when user says something like: [
    "I have pain"
  ]
  confidence: medium    // Okay to ask follow-up questions

  when confident {
    // Proceed with slot-filling
  }

  when uncertain {
    negotiate "Can you tell me more about what's bothering you?" until confident
  }
}
```

---

### Concept 3: Negotiation (Handling Unclear Input)

When confidence is below threshold, the system asks for clarification instead of guessing.

**Example:**
```
Patient: "I don't feel good"
→ Confidence: 0.35 (below 0.50 threshold)
→ Action: Negotiate