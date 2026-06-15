import json
import logging

import analytics

logger = logging.getLogger("recommend")

GROQ_MODEL = "llama-3.3-70b-versatile"


_RESOURCES = {
    "Математика": {
        "_default": [("Khan Academy — Математика", "https://ru.khanacademy.org/math")],
        "Арифметика и проценты": [("Khan Academy — Проценты", "https://ru.khanacademy.org/math/arithmetic")],
        "Алгебра": [("Khan Academy — Алгебра", "https://ru.khanacademy.org/math/algebra")],
        "Геометрия": [("Khan Academy — Геометрия", "https://ru.khanacademy.org/math/geometry")],
        "Вероятность": [("Khan Academy — Вероятность и статистика", "https://ru.khanacademy.org/math/statistics-probability")],
    },
    "Физика": {
        "_default": [("Khan Academy — Физика", "https://www.khanacademy.org/science/physics")],
        "Механика": [("MIT 8.01 Classical Mechanics", "https://ocw.mit.edu/courses/8-01sc-classical-mechanics-fall-2016/")],
        "Кинематика": [("Khan Academy — Кинематика", "https://www.khanacademy.org/science/physics/one-dimensional-motion")],
        "Энергия": [("Khan Academy — Работа и энергия", "https://www.khanacademy.org/science/physics/work-and-energy")],
        "Электричество": [("Khan Academy — Электричество", "https://www.khanacademy.org/science/physics/circuits-topic")],
    },
    "Химия": {
        "_default": [("Khan Academy — Химия", "https://www.khanacademy.org/science/chemistry")],
        "Строение вещества": [("Khan Academy — Атомы и молекулы", "https://www.khanacademy.org/science/chemistry/atomic-structure-and-properties")],
        "Химические реакции": [("Khan Academy — Химические реакции", "https://www.khanacademy.org/science/chemistry/chemical-reactions-stoichiome")],
        "Кислоты и основания": [("Khan Academy — Кислоты и основания", "https://www.khanacademy.org/science/chemistry/acids-and-bases-topic")],
    },
    "Биология": {
        "_default": [("Khan Academy — Биология", "https://www.khanacademy.org/science/biology")],
        "Клетка": [("Khan Academy — Клетка", "https://www.khanacademy.org/science/biology/structure-of-a-cell")],
        "Генетика": [("Khan Academy — Классическая генетика", "https://www.khanacademy.org/science/biology/classical-genetics")],
        "Физиология человека": [("Khan Academy — Системы организма человека", "https://www.khanacademy.org/science/biology/human-biology")],
    },
    "Информатика": {
        "_default": [("MIT OpenCourseWare — Computer Science", "https://ocw.mit.edu/search/?d=Electrical%20Engineering%20and%20Computer%20Science")],
        "Алгоритмы": [("MIT 6.006 Introduction to Algorithms", "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/")],
        "Структуры данных": [("MIT 6.006 — Структуры данных", "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/")],
        "Сети": [("Computer Networking: a Top-Down Approach (ресурсы)", "https://gaia.cs.umass.edu/kurose_ross/index.php")],
        "Базы данных": [("CS50 SQL — Harvard", "https://cs50.harvard.edu/sql/")],
        "Операционные системы": [("OSTEP — Operating Systems: Three Easy Pieces", "https://pages.cs.wisc.edu/~remzi/OSTEP/")],
    },
    "Английский язык": {
        "_default": [("BBC Learning English", "https://www.bbc.co.uk/learningenglish")],
        "Грамматика": [("BBC — English Grammar", "https://www.bbc.co.uk/learningenglish/english/grammar")],
        "Времена глагола": [("BBC — Verb Tenses", "https://www.bbc.co.uk/learningenglish/english/grammar")],
        "Лексика": [("BBC — Vocabulary", "https://www.bbc.co.uk/learningenglish/english/features/vocabulary")],
    },
    "История": {
        "_default": [("Khan Academy — Всемирная история", "https://www.khanacademy.org/humanities/world-history")],
        "Древний мир": [("Khan Academy — Древние цивилизации", "https://www.khanacademy.org/humanities/world-history/world-history-beginnings")],
        "Новое время": [("Khan Academy — 1450–1750", "https://www.khanacademy.org/humanities/world-history/early-modern")],
        "XX век": [("Khan Academy — XX век", "https://www.khanacademy.org/humanities/world-history/euro-hist")],
    },
}


