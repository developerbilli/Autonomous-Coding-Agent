"""Human Approval Gate (Human-in-the-Loop) for Destructive and Sensitive Operations.

Provides structured approval requests, interactive CLI gates, programmatic gates,
and audit trails for operations requiring operator confirmation.
"""

import sys
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from agent.tools.permissions import ToolActionType, RiskLevel


class ApprovalRequest(BaseModel):
    """Structured request submitted to a human operator for confirmation."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: ToolActionType
    target: str
    description: str
    risk_level: RiskLevel
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class ApprovalDecision(BaseModel):
    """Operator decision approving or rejecting an approval request."""
    approved: bool
    reason: Optional[str] = None
    approver: str = "human_operator"
    timestamp: float = Field(default_factory=time.time)


class HumanApprovalGate(ABC):
    """Abstract base class for human approval providers."""

    def __init__(self):
        self.history: List[Dict[str, Any]] = []

    @abstractmethod
    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Evaluates an approval request synchronously."""
        pass

    def record_decision(self, request: ApprovalRequest, decision: ApprovalDecision):
        """Maintains an audit log of all human approval decisions."""
        self.history.append({
            "request_id": request.request_id,
            "action_type": request.action_type.value,
            "target": request.target,
            "risk_level": request.risk_level.value,
            "approved": decision.approved,
            "reason": decision.reason,
            "approver": decision.approver,
            "timestamp": decision.timestamp,
        })


class AutoRejectApprovalGate(HumanApprovalGate):
    """Fails closed safely by rejecting any operation requiring approval (for headless runs)."""

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        decision = ApprovalDecision(
            approved=False,
            reason=f"Operation '{request.target}' rejected: no human operator attached in headless mode.",
            approver="auto_reject_policy",
        )
        self.record_decision(request, decision)
        return decision


class RecordedApprovalGate(HumanApprovalGate):
    """Programmatic approval gate for unit/integration testing with pre-set decisions."""

    def __init__(
        self,
        default_approve: bool = False,
        callback: Optional[Callable[[ApprovalRequest], bool]] = None,
        approver_name: str = "test_evaluator",
    ):
        super().__init__()
        self.default_approve = default_approve
        self.callback = callback
        self.approver_name = approver_name

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        approved = self.callback(request) if self.callback else self.default_approve
        decision = ApprovalDecision(
            approved=approved,
            reason="Approved by test evaluator" if approved else "Rejected by test evaluator",
            approver=self.approver_name,
        )
        self.record_decision(request, decision)
        return decision


class CLIApprovalGate(HumanApprovalGate):
    """Interactive command-line gate prompting the human operator via stdin/stdout."""

    def __init__(self, in_stream=None, out_stream=None):
        super().__init__()
        self.in_stream = in_stream or sys.stdin
        self.out_stream = out_stream or sys.stdout

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        self.out_stream.write("\n" + "=" * 60 + "\n")
        self.out_stream.write(" ⚠️  HUMAN APPROVAL REQUIRED FOR SENSITIVE OPERATION\n")
        self.out_stream.write("=" * 60 + "\n")
        self.out_stream.write(f" Action Type : {request.action_type.value.upper()}\n")
        self.out_stream.write(f" Target      : {request.target}\n")
        self.out_stream.write(f" Risk Level  : {request.risk_level.value.upper()}\n")
        self.out_stream.write(f" Description : {request.description}\n")
        if request.details:
            self.out_stream.write(f" Details     : {request.details}\n")
        self.out_stream.write("-" * 60 + "\n")
        self.out_stream.write(" Do you approve this operation? [y/N]: ")
        self.out_stream.flush()

        try:
            raw_input = self.in_stream.readline().strip().lower()
            approved = raw_input in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            approved = False

        decision = ApprovalDecision(
            approved=approved,
            reason="Confirmed by CLI operator" if approved else "Rejected by CLI operator",
            approver="cli_operator",
        )
        self.record_decision(request, decision)
        return decision
