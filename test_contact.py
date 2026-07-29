"""
test_contact.py

Interactive test script for the contact intelligence feature.
Generates an AI summary for a mock entrepreneur contact, then lets
you chat with the AI as a coach in your terminal.

HOW TO USE:
  python test_contact.py

Make sure your .env file has Azure credentials before running.
Type your questions at the prompt and press Enter to send.
Type 'quit' or 'exit' to end the session.
Type 'history' to see the full conversation so far.
Type 'refresh' to regenerate the summary from scratch.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import generate_summary, chat, get_chat_history, clear_chat_history

# ─────────────────────────────────────────────────────────────────────────────
# MOCK CONTACT DATA
# This represents a realistic entrepreneur contact in the ONOW CRM.
# Covers all data sources: biodata, programs, session notes, team notes,
# survey responses. No assets in this test (no files to download).
# ─────────────────────────────────────────────────────────────────────────────

CONTACT_ID = "test-contact-001"

MOCK_CONTACT = {
    "contact_id":           CONTACT_ID,
    "name":                 "Marcus Thompson",
    "email":                "marcus.thompson@email.com",
    "phone":                "+1-555-201-1111",
    "business_name":        "Thompson Mobile Detail",
    "business_stage":       "Early growth",
    "business_description": "Mobile auto detailing business operating out of a van. "
                            "Serves residential and commercial clients in the local area. "
                            "Currently solo-operated.",
    "location":             "Indianapolis, IN",

    "programs": [
        {
            "name":       "Riverside Small Business Accelerator — Summer 2025",
            "status":     "completed",
            "start_date": "2025-06-01",
            "end_date":   "2025-08-31"
        },
        {
            "name":       "Orange Corners Growth Cohort — Spring 2026",
            "status":     "active",
            "start_date": "2026-03-15",
            "end_date":   None
        }
    ],

    "session_notes": [
        {
            "date":  "2026-03-20",
            "coach": "Priya Sharma",
            "notes": "First session with Marcus. He came prepared with a basic revenue "
                     "spreadsheet but acknowledged he had no formal pricing strategy. "
                     "Currently charging a flat rate for all jobs regardless of vehicle "
                     "size or service complexity. We discussed value-based pricing as a "
                     "starting point. Goal set: research competitor pricing in the area "
                     "and bring a revised price list to next session."
        },
        {
            "date":  "2026-04-10",
            "coach": "Priya Sharma",
            "notes": "Marcus came back with a competitor analysis — three competitors "
                     "identified, all charging 20-40% more than him for comparable services. "
                     "We worked through a new tiered pricing model: Basic, Standard, Premium. "
                     "He was nervous about raising prices and losing existing clients. "
                     "Discussed how to communicate the value increase to loyal customers. "
                     "Goal set: implement new pricing for all new bookings starting May 1. "
                     "Existing clients grandfathered at old rate for 60 days."
        },
        {
            "date":  "2026-05-08",
            "coach": "Priya Sharma",
            "notes": "Check-in on new pricing. Marcus reported 8 new bookings since May 1 "
                     "all at the new rates. Two existing clients asked about the price change "
                     "and both stayed after he explained the service upgrade. Revenue for April "
                     "was up approximately 18% vs March. He is feeling more confident. "
                     "New challenge raised: scheduling is still done entirely by text message "
                     "and he is missing appointments and double-booking occasionally. "
                     "Goal set: evaluate two scheduling tools (Calendly and Jobber) and "
                     "choose one to trial by next session."
        },
        {
            "date":  "2026-06-12",
            "coach": "Priya Sharma",
            "notes": "Marcus chose Jobber after trialing both. He likes that it handles "
                     "invoicing and scheduling in one place. Setup was harder than expected "
                     "and he spent about 6 hours on it over two weeks. Now fully operational. "
                     "No double-bookings in the past 3 weeks. Client response time improved. "
                     "Discussed next growth area: getting corporate or fleet clients. "
                     "Currently all clients are residential word-of-mouth. Goal set: "
                     "identify 5 local businesses with vehicle fleets and cold outreach to them."
        }
    ],

    "team_notes": [
        {
            "date":   "2026-03-15",
            "author": "Program Coordinator",
            "notes":  "Marcus was selected from 47 applicants. Strong application — "
                      "active business, clear goals, coachable demeanor. "
                      "Flagged for potential: high retention customer base, low overhead, "
                      "technically skilled. Main gaps: business systems, marketing, pricing."
        },
        {
            "date":   "2026-05-20",
            "author": "Program Coordinator",
            "notes":  "Mid-program check-in. Marcus is performing above expectations. "
                      "Has implemented pricing changes and scheduling tool ahead of schedule. "
                      "Coach Priya rates engagement as excellent. Recommend for advanced "
                      "track or leadership cohort next cycle if interest."
        }
    ],

    "survey_responses": [
        {
            "question": "Is your business currently operating?",
            "answer":   "Yes, full time since March 2025."
        },
        {
            "question": "Are you the primary day-to-day operator?",
            "answer":   "Yes, I do everything myself."
        },
        {
            "question": "What is your approximate monthly revenue?",
            "answer":   "Around $2,000-$2,500/month at time of application. Now closer to $3,000."
        },
        {
            "question": "What specific areas do you want help with?",
            "answer":   "Pricing, scheduling systems, and figuring out how to get more "
                        "corporate or fleet clients."
        },
        {
            "question": "Have you worked with a business coach or mentor before?",
            "answer":   "No, this is my first time."
        }
    ]
}

# No asset files in this test — would need real SAS URLs
MOCK_ASSETS = []


# ─────────────────────────────────────────────────────────────────────────────
# TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def divider(title: str = ""):
    line = "=" * 70
    print(f"\n{line}")
    if title:
        print(f"  {title}")
        print(line)


def run():
    divider("ONOW Contact Intelligence — Interactive Test")
    print(f"  Contact : {MOCK_CONTACT['name']}")
    print(f"  Business: {MOCK_CONTACT['business_name']}")
    print(f"  ID      : {CONTACT_ID}")
    print()
    print("  Commands:")
    print("    Type any question to chat with the AI")
    print("    'history'  — show full conversation so far")
    print("    'refresh'  — regenerate summary from scratch")
    print("    'reset'    — clear conversation and start over")
    print("    'quit'     — exit")

    # ── Step 1: Generate summary ──────────────────────────────────────────────
    divider("STEP 1: Generating AI Summary")
    print("  Calling AI... this may take a few seconds.\n")

    try:
        result = generate_summary(
            contact_id   = CONTACT_ID,
            contact_data = MOCK_CONTACT,
            assets       = MOCK_ASSETS,
            force_refresh= False
        )
    except Exception as e:
        print(f"  ERROR generating summary: {e}")
        print("  Check your .env file has the correct Azure credentials.")
        sys.exit(1)

    if result["from_cache"]:
        print(f"  (Returned from cache — generated at {result['cached_at']})")
        print(f"  Type 'refresh' at the prompt to regenerate.\n")
    else:
        print("  (Fresh summary generated)\n")

    print("─" * 70)
    print(result["summary"])
    print("─" * 70)

    # ── Step 2: Interactive chat ──────────────────────────────────────────────
    divider("STEP 2: Chat with the AI as Coach")
    print("  The AI has the full contact context. Ask anything about Marcus.\n")

    while True:
        try:
            user_input = input("  You (coach): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Session ended.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("\n  Session ended. Chat history saved.")
            break

        if user_input.lower() == "history":
            divider("Conversation History")
            history = get_chat_history(CONTACT_ID)
            if not history:
                print("  No conversation history yet.")
            else:
                for msg in history:
                    role  = "AI    " if msg["role"] == "assistant" else "Coach "
                    print(f"\n  [{role}] {msg.get('timestamp', '')[:10]}")
                    print(f"  {msg['content']}\n")
                    print("  " + "─" * 60)
            continue

        if user_input.lower() == "refresh":
            divider("Regenerating Summary")
            print("  Calling AI...")
            try:
                result = generate_summary(
                    contact_id    = CONTACT_ID,
                    contact_data  = MOCK_CONTACT,
                    assets        = MOCK_ASSETS,
                    force_refresh = True
                )
                print("\n" + "─" * 70)
                print(result["summary"])
                print("─" * 70 + "\n")
            except Exception as e:
                print(f"  ERROR: {e}")
            continue

        if user_input.lower() == "reset":
            clear_chat_history(CONTACT_ID)
            print("  Chat history cleared. Starting fresh.\n")
            # Re-add the summary as first message
            generate_summary(
                contact_id    = CONTACT_ID,
                contact_data  = MOCK_CONTACT,
                assets        = MOCK_ASSETS,
                force_refresh = False
            )
            continue

        # Send message to AI
        print("\n  AI: thinking...\n")
        try:
            response = chat(
                contact_id    = CONTACT_ID,
                contact_data  = MOCK_CONTACT,
                assets        = MOCK_ASSETS,
                coach_message = user_input
            )
            print("─" * 70)
            print(f"  AI: {response['ai_response']}")
            print("─" * 70)
            print(f"  (Messages in conversation: {response['history_count']})\n")
        except Exception as e:
            print(f"  ERROR: {e}\n")


if __name__ == "__main__":
    run()