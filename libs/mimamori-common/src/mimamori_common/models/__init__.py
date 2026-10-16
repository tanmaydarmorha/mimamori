"""Pydantic models for every schema in `schemas/` plus the HTTP API models.

The `generated/` package is produced by `scripts/generate_models.py` from `schemas/*.json`
(never hand-edit it). This module gives the generated classes readable names. API request and
response models live in `api.py` and are re-exported here.
"""

from .generated import advance_wishes as _wishes
from .generated import call_turn as _call_turn
from .generated import contact_brief as _brief
from .generated import contact_view as _view
from .generated import copilot_turn as _copilot
from .generated import evidence_card as _card
from .generated import playbook as _playbook
from .generated import question_bank as _bank

# schemas/advance-wishes.json
AdvanceWishes = _wishes.AdvanceWishesCaseDbVersionedConsent
TrustedContact = _wishes.TrustedContact
CoolingOff = _wishes.CoolingOff
Disclosure = _wishes.Disclosure

# schemas/copilot-turn.json
CopilotTurn = _copilot.CounterCopilotOutputForOneCustomerTurnModelOutput
Indicator = _copilot.Indicator
CoverStory = _copilot.CoverStory
IndicatorType = _copilot.IndicatorType
Hypothesis = _copilot.Hypothesis

# schemas/evidence-card.json
EvidenceCard = _card.EvidenceCardCaseDb
CardRequest = _card.Request
CardPayee = _card.Payee
FactClaim = _card.FactClaim
QuoteClaim = _card.QuoteClaim
InferenceClaim = _card.InferenceClaim
Risk = _card.Risk
NextQuestion = _card.NextQuestion
DroppedClaim = _card.DroppedItem
CardTool = _card.Tool

# schemas/question-bank.json and playbook.json
QuestionBank = _bank.ApprovedCounterWordingQuestionsAndHoldFirmLines
Question = _bank.Question
HoldLine = _bank.HoldLine
Playbook = _playbook.ScamPlaybookIntelDb

# schemas/contact-brief.json, call-turn.json, contact-view.json
ContactBrief = _brief.ContactBriefCaseServiceConversationService
CallTurn = _call_turn.CallbackTurnGeminiOutputAndReplyTemplates
CallTemplate = _call_turn.Template
CallIntent = _call_turn.Intent
ContactView = _view.ContactViewConversationServiceCaseService

from .api import *  # noqa: E402,F401,F403
from .baseline import (  # noqa: E402,F401
    Baseline, KnownPayee, SeasonalItem, WatchlistEntry, WatchlistSnapshot, WatchlistSource,
)
