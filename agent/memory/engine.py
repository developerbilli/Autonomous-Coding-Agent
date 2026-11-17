"""Unified Memory Engine coordinating Long-Term Semantic and Episodic Memory."""

import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from agent.memory.models import Episode, SemanticPattern, MemoryQuery
from agent.memory.episodic_memory import EpisodicMemoryStore
from agent.memory.semantic_memory import SemanticMemoryStore


class MemoryEngine:
    """Central engine providing unified episodic remediation recall and semantic rule retrieval."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            default_path = repo_root / ".checkpoints" / "long_term_memory.sqlite"
            db_path = str(default_path)

        self.db_path = str(Path(db_path).resolve())
        self.episodic_store = EpisodicMemoryStore(self.db_path)
        self.semantic_store = SemanticMemoryStore(self.db_path)

    def recall_context_for_task(
        self,
        task: str,
        repo_identifier: Optional[str] = None,
        error_signature: Optional[str] = None,
        episode_limit: int = 3,
        pattern_limit: int = 3,
        include_anti_patterns: bool = True,
        strict_repo_scoping: bool = True,
    ) -> Dict[str, Any]:
        """Recalls episodic remediations, anti-pattern warnings, and semantic rules under retention governance."""
        # 1. Query episodic memory for active, proven remediations
        query = MemoryQuery(
            query_text=task,
            repo_identifier=repo_identifier,
            error_signature=error_signature,
            limit=episode_limit,
            include_anti_patterns=include_anti_patterns,
            strict_repo_scoping=strict_repo_scoping,
        )
        episodes = self.episodic_store.recall_episodes(query)

        # 2. Query episodic memory for known anti-patterns (failed strategies to AVOID)
        anti_patterns: List[Episode] = []
        if include_anti_patterns:
            anti_patterns = self.episodic_store.recall_anti_patterns(query)

        # 3. Query semantic memory for validated architectural patterns
        search_query = f"{task} {error_signature or ''}".strip()
        patterns = self.semantic_store.recall_patterns(
            query=search_query,
            repo_identifier=repo_identifier,
            limit=pattern_limit,
        )

        # 4. Format structured summary for agent prompts
        guidance_lines = []
        if episodes:
            guidance_lines.append("### Recalled Past Episodes & Successful Fixes:")
            for ep in episodes:
                guidance_lines.append(f"- **Task**: {ep.task_description}")
                if ep.remediation_strategy:
                    guidance_lines.append(f"  **Proven Remediation**: {ep.remediation_strategy}")
                guidance_lines.append(f"  **Files Modified**: {', '.join(ep.files_modified)}")
                if ep.scope != "global":
                    guidance_lines.append(f"  **Repository Scope**: {ep.repo_identifier}")

        if anti_patterns:
            guidance_lines.append("\n### ⚠️ Known Anti-Patterns & Failed Strategies (DO NOT REPEAT):")
            for ap in anti_patterns:
                fail_desc = ap.failure_reason or ap.remediation_strategy or "Previous approach failed test validation"
                guidance_lines.append(f"- **Warning**: Avoid `{fail_desc}` (Failed in `{ap.repo_identifier}`)")

        if patterns:
            guidance_lines.append("\n### Reusable Architectural & Coding Patterns:")
            for pat in patterns:
                guidance_lines.append(f"- **{pat.title}** ({pat.topic}):")
                guidance_lines.append(f"  {pat.content}")

        return {
            "recalled_episodes": [ep.model_dump() for ep in episodes],
            "recalled_anti_patterns": [ap.model_dump() for ap in anti_patterns],
            "recalled_patterns": [pat.model_dump() for pat in patterns],
            "guidance_summary": "\n".join(guidance_lines) if guidance_lines else "No historical memories found.",
            "total_recalled": len(episodes) + len(patterns) + len(anti_patterns),
        }

    def record_episode_from_state(self, state: Dict[str, Any]) -> Optional[Episode]:
        """Records an episode from completed workflow state with retention and anti-pattern categorization."""
        try:
            task = state.get("task", "")
            if not task:
                return None

            thread_id = state.get("thread_id", f"thread-{int(time.time())}")
            repo_path = state.get("repo_path", "")
            repo_name = Path(repo_path).name if repo_path else "repo"

            # Check outcome
            test_results = state.get("test_results")
            test_passed = bool(test_results and test_results.passed)
            review_result = state.get("review_result")
            q_score = getattr(review_result, "quality_score", None) or getattr(review_result, "overall_score", None)
            review_score = float(q_score) if q_score is not None else (1.0 if test_passed else 0.5)

            # Error signatures
            error_sigs = []
            if test_results and test_results.error_summary:
                error_sigs.append(test_results.error_summary)
            if state.get("error_history"):
                error_sigs.extend([str(e) for e in state["error_history"][-3:]])

            # Remediation strategy
            remediation = None
            if state.get("debug_result"):
                remediation = state["debug_result"].remediation_plan
            elif state.get("manager_plan"):
                remediation = state["manager_plan"].strategy

            coder_res = state.get("coder_result")
            files_modified = coder_res.files_modified if coder_res else list(state.get("proposed_patches", {}).keys())

            # Determine retention scope: generic coding patterns vs repository-specific facts
            is_generic = any(kw in task.lower() for kw in ("zerodivision", "typeerror", "valueerror", "overflow", "syntax", "jwt", "auth"))
            scope = "global" if (is_generic and test_passed and review_score >= 9.0) else "repository"

            # Failure metadata for anti-pattern tracking
            failure_reason = None
            if not test_passed:
                failure_reason = (test_results.error_summary if test_results else None) or "Tests failed during verification"

            episode = Episode(
                episode_id=f"ep_{thread_id}_{int(time.time())}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                thread_id=thread_id,
                repo_identifier=repo_name,
                task_description=task,
                task_type="bug_fix" if ("fix" in task.lower() or "bug" in task.lower()) else "feature",
                error_signatures=error_sigs,
                remediation_strategy=remediation,
                files_modified=files_modified,
                test_passed=test_passed,
                review_score=review_score,
                outcome="success" if test_passed else "failed",
                status="active",
                scope=scope,
                is_anti_pattern=not test_passed,
                failure_reason=failure_reason,
                validation_count=1,
                metadata={"iterations": state.get("iteration_count", 0)},
            )

            self.episodic_store.record_episode(episode)
            return episode
        except Exception:
            return None

    def promote_validated_episode(
        self,
        episode_id: str,
        topic: str,
        title: str,
        content: str,
        tags: List[str],
    ) -> Optional[SemanticPattern]:
        """Promotes an episodic remediation into a permanent semantic pattern after validation."""
        pattern = self.semantic_store.promote_from_episode(
            episode_id=episode_id,
            title=title,
            content=content,
            topic=topic,
            tags=tags,
            confidence=0.95,
            scope="global",
        )
        return pattern


_GLOBAL_MEMORY_ENGINE: Optional[MemoryEngine] = None


def get_memory_engine(db_path: Optional[str] = None) -> MemoryEngine:
    """Returns singleton instance of MemoryEngine."""
    global _GLOBAL_MEMORY_ENGINE
    if _GLOBAL_MEMORY_ENGINE is None or db_path is not None:
        _GLOBAL_MEMORY_ENGINE = MemoryEngine(db_path)
    return _GLOBAL_MEMORY_ENGINE
