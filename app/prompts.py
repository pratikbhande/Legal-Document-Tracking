"""
Centralized prompts for LLM analysis
Optimized for gpt-4o-mini
"""

# Quick validation prompt - checks if document actually references the law
LAW_REFERENCE_VALIDATION_PROMPT = """You are a legal document analyzer. Your task is to determine if a document actually references or discusses a specific law.

**LAW TO CHECK:**
{law_name}

**DOCUMENT TEXT:**
{document_text}

**QUESTION:**
Does this document actually reference, cite, discuss, or mention the law "{law_name}"?

**IMPORTANT RULES:**
1. The document must SPECIFICALLY reference this law by name or discuss its provisions
2. Generic mentions of the topic area (e.g., "domestic violence" when checking for "Illinois Domestic Violence Act") DO NOT count
3. The law name must appear or the document must clearly discuss provisions of this specific law
4. Side mentions in unrelated contexts DO NOT count

**RESPOND WITH ONLY:**
YES - [brief 10 word explanation of where/how it's referenced]
or
NO - [brief 10 word explanation of why it's not referenced]

**EXAMPLES:**

Law: "Privacy Act 2020"
Document: "Under the Privacy Act 2020, businesses must obtain explicit consent..."
Answer: YES - Document directly discusses Privacy Act 2020 consent requirements

Law: "Privacy Act 2020"  
Document: "When evicting tenants, landlords should respect privacy and follow proper procedures..."
Answer: NO - Only mentions privacy generally, not the Privacy Act 2020

Law: "Illinois Domestic Violence Act"
Document: "The Illinois Domestic Violence Act of 1986 provides protections for victims..."
Answer: YES - Document explicitly names and discusses the Illinois Domestic Violence Act

Law: "Illinois Domestic Violence Act"
Document: "Landlords cannot evict tenants who need to leave due to domestic violence situations..."
Answer: NO - Mentions domestic violence topic but not the Illinois Domestic Violence Act
"""

# Detailed analysis prompt (only used when what_changed is provided)
ARTICLE_ANALYSIS_PROMPT = """You are a legal compliance expert. Analyze how a law change affects this document.

**LAW CHANGE:**
Law: {law_name}
Change: {what_changed}

**DOCUMENT:**
{document_text}

**TASK:**
Identify sections affected by this law change. For each:
1. Quote the exact text (max 150 words)
2. Explain the issue
3. Suggest specific updates

**RESPOND IN JSON:**
{{
  "analysis": {{
    "document_mentions_law": true/false,
    "overall_impact": "brief summary",
    "sections_needing_update": [
      {{
        "section_text": "exact quote",
        "issue": "why outdated",
        "suggested_change": "specific update",
        "confidence": 0.0-1.0
      }}
    ]
  }}
}}

Be concise. Only include directly affected sections.
"""