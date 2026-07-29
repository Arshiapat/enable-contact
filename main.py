"""
main.py — ONOW Contact Intelligence Service

Core business logic for AI-powered contact summaries and coach chat.

This service helps coaches prepare for meetings with entrepreneurs by:
1. Generating an AI summary of a contact based on all available data
   (biodata, session notes, program history, survey responses, assets)
2. Enabling coaches to chat with the AI using that same context as a
   knowledge base — the summary is the bot's opening message, and the
   coach can ask follow-up questions in a persistent conversation

Architecture:
  - Contact data is assembled by the ONOW backend and sent to this API
  - Asset files are downloaded from Azure Blob Storage SAS URLs and
    extracted using pdfplumber (born-digital) or pytesseract OCR (scanned)
  - Summaries and chat histories are cached by contact ID so conversations
    persist between sessions
  - Chat history is always included as context so the AI remembers prior
    exchanges within the same conversation

Future:
  - Direct coach-entrepreneur chat history will be added as additional
    context once that integration is ready (placeholder noted in prompts)
"""

import os
import json
import tempfile
import requests as http_requests
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import pdfplumber
from docx import Document
import pytesseract
from PIL import Image
import pdf2image

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CLIENT SETUP
# ─────────────────────────────────────────────────────────────────────────────

# Same Azure OpenAI resource as the screening service
azure_client = OpenAI(
    base_url=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"]
)
DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4-mini")


# ─────────────────────────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

SUMMARY_SYSTEM_PROMPT = """You are an AI assistant helping coaches at Entrepreneur Support Organizations (ESOs)
prepare for meetings with the entrepreneurs they mentor.

You will be given structured information about an entrepreneur contact including:
- Biodata: basic contact information and business background
- Session notes: notes from prior meetings between the coach and entrepreneur
- Team notes: internal ESO team notes about the contact
- Program data: programs the contact has participated in, current and historical
- Survey data: the contact's application form responses
- Asset content: extracted text from uploaded business documents (business plans, financials, etc.)

Your job is to generate a concise, structured briefing that helps the coach quickly get up to speed
before their meeting. The briefing should highlight the most important information a coach needs to
know — key business context, progress since last session, outstanding goals, and anything that
needs attention.

Keep the tone professional but conversational — this is a briefing document, not a formal report.
Be specific and cite actual details from the data rather than making generic statements.

If certain data sections are empty or not provided, skip them gracefully without drawing attention
to the absence.

Structure your response with these sections (skip any section where no relevant data exists):
1. Contact Overview — who they are, their business, current stage
2. Program History — programs participated in, current program status
3. Recent Session Summary — key points from the most recent meeting(s)
4. Business Health — what the data suggests about the business's current state
5. Goals & Progress — stated goals and any evidence of progress or blockers
6. Key Themes & Patterns — recurring topics, challenges, or strengths across sessions
7. Suggested Focus Areas — 2-3 areas the coach may want to address in the upcoming meeting"""


CHAT_SYSTEM_PROMPT = """You are an AI assistant helping a coach at an Entrepreneur Support Organization (ESO)
prepare for and reflect on meetings with an entrepreneur they mentor.

You have been given a full briefing about this entrepreneur contact including their biodata,
session history, program participation, survey responses, and business documents.
This briefing is your knowledge base — answer all questions based on it.

You are in an ongoing conversation with the coach. The conversation history is included so you
can reference prior exchanges and build on them. Be concise, specific, and always ground your
answers in the actual data provided.

If the coach asks about something not covered in the available data, say so clearly rather than
guessing. Do not fabricate session notes, goals, or business details that are not in the data."""


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT EXTRACTION (OCR-aware)
# Replicates the extraction pipeline from the screening service.
# Handles born-digital PDFs, scanned PDFs, DOCX, and image files.
# ─────────────────────────────────────────────────────────────────────────────

OCR_FALLBACK_THRESHOLD = 50


