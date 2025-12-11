# app/scripts/chroma_load_from_csv.py

import sys
import ast
import pandas as pd

from app.services.chroma_service import chroma_service


def load_csv_to_chroma(csv_path: str) -> None:
    df = pd.read_csv(csv_path)

    news_list = []
    for _, row in df.iterrows():
        raw_emb = row.get("summary_embedding")
        if not isinstance(raw_emb, str):
            continue

        try:
            embedding = ast.literal_eval(raw_emb)
        except Exception:
            continue

        news_list.append(
            {
                "title": row.get("title", ""),
                "cluster_id": int(row.get("cluster_id", -1)),
                "summary_embedding": embedding,
            }
        )

    saved = chroma_service.add_news_embeddings(news_list)
    print(f"[INFO] 저장 개수: {saved}")


def main():
    if len(sys.argv) < 2:
        print("사용법: python -m app.scripts.chroma_load_from_csv <csv_path>")
        sys.exit(1)

    csv_path = sys.argv[1]
    load_csv_to_chroma(csv_path)


if __name__ == "__main__":
    main()
