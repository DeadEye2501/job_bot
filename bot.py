import os
import re
import random
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.handlers import MessageHandler
from config import get_logger, session_scope
from models import Chat, Filter, Vacancy, HR, Answer, Statistic

load_dotenv()

logger = get_logger(__name__)


USERNAME_IGNORE_LIST = [
    "best_itjob",
    "it_rab",
    "freeIT_job",
]


class JobBot:
    def __init__(self):
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.phone_number = os.getenv("PHONE_NUMBER")
        self.password = os.getenv("PASSWORD")
        self.threshold = int(os.getenv("THRESHOLD", "10"))
        self.host_username = os.getenv("HOST_USERNAME")
        self.send_delay = int(os.getenv("SEND_DELAY", "300"))
        self.statistics_id = self._setup_statistics()
        self.client = self._setup_client()
        self._setup_handlers()

    def _setup_statistics(self):
        with session_scope() as session:
            statistic = session.query(Statistic).first()
            if not statistic:
                statistic = Statistic()
                session.add(statistic)
                session.commit()
            return statistic.id

    def _setup_client(self):
        sessions_dir = "sessions"
        os.makedirs(sessions_dir, exist_ok=True)
        return Client(
            "job_bot",
            api_id=self.api_id,
            api_hash=self.api_hash,
            workdir=sessions_dir,
            phone_number=self.phone_number,
            password=self.password,
        )
    
    def _setup_handlers(self):
        self.client.add_handler(MessageHandler(self._handle_message))

    async def _handle_message(self, client, message):
        with session_scope() as session:
            if message.chat.type == ChatType.PRIVATE:
                hr = session.query(HR).filter(
                    HR.telegram_id == message.from_user.id
                ).first()
                if hr:
                    vacancy = session.query(Vacancy).filter(
                        Vacancy.hr_id == hr.id
                    ).order_by(Vacancy.created_at.desc()).first()
                    if vacancy and not vacancy.replied_at:
                        vacancy.replied_at = datetime.now()
                        session.commit()
                        self._update_statistics(replied_vacancies=1)
                        message_text = message.text or message.caption or ""
                        hr_link = f"https://t.me/{hr.username}" if hr.username else "no username"
                        notification = f"Ответ от HR @{hr.username}:\n\n{message_text}"
                        if vacancy:
                            notification += f"\n\n**Контакт HR:** [{hr.username}]({hr_link})"
                            notification += f"\n**Вакансия:** {vacancy.title} ({vacancy.score} баллов)"
                            notification += f"\n\n```\n{vacancy.text}\n```"
                        await self._notify_host(notification)
                        logger.info(f"Forwarded message from HR @{hr.username} to host")
                    return
            elif message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                chat = session.query(Chat).filter(
                    Chat.telegram_id == message.chat.id
                ).first()
                if not chat:
                    chat = Chat(
                        telegram_id=message.chat.id,
                        title=message.chat.title or "Unknown",
                        is_active=False
                    )
                    session.add(chat)
                    session.commit()
                    logger.info(f"Added new chat to database: {chat.title} (id: {chat.telegram_id})")
                    return
                if not chat.is_active:
                    return
                message_text = message.text or message.caption or ""
                score = await self._validate_vacancy(message_text, session)
                if score == -1:
                    return
                vacancy = await self._save_vacancy(message_text, chat.id, score, session)
                await self._apply_vacancy(vacancy)
                return
            else:
                logger.info(f"Unknown chat type: {message.chat.type}")
                return

    async def _validate_vacancy(self, text, session):
        filters = session.query(Filter).filter(Filter.is_active == True).all()
        normalized_text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = set(re.findall(r'\b\w+\b', normalized_text))
        total_weight = 0
        found_filters = set()
        for filter_text in filters:
            if filter_text.id in found_filters:
                continue
            normalized_filter = re.sub(r'[^\w\s]', ' ', filter_text.text.lower()).strip()
            filter_words = set(re.findall(r'\b\w+\b', normalized_filter))
            if filter_words and filter_words.issubset(words):
                total_weight += filter_text.weight
                found_filters.add(filter_text.id)
        return total_weight if total_weight >= self.threshold else -1

    async def _save_vacancy(self, text, chat_id, score, session):
        hr = await self._get_hr(text, session)
        title = text.split('\n')[0][:255].rstrip(' :;-')
        vacancy = Vacancy(
            title=title,
            text=text,
            score=score,
            chat_id=chat_id,
            hr_id=hr.id if hr else None
        )
        session.add(vacancy)
        session.commit()
        return vacancy

    async def _get_hr(self, text, session):
        hr_username = await self._get_hr_username(text)
        if not hr_username:
            return None
        hr = session.query(HR).filter(HR.username == hr_username).first()
        if hr:
            return hr
        try:
            user = await self.client.get_users(hr_username)
            if not user:
                logger.warning(f"User @{hr_username} not found")
                return None
            hr = session.query(HR).filter(HR.telegram_id == user.id).first()
            if hr:
                if not hr.username or hr.username != user.username:
                    hr.username = user.username
                    session.commit()
                return hr
            hr = HR(
                telegram_id=user.id,
                username=user.username,
                phone=user.phone_number,
                first_name=user.first_name,
                last_name=user.last_name
            )
            session.add(hr)
            session.commit()
            return hr
        except Exception as e:
            logger.warning(f"Failed to get user info for @{hr_username}: {e}")
            return
    
    async def _get_hr_username(self, text):
        matches = re.findall(r'@([a-zA-Z0-9_]{5,32})', text)
        for username in matches:
            if username.lower() not in [u.lower() for u in USERNAME_IGNORE_LIST]:
                return username
        return None
    
    async def _apply_vacancy(self, vacancy):
        logger.info(f"Applying vacancy: {vacancy.id} - {vacancy.title}")
        if not vacancy.hr:
            notification = f"**Интересная вакансия без контакта HR**"
            notification += f"\n**Вакансия:** {vacancy.title} ({vacancy.score} баллов)"
            notification += f"\n\n```\n{vacancy.text}\n```"
            await self._notify_host(notification)
            self._update_statistics(applied_to_host=1)
            logger.info(f"Notified host about vacancy: {vacancy.id} - {vacancy.title}")
        else:
            with session_scope() as session:
                answers = session.query(Answer).filter(Answer.is_active == True).all()
                if not answers:
                    logger.warning("No active answers found")
                    return
                answer = random.choice(answers)
                message_text = self._format_answer(answer, vacancy)
                await asyncio.sleep(self.send_delay)
                resume_path = self._get_resume_path()
                await self._notify_hr(vacancy.hr.telegram_id, message_text, resume_path)
                self._update_statistics(applied_to_hr=1)
                logger.info(f"Notified HR @{vacancy.hr.username} about vacancy: {vacancy.id} - {vacancy.title}")

    def _format_answer(self, answer, vacancy):
        message_text = answer.text.replace("{vacancy_title}", vacancy.title)
        return message_text

    async def _notify_hr(self, hr_id, text, document=None):
        user = await self.client.get_users(hr_id)
        if document:
            await self.client.send_document(user.id, document, caption=text)
        else:
            await self.client.send_message(user.id, text)

    async def _notify_host(self, text):
        user = await self.client.get_users(self.host_username)
        await self.client.send_message(user.id, text, parse_mode="md")
    
    def _get_resume_path(self):
        files_dir = Path("files")
        if not files_dir.exists():
            logger.warning("Files directory not found")
            return None
        resume_files = list(files_dir.glob("*.pdf"))
        if not resume_files:
            logger.warning("No PDF resume found in files directory")
            return None
        return str(resume_files[0])
    
    def _update_statistics(self, applied_to_hr=0, applied_to_host=0, replied_vacancies=0):
        with session_scope() as session:
            statistic = session.query(Statistic).filter(
                Statistic.id == self.statistics_id
            ).first()
            if statistic:
                statistic.applied_to_hr += applied_to_hr
                statistic.applied_to_host += applied_to_host
                statistic.replied_vacancies += replied_vacancies
                statistic.updated_at = datetime.now()
                session.commit()

    async def start(self):
        await self.client.start()

    async def stop(self):
        await self.client.stop()
