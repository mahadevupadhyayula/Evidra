# AI Runtime Architecture

## Purpose

The AI runtime provides minimal, structured, grounded AI operations for the Evidra Interview Sprint MBP. AI generates proposed content and scores; application services validate, persist, and decide workflow changes.

## EvidraAIService Method List

- `extract_profile`
- `analyze_jd`
- `extract_company_context`
- `extract_evidence`
- `generate_stories`
- `score_stories`
- `score_story_matches`
- `generate_preview`
- `generate_prepkit_analysis`
- `generate_prepkit_artifact`
- `evaluate_answer`
- `phrase_plan_tasks`

## Shared Call Pattern

1. Load approved inputs only.
2. Construct the smallest useful prompt.
3. Call the OpenAI Python SDK for structured output.
4. Validate output with a fixed Pydantic schema.
5. Validate source references.
6. Validate unsupported numeric claims.
7. Retry once for structural/schema failures.
8. Save validated output or failure metadata.
9. Let application services determine state transitions.

## AI May Perform

- Extracting candidate profile fields from confirmed resume text.
- Analyzing a JD supplied by the user.
- Summarizing one safe user-supplied company/product page or pasted company context.
- Extracting evidence candidates from resume text and user highlights.
- Generating reusable stories from approved evidence.
- Scoring stories and story matches using component scores.
- Drafting preview and Prep Kit content from approved inputs.
- Evaluating typed practice answers against approved facts.
- Phrasing deterministic plan tasks.

## AI May Not Perform

- Workflow state transitions.
- Evidence approval.
- Payment status changes.
- Access grants.
- Broad web research.
- Sensitive or demographic inference.
- Unsupported metric creation.
- Employer or achievement invention.
- Provenance removal.
- Destructive duplicate merging.

## Structured Output Rules

- Every operation has one fixed Pydantic schema.
- Unknown values are `null` or explicit missing details.
- Lists must have documented maximum sizes where relevant.
- Numeric scores must be bounded to the documented range.
- Outputs that reference evidence, stories, questions, or source excerpts must include IDs or source locations.
- Free text must be saved only after schema validation succeeds.

## Retry Policy

- Retry once for schema, parsing, or recoverable structural validation failures.
- Do not retry indefinitely.
- Do not retry unsafe URL fetch failures as AI operations.
- Persist final failure in `GenerationRun` or the calling service's error field.
- Preserve prior successful outputs when a retry fails.

## Source Validation

- Evidence cards require source excerpts.
- Stories must reference approved evidence IDs.
- Matches must reference story IDs and relevant evidence IDs.
- JD-based claims must cite or store a JD excerpt when used for matching explanation.
- Prep Kit recommendations must trace to approved evidence, stories, opportunity context, role pack, or user-confirmed company context.

## Unsupported Numeric Claim Validation

- Metrics in evidence must appear in source text or user correction.
- Metrics in stories must trace to approved evidence.
- Metrics in preview or Prep Kit must trace to evidence, stories, or JD/company context.
- Unsupported percentages, revenue numbers, team sizes, timelines, or outcome claims must be removed or flagged as missing details.
- AI may not convert vague claims into precise metrics.

## GenerationRun Metadata

GenerationRun stores:

- `id`
- `sprint_id`
- `operation`
- `status`
- `attempt_count`
- `input_revision`
- `error_code`
- `error_message`
- `started_at`
- `completed_at`
- `created_at`

Statuses:

- `PENDING`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `STALE`

## Testing Rules

- Use fake AI clients in automated tests.
- Test schema validation failures.
- Test unsupported metric rejection.
- Test missing source reference rejection.
- Test one retry only.
- Test that AI output does not change workflow state.
- Test that failed AI calls preserve prior work.

## Deferred AI Platform Features

- Model router.
- Multi-agent orchestration.
- Prompt dashboard.
- LLM judge.
- Prompt benchmark suite.
- Embeddings.
- Vector search.
- Learned ranking.
- Production-scale observability.
