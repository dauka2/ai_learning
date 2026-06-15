#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_demo.py — Автономная демонстрация ИИ-моделей проекта БЕЗ веб-сайта.

Запуск:   python ai_demo.py

Скрипт загружает ОБУЧЕННЫЕ артефакты проекта (model.pkl, recommender.pkl) и
показывает работу всех компонентов ИИ вживую — удобно для защиты, если сайт
по какой-то причине недоступен. Используется тот же код моделей, что и в сайте
(модуль ai_core), поэтому это буквально та же самая нейросеть и тот же лес.
"""
import ai_core


def line(t=""):
    print(t)


def header(t):
    print("\n" + "=" * 64)
    print("  " + t)
    print("=" * 64)


def main():
    header("1. LearnerProfileNet (model.pkl)")
    lpn = ai_core.load_learner_profile_net("model.pkl")
    if lpn is None:
        line("model.pkl не найден — положите его рядом со скриптом.")
    else:
        line(f"Архитектура : {lpn.get('arch')}   |  эпох обучения: {lpn.get('epochs')}")
        line(f"Метрики     : val_acc={lpn.get('val_acc')}  val_auc={lpn.get('val_auc')}  "
             f"(baseline {1-lpn.get('positive_rate',0):.2f})")
        line(f"Признаков   : {len(lpn.get('features', []))}  → {', '.join(lpn.get('features', []))}")
        line("")
        line("Прогон трёх профилей (вход → P(освоения) → стартовый θ):")
        for name, feats in ai_core.LPN_PRESETS.items():
            p, theta = ai_core.lpn_start_theta(lpn, feats)
            lvl = ai_core.IRTSkillTracker(("", ""), theta).level_label()
            line(f"  {name:11} P(mastery)={p:.3f}  →  θ={theta:+.2f}  ({lvl})")

    # ── 2. IRTSkillTracker — адаптивная оценка θ (модель Раша) ─────────
    header("2. IRTSkillTracker — оценка уровня θ по ответам (Раш 1PL)")
    tr = ai_core.IRTSkillTracker(("Математика", "Алгебра"), theta=0.0)
    pol = ai_core.AdaptivePolicyEngine(tr)
    line("Симуляция: ученик отвечает (1=верно, 0=неверно). θ обновляется онлайн.")
    line(f"{'шаг':>3} {'ответ':>6} {'сложность':>10} {'θ':>7} {'P(верно)':>9}")
    answers = [1, 1, 1, 1, 0, 1, 1, 0, 1, 1]   # пример последовательности
    last_correct, last_misc = None, None
    for i, ok in enumerate(answers, 1):
        decision = pol.decide(last_correct, last_misc is not None, allowed=ai_core.DIFFICULTIES)
        diff = decision["difficulty"]
        p = tr.prob_correct(diff)
        tr.update(bool(ok), diff)
        last_correct = bool(ok)
        line(f"{i:>3} {('верно' if ok else 'неверно'):>6} {diff:>10} {tr.theta:>+7.2f} {p:>9.2f}")
    line(f"\nИтог: θ={tr.theta:+.2f} ({tr.level_label()}), "
         f"стандартная ошибка SE(θ)={tr.standard_error():.3f}")

    # ── 3. RecommendationModel — Random Forest, прогноз пробелов ───────
    header("3. RecommendationModel (recommender.pkl) — Multi-Output Random Forest")
    rec = ai_core.RecommendationModel.load("recommender.pkl")
    if rec is None:
        line("recommender.pkl не найден.")
    else:
        info = rec.info()
        line(f"Модель  : {info['model_name']}   |  ROC-AUC по доменам: {info['auc']}")
        line(f"Признаки: {', '.join(info['features'])}")
        line("")
        sample = {f: info["ranges"][f].get("default", 0) for f in info["features"]}
        line(f"Пример поведения студента: {sample}")
        gaps = rec.predict_gaps(sample)
        line("Прогноз вероятности пробела по доменам:")
        for domain, p in gaps.items():
            flag = "  ⚠ пробел" if p >= 0.5 else ""
            line(f"  {domain:22} P(gap)={p:.3f}{flag}")

    header("Готово. Это те же модели, что работают на сайте (модуль ai_core).")


if __name__ == "__main__":
    main()