def _resources_for(subject, topic):
    subj = _RESOURCES.get(subject, {})
    return subj.get(topic) or subj.get("_default") or [("Khan Academy", "https://www.khanacademy.org/")]


def _exercises_for(topic, level):
    base = [
        f"Разобрать 8–10 базовых задач по теме «{topic}» с проверкой ответа.",
        f"Сделать письменный разбор 3 своих ошибок по теме «{topic}» и переформулировать правило.",
        f"Пройти мини-тест из 5 вопросов по теме «{topic}» и зафиксировать точность.",
    ]
    if level in ("Начинающий", "Базовый"):
        base[0] = f"Повторить теорию по теме «{topic}» и решить 6 простых задач с опорой на пример."
    elif level in ("Продвинутый", "Мастер"):
        base[0] = f"Решить 5 задач повышенной сложности по теме «{topic}» без подсказок."
        base.append(f"Объяснить тему «{topic}» своими словами (приём Фейнмана) — устно или письменно.")
    return base[:3]


class RecommendationEngine:
    def __init__(self, conn, user_id, groq_client=None, rec_model=None):
        self.conn = conn
        self.user_id = user_id
        self.groq = groq_client
        self.rec_model = rec_model

    def _gather(self, session_id=None):
        mc = analytics.mistake_categories(self.conn, self.user_id, session_id=session_id)
        subj = analytics.subject_mastery(self.conn, self.user_id)

        if session_id is not None:
            import db as _db
            sess_rows = _db.session_responses(self.conn, session_id)
            sess_topic_pairs = {(r["subject"], r["topic"]) for r in sess_rows}
            all_mastery = analytics.topic_mastery(self.conn, self.user_id)
            sess_mastery = [t for t in all_mastery if (t["subject"], t["topic"]) in sess_topic_pairs]
            sess_mastery.sort(key=lambda t: t["theta"])
            weak_sess = [t for t in sess_mastery if t["theta"] < analytics.WEAK_THETA]
            mid_sess  = [t for t in sess_mastery if analytics.WEAK_THETA <= t["theta"] < analytics.STRONG_THETA]
            strong_sess = [t for t in sess_mastery if t["theta"] >= analytics.STRONG_THETA]
            priority = weak_sess[:3] or mid_sess[:3] or sess_mastery[:3]
            ws = {"weak": weak_sess, "mid": mid_sess, "strong": strong_sess,
                  "weakest": weak_sess[:3], "strongest": list(reversed(strong_sess))[:3]}
        else:
            ws = analytics.weak_and_strong(self.conn, self.user_id)
            priority = ws["weakest"] or ws["mid"][:3] or analytics.topic_mastery(self.conn, self.user_id)[:3]

        gaps = None
        prof = None
        if self.rec_model is not None:
            from db import get_profile
            p = get_profile(self.conn, self.user_id)
            if p and p.get("behavior"):
                prof = p["behavior"]
                try:
                    gaps = self.rec_model.predict_gaps(prof)
                except Exception as e:
                    logger.warning(f"predict_gaps failed: {e}")
        return {"priority": priority, "weak": ws["weak"], "strong": ws["strong"],
                "mistakes": mc, "subjects": subj, "gaps": gaps, "has_profile": prof is not None}

    def _build_blocks(self, g):
        priority = g["priority"]
        gaps = g["gaps"]

        def gap_note(subject):
            if not gaps or self.rec_model is None:
                return None
            dom = self.rec_model.domain_of(subject)
            val = gaps.get(dom)
            return {"domain": dom, "gap_pct": round(val * 100, 1)} if val is not None else None

        block1 = []
        for t in priority:
            block1.append({
                "subject": t["subject"], "topic": t["topic"],
                "theta": t["theta"], "level": t["level"],
                "mastery_pct": t["mastery_pct"], "accuracy": t["accuracy"],
                "gap": gap_note(t["subject"]),
                "reason": f"θ={t['theta']:+.2f} ({t['level']}), точность {t['accuracy']:.0f}%",
            })

        block2 = [{"subject": t["subject"], "topic": t["topic"],
                   "exercises": _exercises_for(t["topic"], t["level"])}
                  for t in priority]

        block3 = [{"subject": t["subject"], "topic": t["topic"],
                   "resources": [{"title": ttl, "url": url}
                                 for ttl, url in _resources_for(t["subject"], t["topic"])]}
                  for t in priority]

        block4 = []
        for i, t in enumerate(priority):
            d1, d2 = i * 2 + 1, i * 2 + 2
            block4.append({"days": [d1, d2], "subject": t["subject"], "topic": t["topic"],
                           "task": f"{t['topic']} — теория, практика, мини-тест"})
        block4.append({"days": [7], "subject": None, "topic": None,
                       "task": "Повтор слабых тем (интервальное закрепление)"})
        block4.append({"days": [14], "subject": None, "topic": None,
                       "task": "Итоговый повтор и контроль всех приоритетных тем"})

        block5 = []
        for t in priority:
            target_norm = min(1.0, t["mastery"] + 0.15) if "mastery" in t else None
            crit = f"точность ≥ 75%, уровень освоения ≥ {round((target_norm or 0) * 100)}%"
            if t["theta"] is not None:
                crit += f" (θ ≥ {t['theta'] + 0.5:+.2f})"
            block5.append({"subject": t["subject"], "topic": t["topic"], "criterion": crit})

        return {"priorities": block1, "exercises": block2, "resources": block3,
                "schedule": block4, "criteria": block5}

    def _plan_items(self, blocks):
        items = []
        for s in blocks["schedule"]:
            day = s["days"][0]
            items.append({"day": day, "task": s["task"]})
        return items

    def _intro(self, g, blocks):
        mistakes = g["mistakes"]["categories"][:3]
        mistake_str = "; ".join(f"{m['type']} ({m['count']})" for m in mistakes) or "явных повторяющихся ошибок не выявлено"
        weak_str = ", ".join(f"{b['topic']}" for b in blocks["priorities"]) or "—"
        deterministic = (f"План на 2 недели построен по вашим данным: приоритетные темы — {weak_str}. "
                         f"Основные типы ошибок: {mistake_str}. "
                         f"Двигайтесь по дням, отмечайте выполненное.")
        if self.groq is None:
            return deterministic
        try:
            r = self.groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "system", "content":
                           "Ты доброжелательный учебный наставник. Перепиши вступление к плану "
                           "живо и поддерживающе, по-русски, 2–3 предложения. "
                           "НЕ добавляй новых фактов, тем и чисел — только перефразируй."},
                          {"role": "user", "content": deterministic}],
                temperature=0.6, max_tokens=300)
            txt = (r.choices[0].message.content or "").strip()
            return txt or deterministic
        except Exception as e:
            logger.warning(f"intro LLM failed: {e}")
            return deterministic

    def generate(self, session_id=None):
        g = self._gather(session_id)
        if not g["priority"]:
            return {"ok": False,
                    "message": "Недостаточно данных: пройдите хотя бы один тест по теме.",
                    "blocks": None, "items": []}
        blocks = self._build_blocks(g)
        intro = self._intro(g, blocks)
        items = self._plan_items(blocks)
        return {
            "ok": True,
            "intro": intro,
            "blocks": blocks,
            "items": items,
            "model_used": bool(g["gaps"] is not None),
            "mistake_categories": g["mistakes"]["categories"],
            "strong": g["strong"],
        }
