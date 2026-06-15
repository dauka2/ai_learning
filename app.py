import os
import random
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import ai_core
import content
import misconception
import db
import analytics
import recommend

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Adaptive Learning (IRT + LPN)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
groq_client = None
if GROQ_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_KEY)
        logger.info("Groq client initialised (key from env).")
    except Exception as e:
        logger.warning(f"Groq init failed, offline mode: {e}")
else:
    logger.info("GROQ_API_KEY not set — offline mode (curated bank).")

LPN = ai_core.load_learner_profile_net(os.path.join(BASE_DIR, "model.pkl"))
RECOMMENDER = ai_core.RecommendationModel.load(os.path.join(BASE_DIR, "recommender.pkl"))
DETECTOR = misconception.MisconceptionDetector(groq_client)

conn = db.get_conn()
db.init_db(conn)
logger.info("DB ready at %s", db.DB_PATH)

ACTIVE = {}

ACTION_LABEL = {
    "REINFORCE": "Закрепляем тему",
    "PROGRESS": "Повышаем сложность",
    "CHALLENGE": "Сложный вызов",
    "MAINTAIN": "Подбор по уровню",
    "DIAGNOSTIC": "Диагностика",
    "FIXED": "Выбранный уровень",
}
DIFFICULTY_STARS = {"primary": "★", "easy": "★★", "medium": "★★★", "hard": "★★★★", "expert": "★★★★★"}


class CreateUserReq(BaseModel):
    name: str = "Студент"
    features: dict | None = None
    behavior: dict | None = None


class RegisterReq(BaseModel):
    username: str
    password: str
    name: str | None = None


class LoginReq(BaseModel):
    username: str
    password: str


class ProfileReq(BaseModel):
    features: dict | None = None
    behavior: dict | None = None


class StartSessionReq(BaseModel):
    user_id: int
    scope: str = "topic"
    subject: str | None = None
    topic: str | None = None
    q_limit: int = 25
    stage: str = "auto"


class AnswerReq(BaseModel):
    answer: str


class PlanItemReq(BaseModel):
    done: bool


class SubjectReq(BaseModel):
    name: str
    icon: str | None = "📘"


class TopicReq(BaseModel):
    subject: str
    topic: str
    concept: str | None = ""


class QuestionReq(BaseModel):
    subject: str
    topic: str
    difficulty: str = "medium"
    question: str
    options: list[str]
    correct: str
    explanation: str | None = ""
    common_mistake: str | None = ""


class GenReq(BaseModel):
    subject: str
    topic: str
    n: int = 5
    difficulty: str | None = None


MIN_QUESTIONS_BEFORE_GEN = 3


def _row_to_card(row):
    import json as _json
    return content.QuestionCard(
        question=row["question"], options=_json.loads(row["options"]),
        correct_answer=row["correct"], explanation=row["explanation"] or "",
        subject=row["subject"], topic=row["topic"], difficulty=row["difficulty"],
        source=row["source"] or "curated", common_mistake=row["common_mistake"] or "",
        concept=row["concept"] or content.CONCEPTS.get((row["subject"], row["topic"]), ""),
        card_id=row["card_id"])


def _shuffle_options(card):
    letters = "abcdefghij"
    opts = list(card.options or [])
    cur = (card.correct_answer or "").strip().lower()[:1]
    correct_idx = letters.find(cur)
    if len(opts) < 2 or not (0 <= correct_idx < len(opts)):
        return card
    positions = list(range(len(opts)))
    random.shuffle(positions)
    card.options = [opts[p] for p in positions]
    card.correct_answer = letters[positions.index(correct_idx)]
    return card


