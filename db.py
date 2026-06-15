import os
import json
import hashlib
import secrets
import datetime as _dt
from typing import Optional

from sqlalchemy import (create_engine, String, Integer, Float, Text, JSON,
                        ForeignKey, select, func, delete)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, sessionmaker)

import content

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "app.db")
DEFAULT_URL = f"sqlite:///{DB_PATH}"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_URL)


def _now():
    return _dt.datetime.utcnow().isoformat(timespec="seconds")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    salt: Mapped[str] = mapped_column(String(64))
    pw_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="student")
    token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(String(32))


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         primary_key=True)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    behavior: Mapped[dict] = mapped_column(JSON, default=dict)
    p_mastery: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32))


class ExamSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(16))
    subject: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    topic: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    started_at: Mapped[str] = mapped_column(String(32))
    finished_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    q_limit: Mapped[int] = mapped_column(Integer, default=25)


class Response(Base):
    __tablename__ = "responses"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(80))
    topic: Mapped[str] = mapped_column(String(80))
    question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    card_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    b: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correct: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    is_correct: Mapped[int] = mapped_column(Integer, default=0)
    theta_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    theta_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    action: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    misconception: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answered_at: Mapped[str] = mapped_column(String(32))


class SkillState(Base):
    __tablename__ = "skill_states"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    subject: Mapped[str] = mapped_column(String(80), primary_key=True)
    topic: Mapped[str] = mapped_column(String(80), primary_key=True)
    theta: Mapped[float] = mapped_column(Float, default=0.0)
    se: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    theta_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32))


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(32))


class PlanItem(Base):
    __tablename__ = "plan_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    task: Mapped[str] = mapped_column(Text, default="")
    done: Mapped[int] = mapped_column(Integer, default=0)


class DB:
    def __init__(self, url=DATABASE_URL):
        self.url = url
        if url.startswith("sqlite"):
            os.makedirs(DATA_DIR, exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args, future=True)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.subjects = []
        self.topics = []
        self.questions = {}


def get_conn(url=DATABASE_URL):
    return DB(url)


def init_db(conn):
    Base.metadata.create_all(conn.engine)
    _merge_admin_taxonomy(conn)
    _seed_taxonomy(conn)
    _seed_questions(conn)
    _load_admin_questions(conn)
    ensure_admin(conn)


def _seed_taxonomy(conn):
    conn.subjects = []
    conn.topics = []
    sid = 0
    for subj, topics in content.SUBJECTS.items():
        sid += 1
        conn.subjects.append({"id": sid, "name": subj,
                              "icon": content.SUBJECT_ICON.get(subj, "")})
        for tp in topics:
            tid = len(conn.topics) + 1
            conn.topics.append({"id": tid, "subject_id": sid, "subject": subj,
                                "name": tp,
                                "concept": content.CONCEPTS.get((subj, tp), "")})


def _seed_questions(conn):
    for card in content.curated_cards():
        upsert_question(conn, card)


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(salt), 120_000).hex()


def new_token():
    return secrets.token_urlsafe(24)


def ensure_admin(conn):
    with conn.Session() as s:
        exists = s.scalar(select(func.count()).select_from(User).where(User.role == "admin"))
        if exists:
            return
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "admin123")
        if s.scalar(select(User).where(User.username == username.lower())):
            return
        salt = secrets.token_hex(16)
        u = User(username=username.lower(), name="Администратор", salt=salt,
                 pw_hash=_hash_password(password, salt), role="admin",
                 token=None, created_at=_now())
        s.add(u)
        s.commit()


def _acc_dict(u, with_token=False):
    d = {"user_id": u.id, "name": u.name, "username": u.username, "role": u.role}
    if with_token:
        d["token"] = u.token
    return d


def get_account_by_username(conn, username):
    with conn.Session() as s:
        u = s.scalar(select(User).where(User.username == (username or "").strip().lower()))
        return _acc_dict(u, with_token=True) if u else None


