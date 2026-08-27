import asyncio
import uuid
import logging
from google.genai import Client

from passline.origination.transcriber import transcribe_media
from passline.origination.cue_builder import build_cues
from passline.origination.translator import translate_cues
from passline.io.srt import write_srt
from passline.pipeline.runner import PipelineRunner
from passline.events.bus import EventBus
from passline.pipeline.approval import approval_queue as _approval_queue

logger = logging.getLogger(__name__)

LANGUAGES = ["en", "fr", "de", "es", "ru", "pt", "zh", "fa"]

JOBS = {}
TASKS = {}

class OriginationJob:
    def __init__(self, job_id: str, bus: EventBus):
        self.job_id = job_id
        self.bus = bus
        self.status = "pending"
        self.error = None
        
    async def run(self, media_bytes: bytes, mime_type: str, source_language: str, client: Client | None = None):
        self.status = "transcribing"
        client = client or Client()
        try:
            segments = await transcribe_media(media_bytes, mime_type, client)
            self.status = "building_cues"
            
            source_cues = build_cues(segments, language=source_language)
            
            self.status = "translating"
            sem = asyncio.Semaphore(3)
            
            async def _run_with_sem(lang):
                async with sem:
                    await self._process_language(lang, source_cues, client)
                    
            tasks = []
            for lang in LANGUAGES:
                tasks.append(asyncio.create_task(_run_with_sem(lang)))
            
            await asyncio.gather(*tasks)
            self.status = "completed"
        except Exception as e:
            logger.exception("Origination job failed")
            self.status = "failed"
            self.error = str(e)
            
    async def _process_language(self, lang: str, source_cues, client):
        try:
            translated = await translate_cues(source_cues, target_language=lang, client=client)
            srt_bytes = write_srt(translated)
            delivery_id = str(uuid.uuid4())
            runner = PipelineRunner(bus=self.bus, approval_queue=_approval_queue)
            
            import os
            import asyncio
            from passline.events.bus import DeliveryEvent, EventType
            
            timeout_s = float(os.getenv("PASSLINE_PIPELINE_TIMEOUT", "240.0"))
            
            pipeline_task = asyncio.create_task(
                runner.run_delivery(
                    srt_bytes=srt_bytes,
                    language=lang,
                    delivery_id=delivery_id,
                    parent_id=self.job_id
                )
            )
            
            done, pending = await asyncio.wait([pipeline_task], timeout=timeout_s)
            
            if pending:
                pipeline_task.cancel()
                logger.error(f"Delivery {delivery_id} for {lang} timed out in orchestrator")
                session_id = f"delivery-{delivery_id}"
                session = await runner._session_service.get_session(
                    app_name="passline",
                    user_id="pipeline",
                    session_id=session_id,
                )
                all_findings = []
                if session:
                    all_findings = session.state.get("all_findings", [])
                report = {
                    "delivery_id": delivery_id,
                    "language": lang,
                    "verdict": "failed",
                    "reason": "timeout",
                    "violations_found": {
                        "remaining_after_repair": len(all_findings),
                    },
                    "all_findings": all_findings,
                }
                self.bus.emit(DeliveryEvent(
                    event_type=EventType.DELIVERY_FAILED,
                    delivery_id=delivery_id,
                    language=lang,
                    details=report,
                ))
            else:
                try:
                    report = pipeline_task.result()
                    if not report or report.get("verdict") in (None, "unknown"):
                        self.bus.emit(DeliveryEvent(
                            event_type=EventType.DELIVERY_FAILED,
                            delivery_id=delivery_id,
                            language=lang,
                            details={
                                "delivery_id": delivery_id,
                                "language": lang,
                                "verdict": "failed",
                                "reason": "no_verdict",
                            }
                        ))
                except Exception as ex:
                    self.bus.emit(DeliveryEvent(
                        event_type=EventType.DELIVERY_FAILED,
                        delivery_id=delivery_id,
                        language=lang,
                        details={
                            "delivery_id": delivery_id,
                            "language": lang,
                            "verdict": "failed",
                            "reason": str(ex),
                        }
                    ))

        except Exception as e:
            logger.exception(f"Failed to process language {lang}")

def cancel_all_jobs():
    for job_id, task in TASKS.items():
        task.cancel()
    JOBS.clear()
    TASKS.clear()

def start_origination(media_bytes: bytes, mime_type: str, source_language: str, bus: EventBus) -> str:
    job_id = str(uuid.uuid4())
    job = OriginationJob(job_id, bus)
    JOBS[job_id] = job
    TASKS[job_id] = asyncio.create_task(job.run(media_bytes, mime_type, source_language))
    return job_id

def get_job_status(job_id: str) -> dict | None:
    job = JOBS.get(job_id)
    if not job:
        return None
    return {"status": job.status, "error": job.error}
