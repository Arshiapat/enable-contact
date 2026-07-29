# ONOW Contact Intelligence

AI-powered contact briefings and coach chat for Entrepreneur Support Organizations (ESOs).
Built for the ONOW Enable platform to help coaches prepare for meetings with entrepreneurs quickly and efficiently.

---

## Features

**AI Contact Briefing**
When a coach opens a contact page, the AI generates a concise one-paragraph summary of the entrepreneur — who they are, what their business is, where they are in the program, and the most relevant things happening right now. The goal is to give the coach everything they need to walk into a meeting oriented, in under 20 seconds of reading.

**Coach Chat**
After reading the summary, the coach can ask follow-up questions in a chat interface. The AI answers based on all available contact data — session notes, program history, business documents, and more. Example questions a coach might ask:
- "Give me a summary of prior interactions"
- "Tell me about the business health"
- "What were this person's last 3 goals"
- "What should I focus on in the next session"

The AI only answers what is asked and does not offer unsolicited suggestions, tasks, or follow-up actions.

**Persistent Chat History**
Chat history is saved between sessions. If a coach leaves the contact page and returns later, the conversation picks up where it left off. The initial AI summary is always the first message in the chat history so the full conversation is self-contained.

**OCR Support for Business Documents**
Asset documents uploaded by the entrepreneur (business plans, financials, etc.) are extracted and included as context. Documents do not need to be born-digital — scanned PDFs and images are handled through automatic OCR using pytesseract. For each page of a PDF, the system first attempts to read the embedded text layer and falls back to OCR if the page appears to be a scan.

**Summary Caching**
Once a summary is generated for a contact, it is cached and returned instantly on subsequent page loads without calling the AI again. When new data is added (new session notes, new assets, etc.), the cache can be invalidated so the next request generates a fresh summary reflecting the updated information.

---

## Data Sources

The AI briefing and chat are powered by all available contact data:

| Source | What it includes |
|---|---|
| Biodata | Name, contact info, business name, stage, description, location |
| Session notes | Notes from prior coach-entrepreneur meetings with dates and coach name |
| Team notes | Internal ESO team notes about the contact |
| Program data | Current and historical program participation with status and dates |
| Survey responses | Application form question/answer pairs |
| Assets | Uploaded business documents (business plans, financials, etc.) extracted via OCR |

**Note:** Direct chat history between coach and entrepreneur is a separate existing feature and is not currently included as context for the AI. This may be added in a future update.

---

## File Structure

```
main.py          Core logic — summary generation, chat, document extraction, caching
api.py           FastAPI HTTP layer — exposes main.py functions as REST endpoints
requirements.txt Python dependencies
test_contact.py  Interactive test script — generates a summary and lets you chat as a coach
.env             Azure OpenAI credentials (shared with screening service)
```

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Install Tesseract OCR binary** (required for scanned document support)
```bash
# macOS
brew install tesseract

# Linux (Ubuntu/Debian)
sudo apt-get install tesseract-ocr
```

**3. Configure environment variables**

The `.env` file uses the same Azure OpenAI resource as the screening service:
```
AZURE_OPENAI_API_KEY=your_azure_openai_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/openai/v1
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.4-mini
SCREENING_API_KEY=your_secret_api_key
```

**4. Run the API**
```bash
uvicorn api:app --reload --port 8001
```

Note: Port 8001 is used to avoid conflicting with the screening service on port 8000.

**5. View interactive documentation**

Open `http://localhost:8001/docs` in a browser to see all endpoints with request/response formats and test them interactively.

---

## Authentication

Every request must include the API key in the header:
```
X-API-Key: your_secret_api_key
```

If `SCREENING_API_KEY` is not set in the environment, authentication is skipped — useful for local development.

---

## API Documentation

Once the server is running, the full interactive API documentation is available at:

```
http://localhost:8001/docs
```

All endpoints are listed there with their exact request and response formats. You can expand any schema (ContactData, SessionNote, etc.) to see the required fields, and use the **Try it out** button to send real requests directly from the browser without writing any code.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/contact/summary` | Generate or retrieve cached AI briefing for a contact |
| `POST` | `/contact/chat` | Send a coach message and get an AI response |
| `GET` | `/contact/{contact_id}/history` | Retrieve full chat history for a contact |
| `DELETE` | `/contact/{contact_id}/history` | Clear chat history for a contact |
| `DELETE` | `/contact/{contact_id}/summary` | Invalidate cached summary (triggers fresh generation on next request) |
| `GET` | `/health` | Health check |

---

## How Chat History Works

When the coach first opens a contact page, `/contact/summary` is called. The generated summary is saved as the first message in the chat history with role `assistant`.

Each time the coach sends a message via `/contact/chat`, the full conversation history is included in the API call to the AI so it can reference prior exchanges. The coach message and AI response are both appended to the history after each turn.

This means token usage increases as the conversation grows — each new message sends all prior messages as context. For a typical coach prep session this is not a significant concern, but very long conversations will cost more per message.

When the coach returns to the contact page on a later visit, `/contact/{id}/history` can be used to restore the full conversation so it continues seamlessly.

To start a fresh conversation, call `DELETE /contact/{contact_id}/history`. The summary remains cached and will be re-added as the first message when the coach next opens the contact.

---

## Testing

Run the interactive test script to generate a summary for a mock entrepreneur and chat with the AI as a coach:

```bash
python test_contact.py
```

Commands available at the prompt:

| Command | What it does |
|---|---|
| Any question | Send to AI and receive a response |
| `history` | Print the full conversation so far |
| `refresh` | Regenerate the summary from scratch |
| `reset` | Clear conversation history and start over |
| `quit` | Exit the test |

---

## Integration Notes for Developers

**Database replacement**
Both the summary cache and chat history cache currently use JSON files (`contact_summary_cache.json` and `contact_chat_cache.json`) as placeholders. Each is marked with a `# TODO` comment. At integration time, replace these with the appropriate ONOW database read/write calls. The function signatures and return shapes stay the same.

**Contact data assembly**
The ONOW backend is responsible for assembling all contact data from the relational database and sending it in the request body. This service does not query the database directly — it receives the data pre-assembled and processes it.

**Asset files**
Asset documents are expected as a list of file references with SAS URLs pointing to files in Azure Blob Storage. The service downloads each file, extracts text (with OCR fallback for scanned documents), and includes the content as context for the AI.

**Summary invalidation**
When new session notes, team notes, assets, or other contact data is added in the CRM, the ONOW backend should call `DELETE /contact/{contact_id}/summary` to clear the cached summary. The next call to `/contact/summary` will then generate a fresh one reflecting the updated data.

**Token usage note**
Chat history is included in full on every API call. Longer conversations cost more per message. Consider implementing a maximum history length or a summarization step for very long conversations if cost becomes a concern at scale.