def fetch_file_from_url(url: str, suffix: str = ".pdf") -> str:
    """
    Download a file from a URL (e.g. Azure Blob Storage SAS URL) to a
    temporary local file. Returns the temp file path.
    Caller is responsible for deleting the temp file after use.
    """
    try:
        response = http_requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as e:
        raise ValueError(f"Failed to download file from URL: {str(e)}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(response.content)
        return tmp.name


def ocr_page_image(image) -> str:
    """Run pytesseract OCR on a PIL Image. Returns extracted text."""
    try:
        image = image.convert("L")
        return pytesseract.image_to_string(image, config="--psm 6").strip()
    except Exception:
        return ""


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF using pdfplumber with pytesseract OCR fallback
    for scanned or image-based pages.
    """
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""
                if len(page_text.strip()) >= OCR_FALLBACK_THRESHOLD:
                    text += page_text + "\n"
                else:
                    try:
                        images = pdf2image.convert_from_path(
                            file_path, dpi=300,
                            first_page=page_num, last_page=page_num
                        )
                        if images:
                            ocr_text = ocr_page_image(images[0])
                            if ocr_text:
                                text += ocr_text + "\n"
                    except Exception:
                        pass
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from a DOCX file using python-docx."""
    text = ""
    try:
        doc = Document(file_path)
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from DOCX: {str(e)}")


def extract_text_from_document(file_path: str) -> dict:
    """
    Extract text from a PDF, DOCX, or image file.
    Returns {"success": bool, "text": str, "message": str, "ocr_used": bool}.
    """
    if not os.path.exists(file_path):
        return {"success": False, "text": "", "message": "File not found.", "ocr_used": False}

    file_size = os.path.getsize(file_path)
    if file_size > 5 * 1024 * 1024:
        return {"success": False, "text": "", "message": "File too large. Max 5MB.", "ocr_used": False}

    file_ext   = os.path.splitext(file_path)[1].lower()
    image_exts = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}

    try:
        if file_ext == ".pdf":
            text     = extract_text_from_pdf(file_path)
            ocr_used = len(text) > 0 and (len(text) / max(1, text.count("\n") + 1)) < 200
        elif file_ext in [".docx", ".doc"]:
            text     = extract_text_from_docx(file_path)
            ocr_used = False
        elif file_ext in image_exts:
            image    = Image.open(file_path)
            text     = ocr_page_image(image)
            ocr_used = True
        else:
            return {
                "success": False, "text": "",
                "message": f"Unsupported format '{file_ext}'.", "ocr_used": False
            }

        if not text:
            return {
                "success": False, "text": "",
                "message": "No text could be extracted from the document.", "ocr_used": ocr_used
            }

        return {"success": True, "text": text, "message": f"Extracted {len(text)} characters.", "ocr_used": ocr_used}

    except Exception as e:
        return {"success": False, "text": "", "message": f"Error: {str(e)}", "ocr_used": False}


def extract_assets(assets: list) -> str:
    """
    Download and extract text from a list of asset file references.
    Each asset has a url, name, and mimeType.
    Returns combined extracted text labeled by filename.
    Assets that fail to extract are skipped with a note.
    """
    if not assets:
        return ""

    parts = []
    for asset in assets:
        url      = asset.get("url", "")
        name     = asset.get("name", "unknown")
        mime     = asset.get("mimeType", "")
        suffix   = os.path.splitext(name)[1].lower() or ".pdf"
        tmp_path = None

        try:
            tmp_path   = fetch_file_from_url(url, suffix=suffix)
            extraction = extract_text_from_document(tmp_path)
            if extraction["success"]:
                parts.append(f"--- {name} ---\n{extraction['text']}")
            else:
                parts.append(f"--- {name} --- [Could not extract: {extraction['message']}]")
        except Exception as e:
            parts.append(f"--- {name} --- [Download failed: {str(e)}]")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# CONTACT CONTEXT BUILDER
# Assembles all contact data into a single structured text block
# that is used as context for both summary generation and chat.
# ─────────────────────────────────────────────────────────────────────────────

