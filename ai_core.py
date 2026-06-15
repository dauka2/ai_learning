import math
import os
import pickle
import logging

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("ai_core")

B_BY_DIFFICULTY = {"primary": -2.0, "easy": -1.0, "medium": 0.0, "hard": +1.0, "expert": +2.0}
DIFFICULTIES = ["primary", "easy", "medium", "hard", "expert"]

GRADE_BANDS = {
    "primary": {"label": "Начальная школа (1–4 класс)", "short": "1–4 кл.", "b": -2.0},
    "easy":    {"label": "5–6 класс",                    "short": "5–6 кл.", "b": -1.0},
    "medium":  {"label": "7–8 класс",                    "short": "7–8 кл.", "b":  0.0},
    "hard":    {"label": "9–10 класс",                   "short": "9–10 кл.", "b": +1.0},
    "expert":  {"label": "Старшая школа, выпускной (11 класс)", "short": "11 кл.", "b": +2.0},
}

STAGES = {
    "grade_1":  {"label": "1 класс",  "difficulties": ["primary"],           "start_theta": -2.8, "fixed": False},
    "grade_2":  {"label": "2 класс",  "difficulties": ["primary"],           "start_theta": -2.5, "fixed": False},
    "grade_3":  {"label": "3 класс",  "difficulties": ["primary", "easy"],   "start_theta": -2.1, "fixed": False},
    "grade_4":  {"label": "4 класс",  "difficulties": ["primary", "easy"],   "start_theta": -1.7, "fixed": False},
    "grade_5":  {"label": "5 класс",  "difficulties": ["primary", "easy"],   "start_theta": -1.3, "fixed": False},
    "grade_6":  {"label": "6 класс",  "difficulties": ["easy", "medium"],    "start_theta": -1.0, "fixed": False},
    "grade_7":  {"label": "7 класс",  "difficulties": ["easy", "medium"],    "start_theta": -0.5, "fixed": False},
    "grade_8":  {"label": "8 класс",  "difficulties": ["medium", "hard"],    "start_theta":  0.0, "fixed": False},
    "grade_9":  {"label": "9 класс",  "difficulties": ["medium", "hard"],    "start_theta":  0.5, "fixed": False},
    "grade_10": {"label": "10 класс", "difficulties": ["hard", "expert"],    "start_theta":  1.0, "fixed": False},
    "grade_11": {"label": "11 класс", "difficulties": ["hard", "expert"],    "start_theta":  1.5, "fixed": False},
    "primary": {"label": "1–4 класс (диапазон)",   "difficulties": ["primary", "easy"],  "start_theta": -2.0, "fixed": False},
    "easy":    {"label": "5–6 класс (диапазон)",   "difficulties": ["easy", "medium"],   "start_theta": -1.0, "fixed": False},
    "medium":  {"label": "7–8 класс (диапазон)",   "difficulties": ["medium", "hard"],   "start_theta":  0.0, "fixed": False},
    "hard":    {"label": "9–10 класс (диапазон)",  "difficulties": ["hard", "expert"],   "start_theta":  1.0, "fixed": False},
    "expert":  {"label": "11 класс (выпускной)",   "difficulties": ["hard", "expert"],   "start_theta":  2.0, "fixed": False},
    "auto":    {"label": "Автоматически (адаптивно)", "difficulties": DIFFICULTIES, "start_theta": None, "fixed": False},
}


def difficulties_for_stage(stage):
    return STAGES.get(stage or "auto", STAGES["auto"])["difficulties"]


def is_fixed_stage(stage):
    return bool(STAGES.get(stage or "auto", STAGES["auto"]).get("fixed"))


def step_difficulty(difficulty, delta, allowed=None):
    pool = [d for d in DIFFICULTIES if (allowed is None or d in allowed)] or DIFFICULTIES
    if difficulty not in pool:
        difficulty = min(pool, key=lambda d: abs(B_BY_DIFFICULTY[d] - B_BY_DIFFICULTY.get(difficulty, 0.0)))
    i = pool.index(difficulty)
    return pool[max(0, min(len(pool) - 1, i + delta))]


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


