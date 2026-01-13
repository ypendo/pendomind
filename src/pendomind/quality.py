"""Quality scoring system for PendoMind knowledge entries."""

from dataclasses import dataclass, field

from pendomind.config import PendoMindConfig


@dataclass
class QualityAnalysis:
    """Result of quality analysis for a knowledge entry."""

    relevance_score: float
    completeness_score: float
    credibility_score: float
    composite_score: float
    relevance_details: str
    completeness_details: str
    recommendations: list[str] = field(default_factory=list)


class QualityScorer:
    """Multi-factor quality assessment for engineering knowledge.

    Calculates a composite quality score based on:
    - Relevance (40%): How relevant is the content to engineering domain
    - Completeness (35%): Does it have problem, cause, solution structure
    - Credibility (25%): How reliable is the source
    """

    # Scoring weights
    WEIGHTS = {
        "relevance": 0.40,
        "completeness": 0.35,
        "credibility": 0.25,
    }

    # Source credibility rankings
    SOURCE_CREDIBILITY = {
        "github": 0.95,
        "confluence": 0.85,
        "jira": 0.80,
        "claude_session": 0.70,
        "slack": 0.60,
    }
    DEFAULT_CREDIBILITY = 0.50

    # Domain keywords for relevance scoring
    HIGH_RELEVANCE_KEYWORDS = [
        "bug",
        "fix",
        "error",
        "exception",
        "stack trace",
        "traceback",
        "implementation",
        "feature",
        "refactor",
        "optimization",
        "incident",
        "outage",
        "rca",
        "root cause",
        "architecture",
        "design",
        "pattern",
        "service",
        "api",
        "database",
        "performance",
    ]

    MEDIUM_RELEVANCE_KEYWORDS = [
        "configuration",
        "deploy",
        "test",
        "review",
        "documentation",
        "setup",
        "migration",
        "update",
        "change",
    ]

    # Structure markers for completeness
    STRUCTURE_MARKERS = {
        "problem": ["problem", "issue", "error", "bug", "symptom", "failing"],
        "cause": ["cause", "reason", "because", "due to", "root cause", "rca"],
        "solution": [
            "solution",
            "fix",
            "resolved",
            "fixed by",
            "workaround",
            "fixed",
        ],
        "context": ["context", "background", "when", "environment", "version", "affect"],
    }

    # Actionable markers for completeness
    ACTIONABLE_MARKERS = [
        "step",
        "1.",
        "2.",
        "3.",
        "first",
        "then",
        "finally",
        "run",
        "execute",
        "add",
        "remove",
        "change",
        "update",
        "```",  # Code examples
    ]

    def __init__(self, config: PendoMindConfig | None = None):
        """Initialize scorer with optional config."""
        self.config = config or PendoMindConfig()

    async def calculate_relevance(
        self, content: str, type_name: str
    ) -> tuple[float, str]:
        """Calculate relevance score for content.

        Args:
            content: The knowledge content
            type_name: Knowledge type (bug, feature, etc.)

        Returns:
            Tuple of (score 0-1, explanation string)
        """
        score = 0.0
        factors = []
        content_lower = content.lower()

        # Keyword density (0-0.4)
        high_matches = sum(
            1 for kw in self.HIGH_RELEVANCE_KEYWORDS if kw.lower() in content_lower
        )
        medium_matches = sum(
            1 for kw in self.MEDIUM_RELEVANCE_KEYWORDS if kw.lower() in content_lower
        )

        keyword_score = min(high_matches * 0.08 + medium_matches * 0.04, 0.4)
        score += keyword_score
        if high_matches > 0:
            factors.append(f"Found {high_matches} high-relevance keywords")
        if medium_matches > 0:
            factors.append(f"Found {medium_matches} medium-relevance keywords")

        # Code/technical content detection (0-0.3)
        has_code_block = "```" in content or "    " in content
        has_stack_trace = "traceback" in content_lower or "at " in content_lower
        has_error_pattern = any(
            p in content_lower for p in ["error:", "exception:", "fatal", "error "]
        )

        technical_score = 0.0
        if has_code_block:
            technical_score += 0.15
            factors.append("Contains code blocks")
        if has_stack_trace:
            technical_score += 0.10
            factors.append("Contains stack trace")
        if has_error_pattern:
            technical_score += 0.05
            factors.append("Contains error patterns")
        score += technical_score

        # Type-specific bonus (0-0.3)
        type_bonus = self._get_type_bonus(content_lower, type_name)
        score += type_bonus
        if type_bonus > 0.1:
            factors.append(f"Type-specific content detected for {type_name}")

        return min(score, 1.0), "; ".join(factors) if factors else "No relevant signals"

    def _get_type_bonus(self, content_lower: str, type_name: str) -> float:
        """Calculate type-specific relevance bonus."""
        bonuses = {
            "bug": 0.2
            if any(kw in content_lower for kw in ["error", "traceback", "fix"])
            else 0.1,
            "feature": 0.2
            if any(kw in content_lower for kw in ["implement", "```", "feature"])
            else 0.1,
            "incident": 0.25
            if any(kw in content_lower for kw in ["rca", "root cause", "timeline"])
            else 0.1,
            "debugging": 0.2
            if any(kw in content_lower for kw in ["traceback", "debug", "stack"])
            else 0.1,
            "architecture": 0.2
            if any(kw in content_lower for kw in ["diagram", "service", "component"])
            else 0.1,
            "error": 0.25
            if any(kw in content_lower for kw in ["error:", "exception", "fatal"])
            else 0.1,
        }
        return bonuses.get(type_name, 0.1)

    async def calculate_completeness(
        self, content: str, type_name: str
    ) -> tuple[float, str]:
        """Calculate completeness score for content.

        Args:
            content: The knowledge content
            type_name: Knowledge type

        Returns:
            Tuple of (score 0-1, explanation string)
        """
        score = 0.0
        present = []
        missing = []
        content_lower = content.lower()

        # Length check (0-0.25)
        word_count = len(content.split())
        if word_count < 20:
            score += 0.05
            missing.append("Very short content (<20 words)")
        elif word_count < 50:
            score += 0.15
            missing.append("Brief content (20-50 words)")
        elif word_count < 150:
            score += 0.20
            present.append("Moderate detail (50-150 words)")
        else:
            score += 0.25
            present.append("Detailed content (150+ words)")

        # Structure check (0-0.35)
        sections_found = 0
        for section, markers in self.STRUCTURE_MARKERS.items():
            if any(m.lower() in content_lower for m in markers):
                sections_found += 1
                present.append(f"Has {section}")
            else:
                missing.append(f"Missing {section}")

        structure_score = sections_found * 0.0875  # 0.35 / 4 sections
        score += structure_score

        # Actionability check (0-0.40)
        actionable_count = sum(
            1 for m in self.ACTIONABLE_MARKERS if m.lower() in content_lower
        )
        actionable_score = min(actionable_count * 0.08, 0.40)
        score += actionable_score

        if actionable_count > 0:
            present.append(f"Contains {actionable_count} actionable elements")
        else:
            missing.append("No actionable steps found")

        explanation = f"Present: {', '.join(present)}. Missing: {', '.join(missing)}"
        return min(score, 1.0), explanation

    async def calculate_credibility(self, source: str) -> tuple[float, str]:
        """Calculate credibility score for a source.

        Args:
            source: Source name (github, confluence, etc.)

        Returns:
            Tuple of (score 0-1, explanation string)
        """
        score = self.SOURCE_CREDIBILITY.get(source, self.DEFAULT_CREDIBILITY)

        explanations = {
            "github": "High credibility: GitHub PRs/issues have code context and review",
            "confluence": "Good credibility: Documented and reviewed content",
            "jira": "Good credibility: Structured ticket with context",
            "slack": "Lower credibility: Conversational, may lack full context",
            "claude_session": "Moderate credibility: AI-assisted, should be verified",
        }

        return score, explanations.get(source, f"Unknown source ({source})")

    async def score(
        self, content: str, type_name: str, source: str
    ) -> QualityAnalysis:
        """Calculate composite quality score with recommendations.

        Args:
            content: The knowledge content to score
            type_name: Knowledge type (bug, feature, etc.)
            source: Source of the content (github, slack, etc.)

        Returns:
            QualityAnalysis with all scores and recommendations
        """
        relevance, rel_details = await self.calculate_relevance(content, type_name)
        completeness, comp_details = await self.calculate_completeness(
            content, type_name
        )
        credibility, cred_details = await self.calculate_credibility(source)

        composite = (
            relevance * self.WEIGHTS["relevance"]
            + completeness * self.WEIGHTS["completeness"]
            + credibility * self.WEIGHTS["credibility"]
        )

        # Generate recommendations
        recommendations = []
        if relevance < 0.6:
            recommendations.append(
                "Add more technical details (code, error messages, stack traces)"
            )
        if completeness < 0.6:
            recommendations.append("Include problem, cause, and solution sections")
        if credibility < 0.7:
            recommendations.append(
                "Consider adding references to GitHub PRs or documentation"
            )
        if len(content.split()) < 50:
            recommendations.append("Expand content with more context and details")

        return QualityAnalysis(
            relevance_score=round(relevance, 2),
            completeness_score=round(completeness, 2),
            credibility_score=round(credibility, 2),
            composite_score=round(composite, 2),
            relevance_details=rel_details,
            completeness_details=comp_details,
            recommendations=recommendations,
        )