def _ensure_active(session_id):
    st = ACTIVE.get(session_id)
    if st:
        return st
    sess = db.get_session(conn, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    mgr = ai_core.IRTSkillManager()
    for s in db.user_skill_states(conn, sess["user_id"]):
        tr = mgr.tracker(s["subject"], s["topic"], s["theta"])
        tr.theta = s["theta"]
        tr.attempts = s["attempts"]
        tr.correct = s["correct"]
        try:
            import json as _json
            tr.theta_history = _json.loads(s["theta_history"]) or [s["theta"]]
        except Exception:
            tr.theta_history = [s["theta"]]
    st = {"mgr": mgr, "current": None, "last_correct": None, "last_misc": None, "stage": "auto"}
    ACTIVE[session_id] = st
    return st


def _seen_topics(session_id):
    return db.session_topics(conn, session_id)


def _next_topic(sess, st):
    scope = sess["scope"]
    if scope == "topic":
        return sess["subject"], sess["topic"]

    mgr = st["mgr"]
    seen = _seen_topics(sess["id"])
    if scope == "subject":
        topics = content.SUBJECTS.get(sess["subject"], [])
        unseen = [(sess["subject"], t) for t in topics if (sess["subject"], t) not in seen]
        if unseen:
            return unseen[0]
        weak = mgr.weakest_topic_in_subject(sess["subject"])
        return weak if weak else (sess["subject"], topics[0])

    all_pairs = [(s, t) for s, ts in content.SUBJECTS.items() for t in ts]
    unseen = [p for p in all_pairs if p not in seen]
    if unseen:
        return unseen[0]
    cand = {k: tr for k, tr in mgr.trackers.items() if tr.attempts > 0}
    if cand:
        return min(cand, key=lambda k: cand[k].theta)
    return all_pairs[0]


def _pick_question(subject, topic, difficulty, used_ids, rephrase, allowed=None, recent_questions=None):
    allowed = allowed or ai_core.DIFFICULTIES

    def pool_for(diff):
        return db.fetch_questions(conn, subject, topic, diff, exclude_card_ids=used_ids)

    pool = pool_for(difficulty)
    exact_missing = not pool
    if not pool:
        near = sorted(allowed, key=lambda d: abs(ai_core.B_BY_DIFFICULTY[d] - ai_core.B_BY_DIFFICULTY[difficulty]))
        for d in near:
            pool = pool_for(d)
            if pool:
                break
    db_card = _row_to_card(random.choice(pool)) if pool else None

    if groq_client is not None and (rephrase or db_card is None or exact_missing):
        gen = content.generate_question(subject, topic, difficulty, groq_client,
                                        recent_questions=recent_questions)
        if gen is not None:
            db.upsert_question(conn, gen)
            return gen

    if db_card is not None:
        return db_card

    for d in allowed:
        ap_unseen = db.fetch_questions(conn, subject, topic, d, exclude_card_ids=used_ids)
        if ap_unseen:
            return _row_to_card(random.choice(ap_unseen))
        ap_all = db.fetch_questions(conn, subject, topic, d, exclude_card_ids=None)
        if ap_all:
            return _row_to_card(random.choice(ap_all))
    any_pool = db.fetch_questions(conn, subject, topic, None, exclude_card_ids=None)
    return _row_to_card(random.choice(any_pool)) if any_pool else None


@app.get("/onboarding")
def onboarding():
    model_card = None
    if LPN is not None:
        model_card = {"arch": LPN.get("arch"), "epochs": LPN.get("epochs"),
                      "val_acc": LPN.get("val_acc"), "val_auc": LPN.get("val_auc"),
                      "threshold": LPN.get("threshold"), "positive_rate": LPN.get("positive_rate"),
                      "labels_ru": LPN.get("labels_ru", {}), "ranges": LPN.get("ranges", {})}
    rec_card = None
    if RECOMMENDER is not None:
        info = RECOMMENDER.info()
        rec_card = {"model_name": info["model_name"], "auc": info["auc"],
                    "labels_ru": info["labels_ru"], "ranges": info["ranges"]}
    return {"features": ai_core.LPN_FEATURES, "presets": ai_core.LPN_PRESETS,
            "model_loaded": LPN is not None, "model": model_card,
            "recommender": rec_card, "groq": groq_client is not None,
            "subjects": list(content.SUBJECTS.keys()),
            "stages": [{"id": k, "label": v["label"]} for k, v in ai_core.STAGES.items()],
            "grade_bands": {k: v["short"] for k, v in ai_core.GRADE_BANDS.items()}}


def _assess_and_save(uid, features, behavior):
    p_mastery = None
    start_theta = 0.0
    assessment = None
    if features and LPN is not None:
        p_mastery, start_theta = ai_core.lpn_start_theta(LPN, features)
        assessment = {"source": "LearnerProfileNet", "p_mastery": round(p_mastery, 3),
                      "start_theta": start_theta,
                      "level": ai_core.IRTSkillTracker(("", ""), start_theta).level_label()}
    db.save_profile(conn, uid, features=features, behavior=behavior, p_mastery=p_mastery)
    return assessment, start_theta


@app.post("/auth/register")
def auth_register(req: RegisterReq):
    try:
        acc = db.create_account(conn, req.username, req.password, req.name)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"user_id": acc["user_id"], "name": acc["name"], "username": acc["username"],
            "role": acc["role"], "token": acc["token"],
            "has_profile": db.has_profile(conn, acc["user_id"])}


