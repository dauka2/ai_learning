import json
import ai_core
import db

WEAK_THETA = -0.2
STRONG_THETA = 0.6


def _label(theta):
    return ai_core.IRTSkillTracker(("", ""), theta).level_label()


def _norm(theta):
    return round((theta + 3.0) / 6.0, 3)


def _accuracy(correct, attempts):
    return round(100.0 * correct / attempts, 1) if attempts else 0.0


def topic_mastery(conn, user_id, subject=None):
    states = [s for s in _user_states(conn, user_id, subject) if s["attempts"] > 0]
    out = []
    for s in states:
        out.append({
            "subject": s["subject"], "topic": s["topic"],
            "theta": round(s["theta"], 3),
            "se": round(s["se"], 3) if s["se"] is not None else None,
            "mastery": _norm(s["theta"]),
            "mastery_pct": round(_norm(s["theta"]) * 100, 1),
            "level": _label(s["theta"]),
            "attempts": s["attempts"], "correct": s["correct"],
            "accuracy": _accuracy(s["correct"], s["attempts"]),
        })
    out.sort(key=lambda r: r["theta"])
    return out


def subject_mastery(conn, user_id):
    by_subj = {}
    for s in _user_states(conn, user_id):
        if s["attempts"] <= 0:
            continue
        d = by_subj.setdefault(s["subject"], {"wsum": 0.0, "tsum": 0.0,
                                              "attempts": 0, "correct": 0,
                                              "topics": 0})
        d["wsum"] += s["theta"] * s["attempts"]
        d["tsum"] += s["attempts"]
        d["attempts"] += s["attempts"]
        d["correct"] += s["correct"]
        d["topics"] += 1
    out = []
    for subj, d in by_subj.items():
        theta = d["wsum"] / d["tsum"] if d["tsum"] else 0.0
        out.append({
            "subject": subj, "theta": round(theta, 3),
            "mastery": _norm(theta), "mastery_pct": round(_norm(theta) * 100, 1),
            "level": _label(theta), "topics_practiced": d["topics"],
            "attempts": d["attempts"], "correct": d["correct"],
            "accuracy": _accuracy(d["correct"], d["attempts"]),
        })
    out.sort(key=lambda r: r["theta"])
    return out


def weak_and_strong(conn, user_id, subject=None):
    tm = topic_mastery(conn, user_id, subject)
    weak = [t for t in tm if t["theta"] < WEAK_THETA]
    strong = [t for t in tm if t["theta"] >= STRONG_THETA]
    mid = [t for t in tm if WEAK_THETA <= t["theta"] < STRONG_THETA]
    return {"weak": weak, "mid": mid, "strong": strong,
            "weakest": weak[:3], "strongest": list(reversed(strong))[:3]}


def mistake_categories(conn, user_id, session_id=None):
    if session_id is not None:
        rows = [r for r in db.session_responses(conn, session_id) if not r["is_correct"]]
    else:
        rows = [r for r in db.user_responses(conn, user_id) if not r["is_correct"]]
    cats = {}
    total = 0
    for r in rows:
        if not r["misconception"]:
            continue
        try:
            m = json.loads(r["misconception"])
        except Exception:
            continue
        mtype = m.get("type", "Прочее")
        total += 1
        c = cats.setdefault(mtype, {"type": mtype, "count": 0,
                                    "subjects": set(), "topics": set(),
                                    "hint": m.get("hint", "")})
        c["count"] += 1
        c["subjects"].add(r["subject"])
        c["topics"].add(r["topic"])
    out = []
    for c in cats.values():
        out.append({"type": c["type"], "count": c["count"],
                    "share": round(100.0 * c["count"] / total, 1) if total else 0.0,
                    "subjects": sorted(c["subjects"]),
                    "topics": sorted(c["topics"]), "hint": c["hint"]})
    out.sort(key=lambda x: -x["count"])
    return {"total_mistakes": total, "categories": out}


def theta_trend(conn, user_id, subject, topic):
    rows = db.user_responses(conn, user_id, subject, topic)
    series = [{"i": i + 1, "theta": round(r["theta_after"], 3),
               "is_correct": bool(r["is_correct"]), "difficulty": r["difficulty"],
               "at": r["answered_at"]}
              for i, r in enumerate(rows)]
    return series


