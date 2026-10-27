"""スケジューリングエンジン。

    problem.py        純粋なデータクラス: ソルバーへの入力（DB・OR-Tools 非依存）
    snapshot.py       DB -> Problem
    model_builder.py  Problem -> CP-SAT モデル（＋ルールプラグイン）
    evaluate.py       純粋関数: スケジュールの検証、KPI と違反の算出
    solve.py          T_SolverRuns の 1 件を最後まで実行し結果を書き込む
"""
