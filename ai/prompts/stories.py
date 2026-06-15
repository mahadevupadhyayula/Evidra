GENERATE_STORIES_SYSTEM_PROMPT = (
    "Generate reusable interview stories from approved evidence only. "
    "Use STAR/CAR structure, short, ninety-second, and detailed answers. "
    "Do not invent employers, achievements, or metrics. Unknowns become missing_details. "
    "Every story must include evidence_ids from the provided approved evidence."
)

SCORE_STORIES_SYSTEM_PROMPT = (
    "Score each reusable interview story using only the provided story and approved evidence. "
    "Return bounded component scores for specificity, impact, ownership, and clarity. "
    "Do not change story text or workflow state."
)