def get_account_by_token(conn, token):
    if not token:
        return None
    with conn.Session() as s:
        u = s.scalar(select(User).where(User.token == token))
        return _acc_dict(u) if u else None


def create_account(conn, username, password, name=None):
    username = (username or "").strip()
    if len(username) < 3:
        raise ValueError("Логин должен быть не короче 3 символов.")
    if len(password or "") < 4:
        raise ValueError("Пароль должен быть не короче 4 символов.")
    key = username.lower()
    with conn.Session() as s:
        if s.scalar(select(User).where(User.username == key)):
            raise ValueError("Такой логин уже занят.")
        salt = secrets.token_hex(16)
        token = new_token()
        u = User(username=key, name=name or username, salt=salt,
                 pw_hash=_hash_password(password, salt), role="student",
                 token=token, created_at=_now())
        s.add(u)
        s.commit()
        return {"user_id": u.id, "name": u.name, "username": u.username,
                "role": u.role, "token": token}


def verify_credentials(conn, username, password):
    with conn.Session() as s:
        u = s.scalar(select(User).where(User.username == (username or "").strip().lower()))
        if not u or _hash_password(password or "", u.salt) != u.pw_hash:
            return None
        u.token = new_token()
        s.commit()
        return {"user_id": u.id, "name": u.name, "username": u.username,
                "role": u.role, "token": u.token}


def get_user_role(conn, user_id):
    with conn.Session() as s:
        u = s.get(User, user_id)
        return u.role if u else None


def create_user(conn, name):
    with conn.Session() as s:
        salt = secrets.token_hex(16)
        u = User(username=f"guest_{secrets.token_hex(4)}", name=name, salt=salt,
                 pw_hash="", role="student", token=None, created_at=_now())
        s.add(u)
        s.commit()
        return u.id


def get_user(conn, user_id):
    with conn.Session() as s:
        u = s.get(User, user_id)
        return _acc_dict(u) if u else None


def save_profile(conn, user_id, features=None, behavior=None, p_mastery=None):
    with conn.Session() as s:
        p = s.get(Profile, user_id)
        if p is None:
            p = Profile(user_id=user_id)
            s.add(p)
        p.features = features or {}
        p.behavior = behavior or {}
        p.p_mastery = p_mastery
        p.updated_at = _now()
        s.commit()


def get_profile(conn, user_id):
    with conn.Session() as s:
        p = s.get(Profile, user_id)
        if not p:
            return None
        return {"features": p.features or {}, "behavior": p.behavior or {},
                "p_mastery": p.p_mastery}


def has_profile(conn, user_id):
    with conn.Session() as s:
        return s.get(Profile, user_id) is not None


def list_subjects(conn):
    return [dict(s) for s in conn.subjects]


def list_topics(conn, subject):
    return [dict(t) for t in conn.topics if t["subject"] == subject]


def upsert_question(conn, card):
    if card.card_id in conn.questions:
        return
    conn.questions[card.card_id] = {
        "id": len(conn.questions) + 1,
        "subject": card.subject, "topic": card.topic,
        "difficulty": card.difficulty, "b": card.b,
        "question": card.question,
        "options": json.dumps(card.options, ensure_ascii=False),
        "correct": card.correct_answer,
        "explanation": card.explanation, "common_mistake": card.common_mistake,
        "concept": card.concept, "source": card.source,
        "card_id": card.card_id, "created_at": _now()}


def fetch_questions(conn, subject, topic=None, difficulty=None, exclude_card_ids=None):
    exclude = set(exclude_card_ids or [])
    out = []
    for q in conn.questions.values():
        if q["subject"] != subject:
            continue
        if topic and q["topic"] != topic:
            continue
        if difficulty and q["difficulty"] != difficulty:
            continue
        if q["card_id"] in exclude:
            continue
        out.append(dict(q))
    return out


def _sess_d(x):
    return {"id": x.id, "user_id": x.user_id, "scope": x.scope,
            "subject": x.subject, "topic": x.topic, "started_at": x.started_at,
            "finished_at": x.finished_at, "status": x.status, "q_limit": x.q_limit}