@app.post("/auth/login")
def auth_login(req: LoginReq):
    res = db.verify_credentials(conn, req.username, req.password)
    if not res:
        raise HTTPException(401, "Неверный логин или пароль.")
    return {"user_id": res["user_id"], "name": res["name"], "username": res["username"],
            "role": res["role"], "token": res["token"],
            "has_profile": db.has_profile(conn, res["user_id"])}


@app.get("/auth/me")
def auth_me(token: str = ""):
    acc = db.get_account_by_token(conn, token)
    if not acc:
        raise HTTPException(401, "Сессия недействительна.")
    return {"user_id": acc["user_id"], "name": acc["name"], "username": acc["username"],
            "role": acc["role"], "has_profile": db.has_profile(conn, acc["user_id"])}


def _require_admin(token: str):
    acc = db.get_account_by_token(conn, token)
    if not acc or acc.get("role") != "admin":
        raise HTTPException(403, "Доступ только для администратора.")
    return acc


def _check_session_access(session_id, token, sess=None):
    if not token:
        return
    acc = db.get_account_by_token(conn, token)
    if not acc:
        return
    if acc.get("role") == "admin":
        return
    owner = sess["user_id"] if sess else db.session_owner(conn, session_id)
    if owner != acc["user_id"]:
        raise HTTPException(403, "Это не ваша сессия.")


@app.get("/admin/overview")
def admin_overview(token: str = ""):
    _require_admin(token)
    return db.admin_overview(conn)


@app.get("/admin/users")
def admin_users(token: str = ""):
    _require_admin(token)
    return {"users": db.admin_list_users(conn)}


@app.get("/admin/users/{user_id}/sessions")
def admin_user_sessions(user_id: int, token: str = ""):
    _require_admin(token)
    sessions = db.user_sessions(conn, user_id, limit=100)
    for s in sessions:
        st = db.session_answer_stats(conn, s["id"])
        s["answered"] = st["answered"]
        s["accuracy"] = round(100.0 * st["correct"] / st["answered"], 1) if st["answered"] else 0.0
    return {"user_id": user_id, "sessions": sessions}


@app.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: int, token: str = ""):
    _require_admin(token)
    ok = db.delete_user(conn, user_id)
    if not ok:
        raise HTTPException(400, "Нельзя удалить этого пользователя.")
    return {"deleted": user_id}


@app.get("/admin/catalog")
def admin_catalog(token: str = ""):
    _require_admin(token)
    cat = []
    for s in db.list_subjects(conn):
        topics = [t["name"] for t in db.list_topics(conn, s["name"])]
        cat.append({"subject": s["name"], "icon": s["icon"], "topics": topics})
    return {"catalog": cat, "difficulties": [
        {"id": d, "label": ai_core.GRADE_BANDS[d]["short"]} for d in ai_core.DIFFICULTIES]}


@app.post("/admin/subjects")
def admin_add_subject(req: SubjectReq, token: str = ""):
    _require_admin(token)
    try:
        name = db.add_subject(conn, req.name, req.icon)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "subject": name}


@app.post("/admin/topics")
def admin_add_topic(req: TopicReq, token: str = ""):
    _require_admin(token)
    try:
        topic = db.add_topic(conn, req.subject, req.topic, req.concept)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "subject": req.subject, "topic": topic}


@app.post("/admin/questions")
def admin_add_question(req: QuestionReq, token: str = ""):
    _require_admin(token)
    if len(req.options) < 2:
        raise HTTPException(400, "Нужно минимум 2 варианта ответа.")
    try:
        qid = db.add_question(conn, req.subject, req.topic, req.difficulty, req.question,
                              req.options, req.correct, req.explanation, req.common_mistake,
                              source="admin", status="approved")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "id": qid,
            "approved_in_topic": db.count_topic_questions(conn, req.subject, req.topic)}


@app.get("/admin/questions")
def admin_list_questions(token: str = "", subject: str = "", topic: str = "", status: str = ""):
    _require_admin(token)
    rows = db.list_admin_questions(conn, subject or None, topic or None, status or None)
    return {"questions": rows}


