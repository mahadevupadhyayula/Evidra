# Core User Flow

## Purpose

This document defines the MBP user journey only. The source-of-truth loop is:

Resume → Profile → Opportunity Context → Approved Evidence → Reusable Stories → Contextual Matching → Free Preview → Payment → Prep Kit → Text Practice → Seven-Day Plan

## 1. Resume

- **User goal:** Provide career source material by uploading a PDF/DOCX resume or pasting resume text.
- **System output:** Extracted or pasted resume text shown for review and correction.
- **Required behaviour:** Validate file type, MIME, and size; store uploaded files privately; parse text without OCR; never send binaries to AI; allow paste fallback; keep one active resume.
- **Exit condition:** User confirms reviewed resume text and the Sprint can move to `RESUME_READY`.

## 2. Profile

- **User goal:** Convert the confirmed resume into an accurate career profile.
- **System output:** Draft profile containing name, current role, current company, years of experience, functional areas, industries, skills, tools, education summary, career summary, and positioning summary.
- **Required behaviour:** Use confirmed resume text only; avoid demographic or sensitive inference; allow user correction; preserve user-confirmed values as source of truth.
- **Exit condition:** User confirms the profile and the Sprint can move to `PROFILE_CONFIRMED`.

## 3. Opportunity Context

- **User goal:** Tell Evidra what interview or role the Sprint should target.
- **System output:** Confirmable opportunity context including JD analysis, role family, seniority, company context, interview stage/date, concerns, and goals.
- **Required behaviour:** Require JD and role family; treat user-selected role family as authoritative; fetch at most one safe user-supplied public company/product URL or use pasted context; block unsafe URLs; perform no broad web research.
- **Exit condition:** User confirms opportunity context and the Sprint can move to `OPPORTUNITY_CONFIRMED`.

## 4. Approved Evidence

- **User goal:** Review and approve career evidence that can support interview answers.
- **System output:** Evidence cards extracted from resume content and manual highlights, each with provenance and missing-detail prompts.
- **Required behaviour:** AI can propose evidence but cannot approve it; every card needs a source excerpt; metrics must come from source text or user correction; rejected or unapproved cards are excluded downstream.
- **Exit condition:** At least three evidence cards are approved, with at least two having clear results, and the Sprint can move through `EVIDENCE_REVIEW` to `EVIDENCE_APPROVED`.

## 5. Reusable Stories

- **User goal:** Receive reusable interview stories grounded in approved evidence.
- **System output:** Up to five to seven STAR/CAR-style stories with short, medium, and detailed answers, competency tags, seniority signals, evidence references, and quality scores.
- **Required behaviour:** Use approved evidence only; avoid unsupported metrics; preserve user edits; do not overwrite edited stories during regeneration.
- **Exit condition:** A usable set of reusable stories exists and the Sprint can move to `STORIES_READY`.

## 6. Contextual Matching

- **User goal:** Understand which stories best fit the target role and interview context.
- **System output:** Story matches against competencies, JD excerpts, role pack, seniority, evidence strength, company/product context, and interview stage.
- **Required behaviour:** AI may provide component scores; Python calculates final weighted score; low-fit stories are not labelled strong; gaps are explicit; user override is stored.
- **Exit condition:** Matches and gaps are generated and the Sprint can move to `MATCHING_READY`.

## 7. Free Preview

- **User goal:** See enough value to understand readiness and decide whether to buy the Prep Kit.
- **System output:** Role summary, five competencies, three strengths, three gaps, evidence completeness, story coverage, one matched-story excerpt, and a paid Prep Kit explanation.
- **Required behaviour:** Preview is useful but incomplete; do not show offer probability; payment gates only the Prep Kit, not user-owned profile, evidence, or stories.
- **Exit condition:** Preview is ready and the Sprint can move to `PREVIEW_READY`.

## 8. Payment

- **User goal:** Pay for the Interview Sprint Prep Kit.
- **System output:** Razorpay order/payment experience and payment status feedback.
- **Required behaviour:** Browser redirects do not unlock access; only verified Razorpay webhooks can mark payment paid; validate signature, amount, order, and idempotency; failed payment preserves work.
- **Exit condition:** A verified webhook marks payment `PAID` and the Sprint can move from `PAYMENT_PENDING` to `PAID`.

## 9. Prep Kit

- **User goal:** Receive a role-specific interview preparation kit.
- **System output:** Role/company briefing, fit summary, competency coverage, story map, question bank, recommended story per question, concern map, missing evidence, practice priorities, seven-day plan, and checklist.
- **Required behaviour:** Require verified payment; ground outputs in approved inputs; avoid unsupported metrics and guaranteed outcomes; maintain one active Prep Kit; preserve paid entitlement if generation fails.
- **Exit condition:** Prep Kit is generated successfully and the Sprint can move to `PREPKIT_READY`.

## 10. Text Practice

- **User goal:** Practise a priority interview question in text.
- **System output:** Scores for relevance, structure, specificity, ownership, impact, and clarity; strengths; improvements; improved answer; follow-up question; unsupported claims.
- **Required behaviour:** Text only; append-only attempts; improved answers cannot invent facts; do not evaluate accent, appearance, or demographics.
- **Exit condition:** At least one practice attempt exists and the Sprint can move to `PRACTICE_ACTIVE`.

## 11. Seven-Day Plan

- **User goal:** Follow a practical daily plan before the interview.
- **System output:** Traceable tasks for evidence strengthening, story improvement, practice, company research, and final review.
- **Required behaviour:** Use a Python rule-based plan engine; AI may phrase tasks only; no generic “be confident” tasks; max two major tasks/day; 20–45 minutes/day; preserve completed tasks; final day is review-focused.
- **Exit condition:** Plan is created and the Sprint can move to `PLAN_READY`; user completion can later move the Sprint to `COMPLETED`.

## Flow-Wide Rules

- No cross-user access.
- AI cannot transition workflow state.
- AI cannot approve evidence.
- AI cannot set payment status.
- AI cannot grant access.
- Upstream edits mark downstream outputs stale.
- Stale paid artifacts are not deleted automatically.
- Failed AI calls preserve prior work.
- External services are mocked in automated tests.
