"""Seed data for the settings table.

Populates prompt blocks and scoring weights so the scorer has explicit
configuration rather than relying on hardcoded fallbacks.
"""

SETTINGS_SEED = {
    "initial_email_prompt_blocks": {
        "opening": "You are an expert sales email evaluator. Score the following outgoing sales email on four dimensions, each from 1 (worst) to 10 (best):",
        "value_proposition": "**value_proposition** — Does the email clearly articulate what value the sender offers to the recipient?",
        "personalisation": "**personalisation** — How tailored is the email to the specific recipient? Does it reference their company, role, recent activity, or pain points?",
        "cta": "**cta** — Is there a clear, specific call to action? Is it easy for the recipient to take the next step?",
        "clarity": "**clarity** — Is the message easy to read and understand? Is it concise with a clear structure?",
        "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
    },
    "chain_email_prompt_blocks": {
        "opening": "You are an expert sales email evaluator. Score the following email within the context of its conversation chain on four dimensions, each from 1 (worst) to 10 (best):",
        "value_proposition": "**value_proposition** — Does the email clearly articulate what value the sender offers?",
        "personalisation": "**personalisation** — How tailored is the email to the specific recipient and conversation context?",
        "cta": "**cta** — Is there a clear, specific call to action?",
        "clarity": "**clarity** — Is the message easy to read and understand? Is it concise with a clear structure?",
        "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
    },
    "chain_evaluation_prompt_blocks": {
        "opening": "You are an expert sales conversation evaluator. Evaluate the following email conversation chain on four dimensions, each from 1 (worst) to 10 (best):",
        "progression": "**progression** — How well does the conversation advance toward the sales goal across emails?",
        "responsiveness": "**responsiveness** — How timely and relevant are the follow-ups?",
        "persistence": "**persistence** — Does the sender maintain appropriate follow-up cadence without being pushy?",
        "conversation_quality": "**conversation_quality** — Overall quality of the conversation as a multi-touch sales engagement.",
        "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "progression": <1-10>,\n  "responsiveness": <1-10>,\n  "persistence": <1-10>,\n  "conversation_quality": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
    },
    "follow_up_email_prompt_blocks": {
        "opening": "You are an expert sales email evaluator. Score the following follow-up email on four dimensions, each from 1 (worst) to 10 (best). This email is a follow-up sent to a prospect who has not responded to prior outreach. Evaluate it in the context of the previous emails shown below.",
        "value_proposition": "**value_proposition** — Does the follow-up introduce a new angle, additional value, or fresh reason to engage? Penalise repetition of the same pitch.",
        "personalisation": "**personalisation** — Does the follow-up reference specific details about the recipient, their company, or prior interactions? Is it more than a generic bump?",
        "cta": "**cta** — Is there a clear, low-friction call to action? Does it differ from previous CTAs to avoid fatigue?",
        "clarity": "**clarity** — Is the message concise and easy to read? Does it avoid spam tropes (excessive urgency, ALL CAPS, clickbait)?",
        "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
    },
    "classifier_prompt_blocks": {
        "opening": "You are an email classification assistant. Analyse the following email and determine its type and extract any quoted/forwarded email metadata. The email includes a Direction field (Incoming or Outgoing) and a To address.",
        "email_type": '**email_type** — Classify as one of: "real_email" (genuine sales or business correspondence with an external party), "auto_reply" (out-of-office, automatic reply, vacation responder), "bounce" (delivery failure, undeliverable), "calendar" (meeting acceptance, decline, tentative), "newsletter" (bulk/marketing email), "not_sales" (internal communication, support ticket response, administrative email, or any outgoing email that is not sales outreach — e.g. emails to internal support systems like Atlassian/Jira/Zendesk, brief acknowledgements like "thanks" or "got it" sent to internal addresses, or internal coordination). For outgoing emails, classify as "not_sales" unless the email is clearly sales outreach to an external prospect. Default to "real_email" only for genuine sales or business correspondence.',
        "quoted_emails": '**quoted_emails** — Extract metadata from any quoted or forwarded emails embedded in the body. For each quoted email found, extract: "from_email", "subject", "date" (if available). Return as a JSON array. Return an empty array if no quoted emails are found.',
        "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "email_type": "<one of: real_email, auto_reply, bounce, calendar, newsletter, not_sales>",\n  "quoted_emails": [{"from_email": "<email>", "subject": "<subject>", "date": "<date or null>"}]\n}',
    },
    "thread_splitter_prompt_blocks": {
        "opening": "You are an email thread parser. The following text is the body of an email that contains one or more quoted or forwarded messages. Split it into individual messages.",
        "messages": '**messages** — Identify every individual message in the thread. For each message extract: "from_name" (or null), "from_email", "to_name" (or null), "to_email" (or null), "date" (ISO 8601 string or null if not available), "subject" (or null), "body_text" (only that message\'s own content, stripped of signatures, disclaimers, and further quoting). The first element must be the top-level message (the actual email that was sent, not a quoted reply).',
        "closing": 'Return the result as a JSON array ordered newest-first (the top-level message first). Respond with ONLY valid JSON, no other text:\n[\n  {"from_name": "...", "from_email": "...", "to_name": "...", "to_email": "...", "date": "...", "subject": "...", "body_text": "..."},\n  ...\n]',
    },
    "thread_split_indicators": ["From:", "wrote:", "Original Message", "Sent:"],
    "weight_value_proposition": 0.35,
    "weight_personalisation": 0.30,
    "weight_cta": 0.20,
    "weight_clarity": 0.15,
}