@app.post("/admin/questions/generate")
def admin_generate_questions(req: GenReq, token: str = ""):
    _require_admin(token)
    have = db.count_topic_questions(conn, req.subject, req.topic, status="approved")
    if have < MIN_QUESTIONS_BEFORE_GEN:
        raise HTTPException(400, f"Сначала добавьте минимум {MIN_QUESTIONS_BEFORE_GEN} "
                                 f"вопроса вручную (сейчас {have}). Тогда Groq продолжит сам.")
    if groq_client is None:
        raise HTTPException(503, "Groq не подключён (нет GROQ_API_KEY). Генерация недоступна.")
    n = max(1, min(10, req.n))
    levels = ai_core.DIFFICULTIES
    created = []
    for i in range(n):
        diff = req.difficulty if req.difficulty in ai_core.B_BY_DIFFICULTY else levels[i % len(levels)]
        gen = content.generate_question(req.subject, req.topic, diff, groq_client)
        if gen is None:
            continue
        qid = db.add_question(conn, req.subject, req.topic, diff, gen.question,
                              gen.options, gen.correct_answer, gen.explanation,
                              gen.common_mistake, source="llm", status="pending")
        created.append(qid)
    return {"ok": True, "generated": len(created),
            "pending": db.list_admin_questions(conn, req.subject, req.topic, status="pending")}


@app.post("/admin/questions/{qid}/approve")
def admin_approve_question(qid: int, token: str = ""):
    _require_admin(token)
    if not db.set_question_status(conn, qid, "approved"):
        raise HTTPException(404, "Вопрос не найден.")
    return {"ok": True, "id": qid}


@app.delete("/admin/questions/{qid}")
def admin_delete_question(qid: int, token: str = ""):
    _require_admin(token)
    if not db.delete_admin_question(conn, qid):
        raise HTTPException(404, "Вопрос не найден.")
    return {"ok": True, "deleted": qid}


@app.post("/users/{user_id}/profile")
def set_profile(user_id: int, req: ProfileReq):
    if db.get_user(conn, user_id) is None:
        raise HTTPException(404, "user not found")
    assessment, start_theta = _assess_and_save(user_id, req.features, req.behavior)
    return {"user_id": user_id, "assessment": assessment, "start_theta": start_theta}


@app.post("/users")
def create_user(req: CreateUserReq):
    uid = db.create_user(conn, req.name)
    assessment, start_theta = _assess_and_save(uid, req.features, req.behavior)
    return {"user_id": uid, "name": req.name, "assessment": assessment,
            "start_theta": start_theta}


@app.get("/users/{user_id}/dashboard")
def dashboard(user_id: int):
    if not db.get_user(conn, user_id):
        raise HTTPException(404, "user not found")
    return analytics.progress_dashboard(conn, user_id)


@app.get("/subjects")
def subjects(user_id: int | None = None, stage: str | None = None):
    out = []
    sm = {s["subject"]: s for s in analytics.subject_mastery(conn, user_id)} if user_id else {}
    allowed = set(content.subjects_for_stage(stage)) if stage else None
    for srow in db.list_subjects(conn):
        name = srow["name"]
        if allowed is not None and name not in allowed:
            continue
        topics = content.SUBJECTS.get(name, [])
        info = sm.get(name)
        out.append({"name": name, "icon": srow["icon"], "topics_total": len(topics),
                    "mastery_pct": info["mastery_pct"] if info else None,
                    "level": info["level"] if info else None,
                    "theta": info["theta"] if info else None})
    return {"subjects": out}


@app.get("/subjects/{subject}/topics")
def topics(subject: str, user_id: int | None = None):
    if subject not in content.SUBJECTS:
        raise HTTPException(404, "subject not found")
    tm = {t["topic"]: t for t in analytics.topic_mastery(conn, user_id, subject)} if user_id else {}
    weakest = None
    if user_id:
        ws = analytics.weak_and_strong(conn, user_id, subject)
        weakest = ws["weakest"][0]["topic"] if ws["weakest"] else None
    out = []
    for tp in content.SUBJECTS[subject]:
        info = tm.get(tp)
        status = "not_started"
        if info:
            status = "gap" if info["theta"] < analytics.WEAK_THETA else (
                     "strong" if info["theta"] >= analytics.STRONG_THETA else "in_progress")
        out.append({"topic": tp, "concept": content.CONCEPTS.get((subject, tp), ""),
                    "mastery_pct": info["mastery_pct"] if info else None,
                    "level": info["level"] if info else None,
                    "attempts": info["attempts"] if info else 0,
                    "status": status, "recommended": (tp == weakest)})
    return {"subject": subject, "topics": out}


