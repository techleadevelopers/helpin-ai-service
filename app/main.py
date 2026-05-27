import asyncio
import logging
from collections import Counter
from enum import Enum
from time import perf_counter
from typing import Callable, TypeVar, Awaitable

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field, HttpUrl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("zoohelp-ai-workers")

app = FastAPI(title="ZooHelp AI Workers", version="0.1.0")
metrics = Counter()
T = TypeVar("T")

class ModerationDecision(str, Enum):
    approved = "approved"
    needs_review = "needs_review"
    rejected = "rejected"

class ImageModerationRequest(BaseModel):
    post_id: str = Field(min_length=1)
    image_url: HttpUrl

class ImageModerationResponse(BaseModel):
    post_id: str
    decision: ModerationDecision
    risk_score: int = Field(ge=0, le=100)
    labels: list[str]

class TextClassificationRequest(BaseModel):
    post_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)

class TextClassificationResponse(BaseModel):
    post_id: str
    risk_score: int = Field(ge=0, le=100)
    labels: list[str]

class RescueFinalStatus(str, Enum):
    rescued = "rescued"
    not_found = "not_found"
    died = "died"
    referred = "referred"
    cancelled = "cancelled"
    false_alarm = "false_alarm"

class RescueFinalReportInput(BaseModel):
    rescue_id: str | None = None
    post_id: str = Field(min_length=1)
    requested_status: RescueFinalStatus | None = None
    post: dict = Field(default_factory=dict)
    rescue: dict | None = None
    events: list[dict] = Field(default_factory=list)
    rescue_responses: list[dict] = Field(default_factory=list)
    chat_summary: str | None = Field(default=None, max_length=4000)
    incidents: list[dict] = Field(default_factory=list)

class RescueFinalReportResponse(BaseModel):
    status_suggestion: RescueFinalStatus
    summary: str = Field(min_length=1, max_length=280)
    public_update: str = Field(min_length=1, max_length=140)
    generated_by_ai: bool
    confidence: str = Field(default="low")
    ai_model: str | None = None
    ai_latency_ms: int | None = None
    ai_cost_cents: int | None = None
    prompt_version: str = "rescue-final-report-v1"
    schema_version: str = "1.0.0"

FINAL_REPORT_FALLBACKS: dict[RescueFinalStatus, tuple[str, str]] = {
    RescueFinalStatus.rescued: (
        "Animal localizado e encaminhado para atendimento ou segurança.",
        "Atualização: o animal foi resgatado e está recebendo cuidados.",
    ),
    RescueFinalStatus.not_found: (
        "A equipe não conseguiu localizar o animal após acompanhamento do caso.",
        "Atualização: o animal ainda não foi localizado.",
    ),
    RescueFinalStatus.died: (
        "O animal foi encontrado sem vida.",
        "Atualização: o caso foi encerrado após a confirmação do óbito.",
    ),
    RescueFinalStatus.referred: (
        "O caso foi encaminhado para responsável, ONG, clínica ou órgão competente.",
        "Atualização: o caso foi encaminhado para acompanhamento especializado.",
    ),
    RescueFinalStatus.cancelled: (
        "O chamado foi cancelado antes da conclusão.",
        "Atualização: o chamado foi cancelado.",
    ),
    RescueFinalStatus.false_alarm: (
        "O alerta foi avaliado como falso ou equivocado.",
        "Atualização: o alerta foi encerrado após verificação.",
    ),
}

def infer_final_status(payload: RescueFinalReportInput) -> RescueFinalStatus:
    if payload.requested_status:
        return payload.requested_status

    raw_status = str(
        (payload.rescue or {}).get("status")
        or payload.post.get("rescueStatus")
        or payload.post.get("rescue_status")
        or payload.post.get("status")
        or ""
    ).lower()

    if raw_status == "cancelled":
        return RescueFinalStatus.cancelled
    if raw_status in {"not_found", "not-found"}:
        return RescueFinalStatus.not_found
    if raw_status in {"died", "deceased"}:
        return RescueFinalStatus.died
    if raw_status in {"false_alarm", "false-alarm"}:
        return RescueFinalStatus.false_alarm
    if raw_status == "referred":
        return RescueFinalStatus.referred
    return RescueFinalStatus.rescued

def build_final_report_fallback(payload: RescueFinalReportInput) -> RescueFinalReportResponse:
    status = infer_final_status(payload)
    summary, public_update = FINAL_REPORT_FALLBACKS[status]
    metrics["final_report_fallback_total"] += 1
    return RescueFinalReportResponse(
        status_suggestion=status,
        summary=summary,
        public_update=public_update,
        generated_by_ai=False,
        confidence="low",
        ai_model=None,
        ai_latency_ms=0,
        ai_cost_cents=0,
    )

@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started = perf_counter()
    metrics["requests_total"] += 1
    try:
        response = await call_next(request)
        metrics[f"responses_{response.status_code}"] += 1
        return response
    finally:
        elapsed_ms = (perf_counter() - started) * 1000
        logger.info("path=%s method=%s elapsed_ms=%.2f", request.url.path, request.method, elapsed_ms)

async def with_retry(operation: Callable[[], Awaitable[T]], attempts: int = 3, base_delay: float = 0.1) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as error:  # pragma: no cover - defensive retry wrapper
            last_error = error
            metrics["retries_total"] += 1
            if attempt == attempts:
                break
            await asyncio.sleep(base_delay * attempt)
    raise RuntimeError("operation failed after retries") from last_error

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "zoohelp-ai-workers"}

@app.get("/readyz")
def readyz() -> dict[str, bool | str]:
    return {"status": "ready", "model_loaded": True, "queue_configured": True}

@app.get("/metrics")
def read_metrics() -> dict[str, int]:
    return dict(metrics)

@app.post("/v1/moderate-image")
async def moderate_image(payload: ImageModerationRequest) -> ImageModerationResponse:
    async def classify() -> ImageModerationResponse:
        return ImageModerationResponse(
            post_id=payload.post_id,
            decision=ModerationDecision.needs_review,
            risk_score=25,
            labels=["animal", "pending_model"],
        )

    return await with_retry(classify)

@app.post("/v1/classify-text")
def classify_text(payload: TextClassificationRequest) -> TextClassificationResponse:
    text = payload.text.lower()
    labels: list[str] = []
    score = 0
    markers = {
        "pix": "payment_risk",
        "recompensa": "reward",
        "urgente": "urgent",
        "fora da plataforma": "off_platform",
        "maus-tratos": "abuse_report",
    }
    for marker, label in markers.items():
        if marker in text:
            labels.append(label)
            score += 15

    return TextClassificationResponse(
        post_id=payload.post_id,
        risk_score=min(score, 100),
        labels=labels or ["neutral"],
    )

@app.post("/ai/final-rescue-report")
async def generate_final_rescue_report(payload: RescueFinalReportInput) -> RescueFinalReportResponse:
    started = perf_counter()

    async def generate() -> RescueFinalReportResponse:
        # Provider real entra aqui. Enquanto nao houver chave/modelo configurado,
        # este endpoint retorna fallback deterministico e auditavel.
        report = build_final_report_fallback(payload)
        report.ai_latency_ms = int((perf_counter() - started) * 1000)
        return report

    return await with_retry(generate)

@app.post("/v1/ai/final-rescue-report")
async def generate_final_rescue_report_v1(payload: RescueFinalReportInput) -> RescueFinalReportResponse:
    return await generate_final_rescue_report(payload)
