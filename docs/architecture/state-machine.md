# Sprint State Machine

## Approved States

- `DRAFT`
- `RESUME_READY`
- `PROFILE_CONFIRMED`
- `OPPORTUNITY_CONFIRMED`
- `EVIDENCE_REVIEW`
- `EVIDENCE_APPROVED`
- `STORIES_READY`
- `MATCHING_READY`
- `PREVIEW_READY`
- `PAYMENT_PENDING`
- `PAID`
- `PREPKIT_READY`
- `PRACTICE_ACTIVE`
- `PLAN_READY`
- `COMPLETED`

## Transition Table

| From | To | Required condition |
| --- | --- | --- |
| `DRAFT` | `RESUME_READY` | User has confirmed parsed or pasted resume text for the active resume. |
| `RESUME_READY` | `PROFILE_CONFIRMED` | User has reviewed, corrected if needed, and confirmed the CareerProfile. |
| `PROFILE_CONFIRMED` | `OPPORTUNITY_CONFIRMED` | User has provided required JD and role family, and confirmed opportunity/company context. |
| `OPPORTUNITY_CONFIRMED` | `EVIDENCE_REVIEW` | Evidence candidates have been extracted or manual highlights added for user review. |
| `EVIDENCE_REVIEW` | `EVIDENCE_APPROVED` | Evidence threshold is met by user-approved cards. |
| `EVIDENCE_APPROVED` | `STORIES_READY` | Reusable stories have been generated from approved evidence only. |
| `STORIES_READY` | `MATCHING_READY` | Story matches have been generated against the confirmed opportunity. |
| `MATCHING_READY` | `PREVIEW_READY` | Free preview has been generated from matching results and approved inputs. |
| `PREVIEW_READY` | `PAYMENT_PENDING` | Razorpay order exists for the Sprint and expected amount/currency. |
| `PAYMENT_PENDING` | `PAID` | Verified Razorpay webhook confirms successful payment for the correct order and amount. |
| `PAID` | `PREPKIT_READY` | Prep Kit generation has succeeded for the paid Sprint and current input revision. |
| `PREPKIT_READY` | `PRACTICE_ACTIVE` | User has started or completed at least one text practice attempt. |
| `PRACTICE_ACTIVE` | `PLAN_READY` | Seven-day improvement plan has been generated from current Sprint inputs. |
| `PLAN_READY` | `COMPLETED` | User has completed the plan or explicitly marks the Sprint complete. |

## Centralized State Rules

- All transitions must go through one workflow service.
- State writes must be transactional.
- AI output cannot transition state.
- Users cannot skip required approval stages.
- Invalid transitions fail safely and preserve prior work.
- Repeated requests must be idempotent.
- Upstream edits mark downstream outputs stale instead of deleting them automatically.

## Evidence Threshold

The transition from `EVIDENCE_REVIEW` to `EVIDENCE_APPROVED` requires:

- At least three approved evidence cards.
- At least two approved evidence cards with clear results.
- Source excerpt/provenance on every approved card.
- Metrics sourced from resume text or user correction.

## Stale Output Table

| Upstream edit | Mark stale |
| --- | --- |
| Resume replacement or confirmed resume text edit | Profile draft, evidence, stories, matches, preview, Prep Kit, practice recommendations, plan. |
| Profile edit | Evidence, stories, matches, preview, Prep Kit, practice recommendations, plan. |
| Opportunity, JD, role family, company context, stage, or concerns edit | Matches, preview, Prep Kit, question bank, practice priorities, plan. |
| Evidence approval, rejection, or edit | Stories, matches, preview, Prep Kit, practice priorities, plan. |
| Story edit | Matches, preview, Prep Kit, practice priorities, plan. |
| Interview date edit | Seven-day plan timing and final review tasks. |

## Forbidden Transitions

- `DRAFT` → `PROFILE_CONFIRMED`.
- `RESUME_READY` → `OPPORTUNITY_CONFIRMED`.
- `PROFILE_CONFIRMED` → `EVIDENCE_APPROVED`.
- `EVIDENCE_REVIEW` → `STORIES_READY`.
- `PREVIEW_READY` → `PAID`.
- `PAYMENT_PENDING` → `PREPKIT_READY`.
- Any transition to `PAID` without a verified webhook.
- Any transition made by AI output.
