PROFILE_EXTRACTION_PROMPT = """
Extract a draft career profile from the confirmed resume text only.
Do not use job descriptions, company context, or external research.
Do not infer sensitive or demographic attributes.
Use null for unknown scalar fields and [] for unknown list fields.
""".strip()
