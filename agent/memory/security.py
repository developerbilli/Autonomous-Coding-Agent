"""Dedicated Memory Security Boundary between Memory Retrieval and Prompt Construction.

Acts as an application-level firewall that inspects, sanitizes, validates,
and quarantines retrieved memories before they can enter agent prompt contexts.
"""

import hashlib
import json
import logging
import re
from typing import Dict, Any, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from agent.memory.models import Episode, SemanticPattern, UntrustedMemoryItem, StructuredMemoryPayload

logger = logging.getLogger("agent.memory.security")


class SecurityViolation(BaseModel):
    """Audit record of a security violation detected in retrieved memory."""
    item_id: str
    item_type: str  # "episode", "anti_pattern", "pattern"
    violation_type: str  # "prompt_injection", "malicious_payload", "scope_violation", "oversized"
    details: str
    action_taken: str  # "quarantined", "sanitized", "truncated"


class MemoryAuditReport(BaseModel):
    """Comprehensive audit report produced by the Memory Security Boundary."""
    total_inspected: int = 0
    total_approved: int = 0
    total_quarantined: int = 0
    total_sanitized: int = 0
    violations: List[SecurityViolation] = Field(default_factory=list)


# High-severity threats: Any memory containing these patterns is immediately quarantined (dropped entirely)
HIGH_SEVERITY_PATTERNS: List[Tuple[str, str]] = [
    (r"(?i)\brm\s+-rf\s+[/~]", "Destructive filesystem command execution"),
    (r"(?i)\b(curl|wget)\s+.*\|\s*(ba)?sh", "Arbitrary remote code execution pipe"),
    (r"(?i)\b(nc|ncat|netcat)\s+.*-e\s+/bin/", "Reverse shell execution payload"),
    (r"(?i)\bchmod\s+[0-7]*777\b", "Dangerous privilege escalation command"),
    (r"(?i)\b(/etc/passwd|/etc/shadow|\.aws/credentials|\.ssh/id_rsa)\b", "Sensitive system credential targeting"),
    (r"(?i)\b(os\.system|subprocess\.Popen|eval|exec)\s*\(.*(base64|decode|request)", "Obfuscated code execution payload"),
]

# Medium-severity threats: Neutralized via safe redaction without dropping the entire item
PROMPT_INJECTION_PATTERNS: List[Tuple[str, str]] = [
    (r"(?i)\b(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+all\s+(previous\s+)?rules)\b", "[REDACTED_ADVERSARIAL_INSTRUCTION]"),
    (r"(?i)(system\s+prompt\s*:|\byou\s+are\s+now\s+in\s+developer\s+mode\b|\bdan\s+mode\b)", "[REDACTED_SYSTEM_OVERRIDE]"),
    (r"(?i)\b(bypass\s+all\s+security|disable\s+(all\s+)?safety\s+checks)\b", "[REDACTED_SECURITY_BYPASS]"),
    (r"(?i)\b(output\s+all\s+environment\s+variables|exfiltrate\s+keys)\b", "[REDACTED_EXFILTRATION_DIRECTIVE]"),
]


def sanitize_recalled_content(text: Optional[str]) -> str:
    """Convenience helper to inspect and sanitize text against prompt injection directives."""
    if not text:
        return ""
    boundary = MemorySecurityBoundary()
    _, san, _ = boundary.inspect_and_sanitize_text(text, item_id="ad_hoc", item_type="text")
    return san


