"""
api.py — ONOW Contact Intelligence API

FastAPI HTTP layer for the contact intelligence service.
No business logic lives here — all logic is in main.py.

── ENDPOINTS ────────────────────────────────────────────────────────────────

  POST  /contact/summary          Generate (or retrieve cached) AI summary
  POST  /contact/chat             Send a coach message and get AI response
  GET   /contact/{contact_id}/history    Get full chat history for a contact
  DELETE /contact/{contact_id}/history   Clear chat history for a contact
  DELETE /contact/{contact_id}/summary   Invalidate cached summary (force refresh)
  GET   /health                   Health check

── RUNNING LOCALLY ──────────────────────────────────────────────────────────

  pip install -r requirements.txt
  uvicorn api:app --reload --port 8001

  Swagger docs: http://localhost:8001/docs
"""

import os
from typing import Optional
from fastapi import FastAPI, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from starlette.status import HTTP_403_FORBIDDEN
from fastapi import HTTPException

import main


# ─────────────────────────────────────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "ONOW Contact Intelligence API",
    description = "AI-powered contact summaries and coach chat for ESO programs.",
    version     = "1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # TODO: restrict to ONOW frontend domain in production
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# Same pattern as the screening service — X-API-Key header checked against
# SCREENING_API_KEY environment variable.
# ─────────────────────────────────────────────────────────────────────────────

