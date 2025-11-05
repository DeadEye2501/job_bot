from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from config import Base


class Filter(Base):
    __tablename__ = 'filters'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    text = Column(Text, nullable=False)
    weight = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)


class Answer(Base):
    __tablename__ = 'answers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    text = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)


class Chat(Base):
    __tablename__ = 'chats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, nullable=False)
    title = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)


class HR(Base):
    __tablename__ = 'hrs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, nullable=False)
    username = Column(String(255), nullable=True)
    phone = Column(String(16), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class Vacancy(Base):
    __tablename__ = 'vacancies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    text = Column(Text, nullable=False)
    hr_id = Column(Integer, ForeignKey('hrs.id'), nullable=True)
    chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)
    score = Column(Integer, default=0)
    replied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    hr = relationship('HR', backref='vacancies')
    chat = relationship('Chat', backref='vacancies')


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    chat = relationship('Chat', backref='messages')


class Statistic(Base):
    __tablename__ = 'statistics'

    id = Column(Integer, primary_key=True, autoincrement=True)
    applied_to_hr = Column(Integer, default=0)
    applied_to_host = Column(Integer, default=0)
    replied_vacancies = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