def create_session(conn, user_id, scope, subject=None, topic=None, q_limit=25):
    with conn.Session() as s:
        x = ExamSession(user_id=user_id, scope=scope, subject=subject, topic=topic,
                        started_at=_now(), status="active", q_limit=q_limit)
        s.add(x)
        s.commit()
        return x.id


def get_session(conn, session_id):
    with conn.Session() as s:
        x = s.get(ExamSession, session_id)
        return _sess_d(x) if x else None


def session_owner(conn, session_id):
    with conn.Session() as s:
        x = s.get(ExamSession, session_id)
        return x.user_id if x else None


def finish_session(conn, session_id):
    with conn.Session() as s:
        x = s.get(ExamSession, session_id)
        if x:
            x.status = "finished"
            x.finished_at = _now()
            s.commit()


def session_response_count(conn, session_id):
    with conn.Session() as s:
        return s.scalar(select(func.count()).select_from(Response)
                        .where(Response.session_id == session_id)) or 0


def session_used_card_ids(conn, session_id):
    with conn.Session() as s:
        rows = s.scalars(select(Response.card_id).where(Response.session_id == session_id)).all()
        return {c for c in rows if c}


def session_topic_question_texts(conn, session_id, subject, topic, limit=6):
    with conn.Session() as s:
        rows = s.scalars(
            select(Response.question)
            .where(Response.session_id == session_id,
                   Response.subject == subject,
                   Response.topic == topic,
                   Response.question.isnot(None))
            .order_by(Response.id.desc())
            .limit(limit)
        ).all()
    return [q for q in rows if q]


def session_topics(conn, session_id):
    with conn.Session() as s:
        rows = s.execute(select(Response.subject, Response.topic)
                         .where(Response.session_id == session_id)).all()
        return {(r[0], r[1]) for r in rows}


def session_answer_stats(conn, session_id):
    with conn.Session() as s:
        answered = s.scalar(select(func.count()).select_from(Response)
                            .where(Response.session_id == session_id)) or 0
        correct = s.scalar(select(func.coalesce(func.sum(Response.is_correct), 0))
                           .where(Response.session_id == session_id)) or 0
        return {"answered": int(answered), "correct": int(correct)}


def user_sessions(conn, user_id, limit=20):
    with conn.Session() as s:
        rows = s.scalars(select(ExamSession).where(ExamSession.user_id == user_id)
                         .order_by(ExamSession.id.desc()).limit(limit)).all()
        return [_sess_d(x) for x in rows]


def _resp_d(r):
    return {"id": r.id, "session_id": r.session_id, "user_id": r.user_id,
            "subject": r.subject, "topic": r.topic, "question": r.question,
            "card_id": r.card_id, "difficulty": r.difficulty, "b": r.b,
            "answer": r.answer, "correct": r.correct, "is_correct": r.is_correct,
            "theta_before": r.theta_before, "theta_after": r.theta_after,
            "action": r.action, "misconception": r.misconception,
            "answered_at": r.answered_at}


def record_response(conn, session_id, user_id, card, answer, is_correct,
                    theta_before, theta_after, action, misconception):
    with conn.Session() as s:
        r = Response(
            session_id=session_id, user_id=user_id,
            subject=card.subject, topic=card.topic, question=card.question,
            card_id=card.card_id, difficulty=card.difficulty, b=card.b,
            answer=answer, correct=card.correct_answer, is_correct=int(is_correct),
            theta_before=theta_before, theta_after=theta_after, action=action,
            misconception=json.dumps(misconception, ensure_ascii=False) if misconception else None,
            answered_at=_now())
        s.add(r)
        s.commit()


def session_responses(conn, session_id):
    with conn.Session() as s:
        rows = s.scalars(select(Response).where(Response.session_id == session_id)
                         .order_by(Response.id)).all()
        return [_resp_d(r) for r in rows]


