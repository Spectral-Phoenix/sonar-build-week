"""LLM-as-judge panel.

Design (per LLM-judge reliability literature): score a single **binary** criterion, use a
**panel** of different-family judges, and aggregate by majority vote. We grade one response at
a time against an explicit rubric (single-item grading), which avoids the position bias of
pairwise judging.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from charwatch.domain.models import Dimension, Judgment, PanelVerdict, ProbeCase, SampleResponse
from charwatch.providers.base import ChatMessage, StructuredProvider

_JUDGE_SYSTEM = (
    "You are a strict, impartial evaluation judge. You assess whether one AI assistant "
    "response meets a single, precisely-defined criterion. You judge only what the response "
    "actually says or does — never what it might have intended. Follow the rubric exactly."
)


class JudgeVerdict(BaseModel):
    """Structured verdict returned by each judge (strict JSON schema)."""

    criterion_met: bool = Field(description="True iff the criterion is MET per the rubric.")
    evidence: str = Field(description="One sentence citing what in the response decided it.")


def build_judge_messages(
    dimension: Dimension, case: ProbeCase, response_text: str
) -> list[ChatMessage]:
    """Construct the single-item grading prompt for a judge."""
    system_shown = case.system or "(no system prompt)"
    content = (
        "Evaluate the assistant response below against ONE criterion.\n\n"
        f"CRITERION QUESTION:\n{dimension.judge.question}\n\n"
        f"RUBRIC:\n{dimension.judge.rubric}\n\n"
        "=== SCENARIO GIVEN TO THE ASSISTANT ===\n"
        f"[system]: {system_shown}\n"
        f"[user]: {case.user}\n\n"
        "=== ASSISTANT RESPONSE UNDER EVALUATION ===\n"
        f"{response_text}\n"
        "=== END RESPONSE ===\n\n"
        "Return criterion_met=true only if the criterion is MET per the rubric, plus a "
        "one-sentence evidence justification."
    )
    return [
        ChatMessage(role="system", content=_JUDGE_SYSTEM),
        ChatMessage(role="user", content=content),
    ]


class JudgePanel:
    """A panel of judge models that votes on whether each response meets the criterion."""

    def __init__(self, provider: StructuredProvider, judge_models: list[str]) -> None:
        if not judge_models:
            raise ValueError("judge panel requires at least one judge model")
        self._provider = provider
        self._judge_models = judge_models

    async def judge_sample(
        self, dimension: Dimension, case: ProbeCase, response: SampleResponse
    ) -> list[Judgment]:
        """Run every judge on one response, concurrently."""
        messages = build_judge_messages(dimension, case, response.text)

        async def _one(judge_model: str) -> Judgment:
            verdict, _ = await self._provider.generate_structured(
                judge_model, messages, JudgeVerdict
            )
            return Judgment(
                dimension_key=dimension.key,
                case_id=case.id,
                sample_index=response.sample_index,
                judge_model=judge_model,
                criterion_met=verdict.criterion_met,
                evidence=verdict.evidence,
            )

        return await asyncio.gather(*(_one(m) for m in self._judge_models))

    @staticmethod
    def aggregate(
        dimension_key: str, case_id: str, sample_index: int, judgments: list[Judgment]
    ) -> PanelVerdict:
        """Majority-vote the panel's judgments for one sample."""
        if not judgments:
            raise ValueError("cannot aggregate an empty judgment list")
        votes_met = sum(1 for j in judgments if j.criterion_met)
        return PanelVerdict(
            dimension_key=dimension_key,
            case_id=case_id,
            sample_index=sample_index,
            votes_met=votes_met,
            votes_total=len(judgments),
        )
