"""
Best-effort API call logging utility.
Writes to api_call_logs table without blocking the caller.
"""
import logging
logger = logging.getLogger(__name__)

COST_RATES = {
    "gemma":    {"in": 0.10,  "out": 0.40},   # OpenRouter gemma-4-31b $/1M tokens
    "claude":   {"in": 3.00,  "out": 15.00},
    "gemini":   {"in": 0.075, "out": 0.30},
}


def log_api_call(
    call_type: str,
    provider: str,
    model: str = None,
    tokens_input: int = None,
    tokens_output: int = None,
) -> None:
    """
    Best-effort: log an API call to api_call_logs. Never raises.
    call_type: "kb_chat" | "compliance_format" | "query_expansion"
    provider: "gemma" | "gemini" | "claude"
    """
    try:
        rate = COST_RATES.get(provider, {"in": 0, "out": 0})
        inp = tokens_input or 0
        out = tokens_output or 0
        cost_usd = (inp / 1_000_000) * rate["in"] + (out / 1_000_000) * rate["out"]

        from app.database import SessionLocal
        from app.models import APICallLog
        db = SessionLocal()
        try:
            entry = APICallLog(
                call_type=call_type,
                provider=provider,
                model=model,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost_usd if (inp or out) else None,
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug("[api_logger] Failed to log call: %s", exc)