class IRTSkillTracker:
    INIT_LR, MIN_LR, LR_DECAY, STREAK_BONUS = 0.60, 0.08, 0.15, 1.3
    THETA_MIN, THETA_MAX = -3.0, 3.0

    def __init__(self, key, theta=0.0):
        self.key = key
        self.theta = theta
        self.attempts = 0
        self.correct = 0
        self.streak = 0
        self.wrong_streak = 0
        self.theta_history = [theta]
        self.fisher_total = 0.0

    def prob_correct(self, difficulty):
        return sigmoid(self.theta - B_BY_DIFFICULTY[difficulty])

    def update(self, is_correct, difficulty):
        b = B_BY_DIFFICULTY[difficulty]
        p_prior = sigmoid(self.theta - b)
        lr = max(self.MIN_LR, self.INIT_LR / (1 + self.LR_DECAY * self.attempts))
        if self.streak >= 3:
            lr *= self.STREAK_BONUS
        outcome = 1.0 if is_correct else 0.0
        self.theta = max(self.THETA_MIN, min(self.THETA_MAX,
                         self.theta + lr * (outcome - p_prior)))
        self.attempts += 1
        self.correct += 1 if is_correct else 0
        if is_correct:
            self.streak += 1
            self.wrong_streak = 0
        else:
            self.streak = 0
            self.wrong_streak += 1
        self.theta_history.append(self.theta)
        p = self.prob_correct(difficulty)
        self.fisher_total += p * (1 - p)
        return self.theta

    def fisher_information(self, difficulty):
        p = self.prob_correct(difficulty)
        return p * (1 - p)

    def standard_error(self):
        return 1.0 / math.sqrt(self.fisher_total) if self.fisher_total > 1e-9 else 99.0

    def optimal_difficulty(self, allowed=None):
        target = self.theta - 0.3
        pool = [d for d in DIFFICULTIES if (allowed is None or d in allowed)] or DIFFICULTIES
        return min(pool, key=lambda d: abs(B_BY_DIFFICULTY[d] - target))

    def level_label(self):
        t = self.theta
        if t < -1.0:
            return "Начинающий"
        if t < -0.2:
            return "Базовый"
        if t < 0.6:
            return "Средний"
        if t < 1.5:
            return "Продвинутый"
        return "Мастер"

    def normalized_level(self):
        return (self.theta + 3.0) / 6.0


class IRTSkillManager:

    def __init__(self):
        self.trackers = {}

    def tracker(self, subject, topic, theta0=0.0):
        key = (subject, topic)
        if key not in self.trackers:
            self.trackers[key] = IRTSkillTracker(key, theta0)
        return self.trackers[key]

    def update(self, subject, topic, is_correct, difficulty):
        return self.tracker(subject, topic).update(is_correct, difficulty)

    def init_theta(self, subject, topic, theta0):
        tr = self.tracker(subject, topic, theta0)
        tr.theta = theta0
        tr.theta_history = [theta0]

    def weakest_topic_in_subject(self, subject):
        cand = {k: t for k, t in self.trackers.items()
                if k[0] == subject and t.attempts > 0}
        return min(cand, key=lambda k: cand[k].theta) if cand else None

    def subject_theta(self, subject):
        ts = [t for k, t in self.trackers.items() if k[0] == subject and t.attempts > 0]
        if not ts:
            return None
        wsum = sum(t.attempts for t in ts)
        return sum(t.theta * t.attempts for t in ts) / wsum if wsum else None


class AdaptivePolicyEngine:
    def __init__(self, tracker: IRTSkillTracker):
        self.tr = tracker
        self.question_count = 0

    def decide(self, last_correct, has_misconception, allowed=None):
        self.question_count += 1
        tr = self.tr
        base = tr.optimal_difficulty(allowed)
        if last_correct is False and has_misconception:
            return {"difficulty": step_difficulty(base, -1, allowed),
                    "action": "REINFORCE", "rephrase": True}
        if tr.wrong_streak >= 2:
            return {"difficulty": step_difficulty(base, -1, allowed),
                    "action": "REINFORCE", "rephrase": False}
        if tr.streak >= 3:
            action = "CHALLENGE" if tr.theta > 1.0 else "PROGRESS"
            return {"difficulty": step_difficulty(base, +1, allowed),
                    "action": action, "rephrase": False}
        return {"difficulty": base, "action": "MAINTAIN", "rephrase": False}