def user_responses(conn, user_id, subject=None, topic=None):
    with conn.Session() as s:
        q = select(Response).where(Response.user_id == user_id)
        if subject:
            q = q.where(Response.subject == subject)
        if topic:
            q = q.where(Response.topic == topic)
        rows = s.scalars(q.order_by(Response.id)).all()
        return [_resp_d(r) for r in rows]


def _state_d(x):
    return {"user_id": x.user_id, "subject": x.subject, "topic": x.topic,
            "theta": x.theta, "se": x.se, "attempts": x.attempts,
            "correct": x.correct, "theta_history": x.theta_history,
            "updated_at": x.updated_at}


def save_skill_state(conn, user_id, subject, topic, theta, se, attempts, correct, theta_history):
    with conn.Session() as s:
        x = s.get(SkillState, (user_id, subject, topic))
        if x is None:
            x = SkillState(user_id=user_id, subject=subject, topic=topic)
            s.add(x)
        x.theta = theta
        x.se = se
        x.attempts = attempts
        x.correct = correct
        x.theta_history = json.dumps(theta_history)
        x.updated_at = _now()
        s.commit()


def get_skill_state(conn, user_id, subject, topic):
    with conn.Session() as s:
        x = s.get(SkillState, (user_id, subject, topic))
        return _state_d(x) if x else None


def user_skill_states(conn, user_id, subject=None):
    with conn.Session() as s:
        q = select(SkillState).where(SkillState.user_id == user_id)
        if subject:
            q = q.where(SkillState.subject == subject)
        return [_state_d(x) for x in s.scalars(q).all()]


def create_plan(conn, user_id, session_id, body, items):
    with conn.Session() as s:
        p = Plan(user_id=user_id, session_id=session_id, body=body, created_at=_now())
        s.add(p)
        s.flush()
        for it in items:
            s.add(PlanItem(plan_id=p.id, day=it.get("day"), task=it.get("task", ""), done=0))
        s.commit()
        return p.id


def _plan_d(conn, s, p):
    items = s.scalars(select(PlanItem).where(PlanItem.plan_id == p.id)
                      .order_by(PlanItem.id)).all()
    return {"id": p.id, "user_id": p.user_id, "session_id": p.session_id,
            "body": p.body or {}, "created_at": p.created_at,
            "items": [{"id": i.id, "plan_id": i.plan_id, "day": i.day,
                       "task": i.task, "done": i.done} for i in items]}


def get_plan(conn, plan_id):
    with conn.Session() as s:
        p = s.get(Plan, plan_id)
        return _plan_d(conn, s, p) if p else None


def latest_plan(conn, user_id):
    with conn.Session() as s:
        p = s.scalar(select(Plan).where(Plan.user_id == user_id)
                     .order_by(Plan.id.desc()).limit(1))
        return _plan_d(conn, s, p) if p else None


def plan_for_session(conn, session_id):
    with conn.Session() as s:
        p = s.scalar(select(Plan).where(Plan.session_id == session_id)
                     .order_by(Plan.id.desc()).limit(1))
        return _plan_d(conn, s, p) if p else None


def set_plan_item_done(conn, item_id, done):
    with conn.Session() as s:
        it = s.get(PlanItem, item_id)
        if it:
            it.done = int(bool(done))
            s.commit()


def admin_list_users(conn):
    with conn.Session() as s:
        users = s.scalars(select(User).order_by(User.id)).all()
        out = []
        for u in users:
            answered = s.scalar(select(func.count()).select_from(Response)
                                .where(Response.user_id == u.id)) or 0
            correct = s.scalar(select(func.coalesce(func.sum(Response.is_correct), 0))
                               .where(Response.user_id == u.id)) or 0
            n_sessions = s.scalar(select(func.count()).select_from(ExamSession)
                                  .where(ExamSession.user_id == u.id)) or 0
            avg_theta = s.scalar(select(func.avg(SkillState.theta))
                                 .where(SkillState.user_id == u.id))
            out.append({
                "user_id": u.id, "username": u.username, "name": u.name,
                "role": u.role, "created_at": u.created_at,
                "sessions": int(n_sessions), "answered": int(answered),
                "correct": int(correct),
                "accuracy": round(100.0 * correct / answered, 1) if answered else 0.0,
                "avg_theta": round(float(avg_theta), 3) if avg_theta is not None else None,
            })
        return out


