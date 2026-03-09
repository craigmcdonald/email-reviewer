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
    "weight_value_proposition": 0.35,
    "weight_personalisation": 0.30,
    "weight_cta": 0.20,
    "weight_clarity": 0.15,
}