LPN_FEATURES = ["digital_literacy_score", "skill_pre_score", "video_completion_pct",
                "assignment_submission_rate", "content_difficulty_avg",
                "engagement_consistency", "total_learning_hours",
                "in_app_quiz_score", "session_count_weekly"]

LPN_PRESETS = {
    "Начинающий": {"digital_literacy_score": 3.5, "skill_pre_score": 15.0, "video_completion_pct": 12.0,
                   "assignment_submission_rate": 8.0, "content_difficulty_avg": 2.8, "engagement_consistency": 0.25,
                   "total_learning_hours": 31.8, "in_app_quiz_score": 40.0, "session_count_weekly": 2.0},
    "Средний":    {"digital_literacy_score": 6.2, "skill_pre_score": 44.9, "video_completion_pct": 41.0,
                   "assignment_submission_rate": 32.7, "content_difficulty_avg": 2.8, "engagement_consistency": 0.5,
                   "total_learning_hours": 31.8, "in_app_quiz_score": 77.5, "session_count_weekly": 5.0},
    "Сильный":    {"digital_literacy_score": 9.0, "skill_pre_score": 75.0, "video_completion_pct": 85.0,
                   "assignment_submission_rate": 80.0, "content_difficulty_avg": 2.8, "engagement_consistency": 0.85,
                   "total_learning_hours": 31.8, "in_app_quiz_score": 95.0, "session_count_weekly": 12.0},
}


def load_learner_profile_net(path="model.pkl"):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning(f"LPN load failed: {e}")
        return None


def p_mastery_to_theta(p):
    return round(max(-1.5, min(1.5, (p - 0.26) * 8.0)), 2)


def lpn_predict_p_mastery(artifact, features: dict):
    if artifact is None:
        return None
    import numpy as np
    mean, std = artifact["mean"], artifact["std"]
    x = np.array([[float(features.get(f, mean[f])) for f in artifact["features"]]], dtype=float)
    mu = np.array([[mean[f] for f in artifact["features"]]])
    sd = np.array([[std[f] if std[f] else 1.0 for f in artifact["features"]]])
    x = (x - mu) / sd
    relu = lambda z: np.maximum(0, z)
    sig = lambda z: 1 / (1 + np.exp(-np.clip(z, -30, 30)))
    a1 = relu(x @ artifact["W1"] + artifact["b1"])
    a2 = relu(a1 @ artifact["W2"] + artifact["b2"])
    p = sig(a2 @ artifact["W3"] + artifact["b3"])
    return float(p.ravel()[0])


def lpn_start_theta(artifact, features: dict):
    p = lpn_predict_p_mastery(artifact, features)
    if p is None:
        return None, 0.0
    return p, p_mastery_to_theta(p)


class RecommendationModel:
    def __init__(self, artifact):
        self.a = artifact

    @classmethod
    def load(cls, path="recommender.pkl"):
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                return cls(pickle.load(f))
        except Exception as e:
            logger.warning(f"RecommendationModel load failed: {e}")
            return None

    def predict_gaps(self, profile: dict):
        import numpy as np
        a = self.a
        x = [[float(profile.get(f, a["medians"][f])) for f in a["features"]]]
        proba = a["model"].predict_proba(np.array(x))
        return {d: float(proba[i][0][1]) for i, d in enumerate(a["domains"])}

    def domain_of(self, subject):
        return self.a["subject_to_domain"].get(subject, self.a["domains"][0])

    def info(self):
        a = self.a
        return {"model_name": a["model_name"], "auc": a["auc"], "domains": a["domains"],
                "features": a["features"], "labels_ru": a["labels_ru"], "ranges": a["ranges"]}