def build_contact_context(contact_data: dict, asset_text: str = "") -> str:
    """
    Assemble all contact data into a structured plain-text context block.

    contact_data fields (all optional — missing fields are skipped):
        contact_id      : str
        name            : str
        email           : str
        phone           : str
        business_name   : str
        business_stage  : str
        business_description : str
        location        : str
        session_notes   : list of {"date": str, "notes": str, "coach": str}
        team_notes      : list of {"date": str, "notes": str, "author": str}
        programs        : list of {"name": str, "status": str, "start_date": str, "end_date": str}
        survey_responses: list of {"question": str, "answer": str}

    asset_text is the pre-extracted text from uploaded business documents.

    Returns a single structured string ready to be included in an AI prompt.
    """
    sections = []

    # ── Biodata ───────────────────────────────────────────────────────────────
    bio_parts = []
    if contact_data.get("name"):
        bio_parts.append(f"Name: {contact_data['name']}")
    if contact_data.get("email"):
        bio_parts.append(f"Email: {contact_data['email']}")
    if contact_data.get("phone"):
        bio_parts.append(f"Phone: {contact_data['phone']}")
    if contact_data.get("location"):
        bio_parts.append(f"Location: {contact_data['location']}")
    if contact_data.get("business_name"):
        bio_parts.append(f"Business: {contact_data['business_name']}")
    if contact_data.get("business_stage"):
        bio_parts.append(f"Stage: {contact_data['business_stage']}")
    if contact_data.get("business_description"):
        bio_parts.append(f"Description: {contact_data['business_description']}")
    if bio_parts:
        sections.append("BIODATA\n" + "\n".join(bio_parts))

    # ── Program history ───────────────────────────────────────────────────────
    programs = contact_data.get("programs", [])
    if programs:
        prog_lines = []
        for p in programs:
            line = f"- {p.get('name', 'Unknown program')} | Status: {p.get('status', 'Unknown')}"
            if p.get("start_date"):
                line += f" | Start: {p['start_date']}"
            if p.get("end_date"):
                line += f" | End: {p['end_date']}"
            prog_lines.append(line)
        sections.append("PROGRAM HISTORY\n" + "\n".join(prog_lines))

    # ── Session notes ─────────────────────────────────────────────────────────
    session_notes = contact_data.get("session_notes", [])
    if session_notes:
        note_parts = []
        for note in session_notes:
            header = f"[{note.get('date', 'Unknown date')}]"
            if note.get("coach"):
                header += f" Coach: {note['coach']}"
            note_parts.append(f"{header}\n{note.get('notes', '')}")
        sections.append("SESSION NOTES\n" + "\n\n".join(note_parts))

    # ── Team notes ────────────────────────────────────────────────────────────
    team_notes = contact_data.get("team_notes", [])
    if team_notes:
        note_parts = []
        for note in team_notes:
            header = f"[{note.get('date', 'Unknown date')}]"
            if note.get("author"):
                header += f" By: {note['author']}"
            note_parts.append(f"{header}\n{note.get('notes', '')}")
        sections.append("TEAM NOTES\n" + "\n\n".join(note_parts))

    # ── Survey responses ──────────────────────────────────────────────────────
    survey = contact_data.get("survey_responses", [])
    if survey:
        survey_lines = [
            f"Q: {r.get('question', '')}\nA: {r.get('answer', '')}"
            for r in survey
        ]
        sections.append("SURVEY RESPONSES\n" + "\n\n".join(survey_lines))

    # ── Asset content ─────────────────────────────────────────────────────────
    if asset_text and asset_text.strip():
        sections.append(f"ASSET DOCUMENTS\n{asset_text}")

    if not sections:
        return "No contact data available."

    return "\n\n" + "\n\n".join(f"=== {s}" for s in sections)


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY CACHE
# Stores generated summaries per contact so they are not regenerated on
# every page load. Cleared when new data is available (e.g. new session notes).
# TODO: Replace JSON file storage with DB-backed storage at integration time.
# ─────────────────────────────────────────────────────────────────────────────

SUMMARY_CACHE_PATH = "contact_summary_cache.json"


def load_summary_cache() -> dict:
    if not os.path.exists(SUMMARY_CACHE_PATH):
        return {}
    with open(SUMMARY_CACHE_PATH, "r") as f:
        return json.load(f)