def admin_overview(conn):
    with conn.Session() as s:
        n_students = s.scalar(select(func.count()).select_from(User)
                              .where(User.role == "student")) or 0
        n_sessions = s.scalar(select(func.count()).select_from(ExamSession)) or 0
        n_finished = s.scalar(select(func.count()).select_from(ExamSession)
                              .where(ExamSession.status == "finished")) or 0
        answered = s.scalar(select(func.count()).select_from(Response)) or 0
        correct = s.scalar(select(func.coalesce(func.sum(Response.is_correct), 0))) or 0

        rows = s.execute(
            select(SkillState.subject, SkillState.topic,
                   func.avg(SkillState.theta), func.sum(SkillState.attempts),
                   func.count())
            .group_by(SkillState.subject, SkillState.topic)).all()
        topics = [{"subject": r[0], "topic": r[1],
                   "avg_theta": round(float(r[2]), 3) if r[2] is not None else 0.0,
                   "attempts": int(r[3] or 0), "learners": int(r[4] or 0)}
                  for r in rows]
        topics.sort(key=lambda t: t["avg_theta"])
        return {
            "students": int(n_students), "sessions": int(n_sessions),
            "finished_sessions": int(n_finished),
            "answered": int(answered), "correct": int(correct),
            "accuracy": round(100.0 * correct / answered, 1) if answered else 0.0,
            "weakest_topics": topics[:8],
            "strongest_topics": list(reversed(topics))[:8] if topics else [],
        }


def delete_user(conn, user_id):
    with conn.Session() as s:
        u = s.get(User, user_id)
        if not u or u.role == "admin":
            return False
        s.execute(delete(Response).where(Response.user_id == user_id))
        s.execute(delete(SkillState).where(SkillState.user_id == user_id))
        s.execute(delete(PlanItem).where(PlanItem.plan_id.in_(
            select(Plan.id).where(Plan.user_id == user_id))))
        s.execute(delete(Plan).where(Plan.user_id == user_id))
        s.execute(delete(ExamSession).where(ExamSession.user_id == user_id))
        s.execute(delete(Profile).where(Profile.user_id == user_id))
        s.delete(u)
        s.commit()
        return True


from ai_core import B_BY_DIFFICULTY as _B_BY_DIFF


class AdminSubject(Base):
    __tablename__ = "admin_subjects"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    icon: Mapped[str] = mapped_column(String(8), default="📘")
    created_at: Mapped[str] = mapped_column(String(32))


class AdminTopic(Base):
    __tablename__ = "admin_topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(80))
    concept: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32))


class AdminQuestion(Base):
    __tablename__ = "admin_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(80), index=True)
    topic: Mapped[str] = mapped_column(String(80), index=True)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    correct: Mapped[str] = mapped_column(String(8))
    explanation: Mapped[str] = mapped_column(Text, default="")
    common_mistake: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="admin")
    status: Mapped[str] = mapped_column(String(16), default="approved")
    created_at: Mapped[str] = mapped_column(String(32))


def _merge_admin_taxonomy(conn):
    with conn.Session() as s:
        for sub in s.scalars(select(AdminSubject)).all():
            content.SUBJECTS.setdefault(sub.name, [])
            if sub.icon:
                content.SUBJECT_ICON.setdefault(sub.name, sub.icon)
        for tp in s.scalars(select(AdminTopic)).all():
            content.SUBJECTS.setdefault(tp.subject, [])
            if tp.name not in content.SUBJECTS[tp.subject]:
                content.SUBJECTS[tp.subject].append(tp.name)
            if tp.concept:
                content.CONCEPTS[(tp.subject, tp.name)] = tp.concept