@app.post("/sessions")
def start_session(req: StartSessionReq):
    if not db.get_user(conn, req.user_id):
        raise HTTPException(404, "user not found")
    if req.scope == "topic" and (not req.subject or not req.topic):
        raise HTTPException(400, "subject and topic required for topic scope")
    if req.scope == "subject" and not req.subject:
        raise HTTPException(400, "subject required for subject scope")

    q_limit = max(5, min(30, req.q_limit))
    sid = db.create_session(conn, req.user_id, req.scope, req.subject, req.topic, q_limit)

    mgr = ai_core.IRTSkillManager()
    prof = db.get_profile(conn, req.user_id)
    start_theta = 0.0
    if prof and prof.get("p_mastery") is not None:
        start_theta = ai_core.p_mastery_to_theta(prof["p_mastery"])
    stage_theta = ai_core.STAGES.get(req.stage or "auto", {}).get("start_theta")
    if stage_theta is not None:
        start_theta = stage_theta

    def init_topic(subject, topic):
        ss = db.get_skill_state(conn, req.user_id, subject, topic)
        if ss:
            tr = mgr.tracker(subject, topic, ss["theta"])
            tr.theta = ss["theta"]; tr.attempts = ss["attempts"]; tr.correct = ss["correct"]
        else:
            mgr.init_theta(subject, topic, start_theta)

    if req.scope == "topic":
        init_topic(req.subject, req.topic)
    elif req.scope == "subject":
        for t in content.SUBJECTS.get(req.subject, []):
            init_topic(req.subject, t)
    else:
        for s, ts in content.SUBJECTS.items():
            for t in ts:
                init_topic(s, t)

    ACTIVE[sid] = {"mgr": mgr, "current": None, "last_correct": None, "last_misc": None,
                   "stage": req.stage or "auto"}
    return {"session_id": sid, "scope": req.scope, "subject": req.subject,
            "topic": req.topic, "q_limit": q_limit, "start_theta": start_theta}


