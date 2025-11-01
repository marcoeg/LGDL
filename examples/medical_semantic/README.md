# Medical Semantic Triage Game

## Overview

This example demonstrates **Phase 1: Context-Aware Semantic Matching** with vocabulary support.

The game handles emergency room triage with understanding of medical slang and colloquialisms through a rich vocabulary definition.

## Key Features

### 1. Vocabulary-Aware Matching

The game understands synonyms and domain-specific terminology:

```lgdl
vocabulary {
    "heart" also means: ["ticker", "chest", "cardiovascular", "cardiac"]
    "pain" also means: ["hurting", "aching", "discomfort", "bothering me"]
}
```

**Example Conversations**:

```
User: "My ticker is really bothering me"
→ Matches: chest_pain_priority (understands "ticker" = "chest/heart")

User: "My noggin is aching"
→ Matches: pain_assessment (understands "noggin" = "head")

User: "My belly hurts real bad"
→ Matches: pain_assessment (understands "belly" = "stomach")
```

### 2. Multi-Turn Slot Filling

Progressive information gathering with context:

```
Assistant: Where exactly is the pain located?
User: my chest
→ Fills location slot with "chest" (understands short response in context)