"""§5: ricalibrazione dei pesi sul campione verificato (data/ground_truth.csv)."""
import pandas as pd

from .common import OUTPUT, ROOT

GT = ROOT / "data" / "ground_truth.csv"
FEATS = ["b_identikit", "b_contesto", "b_orari"]


def run():
    if not GT.exists():
        pd.DataFrame(columns=["Codice", "verificato_il", "ora_verifica", "aperto", "note"]).to_csv(GT, index=False)
    gt = pd.read_csv(GT, dtype=str)
    auto = ROOT / "data" / "ground_truth_segnalazioni.csv"  # scritto da segnalazioni.py
    if auto.exists():
        gt = pd.concat([gt, pd.read_csv(auto, dtype=str)], ignore_index=True)
    gt = gt.dropna(subset=["aperto"])
    if len(gt) < 20:
        print(f"  calibrazione: {len(gt)} negozi verificati, ne servono almeno 20 (vedi campione_verifica.csv)")
        return None
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import confusion_matrix, precision_score, recall_score

    d = pd.read_csv(OUTPUT / "minipa_milano.csv", dtype={"Codice": str}).merge(gt, on="Codice")
    y = d.aperto.str.lower().str.strip().isin(["si", "sì", "1", "true", "yes"])
    if y.nunique() < 2:
        print("  calibrazione: servono sia negozi aperti sia chiusi nel campione")
        return None
    lr = LogisticRegression().fit(d[FEATS], y)
    pos = lr.coef_[0].clip(min=0)
    w = (100 * pos / pos.sum()).round() if pos.sum() else pos
    pred = d.score >= 70
    print("  pesi suggeriti:", dict(zip(FEATS, w)))
    print(f"  precision@>=70: {precision_score(y, pred, zero_division=0):.2f}  recall: {recall_score(y, pred, zero_division=0):.2f}")
    print("  matrice di confusione [[TN FP][FN TP]]:", confusion_matrix(y, pred).tolist())
    return dict(zip(FEATS, w))


if __name__ == "__main__":
    run()
