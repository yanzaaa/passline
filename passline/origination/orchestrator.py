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
        
    async def run(self, media_bytes: bytes, mime_type: str, source_language: str):
        self.status = "transcribing"
        client = Client()
        try:
            segments = await transcribe_media(media_bytes, mime_type, client)
            self.status = "building_cues"
            
            source_cues = build_cues(segments, language=source_language)
            
            self.status = "translating"
            for lang in LANGUAGES:
                await asyncio.sleep(2) # stagger
                asyncio.create_task(self._process_language(lang, source_cues, client))
                
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
            await runner.run_delivery(
                srt_bytes=srt_bytes,
                language=lang,
                delivery_id=delivery_id,
                parent_id=self.job_id
            )
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