def _load_admin_questions(conn):
    with conn.Session() as s:
        for q in s.scalars(select(AdminQuestion).where(AdminQuestion.status == "approved")).all():
            cid = f"admin_{q.id}"
            opts = q.options if isinstance(q.options, str) else json.dumps(q.options, ensure_ascii=False)
            conn.questions[cid] = {
                "id": len(conn.questions) + 1, "subject": q.subject, "topic": q.topic,
                "difficulty": q.difficulty, "b": _B_BY_DIFF.get(q.difficulty, 0.0),
                "question": q.question, "options": opts, "correct": q.correct,
                "explanation": q.explanation or "", "common_mistake": q.common_mistake or "",
                "concept": content.CONCEPTS.get((q.subject, q.topic), ""),
                "source": q.source or "admin", "card_id": cid, "created_at": q.created_at}


def reload_custom_content(conn):
    _merge_admin_taxonomy(conn)
    _seed_taxonomy(conn)
    _load_admin_questions(conn)


def add_subject(conn, name, icon="📘"):
    name = (name or "").strip()
    if not name:
        raise ValueError("Название предмета пустое.")
    with conn.Session() as s:
        if s.get(AdminSubject, name) or name in content.SUBJECTS:
            raise ValueError("Такой предмет уже существует.")
        s.add(AdminSubject(name=name, icon=icon or "📘", created_at=_now()))
        s.commit()
    reload_custom_content(conn)
    return name


def add_topic(conn, subject, topic, concept=""):
    subject = (subject or "").strip()
    topic = (topic or "").strip()
    if not subject or not topic:
        raise ValueError("Укажите предмет и тему.")
    if topic in content.SUBJECTS.get(subject, []):
        raise ValueError("Такая тема уже существует в этом предмете.")
    with conn.Session() as s:
        s.add(AdminTopic(subject=subject, name=topic, concept=concept or "", created_at=_now()))
        s.commit()
    reload_custom_content(conn)
    return topic


def add_question(conn, subject, topic, difficulty, question, options, correct,
                 explanation="", common_mistake="", source="admin", status="approved"):
    if not question or not options or correct is None:
        raise ValueError("Вопрос, варианты и правильный ответ обязательны.")
    if difficulty not in _B_BY_DIFF:
        difficulty = "medium"
    correct = str(correct).strip().lower()[:1]
    with conn.Session() as s:
        q = AdminQuestion(subject=subject, topic=topic, difficulty=difficulty,
                          question=question.strip(), options=list(options), correct=correct,
                          explanation=explanation or "", common_mistake=common_mistake or "",
                          source=source, status=status, created_at=_now())
        s.add(q)
        s.commit()
        qid = q.id
    if status == "approved":
        reload_custom_content(conn)
    return qid


def list_admin_questions(conn, subject=None, topic=None, status=None):
    with conn.Session() as s:
        q = select(AdminQuestion)
        if subject:
            q = q.where(AdminQuestion.subject == subject)
        if topic:
            q = q.where(AdminQuestion.topic == topic)
        if status:
            q = q.where(AdminQuestion.status == status)
        rows = s.scalars(q.order_by(AdminQuestion.id.desc())).all()
        return [{"id": r.id, "subject": r.subject, "topic": r.topic, "difficulty": r.difficulty,
                 "question": r.question, "options": r.options, "correct": r.correct,
                 "explanation": r.explanation, "common_mistake": r.common_mistake,
                 "source": r.source, "status": r.status, "created_at": r.created_at} for r in rows]


def count_topic_questions(conn, subject, topic, status="approved"):
    with conn.Session() as s:
        return s.scalar(select(func.count()).select_from(AdminQuestion)
                        .where(AdminQuestion.subject == subject,
                               AdminQuestion.topic == topic,
                               AdminQuestion.status == status)) or 0


def set_question_status(conn, qid, status):
    with conn.Session() as s:
        q = s.get(AdminQuestion, qid)
        if not q:
            return False
        q.status = status
        s.commit()
    reload_custom_content(conn)
    return True


def delete_admin_question(conn, qid):
    with conn.Session() as s:
        q = s.get(AdminQuestion, qid)
        if not q:
            return False
        s.delete(q)
        s.commit()
    return True
