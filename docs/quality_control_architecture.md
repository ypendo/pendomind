Think of PendoMind as a picky librarian for engineering knowledge. Not everything gets stored — the system filters out low-quality or dangerous content automatically.

  ---
  The Three-Zone System (Thresholds)

  Score 0.0 ────────── 0.65 ────────── 0.85 ────────── 1.0
             ❌ REJECT      ⏳ PENDING       ✅ AUTO-APPROVE
  Zone: Reject
  Score Range: < 0.65
  What Happens: Garbage in, garbage out. Vague or incomplete content is rejected immediately.
  ────────────────────────────────────────
  Zone: Pending
  Score Range: 0.65 - 0.85
  What Happens: "Not sure" zone. The user must explicitly confirm with confirm_knowledge().
  ────────────────────────────────────────
  Zone: Auto-approve
  Score Range: > 0.85
  What Happens: High-quality content goes straight to storage. No human intervention needed.
  Why 0.65 and 0.85?
  - 0.65 is low enough to catch most useful content but filters out one-liners like "fixed the bug"
  - 0.85 is high enough that auto-approved content is almost always genuinely valuable

  ---
  How Quality Score is Calculated

  Three factors, weighted by importance:

  Final Score = (Relevance × 0.40) + (Completeness × 0.35) + (Credibility × 0.25)
  ┌──────────────┬────────┬─────────────────────────────────────────────────────────────────────────────────┐
  │    Factor    │ Weight │                                What It Measures                                 │
  ├──────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Relevance    │ 40%    │ Does it contain engineering keywords like "bug", "fix", "error", "stack trace"? │
  ├──────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Completeness │ 35%    │ Does it have enough structure? Problem + solution + context?                    │
  ├──────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Credibility  │ 25%    │ Where did it come from? GitHub PRs are trusted more than Slack messages.        │
  └──────────────┴────────┴─────────────────────────────────────────────────────────────────────────────────┘
  Why these weights?
  - Relevance is highest because irrelevant content is useless no matter how well-written
  - Completeness matters because "fixed auth" without context helps no one later
  - Credibility is lowest because even Slack can contain gold, and even GitHub PRs can be junk

  ---
  Source Credibility (Trust Hierarchy)

  GitHub (0.95) > Confluence (0.85) > Jira (0.80) > Claude Session (0.70) > Slack (0.60)

  The reasoning:
  - GitHub (0.95): Code-reviewed, has diffs and context attached
  - Confluence (0.85): Usually reviewed documentation
  - Jira (0.80): Structured tickets, but quality varies
  - Claude Session (0.70): AI-assisted discovery — useful but should be verified
  - Slack (0.60): Conversational, often missing context ("yeah that fixed it" — fixed what?!)

  ---
  Type-Specific Overrides

  Not all knowledge types are created equal:
  Type: incident
  Threshold: 0.60 (lenient)
  Why?: During an outage, you need to capture info fast. Polished prose can wait.
  ────────────────────────────────────────
  Type: investigation
  Threshold: 0.60 (lenient)
  Why?: Exploratory findings are inherently rough — that's OK.
  ────────────────────────────────────────
  Type: architecture
  Threshold: 0.75 (strict)
  Why?: Architecture docs live forever and guide decisions. Quality matters more.
  ---
  Security Filtering (Excluded Patterns)

  Immediate rejection if content contains:
  password, api_key, api-key, secret, token, credential, private_key, private-key

  Why? You never want secrets stored in a knowledge base that gets searched and surfaced. This is a hard security boundary.

  ---
  The Pending System

  When content scores between 0.65-0.85, it goes to "pending":

  - TTL: 30 minutes — if you don't confirm, it expires and disappears
  - Cleanup every 60 seconds — expired entries are purged automatically

  Why 30 minutes?
  - Long enough to finish your current task and confirm
  - Short enough that forgotten entries don't pile up forever

  ---
  Visual Summary

                          ┌─────────────────────┐
                          │  remember_knowledge │
                          └──────────┬──────────┘
                                     │
                      ┌──────────────▼──────────────┐
                      │      Content Validation      │
                      │  • Has secrets? → REJECT     │
                      │  • Too short/long? → REJECT  │
                      │  • Invalid type? → REJECT    │
                      └──────────────┬──────────────┘
                                     │
                      ┌──────────────▼──────────────┐
                      │       Quality Scoring        │
                      │  relevance × 0.40            │
                      │  completeness × 0.35         │
                      │  credibility × 0.25          │
                      └──────────────┬──────────────┘
                                     │
                ┌────────────────────┼────────────────────┐
                │                    │                    │
           score < 0.65        0.65-0.85           score > 0.85
                │                    │                    │
                ▼                    ▼                    ▼
           ❌ REJECT           ⏳ PENDING           ✅ STORED
                                     │
                            ┌────────▼────────┐
                            │ confirm_knowledge│
                            │  approve=true?   │
                            └────────┬────────┘
                                     │
                        ┌────────────┴────────────┐
                        │                         │
                     approved                  rejected
                        │                         │
                        ▼                         ▼
                   ✅ STORED                  🗑️ DISCARDED

  ★ Insight ─────────────────────────────────────
  Why have quality control at all? Knowledge bases suffer from the "garbage in, garbage out" problem. Without filtering:
  1. Search results get polluted with noise
  2. Engineers lose trust and stop using the system
  3. The vector database grows with useless embeddings

  The three-zone system balances automation (high-quality goes straight in) with human judgment (borderline cases get reviewed) while rejecting obvious junk automatically.