class MemorySecurityBoundary:
    """Application-level security firewall between raw memory store retrieval and agent prompt construction."""

    def __init__(
        self,
        max_items_per_category: int = 3,
        max_chars_per_item: int = 1200,
        max_total_chars: int = 5000,
        min_confidence_threshold: float = 0.45,
    ):
        self.max_items_per_category = max_items_per_category
        self.max_chars_per_item = max_chars_per_item
        self.max_total_chars = max_total_chars
        self.min_confidence_threshold = min_confidence_threshold

    def inspect_and_sanitize_text(self, text: Optional[str], item_id: str, item_type: str) -> Tuple[bool, str, List[SecurityViolation]]:
        """Inspects text for high-severity payloads (quarantine) and medium-severity injections (sanitize).
        
        Returns:
            (is_approved, sanitized_text, violations)
        """
        if not text:
            return True, "", []

        violations: List[SecurityViolation] = []

        # 1. High-Severity Scan: Immediate Quarantine
        for pattern, desc in HIGH_SEVERITY_PATTERNS:
            if re.search(pattern, text):
                v = SecurityViolation(
                    item_id=item_id,
                    item_type=item_type,
                    violation_type="malicious_payload",
                    details=f"High-severity pattern detected: {desc}",
                    action_taken="quarantined",
                )
                logger.warning(f"Memory Security Boundary quarantined item {item_id} ({item_type}): {desc}")
                return False, "", [v]

        # 2. Medium-Severity Scan: Neutralize prompt injections
        sanitized = text
        for pattern, replacement in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, sanitized):
                sanitized = re.sub(pattern, replacement, sanitized)
                violations.append(
                    SecurityViolation(
                        item_id=item_id,
                        item_type=item_type,
                        violation_type="prompt_injection",
                        details=f"Prompt injection directive neutralized with {replacement}",
                        action_taken="sanitized",
                    )
                )

        # 3. Delimiter Breakout Protection: Neutralize unclosed code fences & XML boundary tags
        sanitized = sanitized.replace("```", "'''")
        sanitized = sanitized.replace("<memory_boundary>", "&lt;memory_boundary&gt;")
        sanitized = sanitized.replace("</memory_boundary>", "&lt;/memory_boundary&gt;")

        # 4. Context Stuffing / DoS Protection: Truncate oversized content
        if len(sanitized) > self.max_chars_per_item:
            sanitized = sanitized[: self.max_chars_per_item] + "\n... [TRUNCATED: Content exceeded security size limit]"
            violations.append(
                SecurityViolation(
                    item_id=item_id,
                    item_type=item_type,
                    violation_type="oversized",
                    details=f"Item length ({len(text)} chars) exceeded limit of {self.max_chars_per_item}",
                    action_taken="truncated",
                )
            )

        return True, sanitized.strip(), violations

    def filter_and_package(
        self,
        episodes: List[Episode],
        anti_patterns: List[Episode],
        patterns: List[SemanticPattern],
        target_repo: Optional[str] = None,
        target_ecosystem: Optional[str] = None,
        target_framework: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enforces multi-layer security boundary filtering, verification, and structured packaging."""
        audit = MemoryAuditReport()

        approved_episodes: List[Dict[str, Any]] = []
        approved_anti_patterns: List[Dict[str, Any]] = []
        approved_patterns: List[Dict[str, Any]] = []

        total_content_length = 0

        # ----------------------------------------------------
        # 1. Inspect and Filter Episodes
        # ----------------------------------------------------
        for ep in episodes[: self.max_items_per_category]:
            audit.total_inspected += 1

            # Scope boundary verification
            if ep.scope == "repository" and target_repo and target_repo not in ep.repo_identifier:
                audit.violations.append(
                    SecurityViolation(
                        item_id=ep.episode_id,
                        item_type="episode",
                        violation_type="scope_violation",
                        details=f"Cross-repository leakage blocked: {ep.repo_identifier} != {target_repo}",
                        action_taken="quarantined",
                    )
                )
                audit.total_quarantined += 1
                continue

            # Text inspection on task description and remediation strategy
            ok_task, san_task, v1 = self.inspect_and_sanitize_text(ep.task_description, ep.episode_id, "episode")
            ok_rem, san_rem, v2 = self.inspect_and_sanitize_text(ep.remediation_strategy or "", ep.episode_id, "episode")

            violations = v1 + v2
            audit.violations.extend(violations)

            if not ok_task or not ok_rem:
                audit.total_quarantined += 1
                continue

            if violations:
                audit.total_sanitized += 1

            audit.total_approved += 1
            approved_episodes.append({
                "episode_id": ep.episode_id,
                "task_description": san_task,
                "remediation_strategy": san_rem,
                "files_modified": ep.files_modified,
                "repo_identifier": ep.repo_identifier,
                "review_score": ep.review_score,
                "scope": ep.scope,
            })

        # ----------------------------------------------------
        # 2. Inspect and Filter Anti-Patterns
        # ----------------------------------------------------
        for ap in anti_patterns[: self.max_items_per_category]:
            audit.total_inspected += 1

            if ap.scope == "repository" and target_repo and target_repo not in ap.repo_identifier:
                audit.violations.append(
                    SecurityViolation(
                        item_id=ap.episode_id,
                        item_type="anti_pattern",
                        violation_type="scope_violation",
                        details=f"Cross-repository anti-pattern leakage blocked: {ap.repo_identifier} != {target_repo}",
                        action_taken="quarantined",
                    )
                )
                audit.total_quarantined += 1
                continue

            fail_desc = ap.failure_reason or ap.remediation_strategy or "Failed test validation"
            ok_fail, san_fail, v_fail = self.inspect_and_sanitize_text(fail_desc, ap.episode_id, "anti_pattern")
            audit.violations.extend(v_fail)

            if not ok_fail:
                audit.total_quarantined += 1
                continue

            if v_fail:
                audit.total_sanitized += 1

            audit.total_approved += 1
            approved_anti_patterns.append({
                "episode_id": ap.episode_id,
                "failure_reason": san_fail,
                "repo_identifier": ap.repo_identifier,
                "scope": ap.scope,
            })

        # ----------------------------------------------------
        # 3. Inspect and Filter Semantic Patterns
        # ----------------------------------------------------
        for pat in patterns[: self.max_items_per_category]:
            audit.total_inspected += 1

            # Confidence floor verification
            if pat.confidence < self.min_confidence_threshold or pat.status != "active":
                audit.violations.append(
                    SecurityViolation(
                        item_id=pat.pattern_id,
                        item_type="pattern",
                        violation_type="low_confidence",
                        details=f"Pattern confidence {pat.confidence} below threshold {self.min_confidence_threshold} or status={pat.status}",
                        action_taken="quarantined",
                    )
                )
                audit.total_quarantined += 1
                continue

            # Ecosystem constraint verification
            if target_ecosystem and pat.ecosystem and pat.ecosystem.lower() != target_ecosystem.lower():
                audit.violations.append(
                    SecurityViolation(
                        item_id=pat.pattern_id,
                        item_type="pattern",
                        violation_type="ecosystem_conflict",
                        details=f"Incompatible ecosystem: {pat.ecosystem} != {target_ecosystem}",
                        action_taken="quarantined",
                    )
                )
                audit.total_quarantined += 1
                continue

            ok_title, san_title, v_t = self.inspect_and_sanitize_text(pat.title, pat.pattern_id, "pattern")
            ok_cont, san_cont, v_c = self.inspect_and_sanitize_text(pat.content, pat.pattern_id, "pattern")
            violations = v_t + v_c
            audit.violations.extend(violations)

            if not ok_title or not ok_cont:
                audit.total_quarantined += 1
                continue

            if violations:
                audit.total_sanitized += 1

            audit.total_approved += 1
            approved_patterns.append({
                "pattern_id": pat.pattern_id,
                "title": san_title,
                "topic": pat.topic,
                "content": san_cont,
                "confidence": pat.confidence,
                "scope": pat.scope,
            })

        # ----------------------------------------------------
        # 4. Assemble Structured Memory Payload (Provenance & Untrusted Tier)
        # ----------------------------------------------------
        structured_items: List[UntrustedMemoryItem] = []

        for ep_dict in approved_episodes:
            # Map back to original episode for provenance metadata
            orig_ep = next((e for e in episodes if e.episode_id == ep_dict["episode_id"]), None)
            thread_id = orig_ep.thread_id if orig_ep else None
            structured_items.append(
                UntrustedMemoryItem.create(
                    item_id=ep_dict["episode_id"],
                    item_type="episode",
                    source_repo=ep_dict["repo_identifier"],
                    origin_thread=thread_id,
                    receipt_ids=[],
                    confidence=ep_dict.get("review_score", 0.7),
                    scope=ep_dict.get("scope", "repository"),
                    content_fields={
                        "task_description": ep_dict["task_description"],
                        "remediation_strategy": ep_dict.get("remediation_strategy", ""),
                        "files_modified": ep_dict.get("files_modified", []),
                    },
                )
            )

        for ap_dict in approved_anti_patterns:
            orig_ap = next((a for a in anti_patterns if a.episode_id == ap_dict["episode_id"]), None)
            thread_id = orig_ap.thread_id if orig_ap else None
            structured_items.append(
                UntrustedMemoryItem.create(
                    item_id=ap_dict["episode_id"],
                    item_type="anti_pattern",
                    source_repo=ap_dict["repo_identifier"],
                    origin_thread=thread_id,
                    receipt_ids=[],
                    confidence=0.0,
                    scope=ap_dict.get("scope", "repository"),
                    content_fields={
                        "failure_reason": ap_dict["failure_reason"],
                    },
                )
            )

        for pat_dict in approved_patterns:
            orig_pat = next((p for p in patterns if p.pattern_id == pat_dict["pattern_id"]), None)
            receipt_ids = [r.receipt_id for r in orig_pat.parse_receipts()] if orig_pat else []
            structured_items.append(
                UntrustedMemoryItem.create(
                    item_id=pat_dict["pattern_id"],
                    item_type="semantic_pattern",
                    source_repo=orig_pat.repo_identifier if orig_pat else "global",
                    origin_thread=None,
                    receipt_ids=receipt_ids,
                    confidence=pat_dict["confidence"],
                    scope=pat_dict["scope"],
                    content_fields={
                        "title": pat_dict["title"],
                        "topic": pat_dict["topic"],
                        "content": pat_dict["content"],
                    },
                )
            )

        payload = StructuredMemoryPayload(
            target_repo=target_repo,
            target_ecosystem=target_ecosystem,
            target_framework=target_framework,
            items=structured_items,
            total_recalled=len(structured_items),
            security_audit=audit.model_dump(),
        )

        guidance_summary = payload.to_untrusted_prompt_block(max_total_chars=self.max_total_chars)

        return {
            "recalled_episodes": approved_episodes,
            "recalled_anti_patterns": approved_anti_patterns,
            "recalled_patterns": approved_patterns,
            "structured_payload": payload,
            "items": [item.model_dump() for item in structured_items],
            "guidance_summary": guidance_summary,
            "total_recalled": len(structured_items),
            "security_audit": audit.model_dump(),
        }