@app.get("/sessions/{session_id}/question")
def next_question(session_id: int):
    sess = db.get_session(conn, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    st = _ensure_active(session_id)

    answered = db.session_response_count(conn, session_id)
    if answered >= sess["q_limit"]:
        return {"done": True, "reason": "limit", "answered": answered}
    if sess["scope"] == "topic":
        tr = st["mgr"].tracker(sess["subject"], sess["topic"])
        if tr.attempts >= 8 and tr.standard_error() < 0.35:
            return {"done": True, "reason": "confident", "answered": answered,
                    "theta": round(tr.theta, 3), "se": round(tr.standard_error(), 3)}

    subject, topic = _next_topic(sess, st)
    tr = st["mgr"].tracker(subject, topic)
    policy = ai_core.AdaptivePolicyEngine(tr)
    stage = st.get("stage", "auto")
    allowed = ai_core.difficulties_for_stage(stage)
    decision = policy.decide(st["last_correct"], st["last_misc"] is not None, allowed=allowed)

    used = db.session_used_card_ids(conn, session_id)
    recent_q = db.session_topic_question_texts(conn, session_id, subject, topic)
    card = _pick_question(subject, topic, decision["difficulty"], used, decision["rephrase"],
                          allowed=allowed, recent_questions=recent_q)
    if card is None:
        raise HTTPException(500, f"no question available for {subject}/{topic}")
    _shuffle_options(card)
    st["current"] = card

    return {
        "done": False,
        "index": answered + 1, "total": sess["q_limit"],
        "subject": card.subject, "topic": card.topic,
        "difficulty": card.difficulty, "difficulty_stars": DIFFICULTY_STARS.get(card.difficulty, ""),
        "action": decision["action"], "action_label": ACTION_LABEL.get(decision["action"], ""),
        "question": card.question, "options": card.options,
        "theta": round(tr.theta, 3), "level": tr.level_label(),
    }


@app.post("/sessions/{session_id}/answer")
def answer(session_id: int, req: AnswerReq):
    import re as _re
    sess = db.get_session(conn, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    st = _ensure_active(session_id)
    card = st["current"]
    if not card:
        raise HTTPException(400, "no active question")

    user_ans = _re.sub(r"^[a-d][).]\s*", "", req.answer.strip().lower()).strip() or req.answer.strip().lower()
    correct = (card.correct_answer or "").strip().lower()
    is_correct = (user_ans == correct)

    tr = st["mgr"].tracker(card.subject, card.topic)
    theta_before = tr.theta
    st["mgr"].update(card.subject, card.topic, is_correct, card.difficulty)
    theta_after = tr.theta

    misc = None
    if not is_correct:
        misc = DETECTOR.detect(card.subject, card.topic, card.question, req.answer, card.correct_answer)
    st["last_correct"] = is_correct
    st["last_misc"] = misc

    db.record_response(conn, session_id, sess["user_id"], card,
                       req.answer, is_correct, theta_before, theta_after,
                       st_action(st), misc)
    db.save_skill_state(conn, sess["user_id"], card.subject, card.topic,
                        tr.theta, tr.standard_error(), tr.attempts, tr.correct, tr.theta_history)

    return {
        "is_correct": is_correct,
        "correct_answer": card.correct_answer,
        "correct_option": _option_text(card, card.correct_answer),
        "explanation": card.explanation or "",
        "common_mistake": (card.common_mistake or "") if not is_correct else "",
        "misconception": misc,
        "theta": round(tr.theta, 3), "level": tr.level_label(),
        "delta_theta": round(theta_after - theta_before, 3),
    }


@app.post("/sessions/{session_id}/finish")
def finish(session_id: int):
    sess = db.get_session(conn, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    db.finish_session(conn, session_id)
    ACTIVE.pop(session_id, None)
    return analytics.session_summary(conn, session_id)


@app.get("/users/{user_id}/analytics")
def user_analytics(user_id: int):
    if not db.get_user(conn, user_id):
        raise HTTPException(404, "user not found")
    return analytics.progress_dashboard(conn, user_id)


@app.get("/users/{user_id}/trend")
def user_trend(user_id: int, subject: str, topic: str | None = None):
    if topic:
        return {"subject": subject, "topic": topic,
                "series": analytics.theta_trend(conn, user_id, subject, topic)}
    return {"subject": subject, "series": analytics.subject_trend(conn, user_id, subject)}


@app.post("/users/{user_id}/plan")
def make_plan(user_id: int, session_id: int | None = None):
    if not db.get_user(conn, user_id):
        raise HTTPException(404, "user not found")
    eng = recommend.RecommendationEngine(conn, user_id, groq_client=groq_client, rec_model=RECOMMENDER)
    result = eng.generate(session_id=session_id)
    if not result["ok"]:
        return result
    snapshot = {
        "intro": result.get("intro"),
        "blocks": result["blocks"],
        "model_used": bool(result.get("model_used")),
        "mistake_categories": result.get("mistake_categories", []),
        "strong": result.get("strong", []),
    }
    plan_id = db.create_plan(conn, user_id, session_id, snapshot, result["items"])
    saved = db.get_plan(conn, plan_id)
    result["plan_id"] = plan_id
    result["items"] = saved["items"]
    return result


def _plan_response(p):
    if not p:
        return {"plan": None}
    body = p.get("body") or {}
    if "blocks" not in body:
        body = {"blocks": body, "intro": None, "model_used": False,
                "mistake_categories": [], "strong": []}
    return {
        "ok": True,
        "plan_id": p["id"],
        "session_id": p.get("session_id"),
        "items": p["items"],
        "intro": body.get("intro") or "План построен из ваших результатов.",
        "blocks": body.get("blocks", {}),
        "model_used": bool(body.get("model_used")),
        "mistake_categories": body.get("mistake_categories", []),
        "strong": body.get("strong", []),
    }


@app.get("/users/{user_id}/plan")
def get_latest_plan(user_id: int):
    return _plan_response(db.latest_plan(conn, user_id))


@app.get("/sessions/{session_id}/summary")
def session_summary(session_id: int, token: str = ""):
    sess = db.get_session(conn, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    _check_session_access(session_id, token, sess)
    return analytics.session_summary(conn, session_id)


@app.get("/sessions/{session_id}/plan")
def get_session_plan(session_id: int, token: str = ""):
    sess = db.get_session(conn, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    _check_session_access(session_id, token, sess)
    return _plan_response(db.plan_for_session(conn, session_id))


@app.patch("/plan_items/{item_id}")
def patch_plan_item(item_id: int, req: PlanItemReq):
    db.set_plan_item_done(conn, item_id, req.done)
    return {"item_id": item_id, "done": req.done}


def st_action(st):
    if st["last_misc"] is not None and st["last_correct"] is False:
        return "REINFORCE"
    return "MAINTAIN"


def _option_text(card, letter):
    if not letter:
        return ""
    idx = ord(letter.lower()) - ord("a")
    return card.options[idx] if 0 <= idx < len(card.options) else ""


@app.get("/")
def index():
    p = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(p):
        return FileResponse(p)
    raise HTTPException(404, "index.html не найден — положите его в static/")


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