def subject_trend(conn, user_id, subject):
    rows = db.user_responses(conn, user_id, subject)
    last = {}
    series = []
    for i, r in enumerate(rows):
        last[r["topic"]] = r["theta_after"]
        avg = sum(last.values()) / len(last)
        series.append({"i": i + 1, "theta": round(avg, 3), "at": r["answered_at"]})
    return series


def session_summary(conn, session_id):
    rows = db.session_responses(conn, session_id)
    sess = db.get_session(conn, session_id)
    if not rows:
        return {"session_id": session_id, "answered": 0, "overall_score": 0.0,
                "mastery_pct": None, "theta": None, "level": None, "delta_theta": 0.0,
                "theta_series": [], "correct": 0, "mistakes": [], "mistake_categories": [],
                "scope": sess["scope"] if sess else None,
                "subject": sess["subject"] if sess else None,
                "topic": sess["topic"] if sess else None}

    correct = sum(r["is_correct"] for r in rows)
    answered = len(rows)
    theta_final = rows[-1]["theta_after"]
    theta_start = rows[0]["theta_before"]

    mistakes = []
    for r in rows:
        if r["is_correct"]:
            continue
        m = json.loads(r["misconception"]) if r["misconception"] else None
        mistakes.append({"question": r["question"], "topic": r["topic"],
                         "difficulty": r["difficulty"],
                         "type": (m or {}).get("type"),
                         "hint": (m or {}).get("hint")})

    mc = mistake_categories(conn, rows[0]["user_id"], session_id=session_id)

    return {
        "session_id": session_id,
        "subject": sess["subject"] if sess else rows[0]["subject"],
        "topic": sess["topic"] if sess else rows[0]["topic"],
        "scope": sess["scope"] if sess else None,
        "answered": answered, "correct": correct,
        "overall_score": _accuracy(correct, answered),
        "theta": round(theta_final, 3),
        "level": _label(theta_final),
        "mastery_pct": round(_norm(theta_final) * 100, 1),
        "delta_theta": round(theta_final - theta_start, 3),
        "theta_series": [round(r["theta_after"], 3) for r in rows],
        "mistakes": mistakes,
        "mistake_categories": mc["categories"],
    }


def progress_dashboard(conn, user_id):
    subj = subject_mastery(conn, user_id)
    tm = topic_mastery(conn, user_id)
    ws = weak_and_strong(conn, user_id)

    coverage = {}
    for srow in db.list_subjects(conn):
        s = srow["name"]
        total = len(db.list_topics(conn, s))
        started = len({t["topic"] for t in tm if t["subject"] == s})
        coverage[s] = {"started": started, "total": total}

    sessions = db.user_sessions(conn, user_id, limit=20)
    sess_list = []
    for s in sessions:
        cnt = db.session_answer_stats(conn, s["id"])
        answered = cnt["answered"] or 0
        ok = cnt["correct"] or 0
        sess_list.append({"id": s["id"], "scope": s["scope"], "subject": s["subject"],
                          "topic": s["topic"], "started_at": s["started_at"],
                          "status": s["status"], "answered": answered,
                          "accuracy": _accuracy(ok, answered)})

    all_resp = db.user_responses(conn, user_id)
    total_answered = len(all_resp)
    total_correct = sum(r["is_correct"] for r in all_resp)

    return {
        "subject_mastery": subj,
        "topic_mastery": tm,
        "weak": ws["weak"], "strong": ws["strong"], "mid": ws["mid"],
        "coverage": coverage,
        "sessions": sess_list,
        "overall": {
            "answered": total_answered, "correct": total_correct,
            "accuracy": _accuracy(total_correct, total_answered),
            "avg_mastery_pct": round(
                sum(t["mastery_pct"] for t in tm) / len(tm), 1) if tm else None,
        },
        "mistake_categories": mistake_categories(conn, user_id)["categories"],
    }


def _user_states(conn, user_id, subject=None):
    return db.user_skill_states(conn, user_id, subject)
