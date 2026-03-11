"""Seed data for the settings table.

Populates prompt blocks and scoring weights so the scorer has explicit
configuration rather than relying on hardcoded fallbacks.
"""

SETTINGS_SEED = {
    "initial_email_prompt_blocks": {
        "opening": (
            "You are a demanding sales email evaluator. Score the following outgoing cold sales email on four dimensions, each from 1 to 10. "
            "Apply these standards strictly: 1-3 = poor (template-like, generic, or adds no value), 4-6 = adequate (competent but unremarkable), "
            "7-8 = strong (demonstrates genuine effort and insight), 9-10 = exceptional (rarely awarded - requires outstanding craft). "
            "Most mass outreach emails should score in the 3-5 range. A score of 7+ on any dimension requires clear, specific evidence of quality beyond the absence of errors. "
            "Consider who the recipient is - emails to well-known or large companies face a higher bar because those prospects receive high volumes of outreach and generic pitches will not cut through."
        ),
        "value_proposition": (
            "**value_proposition** — Does the email present a compelling, specific reason for the recipient to engage? "
            "A strong value proposition identifies a problem or opportunity the recipient faces and explains how the sender addresses it. "
            "Flattering the recipient's own brand ('you already fit how Gen Z does X') is not a value proposition - it tells them what they already know. "
            "Stating that the sender exists and does something generic ('we connect students') without tying it to a specific gap or need in the recipient's business is weak. "
            "Score 1-3 if the email just describes the sender's service without connecting to the recipient's situation. "
            "Score 4-6 if there is a relevant connection but it is obvious or generic to the sector. "
            "Score 7+ only if the email surfaces a specific insight, data point, or angle that gives the recipient a concrete reason to respond."
        ),
        "personalisation": (
            "**personalisation** — How much genuine research about the recipient is evident? "
            "Inserting a company name, industry label, or generic statement about their sector into a template is not personalisation - "
            "if the same paragraph would work for any company in that sector with a name swap, score 1-3. "
            "References to the recipient's specific situation, recent activity, public statements, market challenges, or competitive landscape demonstrate real research. "
            "Well-known companies (major brands, public companies, market leaders) face a higher bar: mentioning what they obviously do is not personalisation. "
            "Score 7+ only if the email shows knowledge that could not come from a 10-second glance at the company homepage."
        ),
        "cta": (
            "**cta** — Is there a clear, specific, low-friction call to action? "
            "A vague 'would you be open to a quick call?' with no proposed time, agenda, or specificity is a 4-5. "
            "Score 7+ if the CTA proposes a concrete next step that makes it easy for the recipient to say yes."
        ),
        "clarity": (
            "**clarity** — Is the message easy to read, well-structured, and concise? "
            "Penalise waffle, excessive length, jargon, and unclear purpose. "
            "A short, well-structured email with a clear point scores well here even if weak on other dimensions."
        ),
        "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
    },
    "chain_email_prompt_blocks": {
        "opening": (
            "You are a demanding sales email evaluator. Score the following email within the context of its conversation chain on four dimensions, each from 1 to 10. "
            "Apply these standards strictly: 1-3 = poor, 4-6 = adequate, 7-8 = strong, 9-10 = exceptional. "
            "A score of 7+ requires clear evidence of quality. Consider the conversation history when evaluating - "
            "does this email advance the relationship or just repeat earlier pitches?"
        ),
        "value_proposition": (
            "**value_proposition** — Does the email articulate specific value for the recipient, building on or advancing beyond what was said in previous messages? "
            "Repeating the same pitch from earlier in the chain is a 1-3. "
            "Score 7+ only if the email introduces new information, addresses a concern raised in the conversation, or deepens the value case."
        ),
        "personalisation": (
            "**personalisation** — Does the email demonstrate genuine knowledge of the recipient's situation? "
            "Template-level personalisation (company name, sector label) is a 1-3. "
            "Drawing on specifics from the conversation or the recipient's business context scores higher. "
            "Score 7+ only if the email shows real research or meaningful engagement with the recipient's needs."
        ),
        "cta": (
            "**cta** — Is there a clear, specific call to action appropriate to this stage of the conversation? "
            "Score 7+ if the CTA proposes a concrete next step."
        ),
        "clarity": (
            "**clarity** — Is the message easy to read, well-structured, and concise? "
            "Penalise waffle, excessive length, and unclear purpose."
        ),
        "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "personalisation": <1-10>,\n  "clarity": <1-10>,\n  "value_proposition": <1-10>,\n  "cta": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
    },
    "chain_evaluation_prompt_blocks": {
        "opening": (
            "You are a demanding sales conversation evaluator. Evaluate the following email conversation chain on four dimensions, each from 1 to 10. "
            "Apply these standards strictly: 1-3 = poor, 4-6 = adequate, 7-8 = strong, 9-10 = exceptional. "
            "Most outreach sequences that get no reply and just repeat the same pitch should score in the 2-4 range."
        ),
        "progression": (
            "**progression** — How well does the conversation advance toward the sales goal across emails? "
            "Sending the same template pitch repeatedly with minor rewording is a 1-3. "
            "Score 7+ only if the sequence shows genuine strategic progression - new angles, escalating value, or adapting based on signals."
        ),
        "responsiveness": (
            "**responsiveness** — How timely and relevant are the follow-ups? "
            "Does the sender adapt to signals from the prospect (or lack thereof)? "
            "Sending on a rigid cadence with no adaptation is a 4-5."
        ),
        "persistence": "**persistence** — Does the sender maintain appropriate follow-up cadence without being pushy or giving up too early?",
        "conversation_quality": (
            "**conversation_quality** — Overall quality of the conversation as a multi-touch sales engagement. "
            "A series of template follow-ups to an unresponsive prospect is a 2-4 regardless of how polished each individual email is."
        ),
        "closing": 'Respond with ONLY a JSON object in this exact format, no other text:\n{\n  "progression": <1-10>,\n  "responsiveness": <1-10>,\n  "persistence": <1-10>,\n  "conversation_quality": <1-10>,\n  "notes": "<brief 1-2 sentence explanation of the scores>"\n}',
    },
    "follow_up_email_prompt_blocks": {
        "opening": (
            "You are a demanding sales email evaluator. Score the following follow-up email on four dimensions, each from 1 to 10. "
            "This email is a follow-up sent to a prospect who has not responded to prior outreach. Evaluate it in the context of the previous emails shown below. "
            "Apply these standards strictly: 1-3 = poor, 4-6 = adequate, 7-8 = strong, 9-10 = exceptional. "
            "A follow-up that simply re-sends the same pitch, asks 'did you see my email?', or lightly rewords the original is poor (1-3). "
            "A good follow-up introduces a genuinely new reason to engage."
        ),
        "value_proposition": (
            "**value_proposition** — Does the follow-up introduce a genuinely new angle, additional value, or fresh reason to engage? "
            "Re-stating the same pitch from the initial email or lightly rewording it is a 1-3. "
            "Adding a new data point, case study, timely hook, or different framing scores higher. "
            "Score 7+ only if the follow-up gives the recipient something meaningfully new that they did not get from the previous emails."
        ),
        "personalisation": (
            "**personalisation** — Does the follow-up show genuine knowledge of the recipient beyond template-level details? "
            "If it reads like the same follow-up template sent to every non-responder with a company name swapped in, score 1-3. "
            "Score 7+ only if it references something specific to the recipient's situation, responds to a signal, or demonstrates real research."
        ),
        "cta": (
            "**cta** — Is there a clear, low-friction call to action? Does it differ from previous CTAs to avoid fatigue? "
            "Repeating 'quick call this or next week?' across follow-ups is a 3-4. "
            "Score 7+ if the CTA is specific, distinct from earlier asks, and easy to act on."
        ),
        "clarity": (
            "**clarity** — Is the message concise and easy to read? "
            "Does it avoid spam tropes (excessive urgency, ALL CAPS, clickbait)? "
            "A short, clear follow-up scores well here."
        ),
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