def save_summary_cache(cache: dict) -> None:
    with open(SUMMARY_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def get_cached_summary(contact_id: str) -> dict | None:
    """Return cached summary for a contact, or None if not yet generated."""
    return load_summary_cache().get(contact_id)


def cache_summary(contact_id: str, summary: str) -> None:
    """Cache a generated summary for a contact."""
    cache = load_summary_cache()
    cache[contact_id] = {
        "summary":    summary,
        "cached_at":  datetime.utcnow().isoformat()
    }
    save_summary_cache(cache)


def invalidate_summary(contact_id: str) -> None:
    """
    Clear the cached summary for a contact.
    Call when new session notes, assets, or other data is added so the
    next request generates a fresh summary reflecting the updated data.
    """
    cache = load_summary_cache()
    if contact_id in cache:
        del cache[contact_id]
        save_summary_cache(cache)


# ─────────────────────────────────────────────────────────────────────────────
# CHAT HISTORY CACHE
# Stores the full conversation history per contact so coaches can return
# to a conversation across sessions. Each message is stored with its role
# (assistant for AI, user for coach) and content.
# TODO: Replace JSON file storage with DB-backed storage at integration time.
# ─────────────────────────────────────────────────────────────────────────────

CHAT_CACHE_PATH = "contact_chat_cache.json"


def load_chat_cache() -> dict:
    if not os.path.exists(CHAT_CACHE_PATH):
        return {}
    with open(CHAT_CACHE_PATH, "r") as f:
        return json.load(f)


def save_chat_cache(cache: dict) -> None:
    with open(CHAT_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def get_chat_history(contact_id: str) -> list:
    """
    Return the full conversation history for a contact.
    Each entry is {"role": "user"|"assistant", "content": str, "timestamp": str}.
    Returns empty list if no conversation exists yet.
    """
    cache = load_chat_cache()
    return cache.get(contact_id, {}).get("messages", [])


def save_chat_message(contact_id: str, role: str, content: str) -> None:
    """
    Append a message to the chat history for a contact.
    role is "user" (coach) or "assistant" (AI).
    """
    cache = load_chat_cache()
    if contact_id not in cache:
        cache[contact_id] = {"messages": []}
    cache[contact_id]["messages"].append({
        "role":      role,
        "content":   content,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_chat_cache(cache)


def clear_chat_history(contact_id: str) -> None:
    """
    Clear the full chat history for a contact.
    Useful if the coach wants to start a fresh conversation.
    """
    cache = load_chat_cache()
    if contact_id in cache:
        del cache[contact_id]
        save_chat_cache(cache)


# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def generate_summary(contact_id: str, contact_data: dict, assets: list, force_refresh: bool = False) -> dict:
    """
    Generate an AI summary for a contact and cache it.

    If a cached summary exists and force_refresh is False, the cached version
    is returned immediately without calling the AI. This ensures the summary
    page loads instantly on subsequent visits.

    If this is the first time a summary is generated for this contact, the
    summary is also saved as the first message in the chat history so the
    coach can start asking questions immediately after reading it.

    Parameters:
        contact_id    — unique ID of the contact in the ONOW system
        contact_data  — dict of contact fields (see build_contact_context)
        assets        — list of asset file refs {"url", "name", "mimeType"}
        force_refresh — if True, regenerate even if a cached summary exists

    Returns:
    {
        "contact_id":  str,
        "summary":     str,
        "from_cache":  bool,
        "cached_at":   str | None
    }
    """
    # Return cached summary if available and not forcing refresh
    if not force_refresh:
        cached = get_cached_summary(contact_id)
        if cached:
            return {
                "contact_id": contact_id,
                "summary":    cached["summary"],
                "from_cache": True,
                "cached_at":  cached["cached_at"]
            }

    # Extract asset documents
    asset_text = extract_assets(assets)

    # Build structured context from all contact data
    context = build_contact_context(contact_data, asset_text)

    # Generate summary from AI
    response = azure_client.chat.completions.create(
        model    = DEPLOYMENT_NAME,
        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user",   "content": f"Please generate a briefing for the following contact:\n{context}"}
        ],
        temperature           = 0.3,
        max_completion_tokens = 2000
    )

    summary = response.choices[0].message.content.strip()

    # Cache the summary
    cache_summary(contact_id, summary)

    # Save the summary as the first message in chat history so the coach
    # can immediately start asking follow-up questions
    # Only do this if no chat history exists yet — don't overwrite existing conversation
    if not get_chat_history(contact_id):
        save_chat_message(contact_id, "assistant", summary)

    return {
        "contact_id": contact_id,
        "summary":    summary,
        "from_cache": False,
        "cached_at":  datetime.utcnow().isoformat()
    }


def chat(contact_id: str, contact_data: dict, assets: list, coach_message: str) -> dict:
    """
    Send a coach message and get an AI response, maintaining full conversation history.

    The AI always receives:
    1. The system prompt with instructions
    2. The full contact context as a system-level knowledge block
    3. The full conversation history so it can reference prior exchanges
    4. The new coach message

    The response and the coach message are both saved to the chat history
    so subsequent messages build on them.

    Parameters:
        contact_id    — unique ID of the contact
        contact_data  — dict of contact fields
        assets        — list of asset file refs (used if no cached asset text)
        coach_message — the coach's new message/question

    Returns:
    {
        "contact_id":    str,
        "coach_message": str,
        "ai_response":   str,
        "timestamp":     str,
        "history_count": int  — total messages in conversation including this one
    }
    """
    # Extract asset text for context
    asset_text = extract_assets(assets)
    context    = build_contact_context(contact_data, asset_text)

    # Get existing conversation history
    history = get_chat_history(contact_id)

    # Build messages array for the API call:
    # System prompt + contact context, then full conversation history, then new message
    messages = [
        {
            "role":    "system",
            "content": f"{CHAT_SYSTEM_PROMPT}\n\nCONTACT DATA:\n{context}"
        }
    ]

    # Add conversation history (role is "user" or "assistant", no timestamp needed)
    for msg in history:
        messages.append({
            "role":    msg["role"],
            "content": msg["content"]
        })

    # Add the new coach message
    messages.append({"role": "user", "content": coach_message})

    # Call AI
    response = azure_client.chat.completions.create(
        model                 = DEPLOYMENT_NAME,
        messages              = messages,
        temperature           = 0.3,
        max_completion_tokens = 1500
    )

    ai_response = response.choices[0].message.content.strip()

    # Save both the coach message and AI response to chat history
    save_chat_message(contact_id, "user",      coach_message)
    save_chat_message(contact_id, "assistant", ai_response)

    return {
        "contact_id":    contact_id,
        "coach_message": coach_message,
        "ai_response":   ai_response,
        "timestamp":     datetime.utcnow().isoformat(),
        "history_count": len(get_chat_history(contact_id))
    }