API_KEY_NAME   = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Validate X-API-Key header. Skipped if SCREENING_API_KEY is not set (local dev)."""
    expected_key = os.environ.get("SCREENING_API_KEY")
    if not expected_key:
        return
    if api_key != expected_key:
        raise HTTPException(
            status_code = HTTP_403_FORBIDDEN,
            detail      = {
                "status":  "error",
                "code":    403,
                "message": "Invalid or missing API key. Include your key in the X-API-Key header."
            }
        )


# Apply auth to all endpoints
app.router.dependencies.append(Depends(verify_api_key))


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def api_error(status_code: int, message: str):
    """Raise a consistent HTTPException with a standard error body shape."""
    raise HTTPException(
        status_code = status_code,
        detail      = {"status": "error", "code": status_code, "message": message}
    )


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────────────────────────────────────

class SessionNote(BaseModel):
    date:   Optional[str] = Field(None, description="Date of the session (YYYY-MM-DD).")
    notes:  str           = Field(...,  description="Session notes text.")
    coach:  Optional[str] = Field(None, description="Name of the coach who wrote the notes.")


class TeamNote(BaseModel):
    date:   Optional[str] = Field(None, description="Date the note was added (YYYY-MM-DD).")
    notes:  str           = Field(...,  description="Team note text.")
    author: Optional[str] = Field(None, description="Name of the team member who wrote the note.")


class ProgramRecord(BaseModel):
    name:       str           = Field(...,  description="Name of the program.")
    status:     Optional[str] = Field(None, description="Status e.g. active, completed, dropped.")
    start_date: Optional[str] = Field(None, description="Program start date (YYYY-MM-DD).")
    end_date:   Optional[str] = Field(None, description="Program end date (YYYY-MM-DD).")


class SurveyResponse(BaseModel):
    question: str = Field(..., description="The survey question text.")
    answer:   str = Field(..., description="The contact's answer.")


class AssetFile(BaseModel):
    url:       str           = Field(...,  description="SAS URL to the file in Azure Blob Storage.")
    name:      str           = Field(...,  description="Original filename e.g. business_plan.pdf")
    mimeType:  str           = Field(...,  description="MIME type e.g. application/pdf")
    sizeBytes: Optional[int] = Field(None, description="File size in bytes.")


class ContactData(BaseModel):
    """
    All available data about a contact.
    All fields are optional — the AI will work with whatever is provided
    and skip sections where data is missing.
    """
    contact_id:           str                      = Field(...,  description="Unique ID of the contact in the ONOW system.")
    name:                 Optional[str]            = Field(None, description="Contact's full name.")
    email:                Optional[str]            = Field(None, description="Contact's email address.")
    phone:                Optional[str]            = Field(None, description="Contact's phone number.")
    business_name:        Optional[str]            = Field(None, description="Name of the entrepreneur's business.")
    business_stage:       Optional[str]            = Field(None, description="Stage of the business e.g. idea, early, growth.")
    business_description: Optional[str]            = Field(None, description="Brief description of the business.")
    location:             Optional[str]            = Field(None, description="Contact's location.")
    session_notes:        list[SessionNote]        = Field(default=[], description="Notes from prior coach-entrepreneur sessions.")
    team_notes:           list[TeamNote]           = Field(default=[], description="Internal ESO team notes about the contact.")
    programs:             list[ProgramRecord]      = Field(default=[], description="Programs the contact has participated in.")
    survey_responses:     list[SurveyResponse]     = Field(default=[], description="Contact's application form responses.")


class SummaryRequest(BaseModel):
    contact:       ContactData    = Field(...,  description="Full contact data.")
    assets:        list[AssetFile] = Field(default=[], description="Business documents uploaded by the contact.")
    force_refresh: bool           = Field(False, description="If True, regenerate even if a cached summary exists.")


class SummaryResponse(BaseModel):
    contact_id:  str
    summary:     str
    from_cache:  bool
    cached_at:   Optional[str]


class ChatRequest(BaseModel):
    contact:       ContactData     = Field(...,  description="Full contact data — same as summary request.")
    assets:        list[AssetFile] = Field(default=[], description="Business documents uploaded by the contact.")
    coach_message: str             = Field(...,  description="The coach's message or question.")


class ChatResponse(BaseModel):
    contact_id:    str
    coach_message: str
    ai_response:   str
    timestamp:     str
    history_count: int


class ChatHistoryMessage(BaseModel):
    role:      str
    content:   str
    timestamp: str


class ChatHistoryResponse(BaseModel):
    contact_id: str
    messages:   list[ChatHistoryMessage]
    count:      int


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/contact/summary",
    response_model = SummaryResponse,
    summary        = "Generate or retrieve an AI briefing summary for a contact",
    description    = (
        "Returns a cached summary if one exists for this contact. "
        "Generates a fresh summary if none exists or if force_refresh is true. "
        "The summary is also saved as the first message in the chat history "
        "so the coach can immediately start asking follow-up questions. "
        "Covers biodata, program history, session notes, team notes, survey responses, "
        "and extracted business document content."
    ),
    tags = ["Contact Intelligence"]
)
def get_contact_summary(request: SummaryRequest):
    try:
        result = main.generate_summary(
            contact_id    = request.contact.contact_id,
            contact_data  = request.contact.model_dump(),
            assets        = [a.model_dump() for a in request.assets],
            force_refresh = request.force_refresh
        )
        return result
    except Exception as e:
        api_error(500, f"Summary generation failed: {str(e)}")


@app.post(
    "/contact/chat",
    response_model = ChatResponse,
    summary        = "Send a coach message and receive an AI response",
    description    = (
        "The AI responds based on the full contact data context and the "
        "conversation history so far. Both the coach message and the AI response "
        "are saved to the persistent chat history. "
        "Example questions: 'give summary of prior interactions', "
        "'tell me about the business health', 'what were this person's last 3 goals'."
    ),
    tags = ["Contact Intelligence"]
)
def send_chat_message(request: ChatRequest):
    if not request.coach_message.strip():
        api_error(400, "coach_message cannot be empty.")
    try:
        result = main.chat(
            contact_id    = request.contact.contact_id,
            contact_data  = request.contact.model_dump(),
            assets        = [a.model_dump() for a in request.assets],
            coach_message = request.coach_message
        )
        return result
    except Exception as e:
        api_error(500, f"Chat failed: {str(e)}")


@app.get(
    "/contact/{contact_id}/history",
    response_model = ChatHistoryResponse,
    summary        = "Get the full chat history for a contact",
    description    = (
        "Returns all messages in the coach-AI conversation for this contact, "
        "including the initial AI summary as the first message. "
        "Use this to restore a conversation when the coach returns to the contact page."
    ),
    tags = ["Contact Intelligence"]
)
def get_history(contact_id: str):
    messages = main.get_chat_history(contact_id)
    return ChatHistoryResponse(
        contact_id = contact_id,
        messages   = [ChatHistoryMessage(**m) for m in messages],
        count      = len(messages)
    )


@app.delete(
    "/contact/{contact_id}/history",
    summary     = "Clear the chat history for a contact",
    description = "Deletes the full conversation history. The coach starts fresh on the next visit.",
    tags        = ["Contact Intelligence"]
)
def delete_history(contact_id: str):
    main.clear_chat_history(contact_id)
    return {"status": "success", "contact_id": contact_id, "message": "Chat history cleared."}


@app.delete(
    "/contact/{contact_id}/summary",
    summary     = "Invalidate the cached summary for a contact",
    description = (
        "Clears the cached summary so the next call to /contact/summary "
        "generates a fresh one. Call this when new session notes, assets, "
        "or other contact data has been added and the summary should reflect the update."
    ),
    tags        = ["Contact Intelligence"]
)
def invalidate_summary(contact_id: str):
    main.invalidate_summary(contact_id)
    return {"status": "success", "contact_id": contact_id, "message": "Summary cache cleared. Next request will regenerate."}


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check", tags=["System"])
def health_check():
    return {"status": "ok", "service": "ONOW Contact Intelligence API", "version": "1.0.0"}